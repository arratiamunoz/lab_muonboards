"""Run 16 Landau-Gaussian pulse-height fit and fit-quality checks."""
import math

import numpy as np
from iminuit import Minuit
from scipy.signal import fftconvolve
from scipy.special import xlogy
from scipy.stats import chi2, landau


STEP=8.; GRID_START=-8192.; GRID= np.arange(GRID_START+STEP/2,24576.,STEP)
KERNEL_GRID=np.arange(-8192,8192+STEP*.1,STEP); EDGES=np.arange(129)*64; CENTERS=(EDGES[1:]+EDGES[:-1])/2
def dist(mu,w,s):
    d=landau.pdf(GRID,loc=mu,scale=w)
    if s>0:
        ker=np.exp(-.5*(KERNEL_GRID/s)**2); ker/=ker.sum(); d=fftconvolve(d,ker,mode='same')
    return np.maximum(d,0.)
def mode(mu,w,s):
    # Translation invariance is exact; interpolate the mode relative to zero location.
    d=dist(0.,w,s); k=int(np.argmax(d)); den=d[k-1]-2*d[k]+d[k+1]
    return mu+float(GRID[k]+STEP*.5*(d[k-1]-d[k+1])/den)
def bounds(gc,p,variant):
    if gc==1:
        ls=[(.45,640),(.57,768),(.36,544)]; us=[(2.18,6720),(1.91,6720),(2.40,7040)]
    else:
        ls=[(.49,1344),(.60,1536),(.40,1152)]; us=[(1.65,7424),(1.47,7296),(1.80,7552)]
    a0,amin=ls[variant]; b0,bmax=us[variant]
    return int(math.ceil(max(a0*p,amin)/64)), int(math.floor(min(b0*p,bmax)/64))
def fit_one(gc,y,p,variant,check_mu=None):
    i,j=bounds(gc,p,variant)
    yy=y[i:j].astype(float); nt=yy.sum(); wbins=j-i
    if nt<20 or wbins<=5:
        return None
    ix=((EDGES[i:j+1]-GRID_START)/STEP).astype(int)
    def expectation(mu,w,s,f):
        d=dist(mu,w,s); cg=np.concatenate(([0.],np.cumsum(d)*STEP))
        probs=np.maximum(np.diff(cg[ix]),1e-15); probs/=probs.sum()
        return nt*((1-f)*probs+f/wbins)
    def cost(mu,w,s,f):
        expected=expectation(mu,w,s,f)
        return float(2*np.sum(expected-yy+xlogy(yy,yy/expected)))
    results=[]
    for w0,s0,f0 in [(p*.095,p*.15,.09),(p*.19,p*.045,.16),(p*.045,p*.23,.03)]:
        m=Minuit(cost,mu=(check_mu if check_mu is not None else p-.45*w0),w=w0,s=s0,f=f0)
        m.errordef=1.; m.strategy=1; m.tol=.10
        m.limits=[(max(128.,EDGES[i]-p*.40),min(EDGES[j],p*1.32)),(35.,min(p*.57,1750.)),(12.,min(p*.60,2180.)),(0.,.55)]
        m.errors=(30.,20.,20.,.015)
        m.migrad(ncall=900)
        results.append(m)
    m=min(results,key=lambda q:(not q.valid,q.fval))
    m.hesse(ncall=1200)
    pars=np.array(tuple(m.values)); mp=mode(*pars[:3]); e=[]
    for k in range(4):
        delta=2. if k<3 else .001
        q=pars.copy(); r=pars.copy(); q[k]+=delta; r[k]-=delta
        e.append((mode(*q[:3])-mode(*r[:3]))/(2*delta))
    cov=np.array(m.covariance) if m.covariance is not None else None
    var=float(np.array(e)@cov@np.array(e)) if cov is not None else float('nan')
    err=math.sqrt(var) if var>0 else float('nan')
    yyhat=expectation(*pars); dof=wbins-5; go=float(chi2.sf(m.fval,dof))
    tail=np.linspace(EDGES[i],EDGES[j],400)
    dd=dist(*pars[:3]); cg=np.concatenate(([0.],np.cumsum(dd)*STEP)); den=cg[ix[-1]]-cg[ix[0]]
    curve=(np.interp(tail,GRID,dd)*nt*(1-pars[3])/den+(nt*pars[3]/(EDGES[j]-EDGES[i])))*64
    mu,w,s,f=pars
    fitflags=[]
    if not (m.valid and np.isfinite(err) and err>0 and m.fmin.has_posdef_covar): fitflags.append('invalid')
    if go<.01: fitflags.append('shape')
    if not EDGES[i]+128<mp<EDGES[j]-128: fitflags.append('edge')
    close=[]
    for z,(lv,hv),name in zip(pars,m.limits,('mu','w','s','f')):
        margin=(hv-lv)*.008
        if min(abs(z-lv),abs(z-hv))<margin: close.append(name)
    if 'mu' in close: fitflags.append('loc_bound')
    if 'w' in close: fitflags.append('width_bound')
    if pars[3]>.54: fitflags.append('bg_bound')
    return {'mpv':float(mp),'err':float(err),'mu':float(mu),'w':float(w),'s':float(s),'f':float(f),'dof':dof,'dev':float(m.fval),'pval':go,
        'lo':int(EDGES[i]),'hi':int(EDGES[j]),'nfit':int(nt),'flags':fitflags,'bounds':close,'curve_x':tail.tolist(),'curve_y':curve.tolist(),
        'expected':yyhat.tolist(),'valid':bool(m.valid),'accurate':bool(m.fmin.has_accurate_covar),'few':int(np.sum(yyhat<5.)),'starts':[float(z.fval) for z in results]}


def fit_spectrum(gain, counts):
    """Fit one gain/channel spectrum, retaining zero bins in all fit windows."""
    gain_index = {"HG": 0, "LG": 1}[gain]
    counts = np.asarray(counts)
    if counts.shape != CENTERS.shape:
        raise ValueError("Expected 128 bins of 64 ADC codes each")
    smoothed = np.convolve(counts, np.ones(5) / 5, mode="same")
    lo, hi = (864, 3500) if gain == "LG" else (2080, 6500)
    candidates = np.flatnonzero((CENTERS >= lo) & (CENTERS <= hi))
    peak = CENTERS[candidates[np.argmax(smoothed[candidates])]]
    if not smoothed[candidates].max():
        return None
    nominal = fit_one(gain_index, counts, peak, 0)
    if nominal is None:
        return None
    alternatives = [fit_one(gain_index, counts, peak, variant, nominal["mu"])
                    for variant in (1, 2)]
    measured = [item for item in alternatives if item is not None]
    drift = max((abs(item["mpv"] - nominal["mpv"]) for item in measured), default=0.0)
    if len(measured) != 2 or any(not item["valid"] or not np.isfinite(item["err"])
                                 for item in measured):
        nominal["flags"].append("alternate_fit")
    if drift > max(0.07 * nominal["mpv"], 2.0 * nominal["err"]):
        nominal["flags"].append("window")
    nominal["drift"] = float(drift)
    nominal["alts"] = [{key: item[key] for key in
                        ("lo", "hi", "mpv", "err", "pval", "bounds", "flags")}
                       for item in measured]
    nominal["seed"] = float(peak)
    return nominal


def fit_accepted(fit):
    return fit is not None and not fit["flags"] and fit["accurate"]
