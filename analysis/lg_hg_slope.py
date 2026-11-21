"""Plot paired JANUS low-gain vs high-gain ADC codes and fit a slope per channel."""
import argparse
import csv
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator
from matplotlib.lines import Line2D
import numpy as np

from adc_mip import run_metadata_label


def read_pairs(path, board):
    required = {"Trg_Id", "Board_Id", "CH_Id", "PHA_HG", "PHA_LG"}
    groups = [[] for _ in range(16)]
    seen = set()
    triggers = set()
    with path.open(newline="", encoding="utf-8-sig") as stream:
        rows = csv.DictReader(line for line in stream if line.strip() and
                              not line.lstrip().startswith("//"))
        if not required.issubset(rows.fieldnames or ()):
            raise ValueError(f"JANUS list CSV must include {sorted(required)}")
        for row in rows:
            if int(row["Board_Id"]) != board:
                continue
            ch, tag = int(row["CH_Id"]), int(row["Trg_Id"])
            triggers.add(tag)
            if not 0 <= ch < 16:
                continue
            if (ch, tag) in seen:
                raise ValueError(f"Repeated event {tag} for channel {ch}")
            seen.add((ch, tag))
            x, y = int(row["PHA_HG"]), int(row["PHA_LG"])
            if 0 <= x < 8192 and 0 <= y < 8192:
                groups[ch].append((x, y))
    if not triggers or not any(groups):
        raise ValueError(f"No valid pairs for board {board}")
    return [np.asarray(v, dtype=int).reshape(-1, 2) for v in groups], len(triggers)


def fit_window(x, y, central=False):
    lo, hi = (1100, 6000) if central else (700, 6500)
    return (x >= lo) & (x <= hi) & (y < 7800)


def fit(x, y):
    """Conditional OLS of LG on HG with an intercept and HC3 statistical error."""
    if len(x) < 3 or np.ptp(x) == 0:
        return None
    z = np.column_stack((np.ones(x.size), x))
    inv = np.linalg.inv(z.T @ z)
    b = inv @ z.T @ y
    e = y - z @ b
    leverage = np.sum((z @ inv) * z, axis=1)
    if np.any(leverage >= 1.0 - 1e-12):
        return None
    h3 = (e / (1 - leverage))**2
    cov = inv @ (z.T @ (h3[:, None] * z)) @ inv
    return b[0], b[1], math.sqrt(max(0, cov[1, 1]))


def plot_gain(groups, out, label, board, summary):
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9.5,'axes.linewidth':0.8,
                         'xtick.direction':'in','ytick.direction':'in',
                         'xtick.top':True,'ytick.right':True,'mathtext.fontset':'dejavusans'})
    fig,axs=plt.subplots(4,4,figsize=(13.0,12.4),sharex=True,sharey=True)
    fig.subplots_adjust(left=.093,right=.98,bottom=.092,top=.894,wspace=.10,hspace=.11)
    fig.text(.093,.971,f'{label}  |  Low gain vs high gain',fontsize=23,fontweight='bold',color='#112738',va='top')
    fig.text(.093,.926,f'Board {board}  /  Channels 0 to 15  /  {summary}',fontsize=11,color='#41596c',va='top')
    tables=[]
    for i,(g,ax) in enumerate(zip(groups,axs.flat)):
        x, y = g.T
        m = fit_window(x, y)
        m2 = fit_window(x, y, central=True)
        estimate = fit(x[m], y[m])
        alternative = fit(x[m2], y[m2])
        r = float(np.corrcoef(x[m], y[m])[0, 1]) if estimate and np.std(y[m]) else None
        a, b, s = estimate or (None, None, None)
        tables.append([i, len(x), int(m.sum()), a, b, s, r, int(m2.sum()),
                       alternative[1] if alternative else None])
        ax.scatter(x[~m],y[~m],s=2.6,c='#7b8792',alpha=.19,linewidths=0,rasterized=True)
        ax.scatter(x[m],y[m],s=3.1,c='#14648e',alpha=.20,linewidths=0,rasterized=True)
        if estimate:
            xx=np.array([x[m].min(),x[m].max()])
            ax.plot(xx,a+b*xx,color='#bd4a18',lw=1.55,zorder=4)
        ax.text(.056,.932,f'CH {i}',transform=ax.transAxes,va='top',fontsize=11,fontweight='bold',color='#112738')
        caption = rf'Slope: ${b:.4f}\,\pm\,{s:.4f}$' if estimate else 'No finite slope'
        ax.text(.056,.804,caption,transform=ax.transAxes,va='top',fontsize=9.5,color='#a53c14',bbox={'facecolor':'white','edgecolor':'none','pad':.7,'alpha':.94})
        ax.set(xlim=(0,8400),ylim=(0,8400))
        ax.xaxis.set_major_locator(MultipleLocator(2000))
        ax.yaxis.set_major_locator(MultipleLocator(2000))
        ax.xaxis.set_minor_locator(MultipleLocator(1000))
        ax.yaxis.set_minor_locator(MultipleLocator(1000))
        ax.tick_params(which='major',length=4,pad=4)
        ax.tick_params(which='minor',length=2.1)
        ax.grid(alpha=.12,linewidth=.5)
        ax.set_axisbelow(True)

    fig.text(.535,.053,'High gain [ADC]',ha='center',fontsize=13)
    fig.text(.027,.498,'Low gain [ADC]',va='center',ha='center',rotation=90,fontsize=13)
    handles=[Line2D([],[],marker='o',ls='none',markerfacecolor='#14648e',markeredgecolor='none',markersize=5,label='Fit sample (HG 700 to 6500 ADC, LG < 7800 ADC)'),
             Line2D([],[],marker='o',ls='none',markerfacecolor='#7b8792',markeredgecolor='none',markersize=5,label='Other events'),
             Line2D([],[],color='#bd4a18',lw=1.65,label='Linear fit')]
    fig.legend(handles=handles,loc='lower center',bbox_to_anchor=(.535,.012),ncol=3,frameon=False,columnspacing=2.1,handlelength=1.6,fontsize=9.5)
    fp = out / "lg_hg_slope.png"
    fig.savefig(fp, dpi=240, facecolor="white")
    plt.close(fig)
    with (out / "lg_hg_slope_results.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["Channel", "Pairs", "Fit_Events", "Intercept_LG_ADC", "Slope_LG_per_HG",
                         "Slope_HC3_Stat_Error", "Pearson_r", "Central_Window_Events",
                         "Central_Window_Slope"])
        writer.writerows(tables)
    return tables


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("csv", type=Path, help="Archived JANUS list-mode CSV")
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--board", type=int, default=0)
    p.add_argument("--label")
    p.add_argument("--live-seconds", type=float, required=True, help="Recorded duration in seconds")
    args = p.parse_args(argv)
    if not math.isfinite(args.live_seconds) or args.live_seconds <= 0:
        p.error("--live-seconds must be finite and positive")
    try:
        groups, trigger_count = read_pairs(args.csv, args.board)
    except (OSError, ValueError) as exc:
        p.error(str(exc))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    plot_gain(groups, args.out_dir, args.label or args.csv.stem, args.board,
              run_metadata_label(args.live_seconds, trigger_count))


if __name__ == "__main__":
    main()
