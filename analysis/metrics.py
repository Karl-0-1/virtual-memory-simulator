"""
metrics.py — MetricsCollector for time-series performance data.

Collects per-tick snapshots of:
  • page fault rate (global + per-process)
  • replacement rate
  • degree of multiprogramming (active process count)
  • resident set size per process
  • free frame count
  • thrashing flag (fault rate > threshold)

Also supports per-run summary aggregation used by the sweep analysis.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class TickSnapshot:
    """One time-series snapshot captured each simulation tick."""
    tick: int
    free_frames: int
    used_frames: int
    active_processes: int
    global_fault_rate: float
    global_replacement_rate: float
    rss_per_proc: Dict[int, int]            # pid → resident pages
    fault_rate_per_proc: Dict[int, float]   # pid → fault rate so far
    is_thrashing: bool = False


@dataclass
class RunSummary:
    """Aggregate statistics for one complete simulation run."""
    policy: str
    physical_frames: int
    num_processes: int
    total_ticks: int

    total_accesses: int = 0
    total_faults: int = 0
    total_replacements: int = 0
    total_writebacks: int = 0

    avg_fault_rate: float = 0.0
    avg_replacement_rate: float = 0.0
    avg_multiprogramming: float = 0.0
    avg_rss: float = 0.0          # average resident set size across all procs
    peak_rss: int = 0
    thrash_fraction: float = 0.0  # fraction of ticks flagged as thrashing

    per_proc_faults: Dict[int, int] = field(default_factory=dict)
    per_proc_replacements: Dict[int, int] = field(default_factory=dict)


class MetricsCollector:
    """
    Collects, stores, and summarises simulation metrics.

    Usage
    -----
        collector = MetricsCollector(thrash_threshold=0.5)
        # inside simulator loop:
        collector.record(tick, mm, processes)
        # at end:
        summary = collector.summarise(policy, cfg)
    """

    THRASH_THRESHOLD = 0.50   # fault rate above this → thrashing

    def __init__(self, thrash_threshold: float = THRASH_THRESHOLD) -> None:
        self._threshold = thrash_threshold
        self.snapshots: List[TickSnapshot] = []

    # ── recording ──────────────────────────────────────────────────────────────

    def record(self, tick: int, mm: object, processes: dict) -> None:
        """Capture one tick snapshot.  mm is a MemoryManager instance."""
        active = [p for p in processes.values() if p.is_alive]

        rss = {p.pid: p.resident_set_size for p in active}
        fault_rates = {p.pid: p.fault_rate for p in active}

        snap = TickSnapshot(
            tick=tick,
            free_frames=mm.frame_manager.free_count(),       # type: ignore[attr-defined]
            used_frames=mm.frame_manager.used_count(),        # type: ignore[attr-defined]
            active_processes=len(active),
            global_fault_rate=mm.global_fault_rate,           # type: ignore[attr-defined]
            global_replacement_rate=mm.global_replacement_rate,  # type: ignore[attr-defined]
            rss_per_proc=rss,
            fault_rate_per_proc=fault_rates,
            is_thrashing=mm.global_fault_rate > self._threshold,  # type: ignore[attr-defined]
        )
        self.snapshots.append(snap)

    # ── summary ────────────────────────────────────────────────────────────────

    def summarise(
        self,
        policy: str,
        physical_frames: int,
        num_processes: int,
        total_ticks: int,
        mm: object,
        processes: dict,
    ) -> RunSummary:
        """Build a RunSummary from collected snapshots."""
        n = len(self.snapshots) or 1

        avg_fault = sum(s.global_fault_rate for s in self.snapshots) / n
        avg_repl = sum(s.global_replacement_rate for s in self.snapshots) / n
        avg_mp = sum(s.active_processes for s in self.snapshots) / n
        avg_rss = (
            sum(sum(s.rss_per_proc.values()) for s in self.snapshots) / n
        )
        peak_rss = max(
            (sum(s.rss_per_proc.values()) for s in self.snapshots), default=0
        )
        thrash = sum(1 for s in self.snapshots if s.is_thrashing) / n

        per_proc_faults = {p.pid: p.page_faults for p in processes.values()}
        per_proc_repl = {p.pid: p.page_replacements for p in processes.values()}

        return RunSummary(
            policy=policy,
            physical_frames=physical_frames,
            num_processes=num_processes,
            total_ticks=total_ticks,
            total_accesses=mm.total_accesses,          # type: ignore[attr-defined]
            total_faults=mm.total_faults,              # type: ignore[attr-defined]
            total_replacements=mm.total_replacements,  # type: ignore[attr-defined]
            total_writebacks=mm.total_writebacks,      # type: ignore[attr-defined]
            avg_fault_rate=avg_fault,
            avg_replacement_rate=avg_repl,
            avg_multiprogramming=avg_mp,
            avg_rss=avg_rss,
            peak_rss=peak_rss,
            thrash_fraction=thrash,
            per_proc_faults=per_proc_faults,
            per_proc_replacements=per_proc_repl,
        )

    # ── time-series extraction ─────────────────────────────────────────────────

    def ticks(self) -> List[int]:
        return [s.tick for s in self.snapshots]

    def fault_rates(self) -> List[float]:
        return [s.global_fault_rate for s in self.snapshots]

    def replacement_rates(self) -> List[float]:
        return [s.global_replacement_rate for s in self.snapshots]

    def multiprogramming_degrees(self) -> List[int]:
        return [s.active_processes for s in self.snapshots]

    def free_frame_counts(self) -> List[int]:
        return [s.free_frames for s in self.snapshots]
