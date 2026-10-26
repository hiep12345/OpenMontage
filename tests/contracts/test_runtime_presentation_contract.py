"""Enforce runtime authority and unresolved-choice guidance across consumers.

For every pipeline in `pipeline_defs/`, the planning-stage skill (proposal
or idea) MUST preserve exact authorized runtime choices, compare viable
alternatives when the choice is unresolved, and surface actual constraints.

This test prevents a new pipeline from being added without the conversation
contract. A fresh-session agent that reads a pipeline's planning skill and
finds no runtime guidance will silently default to Remotion — which is the
exact failure mode this contract prevents.

See:
- AGENT_GUIDE.md → "Composition Runtime Selection"
- skills/core/hyperframes.md → "Runtime authority and unresolved choices"
- skills/meta/reviewer.md → finding #6
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml


ROOT = Path(__file__).resolve().parent.parent.parent
PIPELINE_DIR = ROOT / "pipeline_defs"
SKILLS_DIR = ROOT / "skills"

# Tokens we expect in any compliant planning-stage skill. A skill needs AT
# LEAST one from each group to pass. The groups are intentionally loose —
# this test is a tripwire, not a style enforcer.
_REQUIRED_RUNTIME_TOKENS = [
    "render_runtime",      # the field name must appear
    "hyperframes",         # the alternative runtime must be named
]
# Accept authority preservation as well as unresolved-choice conversation guidance.
_CONVERSATION_TOKENS = [
    "present both",
    "Present Both",
    "PRESENT BOTH",
    "render_runtime_selection",  # pointing at the decision_log category
    "exact authorized",
    "choice is unresolved",
]


def _covers_runtime_contract(body: str) -> bool:
    """Tripwire for new planning consumers, without requiring a menu ritual."""
    normalized = " ".join(body.lower().split())
    return all(token in normalized for token in _REQUIRED_RUNTIME_TOKENS) and any(
        token.lower() in normalized for token in _CONVERSATION_TOKENS
    )


def _planning_stages(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Return every 'proposal' or 'idea' stage (a pipeline may have one or both)."""
    out: list[dict[str, Any]] = []
    for stage in manifest.get("stages", []):
        if stage.get("name") in {"proposal", "idea"}:
            out.append(stage)
    return out


