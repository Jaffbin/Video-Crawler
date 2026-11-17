# Telling whether a file changed, on Windows

*Area: Library organizer (`grab_organizer.py`). Found while building duplicate detection in
milestone M2.*

## The problem

The organizer finds byte-identical files by grouping them by size and hashing the candidates in a
background thread. Hashing a large library takes minutes, and the user may keep downloading,
renaming or deleting files in the meantime. A duplicate finding is only safe to act on if every
file is still the one that was hashed, so the organizer records an identity for each file:

```python
def identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
```

It compares that identity when a file is opened, after it is hashed, at the end of the scan, and
again before the user's reviewed recycling runs.

## Symptom

On Windows, the identity values were not trustworthy:

1. The device and inode values from the directory scan were zero, so they could not tell files
   apart or detect hard links to the same physical file.
2. Files that nobody had touched could be reported as "changed during the check".

## Root cause

**Zero device and inode from `DirEntry.stat()`.** The scan walks folders with `os.scandir`, whose
cached `DirEntry.stat()` on Windows reports `st_ino` and `st_dev` as zero (this is documented
Python behaviour). Every file then had the same `(0, 0)` "physical" identity, so hard-link detection
and identity comparison were meaningless for those values.

**Path and handle APIs disagreed about ctime.** The identity was taken from a path-based `stat`
during the scan, then compared with `os.fstat` on the open file handle while hashing. On Windows the
two APIs did not always report the same value in `st_ctime_ns`, so an untouched file could look
modified. Python on Windows has historically used `st_ctime` for creation time and is moving it
towards metadata-change time, so this field is not a stable thing to compare across APIs.

## Fix

- For files that matter (media and subtitles), the scan takes a real `lstat` of the path instead of
  trusting `DirEntry.stat()`, so device and inode are filled in. A zero inode is never treated as a
  shared physical file.
- When a file is opened for hashing, only the fields both APIs agree on (device, inode, size,
  mtime) are compared between the path identity and the handle identity.
- Each API's *full* identity, including ctime, is still compared with its own earlier value: the
  path identity against the path identity from the scan, and the handle identity before and after
  reading. A file that really changes is still caught by the API that observed it.

After this change, 100 isolated scans passed with no false changes. No delays or retries were added.

## Regression tests

`tests/test_organizer.py`:

- `test_path_and_handle_change_times_can_differ_without_false_changes`
- `test_changed_files_are_excluded_even_after_their_hash_was_read`
- `test_unique_file_changes_and_returned_missing_files_are_rechecked_at_finish`
- `test_recycle_rechecks_every_group_member`

## Lessons

- "Has this file changed?" has no single portable answer; it depends on which API you ask.
  Comparing like with like kept the safety check strict without false alarms.
- Cached directory metadata is a performance shortcut, not an identity.
- The safe default when unsure is to report a file as unknown, not as a duplicate or as missing;
  the organizer never acts on a file whose identity it cannot confirm.
