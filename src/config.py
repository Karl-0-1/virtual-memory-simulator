"""
config.py — Simulation configuration dataclass.

All tuneable parameters live here. The CLI in main.py overrides these defaults.
"""
from dataclasses import dataclass, field
from typing import List


@dataclass
class SimConfig:
    # ── Physical memory ────────────────────────────────────────────────────────
    physical_frames: int = 64          # Total physical page frames
    frame_size_kb: int = 4             # Frame / page size in KB (cosmetic)

    # ── Process workload ───────────────────────────────────────────────────────
    # Rule: num_processes * working_set_size ≈ 0.6 × physical_frames at default
    # → 5 × 8 = 40 pages needed vs 64 frames = comfortable fit (no thrashing)
    num_processes: int = 5             # Concurrent processes
    virtual_pages_per_proc: int = 32   # Virtual address space size (pages)
    working_set_size: int = 8          # Pages per process in active working set
    locality_ratio: float = 0.85       # Fraction of accesses within working set
    phase_shift_interval: int = 100    # Ticks between working-set phase shifts

    # ── Simulation control ─────────────────────────────────────────────────────
    simulation_ticks: int = 3000       # Total memory-access events
    aging_bits: int = 8                # Width of aging shift-register (bits)
    clock_hand_step: int = 1           # Frames inspected per clock tick

    # ── Replacement policy ─────────────────────────────────────────────────────
    # "no_swap" | "clock" | "aging" | "opt"
    policy: str = "aging"

    # ── Sweep mode ─────────────────────────────────────────────────────────────
    # Sweet spot: need ~40 pages for working sets; sweep shows transition clearly
    sweep_frame_sizes: List[int] = field(
        default_factory=lambda: [8, 16, 24, 32, 40, 48, 64, 96, 128, 192, 256]
    )

    # ── Output ─────────────────────────────────────────────────────────────────
    results_dir: str = "results"
    random_seed: int = 42

    def __post_init__(self):
        if self.working_set_size >= self.virtual_pages_per_proc:
            raise ValueError("working_set_size must be < virtual_pages_per_proc")
        if not (0.0 < self.locality_ratio <= 1.0):
            raise ValueError("locality_ratio must be in (0, 1]")
        if self.policy not in ("no_swap", "clock", "aging", "opt"):
            raise ValueError(f"Unknown policy: {self.policy!r}")
