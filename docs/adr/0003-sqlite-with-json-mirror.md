# 0003. Store Library metadata in SQLite with a JSON mirror

Status: Accepted

## Context

Library metadata started as one JSON document per download folder (`.grab-library.json`). Tags,
notes, collections and Recovery records represent hours of manual work, and libraries reach tens
of thousands of entries. Backup restore, older app versions and tests read or write that JSON
document.

## Decision

`SqliteLibraryStore` (`grab_storage.py`) writes each save to `.grab-library.db` in one transaction,
then atomically replaces the JSON document (temp file and rename). On load, if the JSON document is
as new as or newer than the database, it is imported into SQLite first. Full records stay in a
`data` column; frequently filtered fields (`complete`, `favorite`, `source`, `format`) also get
indexed columns. Newer settings such as auto rules go into the key-value `meta` table, so the
schema does not change and older versions keep them intact.

## Consequences

- Transactional writes and indexes, while older versions and backup restore keep working with the
  JSON format.
- The modification-time comparison must treat equal timestamps as "JSON is newer", or a restore
  written within one clock tick of the database looks lost (fixed in `40e9a3c`).
- Two copies must stay consistent; a failed SQLite write raises before the JSON is replaced.
- The whole document is still rewritten on save. This is acceptable at measured sizes (see
  `docs/PERFORMANCE_REVIEW.md`) and should change only with new measurements.

## Alternatives considered

- **JSON only**: simple, but no transactions or indexes.
- **SQLite only**: would break backup restore and downgrades without a migration path.
