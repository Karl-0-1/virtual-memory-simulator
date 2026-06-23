"""
lru_clock.py — Page replacement algorithm implementations.

All replacers share the Replacer abstract interface:
    select_victim(frame_manager, processes) → (frame_id, pid, page)

Implemented algorithms
──────────────────────
  ClockReplacer  — Second-Chance (Clock) algorithm.
                   Sweeps a circular hand; gives pages with referenced=1 a
                   second chance before evicting referenced=0 pages.

  AgingReplacer  — Aging / NFU (Not Frequently Used) with shift register.
                   Each aging tick, the 8-bit history counter is right-shifted
                   and the current referenced bit is ORed into the MSB.
                   The frame with the smallest counter is the victim.

  OPTReplacer    — Bélády's Optimal algorithm (oracle / offline).
                   Requires a pre-computed future-access schedule.
                   Uses the page whose next use is farthest in the future.
                   Included as a theoretical upper-bound comparison.
"""
from __future__ import annotations

import abc
import math
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from src.frame_manager import FrameManager
    from src.process import ProcessDescriptor

# ── type alias ─────────────────────────────────────────────────────────────────
VictimTuple = Tuple[int, int, int]   # (frame_id, owner_pid, owner_page)


class Replacer(abc.ABC):
    """Abstract base for all page-replacement algorithms."""

    @abc.abstractmethod
    def select_victim(
        self,
        frame_manager: "FrameManager",
        processes: Dict[int, "ProcessDescriptor"],
    ) -> Optional[VictimTuple]:
        """
        Choose a frame to evict.

        Returns (frame_id, owner_pid, owner_page) or None if no victim found
        (should not happen in normal operation when memory is full).
        """

    def on_access(self, pid: int, page: int, frame_id: int, tick: int) -> None:
        """Hook called on every memory access (hit or fault). Override if needed."""

    def on_evict(self, frame_id: int) -> None:
        """Hook called just before a frame is evicted."""

    def name(self) -> str:
        return self.__class__.__name__


# ══════════════════════════════════════════════════════════════════════════════
# Clock (Second-Chance) Replacer
# ══════════════════════════════════════════════════════════════════════════════

class ClockReplacer(Replacer):
    """
    Clock / Second-Chance page replacement.

    The "clock hand" sweeps through all physical frames in circular order.
    • If referenced == True  → clear it, advance hand (second chance).
    • If referenced == False → evict this frame.
    """

    def __init__(self, total_frames: int) -> None:
        self._hand: int = 0
        self._total: int = total_frames

    def select_victim(
        self,
        frame_manager: "FrameManager",
        processes: Dict[int, "ProcessDescriptor"],
    ) -> Optional[VictimTuple]:
        used = frame_manager.used_frame_ids()
        if not used:
            return None

        # Build a sorted circular list of in-use frame IDs
        used_set = set(used)
        sweeps = 0
        max_sweeps = self._total * 2   # worst case: two full revolutions

        while sweeps < max_sweeps:
            fid = self._hand % self._total
            self._hand = (self._hand + 1) % self._total
            sweeps += 1

            if fid not in used_set:
                continue

            fd = frame_manager.get_frame(fid)
            pid, page = fd.owner_pid, fd.owner_page
            pte = processes[pid].page_table[page]

            if pte.referenced:
                pte.referenced = False   # second chance
            else:
                return (fid, pid, page)

        # Fallback: evict first used frame (should rarely trigger)
        fid = used[0]
        fd = frame_manager.get_frame(fid)
        return (fid, fd.owner_pid, fd.owner_page)

    def name(self) -> str:
        return "Clock (Second-Chance)"


# ══════════════════════════════════════════════════════════════════════════════
# Aging (NFU with shift register) Replacer
# ══════════════════════════════════════════════════════════════════════════════

class AgingReplacer(Replacer):
    """
    Aging / NFU-with-aging page replacement.

    Each aging interval, PageTable.age_all() shifts every resident page's
    8-bit history counter right by 1 and merges the current referenced bit
    into the MSB.  The page with the smallest counter is the LRU approximation.
    """

    def select_victim(
        self,
        frame_manager: "FrameManager",
        processes: Dict[int, "ProcessDescriptor"],
    ) -> Optional[VictimTuple]:
        used = frame_manager.used_frame_ids()
        if not used:
            return None

        best_fid: int = -1
        best_hist: int = 256   # 8-bit max is 255

        for fid in used:
            fd = frame_manager.get_frame(fid)
            pte = processes[fd.owner_pid].page_table[fd.owner_page]
            if pte.history_counter < best_hist:
                best_hist = pte.history_counter
                best_fid = fid

        if best_fid == -1:
            return None
        fd = frame_manager.get_frame(best_fid)
        return (best_fid, fd.owner_pid, fd.owner_page)

    def name(self) -> str:
        return "Aging (NFU)"


# ══════════════════════════════════════════════════════════════════════════════
# OPT (Bélády's Optimal) Replacer — offline oracle
# ══════════════════════════════════════════════════════════════════════════════

class OPTReplacer(Replacer):
    """
    Optimal (Bélády's) page replacement algorithm.

    Requires the complete future access sequence up front.
    Evicts the page whose next reference is furthest in the future
    (or never referenced again → highest priority for eviction).

    future_schedule: dict mapping (pid, page) → sorted list of future tick indices.
    """

    def __init__(self, future_schedule: Dict[Tuple[int, int], List[int]]) -> None:
        # future_schedule[(pid, page)] = [tick1, tick2, ...] in ascending order
        self._schedule = future_schedule
        self._current_tick: int = 0

    def set_tick(self, tick: int) -> None:
        self._current_tick = tick

    def _next_use(self, pid: int, page: int) -> int:
        """Return the next tick this (pid, page) will be accessed, or ∞."""
        key = (pid, page)
        ticks = self._schedule.get(key, [])
        for t in ticks:
            if t > self._current_tick:
                return t
        return math.inf  # type: ignore[return-value]

    def select_victim(
        self,
        frame_manager: "FrameManager",
        processes: Dict[int, "ProcessDescriptor"],
    ) -> Optional[VictimTuple]:
        used = frame_manager.used_frame_ids()
        if not used:
            return None

        worst_fid: int = -1
        worst_next: float = -1.0

        for fid in used:
            fd = frame_manager.get_frame(fid)
            nxt = self._next_use(fd.owner_pid, fd.owner_page)
            if nxt > worst_next:
                worst_next = nxt
                worst_fid = fid

        fd = frame_manager.get_frame(worst_fid)
        return (worst_fid, fd.owner_pid, fd.owner_page)

    def name(self) -> str:
        return "OPT (Bélády's Optimal)"
