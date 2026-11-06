"""Measure batch recycling on disposable fixtures, never on user downloads."""
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
from grab_library import MediaLibrary  # noqa: E402
from grab_storage import JsonStore  # noqa: E402


def benchmark(size, count, mode, parent):
    timings, writes = [], []
    for _ in range(3):
        with tempfile.TemporaryDirectory(prefix="recycle-benchmark-", dir=parent) as directory:
            root = Path(directory).resolve()
            library = MediaLibrary(lambda: root, {".mp4", ".mp3"})
            records = {f"group-{index % 20}/media-{index:05d}.mp4": {
                "title": f"Media {index}", "favorite": index % 5 == 0,
                "tags": ["sample"], "note": f"Fixture {index}", "complete": True,
            } for index in range(size)}
            items = list(records)[:count]
            for name in items:
                path = root / name
                path.parent.mkdir(exist_ok=True)
                path.write_bytes(b"media")
                path.with_suffix(".jpg").write_bytes(b"cover")
                path.with_suffix(".en.srt").write_bytes(b"subtitle")
            library.store.save({"files": records, "trash": {}, "collections": {}, "version": 1})
            original_save = JsonStore.save
            save_count = 0

            def counted_save(store, value):
                nonlocal save_count
                save_count += 1
                return original_save(store, value)

            with patch.object(JsonStore, "save", counted_save):
                start = time.perf_counter()
                if mode == "batch":
                    result = library.trash_many(items)
                    assert result["processed"] == items and not result["failed"]
                else:
                    for name in items:
                        library.trash(name)
                timings.append((time.perf_counter() - start) * 1000)
            writes.append(save_count)
            data = library.load()
            assert len(data["trash"]) == count and len(data["files"]) == size - count
            assert all(not (root / name).exists() for name in items)
            assert len(list(library.trash_directory().iterdir())) == count * 3
    return {"metadata_records": size, "recycled": count, "mode": mode,
            "median_ms": round(statistics.median(timings), 2), "metadata_saves": writes}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", nargs="+", type=int, default=[1000, 10000])
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument("--modes", nargs="+", choices=["sequential", "batch"], default=["sequential", "batch"])
    args = parser.parse_args()
    if not 1 <= args.count <= 200 or any(not args.count <= size <= 15000 for size in args.sizes):
        parser.error("count must be 1..200 and sizes must be count..15000")
    parent = Path(__file__).resolve().parents[1] / "artifacts"
    parent.mkdir(exist_ok=True)
    for size in args.sizes:
        for mode in args.modes:
            print(json.dumps(benchmark(size, args.count, mode, parent)), flush=True)
