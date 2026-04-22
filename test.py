# python_port/run_term_neonate.py
"""Run the real term_neonate_timothy.json scenario end-to-end.

First full-scale test — uses the actual physiological definition file,
not a toy scenario. Expect the first run to surface things the toy
scenarios never exercised.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from explain import Engine  # noqa: E402

SCENARIO = HERE / "model_definitions" / "adult_female.json"
CSV_OUT = HERE / "output" / "adult_female_python.csv"

# Start small — 5 seconds of simulated time. Expand once it works.
DURATION_S = 15.0
SAMPLE_EVERY_S = 0.01

# A focused watchlist — enough to see physiology, not so many columns that
# the CSV is unreadable. Add more once you've confirmed the baseline runs.
WATCH = [
    ("Heart", "heart_rate_measured"),
    ("Heart", "cardiac_cycle_state"),
    ("Heart", "ecg_signal"),
    ("LV", "pres"),
    ("LV", "vol"),
    ("RV", "pres"),
    ("RV", "vol"),
    ("AA", "pres"),
    ("AA", "vol"),
    ("PA", "pres"),
    ("PA", "vol"),
    ("AA", "ph"),
    ("AA", "pco2"),
    ("AA", "po2"),
]


def run() -> int:
    if not SCENARIO.exists():
        print(f"missing: {SCENARIO}")
        return 1

    print(f"Loading {SCENARIO.name}...")
    eng = Engine()
    t0 = time.time()
    eng.load_file(SCENARIO)
    print(f"  loaded in {time.time() - t0:.2f}s — {len(eng.models)} instances")

    print(f"Running for {DURATION_S}s simulated (step = {eng.modeling_stepsize}s)...")
    t0 = time.time()
    rows = eng.run(DURATION_S, watch=WATCH, sample_every_s=SAMPLE_EVERY_S)
    wall = time.time() - t0
    print(f"  ran in {wall:.2f}s wall  "
          f"({DURATION_S / wall:.1f}x realtime)  "
          f"{len(rows)} samples")

    Engine.write_csv(rows, CSV_OUT)
    print(f"  CSV: {CSV_OUT.relative_to(HERE)}")

    # Physiology sanity print — last-sample snapshot
    print()
    print("Final snapshot:")
    for col in rows[-1]:
        print(f"  {col:40s} = {rows[-1][col]:.4f}")

    return 0


if __name__ == "__main__":
    sys.exit(run())