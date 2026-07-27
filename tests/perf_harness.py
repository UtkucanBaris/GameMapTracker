from __future__ import annotations

import argparse
import sys
import time
import tracemalloc
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def run(point_count: int) -> None:
    from trail_model import TrailModel

    model = TrailModel(min_distance=0.0)
    tracemalloc.start()
    started = time.perf_counter()
    for index in range(point_count):
        if not model.add(float(index), float(index % 100)):
            raise RuntimeError(f"Point {index} was unexpectedly rejected")
    elapsed_ms = (time.perf_counter() - started) * 1000
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    accepted = sum(len(path) for path in model.paths)
    print(f"points={accepted} elapsed_ms={elapsed_ms:.2f} peak_bytes={peak_bytes}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--points", type=int, default=10_000)
    args = parser.parse_args()
    if args.points < 1:
        raise SystemExit("--points must be positive")
    run(args.points)
