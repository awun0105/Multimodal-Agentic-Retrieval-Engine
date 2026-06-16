import sqlite3

from system1.release.mini_seed import build_mini_seed
from system1.validation.release_validator import validate_release


def test_system1_package_imports():
    import system1

    assert system1 is not None


def test_mini_seed_generates_valid_release(tmp_path):
    release_dir = build_mini_seed(tmp_path)
    sqlite_path = release_dir / "db" / "app.sqlite"

    assert sqlite_path.exists()

    with sqlite3.connect(sqlite_path) as connection:
        row = connection.execute(
            "SELECT document_id FROM text_documents_fts WHERE text_documents_fts MATCH ?",
            ("validation",),
        ).fetchone()

    assert row == ("doc:L01_V001:250:caption",)
    result = validate_release(release_dir)
    assert result.passed
