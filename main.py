"""
main.py — CLI entry point for the Virtual Memory Simulator.

Usage examples
──────────────
  # Quick single-run demo (aging, default 64 frames)
  python main.py

  # Single run with a specific policy and frame count
  python main.py --policy clock --frames 32 --ticks 3000

  # Full sweep across all policies and frame sizes → saves charts to results/
  python main.py --sweep

  # Sweep with custom frame sizes
  python main.py --sweep --frames 16,32,64,128,256

  # Live verbose output (shows every page fault)
  python main.py --policy aging --frames 32 --verbose --ticks 200
"""
from __future__ import annotations

import argparse
import os
import sys
import time

from src.config import SimConfig
from src.simulator import Simulator
from analysis.plot import (
    generate_all_sweep_charts,
    plot_time_series_dashboard,
    plot_per_process_faults,
)

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich import box
    RICH = True
except ImportError:
    RICH = False


# ── CLI ────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    # Pull defaults from SimConfig — single source of truth
    _d = SimConfig()
    p = argparse.ArgumentParser(
        description="Virtual Memory Simulator — OS Project",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--policy", default=_d.policy,
                   choices=["no_swap", "clock", "aging", "opt"],
                   help=f"Replacement policy (default: {_d.policy})")
    p.add_argument("--frames", default=str(_d.physical_frames),
                   help=f"Physical frames — single value or comma-separated for sweep (default: {_d.physical_frames})")
    p.add_argument("--processes", type=int, default=_d.num_processes,
                   help=f"Number of concurrent processes (default: {_d.num_processes})")
    p.add_argument("--vp", type=int, default=_d.virtual_pages_per_proc,
                   help=f"Virtual pages per process (default: {_d.virtual_pages_per_proc})")
    p.add_argument("--ws", type=int, default=_d.working_set_size,
                   help=f"Working-set size per process (default: {_d.working_set_size})")
    p.add_argument("--ticks", type=int, default=_d.simulation_ticks,
                   help=f"Total simulation ticks (default: {_d.simulation_ticks})")
    p.add_argument("--seed", type=int, default=_d.random_seed,
                   help=f"Random seed (default: {_d.random_seed})")
    p.add_argument("--sweep", action="store_true",
                   help="Run full multi-policy × multi-frame sweep and generate charts")
    p.add_argument("--policies", default="no_swap,clock,aging,opt",
                   help="Comma-separated policies to include in sweep (default: all)")
    p.add_argument("--out", default=_d.results_dir,
                   help=f"Output directory for charts (default: {_d.results_dir}/)")
    p.add_argument("--verbose", action="store_true",
                   help="Print every page fault event")
    p.add_argument("--no-charts", action="store_true",
                   help="Skip chart generation")
    return p.parse_args()


# ── pretty output helpers ──────────────────────────────────────────────────────

def _banner():
    if RICH:
        c = Console()
        c.print(Panel.fit(
            "[bold cyan]Virtual Memory Simulator[/bold cyan]\n"
            "[dim]Demand-Paged VM · Clock · Aging · OPT · Performance Analysis[/dim]",
            border_style="cyan",
        ))
    else:
        print("=" * 60)
        print("  Virtual Memory Simulator")
        print("=" * 60)


