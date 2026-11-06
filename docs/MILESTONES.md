# Development milestones

Scope confirmed on 2026-10-17. Complete and review milestones in order.

## M1 — Smart collections

Status: complete (2026-10-17).

- Built-in recent saves, not started in this app, continue playback and favorites views.
- Custom named rules for media type, source site, extension, one exact tag, favorite status,
  rolling saved-date window and in-app playback status. Every configured condition must match.
- Live match-count preview; create, rename/edit and confirm deletion of custom collections.
- Use the existing Collection filter and manager, retaining manual collection membership.
- Persist rules per library, remember the selected view and include custom rules in reviewed
  backup/restore merges. Existing conflicting definitions win. Built-ins are not backed up.
- Match newly downloaded or refreshed files without copying/moving files. Playback predicates
  exclude images and incomplete downloads. External-player activity is not inferred.
- Keep rule validation bounded, reject unsupported conditions, and preserve legacy backups.

Verification: 521 backend tests and 209 frontend tests passed. Type checking, frontend build,
Prettier and Ruff passed. Isolated real-browser checks exercised all seven rules, preview,
create/view/reload/edit/empty-result/delete, with screenshots at 1280px and 400px. A clock
regression covers expiry and newly saved files arriving between minute ticks. The frontend
build reports a main-chunk size advisory (about 555 kB, 168 kB gzip); splitting existing screens
for initial-load size is separate follow-up work.

## M2 — Library organization assistant

Status: complete (2026-10-17).

- Find byte-identical files only, not different encodings/resolutions of the same content.
- Group candidates by size before background content hashing; report progress and allow cancel.
- Report recorded files absent from a complete scan. Inaccessible paths and partial scans must
  remain unknown rather than being classified as missing.
- Show media, companions and Recovery sizes separately, without double counting. Moving into
  Recovery does not reclaim disk space.
- Present findings for user review; use existing group recycling and Undo. Never auto-delete.
- First version is limited to the current library and preserves annotations for missing files.

The assistant uses one cancellable worker and paginates large finding lists. Duplicate
recycling requires an explicit selection and confirmation, retains at least one copy per
group, revalidates all reviewed members and reuses companion-aware group recycling and Undo.
Legacy download-history references to Recovery files do not become false missing findings.
Unreadable library metadata stops checks and reviewed recycling instead of overwriting records.

Windows identity checks account for zero device/inode fields from DirEntry.stat and differing
ctime semantics between path and file-handle APIs. Each API's version is checked consistently;
100 isolated scans passed after this correction, without adding delays or retries.

Verification: 556 backend tests and 214 frontend tests passed. One real directory-link test
was skipped because this Windows account cannot create directory links; mocked reparse-path
coverage passed. Type checking, frontend build, Prettier and Ruff passed. Isolated real-browser
checks covered scanning, totals, missing findings, no preselection, retaining a copy, reviewed
recycling, Undo and rescanning, including 1280px/400px layouts and English/Chinese light mode.
The frontend main-chunk advisory remains (about 576 kB, 174 kB gzip).

Full-suite verification exposed intermittent Windows connection aborts when rejecting POSTs
with unread request bodies. A local comparison reproduced four aborts in 200 legacy requests;
bounded body draining returned 200/200 unauthorized responses. Regression coverage preserves
authentication and bounds discarded bytes and time, without client retries.

## M3 — Optional desktop pet shortcut

Status: deferred by user (2026-10-18); not implemented by M2.

- Target Windows first. Prototype transparency, dragging, DPI and multiple-monitor behavior
  before committing to a rendering approach or adding dependencies.
- Accept dropped/pasted links and reuse the existing Quick download confirmation and queue.
  Reading Chrome's active page is outside the confirmed first-version scope.
- Show download status and provide quick access to the app. The user explicitly enables the pet.
- Closing the pet hides it; tray controls can show it again. Full app exit closes all owned
  windows and background resources.
- Decide character artwork and animation states before the M3 implementation phase.

## Additional milestone — Continuous audio playback

Status: complete (2026-10-27). M3 remains deferred.

- Persistent bottom playback bar, shared across app screens and audio details; no sleep timer.
- Add completed local audio individually, from a selection, or from the current filtered view
  across pages. Up to 500 distinct paths per library; adding does not autoplay.
- Reorder by drag or accessible up/down buttons, remove without deleting media, paginate large
  queues, and retain missing entries as unavailable until Library discovers them again.
- Sequential playback, shuffle cycles, off/all/one repeat, 0.5x–2x speed, volume and seeking.
- Persist order, current track and position locally; restore paused after restart. Reuse Library
  progress with optional root-bound writes and follow in-app renames. Backups exclude this queue.
- Keep one audio element outside app navigation, pause the other in-app player when switching
  between audio and video, clean up listeners/resources, and surface playback/storage failures.

Verification: 557 backend tests and 232 frontend tests passed. The existing real directory-link
test was skipped because this Windows account cannot create links. Ruff, Prettier, type checking,
frontend build and diff checks passed. Real-browser checks used silent WAV fixtures for playback,
page navigation, drag ordering, speed, paused position restoration, recycle/Undo, continuous
advance and end-of-list stopping, with 1280px/400px/320px layouts and Chinese light mode.
An isolated Windows WebView2 test also verified already-started audio and automatic advancement
after minimizing and DesktopController.background. Production code does not change autoplay
policy. The build retains a main-chunk advisory (about 606 kB, 182 kB gzip).
