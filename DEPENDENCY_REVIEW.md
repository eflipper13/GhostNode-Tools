# Dependency review

Runtime and development dependencies are declared in `pyproject.toml` and
`requirements-dev.txt`. The project targets Python 3.11 or newer.

`requirements.lock` pins the tested Python 3.11 environment and includes
SHA256 hashes for the downloaded wheel artifacts. A fresh environment was
recreated from that lock and passed `pip check` and the full test suite.

The listed dependencies are external packages and are not copied into this
repository. Their individual license notices must be retained by the package
installation/distribution process. No third-party source fragment was found
copied into the application tree during the source review.
