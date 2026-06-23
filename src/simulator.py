"""
simulator.py — Main simulation loop.

Wires together:
  • WorkloadGenerator  → produces (pid, page, is_write) events
  • MemoryManager      → resolves accesses / faults / replacements
  • MetricsCollector   → records per-tick snapshots

Exposes
  Simulator.run()          → run a single simulation, return RunSummary
  Simulator.run_sweep()    → sweep over frame sizes, return list[RunSummary]
"""
from __future__ import annotations

import random
from typing import Dict, List, Optional

from src.config import SimConfig
from src.memory_manager import MemoryManager
from src.process import ProcessDescriptor, ProcessState
from src.workload import WorkloadGenerator
from src.lru_clock import ClockReplacer, AgingReplacer, OPTReplacer, Replacer
from analysis.metrics import MetricsCollector as AnalysisMetrics, RunSummary


def _build_replacer(policy: str, frames: int, future_schedule=None) -> Optional[Replacer]:
    if policy == "no_swap":
        return None
    if policy == "clock":
        return ClockReplacer(total_frames=frames)
    if policy == "aging":
        return AgingReplacer()
    if policy == "opt":
        if future_schedule is None:
            raise ValueError("OPT replacer requires a pre-computed future_schedule")
        r = OPTReplacer(future_schedule)
        return r
    raise ValueError(f"Unknown policy: {policy!r}")


def _build_processes(cfg: SimConfig) -> Dict[int, ProcessDescriptor]:
    processes = {}
    for i in range(cfg.num_processes):
        pid = i + 1
        proc = ProcessDescriptor(
            pid=pid,
            name=f"proc_{pid}",
            num_pages=cfg.virtual_pages_per_proc,
        )
        processes[pid] = proc
    return processes


class Simulator:
    """
    Runs one demand-paging simulation and returns performance metrics.

    Parameters
    ----------
    cfg      : SimConfig — full configuration
    policy   : override cfg.policy if provided
    frames   : override cfg.physical_frames if provided
    verbose  : print per-fault messages (for small demos)
    """

    def __init__(
        self,
        cfg: SimConfig,
        policy: Optional[str] = None,
        frames: Optional[int] = None,
        verbose: bool = False,
    ) -> None:
        self.cfg = cfg
        self.policy = policy or cfg.policy
        self.frames = frames or cfg.physical_frames
        self.verbose = verbose

    # ══════════════════════════════════════════════════════════════════════════
    # Public API
    # ══════════════════════════════════════════════════════════════════════════

    def run(self) -> RunSummary:
        """Execute a single simulation run and return a summary."""
        cfg = self.cfg
        policy = self.policy
        frames = self.frames

        # 1. Build processes
        processes = _build_processes(cfg)
        pids = list(processes.keys())

        # 2. Build workload generator
        wg = WorkloadGenerator(
            pids=pids,
            virtual_pages=cfg.virtual_pages_per_proc,
            working_set_size=cfg.working_set_size,
            locality_ratio=cfg.locality_ratio,
            phase_interval=cfg.phase_shift_interval,
            seed=cfg.random_seed,
        )

        # 3. Pre-compute OPT schedule if needed
        future_schedule = None
        if policy == "opt":
            future_schedule = wg.precompute_schedule(cfg.simulation_ticks)

        # 4. Build replacer & memory manager
        replacer = _build_replacer(policy, frames, future_schedule)
        mm = MemoryManager(
            physical_frames=frames,
            policy=policy,
            replacer=replacer,
            aging_interval=5,
        )

        # 5. Metrics collector
        collector = AnalysisMetrics()

        # 6. Main simulation loop
        for tick, (pid, page, is_write) in enumerate(
            wg.generate_stream(cfg.simulation_ticks)
        ):
            # Notify OPT replacer of current tick
            if policy == "opt" and replacer:
                replacer.set_tick(tick)          # type: ignore[attr-defined]

            proc = processes[pid]
            if not proc.is_alive:
                continue

            is_fault = mm.access(proc, page, is_write, tick, processes)

            if self.verbose and is_fault:
                fd = mm.frame_manager.get_frame(proc.page_table[page].frame_number) if proc.is_alive and proc.page_table[page].valid else None
                print(f"  [t={tick:4d}] FAULT pid={pid} page={page} → frame={fd.frame_id if fd else '?'}")

            # Periodic aging
            if (tick + 1) % mm.aging_interval == 0:
                mm.do_aging(processes)

            # Snapshot every 10 ticks
            if tick % 10 == 0:
                collector.record(tick, mm, processes)

            # In no_swap mode, clean up terminated processes' frames
            if policy == "no_swap" and not proc.is_alive:
                mm.release_process_frames(proc)

        # Final snapshot
        collector.record(cfg.simulation_ticks - 1, mm, processes)

        return collector.summarise(
            policy=policy,
            physical_frames=frames,
            num_processes=cfg.num_processes,
            total_ticks=cfg.simulation_ticks,
            mm=mm,
            processes=processes,
        ), collector

    # ══════════════════════════════════════════════════════════════════════════
    # Sweep mode
    # ══════════════════════════════════════════════════════════════════════════

    def run_sweep(
        self,
        policies: Optional[List[str]] = None,
        frame_sizes: Optional[List[int]] = None,
    ) -> Dict[str, List[RunSummary]]:
        """
        Sweep over (policy × frame_size) combinations.

        Returns a dict: policy_name → [RunSummary per frame size].
        """
        if policies is None:
            policies = ["no_swap", "clock", "aging", "opt"]
        if frame_sizes is None:
            frame_sizes = self.cfg.sweep_frame_sizes

        results: Dict[str, List[RunSummary]] = {p: [] for p in policies}

        total = len(policies) * len(frame_sizes)
        done = 0

        for policy in policies:
            for frames in frame_sizes:
                done += 1
                print(
                    f"  [{done:2d}/{total}] policy={policy:<8s} frames={frames:4d} ...",
                    end="",
                    flush=True,
                )
                sim = Simulator(self.cfg, policy=policy, frames=frames)
                summary, _ = sim.run()
                results[policy].append(summary)
                print(
                    f" fault={summary.avg_fault_rate:.3f}  "
                    f"repl={summary.avg_replacement_rate:.3f}  "
                    f"mp={summary.avg_multiprogramming:.1f}"
                )

        return results
