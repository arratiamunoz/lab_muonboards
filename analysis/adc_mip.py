"""Analyze archived CAEN JANUS list-mode CSVs. Does not access hardware."""
import argparse
import csv
import math
from pathlib import Path

import numpy as np

from refine import estimate_peak
from plot import plot_mpv, plot_spectra


def read_histograms(path, board=0):
    """Return HG/LG counts for channels 0-15 and saved trigger count."""
    histograms = np.zeros((2, 16, 128), dtype=np.int64)
    triggers = set()
    rejected = 0
    required = {"Trg_Id", "Board_Id", "CH_Id", "PHA_HG", "PHA_LG"}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(line for line in stream if line.strip() and
                                not line.lstrip().startswith("//"))
        if not required.issubset(reader.fieldnames or ()):
            raise ValueError(f"JANUS list CSV must have these columns: {sorted(required)}")
        for row in reader:
            if int(row["Board_Id"]) != board:
                continue
            triggers.add(int(row["Trg_Id"]))
            channel = int(row["CH_Id"])
            if not 0 <= channel < 16:
                continue
            for index, name in enumerate(("PHA_HG", "PHA_LG")):
                code = int(row[name], 10)
                if 0 <= code < 8192:
                    histograms[index, channel, code // 64] += 1
                else:
                    rejected += 1
    if not triggers:
        raise ValueError(f"No saved triggers for board {board}")
    if not histograms.any():
        raise ValueError(f"No valid pulse heights in channels 0-15 for board {board}")
    return histograms, len(triggers), rejected


def write_fit_table(path, fits):
    fields = {
        "model": "Model", "mpv": "Convolved_MPV_ADC",
        "stat_low": "Stat_minus_ADC", "stat_high": "Stat_plus_ADC",
        "stat_method": "Stat_interval_method",
        "variation_lo": "Fit_variation_min_ADC", "variation_hi": "Fit_variation_max_ADC",
        "drift": "Max_Fit_Variation_ADC", "lo": "Window_Low_ADC", "hi": "Window_High_ADC",
        "nfit": "Fit_Entries", "dev": "Poisson_Deviance", "dof": "Degrees_of_Freedom",
        "pval": "Approximate_P_Value", "mu": "Model_Location_ADC",
        "w": "Landau_Scale_ADC", "s": "Gaussian_Sigma_ADC", "f": "Background_Fraction",
        "few": "Bins_Expected_lt_5"
    }
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(["Gain", "Channel", *fields.values(), "Estimated", "Fit_Diagnostics",
                         "Near_Parameter_Limit", "Alternate_Windows_Low_High_MPV_ADC"])
        for gain in ("LG", "HG"):
            for channel in range(16):
                fit = fits[f"{gain}{channel:02d}"]
                if fit is None:
                    writer.writerow([gain, channel, *([""] * len(fields)), False,
                                     "No finite fit estimate", "", ""])
                    continue
                reasons = fit["flags"] + ([] if fit["accurate"] else ["covariance"])
                values = [format(fit[key], ".8g") if isinstance(fit[key], float)
                          and math.isfinite(fit[key]) else
                          "" if isinstance(fit[key], float) else fit[key] for key in fields]
                alternatives = "; ".join(
                    f"{item['lo']}-{item['hi']}:{item['mpv']:.1f}" for item in fit["alts"])
                writer.writerow([gain, channel, *values, True, "; ".join(reasons),
                                 "; ".join(fit["bounds"]), alternatives])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path, help="Archived JANUS list-mode CSV")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--board", type=int, default=0, help="Board_Id to analyze (default 0)")
    parser.add_argument("--label", default=None, help="Run label printed on the figures")
    parser.add_argument("--live-seconds", type=float, help="Exposure for saved trigger rate")
    parser.add_argument("--setup", default="", help="Verified run settings label")
    parser.add_argument("--spectra-ymax", type=int, default=60)
    parser.add_argument("--fits-ymax", type=int, default=65)
    parser.add_argument("--spectra-only", action="store_true", help="Skip Minuit fits")
    args = parser.parse_args(argv)
    if args.live_seconds is not None and not (math.isfinite(args.live_seconds)
                                              and args.live_seconds > 0):
        parser.error("--live-seconds must be finite and positive")
    if min(args.spectra_ymax, args.fits_ymax) <= 0:
        parser.error("Display caps must be positive")
    try:
        histograms, triggers, rejected = read_histograms(args.csv, args.board)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    label = args.label or args.csv.stem
    output = args.out_dir
    output.mkdir(parents=True, exist_ok=True)
    summary = f"{triggers:,} saved triggers"
    if args.live_seconds is not None:
        summary += f"  /  {args.live_seconds:,.2f} s  /  {triggers / args.live_seconds:.2f} Hz"
    print(f"Board {args.board}: {summary}; ignored {rejected} out-of-range ADC readings",
          flush=True)
    plot_spectra(histograms, output, label, summary + "  /  64 ADC per bin",
                 args.setup, args.spectra_ymax)
    if args.spectra_only:
        return
    fits = {f"{gain}{channel:02d}": estimate_peak(gain, histograms[index, channel])
            for index, gain in enumerate(("HG", "LG")) for channel in range(16)}
    plot_spectra(histograms, output, label, f"{triggers:,} saved triggers  /  64 ADC per bin",
                 args.setup, args.fits_ymax, fits)
    stats = plot_mpv(fits, output, label)
    write_fit_table(output / "mip_fit_results.csv", fits)
    for gain, result in stats.items():
        print(f"{gain}: {result['n']}/16 estimated; mean {result['mean']:.2f} ADC; "
              f"relative population spread {result['spread']:.2f}%")


if __name__ == "__main__":
    main()
