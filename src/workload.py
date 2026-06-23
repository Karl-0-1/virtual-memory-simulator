"""
workload.py — Synthetic memory access workload generator.

Produces a stream of (pid, virtual_page_number) access events that simulate
realistic program behaviour:

  • Locality of reference   — fraction `locality_ratio` of accesses fall within
                              the process's current working set; the rest are
                              random pages (cold misses / scans).
  • Phase shifts            — every `phase_shift_interval` ticks the working set
                              rolls to new pages, simulating program phase changes.
  • Multi-process           — accesses are interleaved across all living processes.

The generator can also pre-compute the full future schedule for the OPT replacer.
"""
from __future__ import annotations

import random
from collections import defaultdict
from typing import Dict, Generator, List, Set, Tuple


AccessEvent = Tuple[int, int, bool]   # (pid, virtual_page, is_write)


class WorkloadGenerator:
    """
    Generates memory access traces for N processes.

    Parameters
    ----------
    pids              : list of active process IDs
    virtual_pages     : virtual address space size per process (pages)
    working_set_size  : number of pages in the hot working set
    locality_ratio    : fraction of accesses within the working set
    phase_interval    : ticks between working-set phase shifts
    write_ratio       : fraction of accesses that are writes (set dirty bit)
    seed              : random seed for reproducibility
    """

    def __init__(
        self,
        pids: List[int],
        virtual_pages: int,
        working_set_size: int,
        locality_ratio: float,
        phase_interval: int,
        write_ratio: float = 0.30,
        seed: int = 42,
    ) -> None:
        self._pids = list(pids)
        self._vp = virtual_pages
        self._ws_size = working_set_size
        self._locality = locality_ratio
        self._phase_interval = phase_interval
        self._write_ratio = write_ratio
        self._seed = seed                      # store for OPT oracle replay
        self._rng = random.Random(seed)

        # current working set per process
        self._working_sets: Dict[int, Set[int]] = {
            pid: self._new_working_set() for pid in self._pids
        }
        # tick counter per process to know when to phase-shift
        self._phase_counters: Dict[int, int] = {pid: 0 for pid in self._pids}

    # ── working set management ─────────────────────────────────────────────────

    def _new_working_set(self) -> Set[int]:
        """Pick `working_set_size` random pages as the new hot set."""
        pages = self._rng.sample(range(self._vp), min(self._ws_size, self._vp))
        return set(pages)

    def get_working_set(self, pid: int) -> Set[int]:
        return self._working_sets.get(pid, set())

    def _maybe_phase_shift(self, pid: int) -> None:
        self._phase_counters[pid] += 1
        if self._phase_counters[pid] >= self._phase_interval:
            self._phase_counters[pid] = 0
            self._working_sets[pid] = self._new_working_set()

    # ── access generation ──────────────────────────────────────────────────────

    def next_access(self, pid: int, tick: int) -> AccessEvent:
        """Generate the next memory access for the given process."""
        self._maybe_phase_shift(pid)
        ws = self._working_sets[pid]

        if self._rng.random() < self._locality and ws:
            # hot access — within working set
            page = self._rng.choice(list(ws))
        else:
            # cold access — anywhere in virtual address space
            page = self._rng.randrange(self._vp)

        is_write = self._rng.random() < self._write_ratio
        return (pid, page, is_write)

    def generate_stream(
        self, total_ticks: int
    ) -> Generator[AccessEvent, None, None]:
        """
        Yield `total_ticks` access events, round-robining across alive processes.
        """
        for tick in range(total_ticks):
            pid = self._pids[tick % len(self._pids)]
            yield self.next_access(pid, tick)

    # ── OPT oracle support ─────────────────────────────────────────────────────

    def precompute_schedule(
        self, total_ticks: int
    ) -> Dict[Tuple[int, int], List[int]]:
        """
        Pre-compute the full access sequence for the OPT replacer oracle.

        Creates a TWIN WorkloadGenerator with the identical construction
        seed and parameters, then replays the full stream.  This guarantees
        the oracle sees exactly the same (pid, page) sequence that the actual
        simulation will produce — without touching the live generator's state.

        Returns a dict: (pid, page) → sorted list of tick indices.
        """
        # Build an identical twin generator from the same seed
        twin = WorkloadGenerator(
            pids=self._pids,
            virtual_pages=self._vp,
            working_set_size=self._ws_size,
            locality_ratio=self._locality,
            phase_interval=self._phase_interval,
            write_ratio=self._write_ratio,
            seed=self._seed,
        )

        schedule: Dict[Tuple[int, int], List[int]] = defaultdict(list)
        for tick, (pid, page, _) in enumerate(twin.generate_stream(total_ticks)):
            schedule[(pid, page)].append(tick)

        return dict(schedule)
