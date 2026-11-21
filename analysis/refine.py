"""Refine flagged spectra and report modes without discarding finite estimates."""
import numpy as np
from iminuit import Minuit
from scipy.special import ndtr, xlogy
from scipy.stats import chi2

from fit import EDGES, GRID_START, dist, fit_spectrum, mode

FINE_STEP = 4.0
LANDAU_GAUSSIAN = "Landau-Gaussian + flat background"
GAUSSIAN = "Gaussian + flat background"


def profile_mode(counts, initial, gaussian=False):
    """Fit with the signal mode as the free parameter; profile at Delta deviance 1."""
    z = initial.copy()
    i, j = z["lo"] // 64, z["hi"] // 64
    lo, hi = z["lo"], z["hi"]
    bins = EDGES[i:j + 1]
    indices = ((bins - GRID_START) / FINE_STEP).astype(int)
    y = counts[i:j]
    total = y.sum()

    def expected(mpv, w, s, f):
        if gaussian:
            cdf = ndtr((bins - mpv) / s)
        else:
            mu = mpv - mode(0.0, w, s, FINE_STEP)
            density = dist(mu, w, s, FINE_STEP)
            cdf = np.r_[0, np.cumsum(density) * FINE_STEP][indices]
        mass = np.maximum(np.diff(cdf), 1e-15)
        return total * ((1 - f) * mass / mass.sum() + f / (j - i))

    def deviance(mpv, w, s, f):
        pred = expected(mpv, w, s, f)
        return float(2 * np.sum(pred - y + xlogy(y, y / pred)))

    m = Minuit(deviance, mpv=z["mpv"], w=z["w"], s=z["s"], f=z["f"])
    m.errordef = 1
    m.tol = 0.02
    m.limits = [(lo, hi), (9, 1750), (12, 2180), (0, 0.90)]
    m.errors = (30, 20, 20, 0.015)
    if gaussian:
        m.fixed["w"] = True
    m.migrad(ncall=1200)
    if not m.valid:
        return None
    m.hesse()
    m.minos("mpv", ncall=2500)
    error = m.merrors["mpv"]
    if not error.is_valid or not error.lower < 0 < error.upper:
        return None
    mpv, w, s, f = m.values
    if gaussian:
        dof = j - i - 4
        curve_x = np.linspace(lo, hi, 400)
        norm = ndtr((hi - mpv) / s) - ndtr((lo - mpv) / s)
        density = np.exp(-0.5 * ((curve_x - mpv) / s)**2) / (s * np.sqrt(2 * np.pi))
        curve_y = 64 * total * ((1 - f) * density / norm + f / (hi - lo))
        expected_values = expected(*m.values)
        z.update(mpv=float(mpv), mu=float(mpv), s=float(s), w=0.0, f=float(f),
                 dev=float(m.fval), dof=dof, pval=float(chi2.sf(m.fval, dof)),
                 curve_x=curve_x.tolist(), curve_y=curve_y.tolist(),
                 expected=expected_values.tolist(), model=GAUSSIAN,
                 few=int(np.sum(expected_values < 5)),
                 flags=(["shape"] if chi2.sf(m.fval, dof) < 0.01 else []),
                 bounds=[], accurate=bool(m.fmin.has_accurate_covar))
    elif abs(mpv - z["mpv"]) > 3:
        return None
    z["stat_low"] = -float(error.lower)
    z["stat_high"] = float(error.upper)
    z["stat_method"] = "Minuit2 MINOS"
    return z


def estimate_peak(gain, counts):
    nominal = fit_spectrum(gain, counts)
    if nominal is None or not np.isfinite(nominal["mpv"]):
        return None
    result = nominal.copy()
    result["model"] = LANDAU_GAUSSIAN
    sensitivity = nominal
    if nominal["flags"] or not nominal["accurate"]:
        candidate = fit_spectrum(gain, counts, refined=True)
        if candidate is not None and candidate["valid"] and np.isfinite(candidate["mpv"]):
            sensitivity = candidate
            result = dict(candidate, model=LANDAU_GAUSSIAN)
            gaussian = "width_bound" in candidate["flags"]
            profiled = profile_mode(counts, result, gaussian)
            if profiled is not None:
                result = profiled
                if gaussian:
                    alternates = []
                    for a in candidate["alts"]:
                        start = dict(result, lo=a["lo"], hi=a["hi"], mpv=a["mpv"])
                        new = profile_mode(counts, start, gaussian=True)
                        if new is not None:
                            alternates.append({k: new[k] for k in ("lo", "hi", "mpv",
                                                 "stat_low", "stat_high", "pval")})
                    result["alts"] = alternates
            else:
                result["flags"] = result["flags"] + ["profile_unavailable"]
    # Publish the finite mode even when its statistical interval is unavailable.
    # For the Gaussian limit, keep the competing Landau-Gaussian fits in the sensitivity.
    centers = [result["mpv"], *(alt["mpv"] for alt in result["alts"])]
    if result["model"] == GAUSSIAN:
        centers.extend([sensitivity["mpv"], *(v["mpv"] for v in sensitivity["alts"])])
    finite = [value for value in centers if np.isfinite(value)]
    result["variation_lo"], result["variation_hi"] = min(finite), max(finite)
    result["drift"] = max(result["mpv"] - min(finite), max(finite) - result["mpv"])
    error = result["err"]
    result.setdefault("stat_low", error)
    result.setdefault("stat_high", error)
    result.setdefault("stat_method", "Hesse propagation")
    return result
