# Offline rollback guidance

This document describes release review only; it does not authorize production
operations.

For an uninstalled release, discard the isolated extraction directory and
restore the previously approved source and configuration from their separately
managed backups. Do not use `git reset`, `git clean`, or `git checkout` on a
working tree containing user changes.

For a database migration, stop the application under an approved maintenance
procedure, preserve the original database and WAL/SHM files, validate a backup
with SQLite `integrity_check`, and restore only a verified backup with matching
ownership and permissions. Never overwrite a production database from this
document alone.
