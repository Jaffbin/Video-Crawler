"""Benchmark bounded library scans using isolated synthetic files, never user downloads."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import webui  # noqa: E402


def benchmark(size, parent):
    with tempfile.TemporaryDirectory(prefix=f"library-{size}-", dir=parent) as directory:
        webui.ROOT = Path(directory).resolve()
        webui.JOB_MANAGER.reset()
        records = {}
        for index in range(size):
            folder = webui.ROOT / f"group-{index % 20}"
            folder.mkdir(exist_ok=True)
            path = folder / f"media-{index:05d}{'.mp4' if index % 2 == 0 else '.mp3'}"
            path.write_bytes(b"fixture")
            records[path.relative_to(webui.ROOT).as_posix()] = {"title": f"Media {index}", "complete": True,
                "tags": ["sample"], "note": f"Fixture item {index}", "favorite": index % 10 == 0}
            if index % 4 == 0:
                path.with_suffix(".jpg").write_bytes(b"cover")
        webui.LIBRARY.store.save({"files": records, "collections": {}, "trash": {}, "version": 1})
        forced = []
        for _ in range(3):
            start = time.perf_counter()
            result = webui.list_files(force=True)
            forced.append((time.perf_counter() - start) * 1000)
            assert len(result) == size
        cached = []
        for _ in range(10):
            start = time.perf_counter()
            webui.list_files()
            cached.append((time.perf_counter() - start) * 1000)
        original = Path.is_file
        calls = 0
        def counted(path, *args, **kwargs):
            nonlocal calls
            calls += 1
            return original(path, *args, **kwargs)
        with patch.object(Path, "is_file", counted):
            webui.list_files(force=True)
        return {"media": size, "forced_scan_ms": round(statistics.median(forced), 2),
                "cached_scan_ms": round(statistics.median(cached), 3), "path_is_file_calls": calls,
                "scan_incomplete": webui.FILES_CACHE["scan"]["incomplete"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", nargs="+", type=int, default=[1000, 10000])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    parent = Path(__file__).resolve().parents[1] / "artifacts"
    parent.mkdir(exist_ok=True)
    if any(size < 1 or size > 15000 for size in args.sizes):
        parser.error("sizes must be between 1 and 15000")
    results = []
    for size in args.sizes:
        value = benchmark(size, parent)
        results.append(value)
        print(json.dumps(value), flush=True)
    if args.output:
        args.output.write_text(json.dumps(results, indent=2), encoding="utf-8")