def _print_summary(summary, collector=None):
    if RICH:
        c = Console()
        t = Table(title=f"Run Summary — {summary.policy.upper()} | {summary.physical_frames} frames",
                  box=box.ROUNDED, border_style="cyan")
        t.add_column("Metric", style="bold white")
        t.add_column("Value", style="cyan")
        t.add_row("Total Accesses",         f"{summary.total_accesses:,}")
        t.add_row("Total Page Faults",      f"{summary.total_faults:,}")
        t.add_row("Total Replacements",     f"{summary.total_replacements:,}")
        t.add_row("Total Write-Backs",      f"{summary.total_writebacks:,}")
        t.add_row("Avg Fault Rate",         f"{summary.avg_fault_rate:.2%}")
        t.add_row("Avg Replacement Rate",   f"{summary.avg_replacement_rate:.2%}")
        t.add_row("Avg Multiprogramming",   f"{summary.avg_multiprogramming:.2f}")
        t.add_row("Avg RSS (all procs)",    f"{summary.avg_rss:.1f} pages")
        t.add_row("Peak RSS",               f"{summary.peak_rss} pages")
        t.add_row("Thrashing (% ticks)",    f"{summary.thrash_fraction:.1%}")
        c.print(t)
    else:
        print(f"\n{'='*55}")
        print(f"  Policy: {summary.policy}  |  Frames: {summary.physical_frames}")
        print(f"{'='*55}")
        print(f"  Total Accesses    : {summary.total_accesses:,}")
        print(f"  Page Faults       : {summary.total_faults:,}")
        print(f"  Replacements      : {summary.total_replacements:,}")
        print(f"  Write-Backs       : {summary.total_writebacks:,}")
        print(f"  Avg Fault Rate    : {summary.avg_fault_rate:.2%}")
        print(f"  Avg Replace Rate  : {summary.avg_replacement_rate:.2%}")
        print(f"  Avg Multiprog.    : {summary.avg_multiprogramming:.2f}")
        print(f"  Peak RSS          : {summary.peak_rss} pages")
        print(f"  Thrashing         : {summary.thrash_fraction:.1%} of ticks")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()
    _banner()

    # parse frame sizes
    frame_vals = [int(x.strip()) for x in args.frames.split(",")]
    sweep_policies = [p.strip() for p in args.policies.split(",")]

    cfg = SimConfig(
        physical_frames=frame_vals[0],
        num_processes=args.processes,
        virtual_pages_per_proc=args.vp,
        working_set_size=args.ws,
        simulation_ticks=args.ticks,
        policy=args.policy,
        sweep_frame_sizes=frame_vals if len(frame_vals) > 1 else SimConfig().sweep_frame_sizes,
        results_dir=args.out,
        random_seed=args.seed,
    )

    os.makedirs(args.out, exist_ok=True)

    # ── SWEEP MODE ─────────────────────────────────────────────────────────────
    if args.sweep:
        print(f"\n[Sweep Mode] policies={sweep_policies}  frames={cfg.sweep_frame_sizes}\n")
        t0 = time.perf_counter()
        sim = Simulator(cfg, verbose=False)
        sweep_results = sim.run_sweep(policies=sweep_policies)
        elapsed = time.perf_counter() - t0
        print(f"\n  Sweep completed in {elapsed:.1f}s")

        if not args.no_charts:
            print("\n[Generating Charts]")
            paths = generate_all_sweep_charts(sweep_results, args.out)
            print(f"\n  {len(paths)} charts saved to '{args.out}/'")

        # Print summary table for each policy at median frame size
        mid_idx = len(cfg.sweep_frame_sizes) // 2
        for policy in sweep_policies:
            s = sweep_results[policy][mid_idx]
            _print_summary(s)

    # ── SINGLE RUN MODE ────────────────────────────────────────────────────────
    else:
        frames = frame_vals[0]
        print(f"\n[Single Run] policy={args.policy}  frames={frames}  ticks={args.ticks}\n")
        t0 = time.perf_counter()
        sim = Simulator(cfg, policy=args.policy, frames=frames, verbose=args.verbose)
        summary, collector = sim.run()
        elapsed = time.perf_counter() - t0
        print(f"  Completed in {elapsed:.2f}s")

        _print_summary(summary, collector)

        if not args.no_charts:
            print("\n[Generating Charts]")
            p1 = plot_time_series_dashboard(collector, args.policy, frames, args.out)
            p2 = plot_per_process_faults(summary, args.out)
            print(f"  Charts saved to '{args.out}/'")


if __name__ == "__main__":
    main()
