from scripts.check_tracked_artifacts import forbidden_paths


def test_approved_dependency_lockfile_is_allowed():
    assert forbidden_paths(["requirements.lock"]) == []


def test_runtime_sqlite_is_rejected():
    assert forbidden_paths(["data/example.sqlite3"]) == ["data/example.sqlite3"]


def test_runtime_lock_is_rejected():
    assert forbidden_paths(["data/example.lock"]) == ["data/example.lock"]


def test_environment_file_is_rejected():
    assert forbidden_paths([".env"]) == [".env"]


def test_environment_template_remains_allowed():
    assert forbidden_paths([".env.example"]) == []
