"""
Shared concentration-time graph rendering helpers.
"""

import math

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection

from core.calculations import canonical_drug_name


def concentration_unit(drug: str = "MPA") -> str:
    return "\u03bcg/mL" if canonical_drug_name(drug) == "MPA" else "ng/mL"


def concentration_y_axis(concs) -> tuple[float, np.ndarray]:
    values = np.array(concs, dtype=float)
    max_conc = float(np.nanmax(values)) if values.size else 0.0
    step = 5.0 if max_conc <= 50 else 10.0
    y_top = max(step, math.ceil(max_conc / step) * step)
    ticks = np.arange(0, y_top + step * 0.5, step)
    return y_top, ticks


def draw_concentration_time_graph(ax, times, concs, drug: str = "MPA", *,
                                  title_size=12, label_size=10,
                                  tick_size=9, line_width=2.6,
                                  point_size=42, point_edge_width=1.4,
                                  axis_color="#000000",
                                  tick_color="#000000",
                                  title_color="#1A1A2E",
                                  red="#E53935"):
    plot_times = np.array(times, dtype=float)
    plot_concs = np.array(concs, dtype=float)
    order = np.argsort(plot_times)
    plot_times = plot_times[order]
    plot_concs = plot_concs[order]

    ax.clear()
    ax.set_facecolor("white")
    ax.grid(True, linestyle="--", color="#EEEEEE", alpha=0.9, zorder=0)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(axis_color)
    ax.spines["bottom"].set_color(axis_color)
    ax.spines["left"].set_linewidth(2.0)
    ax.spines["bottom"].set_linewidth(2.0)
    ax.tick_params(colors=tick_color, labelsize=tick_size)

    if plot_times.size < 1:
        return

    t_fine = plot_times
    c_fine = plot_concs
    norm = plt.Normalize(
        t_fine[0],
        t_fine[-1] if t_fine[-1] != t_fine[0] else t_fine[0] + 1,
    )

    if plot_times.size > 1:
        points = np.array([t_fine, c_fine]).T.reshape(-1, 1, 2)
        segs = np.concatenate([points[:-1], points[1:]], axis=1)
        lc = LineCollection(segs, cmap="rainbow", norm=norm, linewidth=line_width, zorder=3)
        lc.set_array(t_fine[:-1])
        ax.add_collection(lc)

        n_fill = 100
        t_segs = np.linspace(t_fine[0], t_fine[-1], n_fill + 1)
        for i in range(n_fill):
            ts = t_segs[i:i + 2]
            cs_seg = np.interp(ts, plot_times, plot_concs)
            ax.fill_between(
                ts, 0, cs_seg,
                color=plt.cm.rainbow(norm(t_segs[i])),
                alpha=1.0,
                zorder=1,
            )

    dot_colors = plt.cm.rainbow(np.linspace(0, 1, len(plot_times)))
    ax.scatter(
        plot_times, plot_concs,
        color=dot_colors,
        s=point_size,
        zorder=5,
        edgecolors="white",
        linewidth=point_edge_width,
    )

    ax.annotate(
        "Trough", (plot_times[0], plot_concs[0]),
        xytext=(8, 12), textcoords="offset points",
        color=red, fontsize=tick_size, fontweight="bold",
        arrowprops=dict(arrowstyle="-", color=red, lw=1),
    )

    y_top, y_ticks = concentration_y_axis(plot_concs)
    ax.set_xlim(left=0, right=plot_times[-1])
    ax.set_xticks(plot_times)
    ax.set_xticklabels([f"{t:g}" for t in plot_times])
    ax.set_ylim(bottom=0, top=y_top)
    ax.set_yticks(y_ticks)
    for tick_label in ax.get_xticklabels() + ax.get_yticklabels():
        tick_label.set_fontweight("bold")
    ax.set_xlabel("Time (hours)", fontsize=label_size, fontweight="bold")
    ax.set_ylabel(f"Conc. ({concentration_unit(drug)})", fontsize=label_size, fontweight="bold")
    ax.set_title(
        "Concentration-Time Graph",
        fontsize=title_size,
        fontweight="bold",
        color=title_color,
        pad=12,
    )
