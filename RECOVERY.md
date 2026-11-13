# Offline recovery

This release candidate is restored from its archive into a new directory and
configured through `.env.example` or an operator-owned environment file.

1. Verify the archive checksum and extract it into a new directory.
2. Create a Python 3.11 virtual environment outside the source archive.
3. Install dependencies from the approved, pinned release manifest.
4. Set `GHOSTNODE_INTELLIGENCE_DB` to a test database for validation.
5. Run the test suite and `python -m compileall` before any service review.

Do not copy production SQLite, wallet files, cookies, `ghost.conf`, locks, or
runtime reports into the release tree. Production migration and service
activation require a separate approved runbook.
