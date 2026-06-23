"""
process.py — ProcessDescriptor data structure.

Tracks the full state of a simulated process:
  • identity (pid, name)
  • lifecycle state machine: RUNNING → BLOCKED → TERMINATED
  • owned PageTable
  • working-set metadata
  • per-process performance counters
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Set

from src.page_table import PageTable


class ProcessState(Enum):
    RUNNING    = auto()
    BLOCKED    = auto()   # waiting for a page to be loaded (page fault in progress)
    TERMINATED = auto()   # killed due to OOM in no_swap mode or end of workload


@dataclass
class ProcessDescriptor:
    """Full descriptor for a simulated process."""

    pid: int
    name: str
    num_pages: int          # virtual address space size (pages)

    # lifecycle
    state: ProcessState = ProcessState.RUNNING
    birth_tick: int = 0
    death_tick: int = -1

    # working-set tracking (updated by WorkloadGenerator on phase shifts)
    working_set: Set[int] = field(default_factory=set)

    # ── performance counters ───────────────────────────────────────────────────
    total_accesses: int = 0
    page_faults: int = 0
    page_replacements: int = 0   # replacements caused BY this process
    pages_written_back: int = 0  # dirty pages evicted

    # ── page table ─────────────────────────────────────────────────────────────
    page_table: PageTable = field(init=False)

    def __post_init__(self) -> None:
        self.page_table = PageTable(pid=self.pid, num_pages=self.num_pages)

    # ── computed properties ────────────────────────────────────────────────────

    @property
    def is_alive(self) -> bool:
        return self.state != ProcessState.TERMINATED

    @property
    def fault_rate(self) -> float:
        if self.total_accesses == 0:
            return 0.0
        return self.page_faults / self.total_accesses

    @property
    def replacement_rate(self) -> float:
        if self.total_accesses == 0:
            return 0.0
        return self.page_replacements / self.total_accesses

    @property
    def resident_set_size(self) -> int:
        return self.page_table.resident_count()

    def terminate(self, tick: int) -> None:
        self.state = ProcessState.TERMINATED
        self.death_tick = tick

    def __repr__(self) -> str:
        return (
            f"Proc(pid={self.pid} name={self.name!r} "
            f"state={self.state.name} "
            f"faults={self.page_faults}/{self.total_accesses} "
            f"rss={self.resident_set_size})"
        )