def _load_manifest(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_skill(skill_ref: str) -> tuple[Path, str]:
    """Resolve a manifest `skill:` string to its markdown path + contents."""
    candidate = SKILLS_DIR / f"{skill_ref}.md"
    assert candidate.is_file(), (
        f"Manifest references skill {skill_ref!r} but {candidate} does not exist."
    )
    return candidate, candidate.read_text(encoding="utf-8")


ALL_MANIFESTS = sorted(PIPELINE_DIR.glob("*.yaml"))
assert ALL_MANIFESTS, "No pipeline manifests found"

# Test-only pipelines that don't compose final video go on this list with
# an explicit reason. Everything else is required to follow the contract.
_EXCLUDED_PIPELINES = {
    "framework-smoke": "minimal 2-stage smoke test, no compose stage",
}


@pytest.mark.parametrize(
    "manifest_path",
    [p for p in ALL_MANIFESTS if p.stem not in _EXCLUDED_PIPELINES],
    ids=lambda p: p.stem,
)
def test_planning_skill_mentions_runtime_contract(manifest_path: Path):
    """Every pipeline that reaches compose must have runtime guidance in its
    planning-stage skill."""
    manifest = _load_manifest(manifest_path)
    planning = _planning_stages(manifest)
    assert planning, (
        f"Pipeline {manifest_path.stem} has no 'proposal' or 'idea' stage. "
        f"Add one, or add this pipeline to _EXCLUDED_PIPELINES with a reason."
    )

    # At least ONE of the planning skills in this pipeline must cover the
    # contract (pipelines with both proposal+idea only need one to carry it).
    matched_skill: str | None = None
    matched_why: dict[str, bool] = {}
    for stage in planning:
        skill_ref = stage.get("skill")
        if not skill_ref:
            continue
        _, body = _load_skill(skill_ref)
        covers_conversation = _covers_runtime_contract(body)
        if covers_conversation:
            matched_skill = skill_ref
            matched_why = {
                "mentions_render_runtime": "render_runtime" in body,
                "mentions_hyperframes": "hyperframes" in body,
                "conversation_token_found": covers_conversation,
            }
            break

    assert matched_skill, (
        f"Pipeline {manifest_path.stem}: no planning-stage skill covers the "
        f"runtime-selection contract. Each pipeline's proposal- or idea-director "
        f"must discuss render_runtime, name hyperframes, and cover exact authority, "
        f"unresolved alternatives or a `render_runtime_selection` decision. A fresh-session agent reading "
        f"this pipeline's plan would silently default to Remotion. Fix the skill "
        f"that drives the planning stage."
    )


@pytest.mark.parametrize(
    "manifest_path",
    [p for p in ALL_MANIFESTS if p.stem not in _EXCLUDED_PIPELINES],
    ids=lambda p: p.stem,
)
def test_compose_stage_references_runtime_routing(manifest_path: Path):
    """Compose stage's director skill must also cover runtime routing, so
    that even a pipeline whose planning skill somehow misses the contract
    cannot silently render under the wrong runtime."""
    manifest = _load_manifest(manifest_path)
    compose_stage = next(
        (s for s in manifest.get("stages", []) if s.get("name") == "compose"),
        None,
    )
    if compose_stage is None:
        # Some pipelines use alternate terminal stages; skip.
        pytest.skip(f"{manifest_path.stem} has no 'compose' stage")

    skill_ref = compose_stage.get("skill")
    assert skill_ref, f"{manifest_path.stem} compose stage has no skill reference"
    _, body = _load_skill(skill_ref)
    # Compose-directors must at minimum mention render_runtime AND either
    # route by runtime or surface a hard constraint (HyperFrames deferred).
    assert "render_runtime" in body, (
        f"{skill_ref} does not mention render_runtime. Compose MUST route by "
        f"render_runtime; without this instruction the agent will fall back to "
        f"the tool's legacy behavior (silently pick Remotion)."
    )
    # Must also mention HyperFrames explicitly so a reviewer can tell the
    # author considered it and either enabled or rejected it with reason.
    assert re.search(r"hyperframes|HyperFrames", body), (
        f"{skill_ref} does not mention HyperFrames at all. Even on deferred "
        f"pipelines, the compose-director must name HyperFrames so the agent "
        f"can surface the constraint to the user rather than silently pick "
        f"Remotion. See documentary-montage or talking-head compose-director "
        f"for the deferred-pipeline template."
    )


def test_agent_guide_preserves_authorized_runtime_and_resolves_real_choices():
    """Runtime discovery resolves missing choices while preserving exact authority."""
    guide = (ROOT / "AGENT_GUIDE.md").read_text(encoding="utf-8")
    runtime = guide.split("### Composition Runtime Selection\n", 1)[1].split("\n### ", 1)[0]
    assert "Preserve a runtime already selected by the user" in runtime
    assert "including a new actionable brief with exact choices" in runtime
    assert 'video_compose.get_info()["render_engines"]' in runtime
    assert "concrete blocker, not permission to silently substitute" in runtime
    assert "When runtime choice is unresolved" in runtime
    assert "Present both Remotion and" in runtime
    assert "when they are genuine alternatives" in runtime
    assert "no full\nmenu or repeat approval" in runtime
    assert "manifest's approval gates" in runtime
    assert "Material changes require the applicable new authorization" in runtime


def test_reviewer_distinguishes_exact_authority_from_silent_default_and_swap():
    """Review guards genuine defaults/swaps without reopening authorized choices."""
    body = (SKILLS_DIR / "meta" / "reviewer.md").read_text(encoding="utf-8")
    selection = body.split("6. **Runtime authority and unresolved choices**", 1)[1].split(
        "\n## Delivery Promise Review", 1
    )[0]
    assert "a single recorded option is valid" in selection
    assert "including a new actionable brief with exact choices" in selection
    assert "Do not reopen an authorized choice" in selection
    assert "When runtime choice is unresolved" in selection
    assert "both viable for the brief" in selection
    assert "Silently defaulting in this case → **CRITICAL**" in selection
    assert "concrete blocker; silent substitution → **CRITICAL**" in selection
    assert "log entry alone does not approve a material change" in selection
    assert "manifest's proposal/asset approval gates" in selection
    assert "authorized spend, material-change approval and separate publication approval" in selection


@pytest.mark.parametrize(
    "body,expected",
    [
        ("Production planning with no runtime guidance", False),
        ("render_runtime only", False),
        ("render_runtime hyperframes", False),
        ("Preserve an exact authorized render_runtime, including hyperframes", True),
        ("render_runtime: remotion or hyperframes when choice is unresolved", True),
        ("render_runtime hyperframes: record render_runtime_selection", True),
    ],
)
def test_planning_tripwire_rejects_missing_guidance_and_accepts_authority(body, expected):
    assert _covers_runtime_contract(body) is expected


def _runtime_consumers() -> list[Path]:
    consumers = [
        SKILLS_DIR / "core/hyperframes.md",
        SKILLS_DIR / "meta/animation-runtime-selector.md",
        SKILLS_DIR / "meta/video-reference-analyst.md",
    ]
    for manifest_path in ALL_MANIFESTS:
        if manifest_path.stem in _EXCLUDED_PIPELINES:
            continue
        manifest = _load_manifest(manifest_path)
        for stage in _planning_stages(manifest):
            path, body = _load_skill(stage["skill"])
            if _covers_runtime_contract(body):
                consumers.append(path)
        for stage in manifest.get("stages", []):
            if stage.get("name") == "compose":
                consumers.append(_load_skill(stage["skill"])[0])
    return sorted(set(consumers))


@pytest.mark.parametrize("path", _runtime_consumers(), ids=lambda p: p.relative_to(ROOT).as_posix())
def test_actual_runtime_consumers_preserve_authority_blockers_and_gates(path):
    """Canonical producer and real manifest consumers must agree on authority."""
    body = " ".join(path.read_text(encoding="utf-8").split())
    assert '"Composition Runtime Selection"' in body
    assert "exact authorized `render_runtime`" in body
    assert "concrete blocker" in body
    assert "publication approval" in body
    assert "authorized spend" in body
    assert "proposal/asset" in body
    if path.name != "compose-director.md":
        assert "including a new actionable brief with exact choices" in body
        assert "choice is unresolved" in body
        assert "both are viable" in body
        assert "without a runtime menu or repeat approval" in body


def test_runtime_consumers_do_not_reference_retired_always_both_rule():
    # Traverse every actual manifest consumer, not only files that already pass
    # a token heuristic (which would hide stale/noncompliant consumers).
    manifest_consumers = [
        _load_skill(stage["skill"])[0]
        for manifest_path in ALL_MANIFESTS
        for stage in _load_manifest(manifest_path).get("stages", []) if stage.get("skill")
    ]
    paths = sorted(set(manifest_consumers + list((SKILLS_DIR / "pipelines").rglob("*.md")) + _runtime_consumers() + [
        SKILLS_DIR / "meta/onboarding.md",
        SKILLS_DIR / "meta/reviewer.md",
        SKILLS_DIR / "pipelines/character-animation/executive-producer.md",
    ]))
    for path in paths:
        # The retired heading also survived in line-wrapped references. Compare
        # prose whitespace so a wrapped stale rule cannot escape this traversal.
        body = " ".join(path.read_text(encoding="utf-8").split())
        assert "Present Both Composition Runtimes" not in body, path
        assert "when both were available is a CRITICAL" not in body, path
        assert "the constraint does NOT skip the conversation" not in body, path
        assert "the lock to remotion is NOT an excuse" not in body, path
        assert not re.search(r"only viable (?:choice|runtime).*OK to proceed\?", body), path


def test_character_renderer_handoff_cannot_override_authorized_runtime():
    body = (SKILLS_DIR / "pipelines/character-animation/compose-director.md").read_text(encoding="utf-8")
    assert "For the approved HyperFrames path" in body
    assert "do not let the renderer overwrite runtime authority" in body
    assert "HyperFrames renderer does not establish Remotion parity" in body
    proposal = (SKILLS_DIR / "pipelines/character-animation/proposal-director.md").read_text(encoding="utf-8")
    assert "Do not batch-generate all assets until this sample is approved" in proposal


def test_talking_head_degraded_caption_fallback_requires_authorization():
    body = (SKILLS_DIR / "pipelines/talking-head/compose-director.md").read_text(encoding="utf-8")
    assert "block the locked Remotion path before invoking `remotion_caption_burn`" in body
    assert "After applicable material-change approval and a logged `render_runtime_selection` decision" in body
