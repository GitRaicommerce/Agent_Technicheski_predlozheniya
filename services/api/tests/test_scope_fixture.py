"""Integrity checks for the shared scope-preservation fixture."""

from __future__ import annotations

from tests.scope_fixture import fixture_chunks, late_violation_text, load_scope_fixture


def test_every_expected_quote_exists_verbatim_on_its_page():
    fixture = load_scope_fixture()
    pages = {
        (file["file_id"], page["page"]): page["text"]
        for file in fixture["files"]
        for page in file["pages"]
    }
    for entry in fixture["expected_requirements"] + fixture["expected_exclusions"]:
        text = pages[(entry["file_id"], entry["page"])]
        assert entry["quote"] in text, entry["key"]


def test_fixture_covers_every_required_acceptance_case():
    fixture = load_scope_fixture()
    kinds = {entry["kind"] for entry in fixture["expected_requirements"]}
    assert {"cross_ref", "content", "prohibition", "obligation", "evaluation"} <= kinds
    assert any(entry.get("parent_key") for entry in fixture["expected_requirements"])
    last_pages = {
        file["file_id"]: max(page["page"] for page in file["pages"])
        for file in fixture["files"]
    }
    assert any(
        entry["page"] == last_pages[entry["file_id"]]
        for entry in fixture["expected_requirements"]
    )
    assert any(len(entry["quote"]) < 20 for entry in fixture["expected_requirements"])
    assert fixture["expected_exclusions"][0]["scope"] == "qualification_admin"
    assert fixture["unsupported_commitment"]["supported_by_source"] is False


def test_late_violation_sits_beyond_60000_characters():
    text = late_violation_text()
    violation = load_scope_fixture()["late_text_violation"]["violation_sentence"]
    assert text.index(violation) >= 60000


def test_fixture_chunks_are_one_per_page():
    chunks = fixture_chunks()
    assert len(chunks) == 5
    assert len({chunk["chunk_id"] for chunk in chunks}) == 5
