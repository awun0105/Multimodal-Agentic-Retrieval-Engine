import sqlite3

from system1.release.mini_seed import build_mini_seed, discover_paired_inputs
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


def test_input_discovery_pairs_real_subset():
    pairs = discover_paired_inputs("input")
    assert [pair["video_id"] for pair in pairs] == ["L21_V001", "L21_V002", "L21_V003"]


def test_mini_seed_can_use_real_subset(tmp_path):
    release_dir = build_mini_seed(tmp_path, input_dir="input")

    with sqlite3.connect(release_dir / "db" / "app.sqlite") as connection:
        count = connection.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
        video_id = connection.execute("SELECT video_id FROM videos ORDER BY video_id LIMIT 1").fetchone()[0]

    assert count == 3
    assert video_id == "L21_V001"
    assert validate_release(release_dir).passed
