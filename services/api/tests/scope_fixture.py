"""Loader for the synthetic scope-preservation fixture.

The fixture is the shared deterministic input of the acceptance tests for
requirement conservation, plan validation and the independent plan audit. It
is synthetic and contains no confidential tender data.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "scope_fixture.json"


@lru_cache(maxsize=1)
def load_scope_fixture() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def fixture_chunks() -> list[dict[str, Any]]:
    """One chunk per page, in the shape the understanding pass consumes."""
    fixture = load_scope_fixture()
    chunks: list[dict[str, Any]] = []
    for file in fixture["files"]:
        for page in file["pages"]:
            chunks.append(
                {
                    "chunk_id": f"{file['file_id']}-p{page['page']}",
                    "file_id": file["file_id"],
                    "filename": file["filename"],
                    "page": page["page"],
                    "section_path": None,
                    "text": page["text"],
                }
            )
    return chunks


def late_violation_text() -> str:
    late = load_scope_fixture()["late_text_violation"]
    filler = late["filler_sentence"]
    repeats = late["filler_min_chars"] // len(filler) + 1
    return filler * repeats + late["violation_sentence"]
