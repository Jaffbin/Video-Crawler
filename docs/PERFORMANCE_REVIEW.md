# Library performance and code reuse review

Measured on the development Windows machine on 2026-10-17. These are local synthetic fixtures,
not guarantees for every drive or machine. User downloads and browser profiles were not used.

## Measurements

`scripts/benchmark_library.py` creates isolated media placeholders in 20 folders, with a JPEG
cover for one in four files, and removes the fixture afterward. Forced scan times are medians
of three runs on a warm filesystem. The fast cache is measured separately.

| Media records | Before: forced scan | After: forced scan | Before / after `Path.is_file` calls |
| --- | ---: | ---: | ---: |
| 1,000 | 423 ms | 69 ms | 6,000 / 0 |
| 10,000 | 4,223 ms | 918 ms | 60,000 / 0 |

The 10,000-record forced scan improved by about 78%. Cached scans remained around 0.001 ms.
Zero `Path.is_file` calls does not mean zero filesystem I/O: directory enumeration and entry
metadata reads still occur. Truncated/unreadable scans or symbolic media deliberately retain
the previous filesystem companion checks to avoid exposing covers as independent images.

`node scripts/benchmark_library_frontend.mjs` measures the existing filter/sort function and
the all-selected membership calculation on synthetic data. At 10,000 rows: query filtering
was about 6 ms; name sorting 3 ms; array-based selection membership 1,372 ms versus about
1 ms with a Set, including Set creation. The app now memoizes selection Sets, selected rows,
and source/format choices instead of repeating quadratic lookups on every render.

A separate Edge fixture supplied synthetic metadata and tiny local artwork to the real built
interface. These timings include automation overhead and exclude a real disk scan:

| Records | Initial page | Next page | Search | Sort | Select visible |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1,000 | 399 ms | 239 ms | 38 ms | 59 ms | 59 ms |
| 10,000 | 402 ms | 88 ms | 58 ms | 76 ms | 78 ms |

Only 50 gallery rows were mounted for the initial page in both cases. Search, sorting, pagination
and selection preserved their existing behavior. Browser rendering tests use generated API data;
they are distinct from the filesystem scan and JavaScript microbenchmarks above.

## Reuse changes and retained boundaries

- Chrome toolbar, reserved shortcut and context-menu actions share `popup.js`, `checkedPage`,
  the authenticated connection protocol and the existing completed-download review. No second
  enqueue implementation or content script was added. Temporary selection transport is isolated
  in `entrypoints.js`; it does not create download tasks.
- `MediaLibrary.is_attachment` and `cover_path` remain the single source of companion rules.
  The scanner passes its bounded, symlink-free directory snapshot to those methods. Other
  operations keep their existing default filesystem checks. This avoids duplicating the rules
  in an independently implemented scan index.
- Library selection now uses memoized Sets. Completed bulk-operation cleanup uses a Set too.
  Search/date/sort helper compatibility and collection/favorite behavior remain unchanged.
- The legacy inline web interface still duplicates some React presentation logic. It remains
  a compatibility fallback when the built frontend is missing; removing it would be a separate
  compatibility decision, not incidental cleanup.
- Download-option validation appears in Python and TypeScript because both sides are trust
  boundaries. Backup allowlists intentionally exclude credentials and connection details.
  Sharing unvalidated structures merely to remove similar-looking code would weaken that boundary.

## Batch recycling follow-up

The batch endpoint previously called single-file recycling repeatedly. Each item reloaded the
whole metadata document, saved it with an atomic replacement and `fsync`, then moved its group.
It now shares a batch implementation with single-file recycling: load once, validate groups,
persist all recovery intents once, then move groups individually. Only successfully rolled-back
failures require a second, combined metadata save. Invalid groups do not write anything.
Restoring and permanently deleting Recovery selections retain their existing per-item saves;
this follow-up optimizes moving Library files into Recovery only.

`scripts/benchmark_library_trash.py` measures 200 media groups, each with a cover and subtitle,
distributed across 20 folders. The full metadata document contains the indicated number of
records; only the 200 selected groups have physical fixture files. Setup and cleanup are excluded;
times are medians of three runs with real metadata writes on this Windows machine.

| Metadata records | Recycled groups | Before | After | Metadata saves before / after |
| --- | ---: | ---: | ---: | ---: |
| 1,000 | 200 | 3,470 ms | 2,467 ms | 200 / 1 |
| 10,000 | 200 | 10,648 ms | 2,573 ms | 200 / 1 |

The 10,000-record case improved by about 76%. This measures the library operation, excluding
HTTP handling, history persistence and UI refresh. File moves still perform filesystem I/O;
the reduction concerns complete metadata-document saves, not every disk operation.

Recovery intents retain the original file identities (device, inode, size and modification time)
in an optional `originals` field. Restore can finish an interrupted operation when some files
are in Recovery and others remain at their original locations, accepting only unchanged original
files and refusing replacements. Legacy records without identities keep their strict restore
behavior. If a group rollback or the final failure-cleanup save fails, its durable recovery
record remains available instead of discarding the only record of moved files. Undo IDs still
include only successful groups. No new journal, dependency or background writer was introduced.

Tests simulate interruption before/after each of six file moves, restarting the library and
restoring byte-for-byte content plus organization. They also exercise initial-save failure,
locked companions, rollback failure, cleanup-save failure, interrupted restore, restore-save
failure, legacy records, replacement conflicts and the real batch API's partial-success Undo.
These simulate process interruption; they do not establish behavior under abrupt power loss.
Follow-up verification: all 482 Python tests and all 33 `FileGallery` frontend tests passed.
Repository-wide Ruff and `git diff --check` passed. The frontend bundle was not changed.

## Remaining follow-up candidates

- Recovery size reporting still enumerates matching files for each record. A single directory
  inventory could reduce repeated enumeration for large Recovery lists; it is not changed here.
- The state API still transfers the discovered Library snapshot and filters/pages on the client.
  Server pagination or a database could help much larger libraries, but the measured 10,000-row
  workload did not justify an architectural migration in this change.
- `FileGallery` and the backend coordinator are large modules. Future feature work can extract
  cohesive workflows with tests; file size alone does not justify rewriting working behavior.

## Reproduce

```powershell
.venv\Scripts\python.exe scripts/benchmark_library.py
.venv\Scripts\python.exe scripts/benchmark_library_trash.py
node scripts/benchmark_library_frontend.mjs
node --test browser-extension/tests/*.test.js
```

Review the normal Python/frontend regression suites as well. Do not run a frontend build
concurrently with the backend built-resource integrity test, because the build replaces hashed assets.

Original scan/extension change verification: 462 Python tests, 198 frontend tests and 19 extension protocol/
entrypoint tests passed; frontend type/build and formatting checks passed. Loaded Chromium tested
the native confirmation popup, selected-link transport, single-use/expired intent handling and
confirmation-tab fallback. Chrome reported the reserved shortcut registered as Alt+Shift+V.
Physical keyboard activation was not manually verified: injecting keys into the headless page
did not exercise the browser accelerator, so that exploratory check is not counted as a pass.

One pre-existing media-organization test initially encountered Windows error 5 during an atomic
file replacement. Its isolated rerun and the complete suite passed; the transient cause was not
established. No storage retry or delay was introduced to conceal that failure.
