from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

CANONICAL = ROOT / "Agent.md"
BRIDGES = {
    "AGENTS.md": ROOT / "AGENTS.md",
    "CLAUDE.md": ROOT / "CLAUDE.md",
}

REQUIRED_AGENT_SECTIONS = (
    "## Project Purpose",
    "## Repository Map",
    "## Required Startup Path",
    "## Required Checks",
    "## Database And Migrations",
    "## Coding Style",
    "## Git Discipline",
    "## Documentation Rules",
    "## Stability Definition",
    "## Safety Rules",
    "## Executor Notes",
)

REQUIRED_AGENT_TERMS = (
    "Codex",
    "Claude Code",
    "Codespaces",
    "docker compose -f docker-compose.dev.yml",
    "scripts\\start-dev.ps1",
    "services/api",
    "apps/web",
    "docs/ENGINEERING_OVERVIEW.md",
    "Do not edit it manually.",
    "Do not revert unrelated changes.",
)

BRIDGE_REQUIRED_PHRASES = (
    "Agent.md",
    "canonical operating guide",
)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise AssertionError(f"{path.relative_to(ROOT)} must be valid UTF-8") from exc


def _assert_exists(path: Path) -> None:
    if not path.is_file():
        raise AssertionError(f"Missing required agent guide file: {path.relative_to(ROOT)}")


def _assert_contains(text: str, path: Path, required: tuple[str, ...]) -> None:
    missing = [item for item in required if item not in text]
    if missing:
        rel = path.relative_to(ROOT)
        raise AssertionError(f"{rel} is missing required content: {', '.join(missing)}")


def check_agent_guides() -> None:
    _assert_exists(CANONICAL)
    agent_text = _read(CANONICAL)
    _assert_contains(agent_text, CANONICAL, REQUIRED_AGENT_SECTIONS)
    _assert_contains(agent_text, CANONICAL, REQUIRED_AGENT_TERMS)

    for name, path in BRIDGES.items():
        _assert_exists(path)
        bridge_text = _read(path)
        _assert_contains(bridge_text, path, BRIDGE_REQUIRED_PHRASES)
        if len(bridge_text.split()) > 80:
            raise AssertionError(
                f"{name} should stay a short bridge to Agent.md, not a second source of truth"
            )


def main() -> int:
    try:
        check_agent_guides()
    except AssertionError as exc:
        print(f"Agent guide check failed: {exc}", file=sys.stderr)
        return 1

    print("Agent guide check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
