"""Publication-style ADC spectra and Minuit fit summary."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator, MultipleLocator
import numpy as np
from scipy.stats import chi2

from fit import CENTERS

plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10.,'axes.linewidth':.75,
 'axes.edgecolor':'#253640','xtick.direction':'in','ytick.direction':'in',
 'xtick.major.size':4.5,'ytick.major.size':4.5,'xtick.minor.size':2.2,'ytick.minor.size':2.2,
 'text.color':'#152630','axes.labelcolor':'#152630','xtick.color':'#344650','ytick.color':'#344650',
 'pdf.fonttype':42,'figure.facecolor':'white','savefig.facecolor':'white'})
cols={'HG':'#17648A','LG':'#A65020'}; marks={'HG':'o','LG':'s'}; ch=np.arange(16)

def save(fig, path):
    fig.savefig(path.with_suffix(".png"), dpi=260)
    fig.savefig(path.with_suffix(".pdf"))


def garwood(counts):
    """Central 68.27% Poisson confidence limits for unweighted counts."""
    n = np.asarray(counts, dtype=float)
    low = np.zeros_like(n)
    positive = n > 0
    low[positive] = chi2.ppf(0.15865525393145707, 2 * n[positive]) / 2
    high = chi2.ppf(0.8413447460685429, 2 * (n + 1)) / 2
    return low, high


def plot_mpv(fs, output, label):
    fig,axs=plt.subplots(1,2,figsize=(11.4,5.05),sharex=True)
    fig.subplots_adjust(left=.08,right=.973,bottom=.16,top=.778,wspace=.25)
    results = {}
    for gain,ax in zip(("LG","HG"),axs):
        good = np.array([fs.get(f"{gain}{j:02d}") is not None for j in ch])
        v = [fs[f"{gain}{j:02d}"] for j in ch[good]]
        mid = np.array([f["mpv"] for f in v])
        stat = np.array([[f[k] for f in v] for k in ("stat_low", "stat_high")])
        stat_ok = np.isfinite(stat).all(axis=0) & (stat > 0).all(axis=0)
        windows = np.array([(f["variation_lo"], f["variation_hi"]) for f in v])
        mean = float(mid.mean()) if len(mid) else float("nan")
        spread = float(100 * mid.std() / mean) if len(mid) and mean else float("nan")
        results[gain] = {"n": len(mid), "mean": mean, "spread": spread}
        color = cols[gain]
        y_upper = 350
        if len(mid):
            ax.axhline(mean, ls=(0, (4, 3)), color=color, alpha=.45, lw=1.05)
            ax.vlines(ch[good], windows[:, 0], windows[:, 1],
                      color="#84929A", lw=1.1, zorder=2)
            ax.plot(ch[good], mid, marks[gain], color=color, ms=4.7, zorder=4)
            ax.errorbar(ch[good][stat_ok], mid[stat_ok], yerr=stat[:, stat_ok],
                        fmt="none", color=color, lw=1.05, capsize=2.25, capthick=.95, zorder=3)
            y_upper = max(y_upper, (mid + np.where(stat_ok, stat[1], 0)).max(),
                          windows[:, 1].max())
        ax.set_ylim(0, 1.13 * y_upper)
        assert ax.get_ylim()[0]==0
        ax.set_xlim(-.72,15.72)
        ax.tick_params(which="both",top=True,right=True,labelsize=9.35)
        ax.xaxis.set_major_locator(MultipleLocator(1))
        ax.yaxis.set_major_locator(MaxNLocator(6))
        ax.set_xlabel("Channel",fontsize=11)
        ax.set_ylabel("MPV (ADC codes)",fontsize=11)
        ax.set_title("Low gain" if gain=="LG" else "High gain",loc="left",
                     fontweight="bold",color=color,fontsize=13,pad=9)
        summary = (f"{len(mid)} channels    Mean {mean:,.0f} ADC    Relative spread "
                   f"{spread:.1f}%" if len(mid) else "No finite MPV estimates")
        ax.text(.035, .055, summary,
                transform=ax.transAxes,fontsize=8.85,va="bottom",ha="left")
    fig.text(.08,.95,f"{label} | MIP-like peak position",fontsize=20.5,weight="bold",va="top")
    fig.text(.08,.875,"Minuit2   /   Colored bars: statistical   /   Gray lines: fit-window and shape variation",
             color="#465963",fontsize=10.2,va="top")
    save(fig, output / "mip_mpv_by_channel")
    plt.close(fig)
    return results


def plot_spectra(h, output, label, summary, metadata, ymax, fs=None):
    x = CENTERS
    gaussian_labels = [f"{key[:2]} {key[2:]}" for key, fit in (fs or {}).items()
                       if fit is not None and fit["model"].startswith("Gaussian")]
    L, U = garwood(np.arange(min(ymax, int(h.max())) + 1))
    fig,axs=plt.subplots(4,4,figsize=(13.3,9.55),sharex=True,sharey=True)
    fig.subplots_adjust(left=.092,right=.975,bottom=.103,top=.815,wspace=.155,hspace=.21)
    for j,ax in enumerate(axs.flat):
        for gain,g in [('LG',1),('HG',0)]:
            y=h[g,j]; z=fs.get(f'{gain}{j:02d}') if fs else None; color=cols[gain]; keep=(y>0)&(y<=ymax); n=y[keep]
            ax.errorbar(x[keep],n,yerr=[n-L[n],U[n]-n],fmt=marks[gain],color=color,ecolor=color,mec=color,mew=.45,mfc=(color if gain=='HG' else 'white'),ms=1.75,elinewidth=.40,capsize=0,alpha=.49,zorder=2)
            clip=np.flatnonzero(y>ymax)
            for seq in np.split(clip,np.flatnonzero(np.diff(clip)>1)+1):
                if len(seq):
                    ax.plot(x[seq].mean(),ymax*(.974 if gain=='HG' else .925),'^',color=color,mec='white',mew=.25,ms=3,zorder=8)
            if z is not None:
                line = "#606D74" if len(gaussian_labels) > 4 and z["model"].startswith("Gaussian") else color
                ax.plot(z['curve_x'], z['curve_y'], color=line, ls="-", lw=1.15, zorder=4)
        ax.set_xlim(0,8192);ax.set_ylim(0,ymax)
        ax.xaxis.set_major_locator(MultipleLocator(2048));ax.xaxis.set_minor_locator(MultipleLocator(512))
        ax.yaxis.set_major_locator(MultipleLocator(15));ax.yaxis.set_minor_locator(MultipleLocator(5))
        ax.tick_params(which='both',top=True,right=True,labelsize=9.4)
        ax.text(.93,.89,f'Ch {j:02d}',transform=ax.transAxes,fontsize=9.6,weight='bold',ha='right',zorder=12)
    fig.text(.092,.959,f'{label} | {"MIP-like pulse-height fits" if fs else "Pulse-height spectra"}',fontsize=21,weight='bold',va='top')
    fig.text(.092,.908,summary + ('  /  Minuit peak fits + flat background' if fs else ''),color='#465963',fontsize=10.25,va='top')
    more='Points: 68.27% Poisson bars   /   Curves shown over fit windows   /   Triangles: above scale'
    if gaussian_labels:
        more = ("68.27% Poisson bars   /   Gray models: Gaussian limit   /   "
                "Triangles: above scale")
        if len(gaussian_labels) <= 4:
            more = ("68.27% Poisson bars   /   Gaussian limit: "
                    + ", ".join(gaussian_labels) + "   /   Triangles: above scale")
    if not fs: more='68.27% Poisson intervals (Garwood)   /   Zero-count bins not drawn   /   Triangles: above scale'
    fig.text(.092,.871,more,color='#465963',fontsize=9.6,va='top')
    fig.text(.092,.841,metadata,color='#465963',fontsize=9.1,va='top')
    fig.legend([Line2D([0],[0],color=cols[g],marker=marks[g],lw=1.15,ms=4,
        mfc=(cols[g] if g=='HG' else 'white')) for g in ('HG','LG')],['High gain','Low gain'],frameon=False,loc='upper right',bbox_to_anchor=(.98,.93))
    fig.supxlabel('Pulse height (ADC codes)',x=.536,y=.04,fontsize=12)
    fig.supylabel('Counts per 64 ADC bin',x=.032,y=.458,fontsize=12)
    save(fig, output / ('mip_fitted_spectra' if fs else 'adc_spectra'))
    plt.close(fig)
