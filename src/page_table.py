"""
page_table.py — PageTableEntry and PageTable data structures.

Each process owns one PageTable.  A PageTableEntry holds all per-page metadata:
  • valid / dirty / referenced bits
  • frame mapping
  • 8-bit aging history counter (for Aging / NFU approximate LRU)
  • last-access tick (for OPT oracle and statistics)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class PageTableEntry:
    """One entry in a process page table."""

    page_number: int

    # ── hardware-maintained bits ───────────────────────────────────────────────
    valid: bool = False          # True  → page is resident in a physical frame
    dirty: bool = False          # True  → page has been written (needs writeback)
    referenced: bool = False     # True  → accessed since last clock sweep

    # ── OS-maintained fields ───────────────────────────────────────────────────
    frame_number: int = -1       # Physical frame (-1 = not resident)
    history_counter: int = 0     # 8-bit aging register (MSB shift each tick)
    last_access_tick: int = -1   # Simulation tick of most recent access

    # ── statistics ─────────────────────────────────────────────────────────────
    access_count: int = 0
    fault_count: int = 0

    def age(self) -> None:
        """Shift aging register right by 1 and merge referenced bit into MSB."""
        self.history_counter = (self.history_counter >> 1) | (
            0x80 if self.referenced else 0x00
        )
        self.referenced = False   # clear after each aging interval

    def invalidate(self) -> None:
        """Evict this page (called by the replacer)."""
        self.valid = False
        self.frame_number = -1
        self.referenced = False
        # Keep history_counter — helps if page is re-loaded

    def __repr__(self) -> str:
        status = "R" if self.valid else " "
        status += "D" if self.dirty else " "
        status += "r" if self.referenced else " "
        return (
            f"PTE(page={self.page_number:3d} frame={self.frame_number:4d} "
            f"[{status}] hist={self.history_counter:08b})"
        )


class PageTable:
    """
    Per-process page table: a fixed-size array of PageTableEntry objects.
    Supports O(1) lookup by page number.
    """

    def __init__(self, pid: int, num_pages: int) -> None:
        self.pid = pid
        self.num_pages = num_pages
        self._entries: Dict[int, PageTableEntry] = {
            i: PageTableEntry(page_number=i) for i in range(num_pages)
        }

    # ── access helpers ─────────────────────────────────────────────────────────

    def __getitem__(self, page: int) -> PageTableEntry:
        return self._entries[page]

    def get(self, page: int) -> Optional[PageTableEntry]:
        return self._entries.get(page)

    def resident_pages(self) -> list[PageTableEntry]:
        """Return all currently-resident PTEs."""
        return [e for e in self._entries.values() if e.valid]

    def resident_count(self) -> int:
        return sum(1 for e in self._entries.values() if e.valid)

    # ── aging ──────────────────────────────────────────────────────────────────

    def age_all(self) -> None:
        """Called each aging interval — shift history counters for resident pages."""
        for entry in self._entries.values():
            if entry.valid:
                entry.age()

    # ── debug ──────────────────────────────────────────────────────────────────

    def dump(self) -> str:
        lines = [f"PageTable(pid={self.pid}, pages={self.num_pages})"]
        for e in self._entries.values():
            if e.valid or e.fault_count > 0:
                lines.append(f"  {e}")
        return "\n".join(lines)
