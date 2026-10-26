"""Operator notebooks hold settings, setup, and one CLI call each (plan Step 5e, GUIDE.md Rule 10)."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

NOTEBOOKS = Path(__file__).resolve().parents[1] / "notebooks"

KEPT = {
    "00B_master_ingestion_and_assignment.ipynb": None,
    "00C_master_ingestion_local.ipynb": None,
    "01_worker_batch.ipynb": "worker-batch",
    "02_caption_batch.ipynb": "caption-batch",
    "03_build_release.ipynb": "build-release",
}

# Phase00 notebooks still hold logic in these code cells (0-based cell index).
# Reducing them to settings plus CLI calls is a later task (plan Step 5e table).
# Shrink this list as cells are reduced; never add to it.
LOGIC_CELL_ALLOWLIST = {
    "00B_master_ingestion_and_assignment.ipynb": {0, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 17, 18, 21, 22, 23, 24},
    "00C_master_ingestion_local.ipynb": {0, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21},
}

SECRET_SOURCES = ("kaggle_secrets", "google.colab", "os.environ")


def _cells(name: str) -> list[dict]:
    return json.loads((NOTEBOOKS / name).read_text(encoding="utf-8"))["cells"]


def _source(cell: dict) -> str:
    return "".join(cell.get("source", []))


def _parse(source: str) -> ast.Module:
    # IPython magics and shell escapes are not Python.
    lines = [line for line in source.splitlines() if not line.lstrip().startswith(("%", "!"))]
    return ast.parse("\n".join(lines))


def _is_settings(tree: ast.Module) -> bool:
    return bool(tree.body) and all(isinstance(node, (ast.Assign, ast.AnnAssign)) for node in tree.body)


def _is_setup(source: str) -> bool:
    return source.lstrip().startswith("# Setup")


def _is_cli_call(source: str, tree: ast.Module) -> bool:
    if '"system1.cli"' not in source:
        return False
    calls = [
        node
        for node in tree.body
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "system1"
    ]
    return len(calls) == 1


def _code_cells(name: str):
    for index, cell in enumerate(_cells(name)):
        if cell["cell_type"] == "code":
            source = _source(cell)
            yield index, source, _parse(source)


@pytest.mark.parametrize("name", sorted(KEPT))
def test_cells_are_markdown_settings_setup_or_one_cli_call(name):
    allowed = LOGIC_CELL_ALLOWLIST.get(name, set())
    offending = [
        index
        for index, source, tree in _code_cells(name)
        if not (_is_settings(tree) or _is_setup(source) or _is_cli_call(source, tree))
    ]
    assert sorted(set(offending) - allowed) == [], f"{name}: logic cells outside the allowlist"
    assert sorted(allowed - set(offending)) == [], f"{name}: allowlist entries no longer needed"


@pytest.mark.parametrize("name", sorted(KEPT))
def test_no_cell_imports_system1_modules(name):
    allowed = LOGIC_CELL_ALLOWLIST.get(name, set())
    for index, _source_text, tree in _code_cells(name):
        if index in allowed:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert not any(alias.name.split(".")[0] == "system1" for alias in node.names), (name, index)
            if isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] != "system1", (name, index)


@pytest.mark.parametrize("name", sorted(KEPT))
def test_secrets_come_from_secret_stores_and_are_never_printed(name):
    joined = "\n".join(_source(cell) for cell in _cells(name) if cell["cell_type"] == "code")
    assert "HF_TOKEN" in joined
    assert any(source in joined for source in SECRET_SOURCES)
    for index, _source_text, tree in _code_cells(name):
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
                names = {n.id.lower() for arg in node.args for n in ast.walk(arg) if isinstance(n, ast.Name)}
                assert not any("token" in n for n in names), (name, index)


@pytest.mark.parametrize("name, command", [(n, c) for n, c in sorted(KEPT.items()) if c])
def test_batch_notebooks_run_their_cli_command(name, command):
    cells = _cells(name)
    assert cells[0]["cell_type"] == "markdown"
    code = [(source, tree) for _index, source, tree in _code_cells(name)]
    assert _is_settings(code[0][1])
    assert sum(_is_cli_call(source, tree) for source, tree in code) == 1
    assert any(f'"{command}"' in source for source, _tree in code)
