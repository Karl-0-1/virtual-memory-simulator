"""
memory_manager.py — Core virtual memory manager.

Handles:
  • Page table walks (hit / fault detection)
  • Frame allocation on fault
  • Page replacement (via injected Replacer strategy)
  • Dirty-page writeback accounting
  • Aging interval management
  • OOM handling (no_swap mode)

The MemoryManager does NOT own the Replacer or WorkloadGenerator; they are
injected at construction time (strategy / dependency-injection pattern).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Optional

from src.frame_manager import FrameManager
from src.process import ProcessDescriptor, ProcessState

if TYPE_CHECKING:
    from src.lru_clock import Replacer


class MemoryManager:
    """
    Demand-paged virtual memory manager.

    Parameters
    ----------
    physical_frames  : total number of physical page frames
    policy           : "no_swap" | "clock" | "aging" | "opt"
    replacer         : Replacer instance (None for no_swap mode)
    aging_interval   : how many ticks between aging register shifts
    """

    def __init__(
        self,
        physical_frames: int,
        policy: str,
        replacer: Optional["Replacer"],
        aging_interval: int = 5,
    ) -> None:
        self.policy = policy
        self.replacer = replacer
        self.aging_interval = aging_interval

        self.frame_manager = FrameManager(physical_frames)

        # global counters
        self.total_accesses: int = 0
        self.total_faults: int = 0
        self.total_replacements: int = 0
        self.total_writebacks: int = 0

    # ══════════════════════════════════════════════════════════════════════════
    # Main entry point: handle one memory access
    # ══════════════════════════════════════════════════════════════════════════

    def access(
        self,
        process: ProcessDescriptor,
        page: int,
        is_write: bool,
        tick: int,
        processes: Dict[int, ProcessDescriptor],
    ) -> bool:
        """
        Simulate a memory access for `process` to virtual page `page`.

        Returns True on a page fault, False on a hit.
        Updates all relevant counters on the process and globally.
        """
        self.total_accesses += 1
        process.total_accesses += 1

        pte = process.page_table[page]
        pte.access_count += 1

        # ── Page HIT ──────────────────────────────────────────────────────────
        if pte.valid:
            pte.referenced = True
            if is_write:
                pte.dirty = True
            pte.last_access_tick = tick
            if self.replacer:
                self.replacer.on_access(process.pid, page, pte.frame_number, tick)
            return False   # hit

        # ── Page FAULT ────────────────────────────────────────────────────────
        self.total_faults += 1
        process.page_faults += 1
        pte.fault_count += 1

        frame_id = self._allocate_or_replace(process, page, tick, processes)

        if frame_id is None:
            # OOM in no_swap mode → terminate process
            process.terminate(tick)
            return True

        # Map the page into the allocated frame
        pte.frame_number = frame_id
        pte.valid = True
        pte.referenced = True
        pte.dirty = is_write
        pte.last_access_tick = tick

        fd = self.frame_manager.get_frame(frame_id)
        fd.owner_pid = process.pid
        fd.owner_page = page

        if self.replacer:
            self.replacer.on_access(process.pid, page, frame_id, tick)

        return True   # fault

    # ══════════════════════════════════════════════════════════════════════════
    # Frame allocation — free or via replacement
    # ══════════════════════════════════════════════════════════════════════════

    def _allocate_or_replace(
        self,
        process: ProcessDescriptor,
        page: int,
        tick: int,
        processes: Dict[int, ProcessDescriptor],
    ) -> Optional[int]:
        """
        Try to get a free frame.  If full and swapping is enabled, evict a
        victim page first.  Returns a frame_id or None (no_swap + full).
        """
        frame_id = self.frame_manager.allocate_frame(process.pid, page)
        if frame_id is not None:
            return frame_id

        # No free frames
        if self.policy == "no_swap" or self.replacer is None:
            return None   # signal OOM

        # ── Select and evict a victim ─────────────────────────────────────────
        victim = self.replacer.select_victim(self.frame_manager, processes)
        if victim is None:
            return None

        victim_fid, victim_pid, victim_page = victim
        victim_proc = processes.get(victim_pid)

        if victim_proc and victim_proc.is_alive:
            victim_pte = victim_proc.page_table[victim_page]

            # Dirty writeback
            if victim_pte.dirty:
                self.total_writebacks += 1
                victim_proc.pages_written_back += 1
                victim_pte.dirty = False

            victim_pte.invalidate()
            self.replacer.on_evict(victim_fid)

        # Re-use the evicted frame
        self.total_replacements += 1
        process.page_replacements += 1

        fd = self.frame_manager.get_frame(victim_fid)
        fd.owner_pid = process.pid
        fd.owner_page = page
        fd.in_use = True

        return victim_fid

    # ══════════════════════════════════════════════════════════════════════════
    # Aging tick (call every `aging_interval` simulation ticks)
    # ══════════════════════════════════════════════════════════════════════════

    def do_aging(self, processes: Dict[int, ProcessDescriptor]) -> None:
        """Shift all resident pages' aging counters. Called periodically."""
        if self.policy != "aging":
            return
        for proc in processes.values():
            if proc.is_alive:
                proc.page_table.age_all()

    # ══════════════════════════════════════════════════════════════════════════
    # Process termination cleanup
    # ══════════════════════════════════════════════════════════════════════════

    def release_process_frames(self, process: ProcessDescriptor) -> int:
        """
        Free all frames owned by a terminated process.
        Returns the number of frames released.
        """
        released = 0
        for pte in process.page_table.resident_pages():
            self.frame_manager.free_frame(pte.frame_number)
            pte.invalidate()
            released += 1
        return released

    # ── stats ──────────────────────────────────────────────────────────────────

    @property
    def global_fault_rate(self) -> float:
        if self.total_accesses == 0:
            return 0.0
        return self.total_faults / self.total_accesses

    @property
    def global_replacement_rate(self) -> float:
        if self.total_accesses == 0:
            return 0.0
        return self.total_replacements / self.total_accesses
