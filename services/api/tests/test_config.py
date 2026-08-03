from __future__ import annotations

from app.core.config import Settings


def test_generation_pipeline_defaults_to_v1(monkeypatch):
    monkeypatch.delenv("GENERATION_PIPELINE", raising=False)

    assert Settings(_env_file=None).generation_pipeline == "v1"


def test_generation_pipeline_can_be_enabled_explicitly(monkeypatch):
    monkeypatch.setenv("GENERATION_PIPELINE", "v2")

    assert Settings(_env_file=None).generation_pipeline == "v2"
