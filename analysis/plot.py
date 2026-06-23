"""
plot.py — Matplotlib chart generation for simulation results.

Charts produced
───────────────
  1. Fault Rate vs Physical Frames      — policy comparison line chart
  2. Replacement Rate vs Physical Frames — policy comparison
  3. Degree of Multiprogramming vs Frames — active processes over memory
  4. Time-Series Dashboard              — fault rate + replacements + RSS + free frames
  5. Per-Process Fault Distribution     — bar chart of faults per process

All charts are saved to cfg.results_dir as PNG files.
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional, TYPE_CHECKING

import matplotlib
matplotlib.use("Agg")   # headless rendering
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

if TYPE_CHECKING:
    from analysis.metrics import RunSummary, MetricsCollector

# ── colour palette (colourblind-friendly) ─────────────────────────────────────
PALETTE = {
    "no_swap":  "#e74c3c",   # red
    "clock":    "#3498db",   # blue
    "aging":    "#2ecc71",   # green
    "opt":      "#f39c12",   # amber
}
POLICY_LABELS = {
    "no_swap": "No Swap (Baseline)",
    "clock":   "Clock (Second-Chance)",
    "aging":   "Aging / NFU",
    "opt":     "OPT (Bélády Optimal)",
}

STYLE = {
    "figure.facecolor": "#0f1117",
    "axes.facecolor":   "#1a1d27",
    "axes.edgecolor":   "#3a3f5c",
    "axes.labelcolor":  "#e0e0e0",
    "axes.titlecolor":  "#ffffff",
    "xtick.color":      "#a0a0a0",
    "ytick.color":      "#a0a0a0",
    "grid.color":       "#2a2d3e",
    "grid.linestyle":   "--",
    "grid.alpha":       0.6,
    "legend.facecolor": "#1a1d27",
    "legend.edgecolor": "#3a3f5c",
    "legend.labelcolor":"#e0e0e0",
    "text.color":       "#e0e0e0",
    "font.family":      "DejaVu Sans",
}


def _apply_style():
    plt.rcParams.update(STYLE)


def _save(fig: plt.Figure, path: str) -> None:
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"  ✓ Saved: {path}")


# ══════════════════════════════════════════════════════════════════════════════
# Chart 1 — Fault Rate vs Physical Frames
# ══════════════════════════════════════════════════════════════════════════════

def plot_fault_rate_vs_frames(
    sweep_results: Dict[str, List["RunSummary"]],
    out_dir: str,
) -> str:
    _apply_style()
    fig, ax = plt.subplots(figsize=(9, 5))

    for policy, summaries in sweep_results.items():
        frames = [s.physical_frames for s in summaries]
        rates  = [s.avg_fault_rate for s in summaries]
        ax.plot(
            frames, rates,
            marker="o", linewidth=2.5, markersize=7,
            color=PALETTE.get(policy, "#aaaaaa"),
            label=POLICY_LABELS.get(policy, policy),
        )

    ax.set_xlabel("Physical Frames (Memory Size)", fontsize=12)
    ax.set_ylabel("Average Page-Fault Rate", fontsize=12)
    ax.set_title("Page Fault Rate vs Physical Memory Size", fontsize=14, fontweight="bold")
    ax.yaxis.set_major_formatter(mticker.PercentFormatter(xmax=1.0))
    ax.legend(framealpha=0.9)
    ax.grid(True)
    fig.tight_layout()

    path = os.path.join(out_dir, "fault_rate_vs_frames.png")
    _save(fig, path)
    return path


# ══════════════════════════════════════════════════════════════════════════════
# Chart 2 — Replacement Rate vs Physical Frames
# ══════════════════════════════════════════════════════════════════════════════

def plot_replacement_rate_vs_frames(
    sweep_results: Dict[str, List["RunSummary"]],
    out_dir: str,
) -> str:
    _apply_style()
    fig, ax = plt.subplots(figsize=(9, 5))

    for policy, summaries in sweep_results.items():
        if policy == "no_swap":
            continue   # no replacements in no_swap
        frames = [s.physical_frames for s in summaries]
        rates  = [s.avg_replacement_rate for s in summaries]
        ax.plot(
            frames, rates,
            marker="s", linewidth=2.5, markersize=7,
            color=PALETTE.get(policy, "#aaaaaa"),
            label=POLICY_LABELS.get(policy, policy),
        )

    ax.set_xlabel("Physical Frames (Memory Size)", fontsize=12)
    ax.set_ylabel("Average Page-Replacement Rate", fontsize=12)
    ax.set_title("Page Replacement Rate vs Physical Memory Size", fontsize=14, fontweight="bold")
    ax.yaxis.set_major_formatter(mticker.PercentFormatter(xmax=1.0))
    ax.legend(framealpha=0.9)
    ax.grid(True)
    fig.tight_layout()

    path = os.path.join(out_dir, "replacement_rate_vs_frames.png")
    _save(fig, path)
    return path


# ══════════════════════════════════════════════════════════════════════════════
# Chart 3 — Degree of Multiprogramming vs Frames
# ══════════════════════════════════════════════════════════════════════════════

def plot_multiprogramming_vs_frames(
    sweep_results: Dict[str, List["RunSummary"]],
    out_dir: str,
) -> str:
    _apply_style()
    fig, ax = plt.subplots(figsize=(9, 5))

    for policy, summaries in sweep_results.items():
        frames = [s.physical_frames for s in summaries]
        mp     = [s.avg_multiprogramming for s in summaries]
        ax.plot(
            frames, mp,
            marker="^", linewidth=2.5, markersize=7,
            color=PALETTE.get(policy, "#aaaaaa"),
            label=POLICY_LABELS.get(policy, policy),
        )

    ax.set_xlabel("Physical Frames (Memory Size)", fontsize=12)
    ax.set_ylabel("Average Active Processes", fontsize=12)
    ax.set_title("Degree of Multiprogramming vs Physical Memory Size", fontsize=14, fontweight="bold")
    ax.legend(framealpha=0.9)
    ax.grid(True)
    fig.tight_layout()

    path = os.path.join(out_dir, "multiprogramming_vs_frames.png")
    _save(fig, path)
    return path


# ══════════════════════════════════════════════════════════════════════════════
# Chart 4 — Time-Series Dashboard (single run)
# ══════════════════════════════════════════════════════════════════════════════

def plot_time_series_dashboard(
    collector: "MetricsCollector",
    policy: str,
    frames: int,
    out_dir: str,
) -> str:
    _apply_style()
    ticks = collector.ticks()
    fig, axes = plt.subplots(2, 2, figsize=(14, 8))
    fig.suptitle(
        f"Time-Series Dashboard — {POLICY_LABELS.get(policy, policy)} | {frames} Frames",
        fontsize=14, fontweight="bold", color="#ffffff",
    )

    color = PALETTE.get(policy, "#aaaaaa")

    # (0,0) fault rate
    ax = axes[0, 0]
    ax.plot(ticks, collector.fault_rates(), color=color, linewidth=1.8)
    ax.set_ylabel("Global Fault Rate")
    ax.set_title("Page Fault Rate Over Time")
    ax.yaxis.set_major_formatter(mticker.PercentFormatter(xmax=1.0))
    ax.grid(True)

    # (0,1) replacement rate
    ax = axes[0, 1]
    ax.plot(ticks, collector.replacement_rates(), color="#f39c12", linewidth=1.8)
    ax.set_ylabel("Replacement Rate")
    ax.set_title("Page Replacement Rate Over Time")
    ax.yaxis.set_major_formatter(mticker.PercentFormatter(xmax=1.0))
    ax.grid(True)

    # (1,0) multiprogramming
    ax = axes[1, 0]
    ax.fill_between(ticks, collector.multiprogramming_degrees(), alpha=0.5, color="#9b59b6")
    ax.plot(ticks, collector.multiprogramming_degrees(), color="#9b59b6", linewidth=1.8)
    ax.set_xlabel("Simulation Tick")
    ax.set_ylabel("Active Processes")
    ax.set_title("Degree of Multiprogramming")
    ax.grid(True)

    # (1,1) free frames
    ax = axes[1, 1]
    ax.fill_between(ticks, collector.free_frame_counts(), alpha=0.4, color="#1abc9c")
    ax.plot(ticks, collector.free_frame_counts(), color="#1abc9c", linewidth=1.8)
    ax.set_xlabel("Simulation Tick")
    ax.set_ylabel("Free Frames")
    ax.set_title("Free Physical Frames Over Time")
    ax.grid(True)

    fig.tight_layout()
    fname = f"dashboard_{policy}_{frames}frames.png"
    path = os.path.join(out_dir, fname)
    _save(fig, path)
    return path


# ══════════════════════════════════════════════════════════════════════════════
# Chart 5 — Per-Process Fault Bar Chart
# ══════════════════════════════════════════════════════════════════════════════

def plot_per_process_faults(
    summary: "RunSummary",
    out_dir: str,
) -> str:
    _apply_style()
    fig, ax = plt.subplots(figsize=(10, 5))

    pids = sorted(summary.per_proc_faults.keys())
    faults = [summary.per_proc_faults[p] for p in pids]
    repls  = [summary.per_proc_replacements.get(p, 0) for p in pids]

    x = np.arange(len(pids))
    w = 0.35
    ax.bar(x - w/2, faults, width=w, label="Page Faults",
           color=PALETTE.get(summary.policy, "#3498db"), alpha=0.9)
    ax.bar(x + w/2, repls, width=w, label="Replacements Caused",
           color="#e67e22", alpha=0.9)

    ax.set_xticks(x)
    ax.set_xticklabels([f"P{p}" for p in pids])
    ax.set_xlabel("Process ID")
    ax.set_ylabel("Count")
    ax.set_title(
        f"Per-Process Faults & Replacements — "
        f"{POLICY_LABELS.get(summary.policy, summary.policy)} | {summary.physical_frames} Frames",
        fontsize=12, fontweight="bold",
    )
    ax.legend(framealpha=0.9)
    ax.grid(True, axis="y")
    fig.tight_layout()

    fname = f"per_proc_{summary.policy}_{summary.physical_frames}frames.png"
    path = os.path.join(out_dir, fname)
    _save(fig, path)
    return path


# ══════════════════════════════════════════════════════════════════════════════
# Convenience — generate all sweep charts at once
# ══════════════════════════════════════════════════════════════════════════════

def generate_all_sweep_charts(
    sweep_results: Dict[str, List["RunSummary"]],
    out_dir: str,
) -> List[str]:
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    paths.append(plot_fault_rate_vs_frames(sweep_results, out_dir))
    paths.append(plot_replacement_rate_vs_frames(sweep_results, out_dir))
    paths.append(plot_multiprogramming_vs_frames(sweep_results, out_dir))
    return paths
