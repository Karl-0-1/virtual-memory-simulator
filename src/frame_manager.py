"""
frame_manager.py — Physical memory frame pool.

Manages the system's physical page frames.  Provides O(1) allocation (free-list
deque) and O(1) lookup (direct-address array indexed by frame_id).

FrameDescriptor
  frame_id      — unique integer [0, total_frames)
  owner_pid     — process that currently owns this frame (-1 = free)
  owner_page    — virtual page number mapped to this frame (-1 = free)
  in_use        — convenience bool

FrameManager
  allocate_frame(pid, page) → frame_id | None
  free_frame(frame_id)
  get_frame(frame_id) → FrameDescriptor
  all_used_frames() → list[FrameDescriptor]
"""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class FrameDescriptor:
    """Metadata for one physical page frame."""
    frame_id: int
    owner_pid: int = -1
    owner_page: int = -1
    in_use: bool = False

    def __repr__(self) -> str:
        if not self.in_use:
            return f"Frame({self.frame_id}: FREE)"
        return f"Frame({self.frame_id}: pid={self.owner_pid} page={self.owner_page})"


class FrameManager:
    """
    Physical frame pool.

    Internally maintains:
      _frames     — direct-address array indexed by frame_id  → O(1) lookup
      _free_list  — deque of available frame IDs              → O(1) alloc/free
    """

    def __init__(self, total_frames: int) -> None:
        self.total_frames = total_frames
        self._frames: List[FrameDescriptor] = [
            FrameDescriptor(frame_id=i) for i in range(total_frames)
        ]
        self._free_list: deque[int] = deque(range(total_frames))

    # ── allocation ─────────────────────────────────────────────────────────────

    def allocate_frame(self, pid: int, page: int) -> Optional[int]:
        """
        Pop a frame from the free list and assign it to (pid, page).
        Returns the frame_id, or None if physical memory is full.
        """
        if not self._free_list:
            return None
        fid = self._free_list.popleft()
        fd = self._frames[fid]
        fd.owner_pid = pid
        fd.owner_page = page
        fd.in_use = True
        return fid

    def free_frame(self, frame_id: int) -> None:
        """
        Release a frame back to the free list.
        Caller is responsible for invalidating the associated PTE.
        """
        fd = self._frames[frame_id]
        fd.owner_pid = -1
        fd.owner_page = -1
        fd.in_use = False
        self._free_list.append(frame_id)

    # ── query ──────────────────────────────────────────────────────────────────

    def get_frame(self, frame_id: int) -> FrameDescriptor:
        return self._frames[frame_id]

    def all_used_frames(self) -> List[FrameDescriptor]:
        return [f for f in self._frames if f.in_use]

    def used_frame_ids(self) -> List[int]:
        return [f.frame_id for f in self._frames if f.in_use]

    def free_count(self) -> int:
        return len(self._free_list)

    def used_count(self) -> int:
        return self.total_frames - len(self._free_list)

    def is_full(self) -> bool:
        return len(self._free_list) == 0

    # ── debug ──────────────────────────────────────────────────────────────────

    def dump(self) -> str:
        lines = [f"FrameManager(total={self.total_frames} free={self.free_count()})"]
        for f in self._frames:
            lines.append(f"  {f}")
        return "\n".join(lines)
