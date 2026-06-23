# Virtual Memory Simulator

> **Operating Systems Project** — Demand-Paged Virtual Memory Simulation with Approximate LRU Replacement

---

## Overview

This project simulates a **demand-paged virtual memory system** supporting multiple concurrent processes. It benchmarks three page-replacement strategies against a no-swap baseline and produces detailed performance analysis across varied memory sizes.

---

## Architecture

```
WorkloadGenerator  ──→  Simulator (main loop)
  (locality, phase          │
   shifts, OPT oracle)      ▼
                       MemoryManager
                       ├── FrameManager       O(1) alloc (free-list deque)
                       ├── PageTable          per-process PTEs + history counters
                       └── Replacer ─────────┬── ClockReplacer  (Second-Chance)
                                             ├── AgingReplacer  (NFU shift-register)
                                             └── OPTReplacer    (Bélády's Optimal)
                            │
                            ▼
                       MetricsCollector ──→ Matplotlib Charts
```

---

## Key Data Structures

| Structure | Module | Complexity |
|---|---|---|
| `FrameDescriptor[]` | `frame_manager.py` | O(1) lookup by frame_id |
| `deque` free-list | `frame_manager.py` | O(1) alloc & free |
| `PageTableEntry{}` | `page_table.py` | O(1) by page number |
| Aging history counter | `page_table.py` | 8-bit shift register |
| Clock hand | `lru_clock.py` | O(F) worst-case sweep |

---

## Replacement Algorithms

### 1. No Swap (Baseline)
- Physical memory only; processes are terminated on Out-Of-Memory
- No replacement ever occurs — measures maximum possible fault rate

### 2. Clock (Second-Chance)
- Circular sweep with a hardware-maintained **reference bit**
- First pass: clear referenced pages (give second chance)
- Second pass: evict unreferenced pages
- O(F) victim selection in worst case (F = frame count)

### 3. Aging / NFU
- Each page maintains an **8-bit history counter**
- Every aging tick: `counter = (counter >> 1) | (referenced ? 0x80 : 0x00)`
- Victim = page with smallest counter (least recently used)
- Approximates LRU with configurable resolution (bit width)

### 4. OPT (Bélády's Optimal) — oracle upper bound
- Pre-computes the complete future access sequence
- Victim = page whose next use is farthest in the future
- Provides the theoretical minimum fault rate — used as comparison baseline

---

## Performance Metrics

| Metric | Description |
|---|---|
| **Page Fault Rate** | Faults / total accesses (global + per-process) |
| **Replacement Rate** | Replacements / total accesses |
| **Degree of Multiprogramming** | Avg active process count over simulation time |
| **Resident Set Size (RSS)** | Pages in memory per process |
| **Dirty Write-Backs** | Pages needing I/O on eviction |
| **Thrashing Flag** | Fault rate > 50% threshold |

---

## Installation

```bash
git clone <repo-url>
cd os_op
pip install -r requirements.txt
```

---

## Usage

### Quick Demo (single run, Aging policy)
```bash
python main.py
```

### Single Run — specify policy and memory size
```bash
python main.py --policy clock   --frames 32  --ticks 3000
python main.py --policy aging   --frames 64
python main.py --policy no_swap --frames 48
python main.py --policy opt     --frames 64
```

### Full Performance Sweep (all policies × all frame sizes)
```bash
python main.py --sweep
```

Generates 3 charts in `results/`:
- `fault_rate_vs_frames.png`
- `replacement_rate_vs_frames.png`
- `multiprogramming_vs_frames.png`

### Custom Sweep
```bash
python main.py --sweep --frames 16,32,64,128,256 --policies clock,aging,opt
```

### Verbose fault tracing
```bash
python main.py --policy aging --frames 16 --ticks 200 --verbose
```

### All CLI Options
```
--policy     Replacement policy: no_swap | clock | aging | opt
--frames     Frame count (single or comma-separated for sweep)
--processes  Number of concurrent processes (default: 8)
--vp         Virtual pages per process (default: 64)
--ws         Working-set size (default: 10)
--ticks      Simulation ticks (default: 2000)
--seed       Random seed (default: 42)
--sweep      Run multi-policy × multi-frame sweep
--policies   Comma-separated policies for sweep
--out        Output directory for charts (default: results/)
--verbose    Print every page fault event
--no-charts  Skip chart generation
```

---

## Sample Results

After a full sweep (`python main.py --sweep`) with default config  
(5 processes · 32 virtual pages · 8-page working set · 3000 ticks):

**At 48 frames** (working-set boundary — all 5 × 8 = 40 pages just fit):

| Policy | Fault Rate | Replacement Rate | Avg Multiprog | Thrashing |
|---|---|---|---|---|
| No Swap | 63.8% | 0% | 4.7 | 75.0% |
| Clock | 28.1% | 20.2% | 5.0 | 3.0% |
| Aging (NFU) | 45.6% | 37.8% | 5.0 | 16.9% |
| **OPT (Oracle)** | **17.7%** | **9.9%** | **5.0** | **3.0%** |

**At 64 frames** (comfortable fit — working sets easily resident):

| Policy | Fault Rate | Replacement Rate |
|---|---|---|
| Clock | 20.9% | 11.5% |
| Aging (NFU) | 35.0% | 25.6% |
| OPT | 15.9% | 6.5% |

**At 256 frames** (all policies converge — no pressure):

| Policy | Fault Rate | Replacement Rate |
|---|---|---|
| Clock | 13.8% | 0.0% |
| Aging (NFU) | 13.8% | 0.0% |
| OPT | 13.8% | 0.0% |

> **Note:** Residual 13.8% at large frame counts is the cold-start rate — every page is a fault on its very first access (demand paging). This is correct OS behaviour.

> **Key insight:** OPT achieves 37% fewer faults than Clock and 61% fewer than Aging at the working-set boundary (48 frames), demonstrating the cost of approximation in real LRU implementations.

---

## Project Structure

```
os_op/
├── main.py              ← CLI entry point
├── requirements.txt
├── src/
│   ├── config.py        ← SimConfig (all parameters)
│   ├── process.py       ← ProcessDescriptor + ProcessState
│   ├── page_table.py    ← PageTableEntry + PageTable
│   ├── frame_manager.py ← Physical frame pool (O(1) free-list)
│   ├── lru_clock.py     ← Clock, Aging, OPT replacers
│   ├── memory_manager.py← Demand-paging core logic
│   ├── workload.py      ← Synthetic workload generator
│   └── simulator.py     ← Main simulation loop + sweep
├── analysis/
│   ├── metrics.py       ← MetricsCollector + RunSummary
│   └── plot.py          ← Matplotlib chart generation
└── results/             ← Auto-generated output charts
```

---

## Concepts Demonstrated

- **Demand paging**: pages loaded only on first access
- **Page fault handling**: free-frame allocation → replacement → mapping
- **Dirty bit**: tracks modified pages requiring writeback on eviction
- **Reference bit**: hardware-set flag cleared by OS during replacement
- **Working-set model**: locality of reference with phase transitions
- **Thrashing**: detected when fault rate exceeds multiprogramming benefits
- **Bélády's anomaly**: not applicable to LRU/OPT (only affects FIFO)

---

## Author

**Keshab Agarwal** | Operating Systems Project
