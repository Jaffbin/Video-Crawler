# 0004. Move files to Recovery instead of deleting them

Status: Accepted

## Context

Users rename, move, deduplicate and delete media from the Library, often in batches. A video has
companions (subtitles, covers, metadata) that must move with it. Mistakes are easy, and a lost file
often cannot be downloaded again.

## Decision

"Delete" moves a file and its companions into a hidden `.grab-trash` folder inside the library and
records where they came from, together with each file's identity (device, inode, size, mtime).
Restore refuses to replace anything already at the original location. The recorded identities let
a failed batch roll back safely and let an interrupted restore resume without accepting a
different file in place of the original. Permanent deletion is a separate, confirmed
action on Recovery items. `MediaLibrary` in `grab_library.py` is the single place that knows the
companion rules; the organizer and batch actions call it instead of re-implementing them.

## Consequences

- Every destructive action in the UI is reversible until the user empties Recovery.
- Recovery does not free disk space; the organizer reports Recovery size separately so this is not
  hidden.
- Restore never overwrites a file that later appeared at the old path.
- Batch operations save metadata once per batch rather than once per file (200 saves became 1 in
  the case measured in `docs/PERFORMANCE_REVIEW.md`).

## Alternatives considered

- **Windows Recycle Bin**: platform-specific, and loses companion grouping and Library annotations.
- **Immediate deletion behind a confirmation dialog**: confirmations get clicked through.
