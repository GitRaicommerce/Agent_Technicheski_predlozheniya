"""Runtime model policy: which model and reasoning effort each LLM role uses.

Every LLM call in the application passes an ``agent`` label. The label maps to
a *role*; the role maps to a *profile* (provider, model, reasoning effort,
criticality, optional quality-equivalent fallback). Choosing a model is
therefore an explicit, persisted decision per role — not a side effect of one
global default.

Rules (IMPLEMENTATION_PLAN_GPT6_SOL.md §3, cards K-24/K-22):
- Unknown labels are an explicit error, never an implicit default model.
- Critical roles never silently fall back to a weaker model. A fallback is used
  only when the policy explicitly configures one for that role.
- Effort strings are validated; ``ultra`` is a Codex mode, not an API value.
- Defaults are evaluation targets, not measured proof of sufficiency. They can
  be overridden per role with the ``LLM_ROLE_POLICY`` JSON setting.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from typing import Any

from app.core.config import settings

POLICY_VERSION_DEFAULT = "2026-09-25.1"

# Effort values accepted by the reasoning API. "none" is supported by Sol-class
# models only; "ultra" is deliberately absent (Codex multi-agent mode).
EFFORT_VALUES = {"none", "low", "medium", "high", "xhigh", "max"}
EFFORT_NONE_CAPABLE_PREFIXES = ("gpt-6-sol",)


class ModelPolicyError(ValueError):
    """Invalid policy configuration or an unknown role label."""


@dataclass(frozen=True)
class ModelProfile:
    role: str
    provider: str
    model: str
    effort: str | None
    critical: bool
    fallback_provider: str | None = None
    fallback_model: str | None = None
    fallback_effort: str | None = None

    def as_record(self) -> dict[str, Any]:
        return asdict(self)


# agent label → role. Keep in sync with every ``llm_gateway.call(agent=...)``.
ROLE_BY_AGENT: dict[str, str] = {
    "understanding_map": "understanding",
    "understanding_proposal_audit": "understanding",
    "content_plan_author": "plan_author",
    "plan_audit_extract": "plan_audit",
    "plan_audit_compare": "plan_audit",
    "drafting": "drafting_routine",
    "drafting_routine": "drafting_routine",
    "drafting_complex": "drafting_complex",
    # Repairs inherit the writer's class; callers pass the writer's role via
    # ``role_override``. Without an override they use the routine writer.
    "drafting_calendar_guard": "drafting_routine",
    # Optional editorial assembly produces new, unverified text: explicit
    # author profile (WP-08 removes it from the standard finalization path).
    "drafting_v2_assembly": "drafting_complex",
    "criteria_verifier": "verification",
    "consistency_claims": "verification",
    "consistency_conflicts": "verification",
    "verifier": "verification",
    "schedule": "binding_reading",
    "legislation": "binding_reading",
    "orchestrator": "routing",
    "examples": "routing",
    "tender_struct": "legacy_plan",
}

ASTRA = "gpt-6-astra"
SOL = "gpt-6-sol"

_DEFAULT_PROFILES: dict[str, dict[str, Any]] = {
    "understanding": {"model": ASTRA, "effort": "xhigh", "critical": True},
    "plan_author": {"model": ASTRA, "effort": "xhigh", "critical": True},
    "plan_audit": {"model": ASTRA, "effort": "xhigh", "critical": True},
    "drafting_routine": {"model": SOL, "effort": "high", "critical": False},
    "drafting_complex": {"model": ASTRA, "effort": "xhigh", "critical": True},
    "verification": {"model": ASTRA, "effort": "xhigh", "critical": True},
    "binding_reading": {"model": ASTRA, "effort": "high", "critical": True},
    "routing": {"model": SOL, "effort": "medium", "critical": False},
    "legacy_plan": {"model": ASTRA, "effort": "xhigh", "critical": True},
}


def policy_version() -> str:
    return settings.llm_policy_version or POLICY_VERSION_DEFAULT


def _validate_effort(model: str, effort: str | None, *, role: str) -> None:
    if effort is None:
        return
    if effort not in EFFORT_VALUES:
        raise ModelPolicyError(
            f"Невалидно reasoning effort '{effort}' за роля '{role}'. "
            f"Позволени: {', '.join(sorted(EFFORT_VALUES))}."
        )
    if effort == "none" and not model.lower().startswith(
        EFFORT_NONE_CAPABLE_PREFIXES
    ):
        raise ModelPolicyError(
            f"Effort 'none' не се поддържа от модел '{model}' (роля '{role}')."
        )


def _overrides() -> dict[str, dict[str, Any]]:
    raw = (settings.llm_role_policy or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ModelPolicyError(f"LLM_ROLE_POLICY не е валиден JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ModelPolicyError("LLM_ROLE_POLICY трябва да е JSON обект по роли.")
    for role, value in parsed.items():
        if role not in _DEFAULT_PROFILES:
            raise ModelPolicyError(f"LLM_ROLE_POLICY съдържа непозната роля '{role}'.")
        if not isinstance(value, dict):
            raise ModelPolicyError(f"LLM_ROLE_POLICY['{role}'] трябва да е обект.")
    return parsed


def policy_mode() -> str:
    mode = (settings.llm_role_policy_mode or "legacy").strip().lower()
    if mode not in {"legacy", "roles"}:
        raise ModelPolicyError(
            f"LLM_ROLE_POLICY_MODE трябва да е 'legacy' или 'roles', не '{mode}'."
        )
    return mode


def _base_profile(role: str) -> dict[str, Any]:
    if policy_mode() == "roles":
        return dict(_DEFAULT_PROFILES[role])
    # Legacy mode reproduces the pre-policy behavior exactly: one global model,
    # no reasoning-effort parameter, the global fallback for every role.
    return {
        "model": settings.llm_default_model,
        "effort": None,
        "critical": False,
    }


def profile_for_role(role: str) -> ModelProfile:
    if role not in _DEFAULT_PROFILES:
        raise ModelPolicyError(f"Непозната LLM роля '{role}'.")
    merged: dict[str, Any] = {
        "provider": settings.llm_default_provider,
        **_base_profile(role),
        # Explicit per-role overrides apply in both modes, which allows a
        # gradual, role-by-role rollout.
        **_overrides().get(role, {}),
    }
    profile = ModelProfile(
        role=role,
        provider=str(merged["provider"]),
        model=str(merged["model"]),
        effort=merged.get("effort"),
        critical=bool(merged.get("critical", False)),
        fallback_provider=merged.get("fallback_provider"),
        fallback_model=merged.get("fallback_model"),
        fallback_effort=merged.get("fallback_effort"),
    )
    _validate_effort(profile.model, profile.effort, role=role)
    if profile.fallback_model:
        _validate_effort(profile.fallback_model, profile.fallback_effort, role=role)
    if profile.critical:
        return profile
    # Non-critical roles keep the legacy globally configured fallback unless
    # the policy sets an explicit one.
    if not profile.fallback_model and settings.llm_fallback_model:
        profile = replace(
            profile,
            fallback_provider=settings.llm_fallback_provider or None,
            fallback_model=settings.llm_fallback_model,
            fallback_effort=None,
        )
    return profile


def resolve_profile(agent: str, role_override: str | None = None) -> ModelProfile:
    """Profile for an agent label. Unknown labels are an explicit error."""
    if role_override:
        return profile_for_role(role_override)
    role = ROLE_BY_AGENT.get(agent or "")
    if role is None:
        raise ModelPolicyError(
            f"LLM извикване с непознат agent етикет '{agent}'. Добавете го в "
            "ROLE_BY_AGENT, за да има изрично избран модел."
        )
    return profile_for_role(role)


def explicit_profile(provider: str, model: str, effort: str | None = None) -> ModelProfile:
    """Ad-hoc profile for callers that pass provider/model explicitly."""
    _validate_effort(model, effort, role="explicit")
    return ModelProfile(
        role="explicit",
        provider=provider,
        model=model,
        effort=effort,
        critical=False,
        fallback_provider=settings.llm_fallback_provider or None,
        fallback_model=settings.llm_fallback_model or None,
    )


def validate_policy() -> dict[str, dict[str, Any]]:
    """Resolve every role once; raises on any invalid configuration."""
    return {role: profile_for_role(role).as_record() for role in _DEFAULT_PROFILES}
