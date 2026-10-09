from pathlib import Path
import re

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_music_plans_discover_all_music_capabilities() -> None:
    instruction_files = [
        "AGENT_GUIDE.md",
        "skills/pipelines/cinematic/idea-director.md",
        "skills/pipelines/cinematic/proposal-director.md",
        "skills/pipelines/documentary-montage/idea-director.md",
        "skills/pipelines/explainer/proposal-director.md",
    ]

    for relative_path in instruction_files:
        text = _read(relative_path)
        for capability in ("music_library", "music_search", "music_generation"):
            assert f'get_by_capability("{capability}")' in text, (
                f"{relative_path} omits the {capability!r} music source"
            )


def test_explainer_directors_do_not_reference_fictitious_submit_functions() -> None:
    for stage in ("idea", "script", "scene"):
        text = _read(f"skills/pipelines/explainer/{stage}-director.md")
        assert "handle_explainer_" not in text


PLATFORM_POINTERS = (
    "CLAUDE.md",
    "CODEX.md",
    "CURSOR.md",
    "COPILOT.md",
    ".github/copilot-instructions.md",
    ".cursor/rules/openmontage.mdc",
)


def _guide_section(title: str) -> str:
    guide = _read("AGENT_GUIDE.md")
    match = re.search(
        rf"^#{{2,3}} {re.escape(title)}\n(.*?)(?=^#{{2,3}} |\Z)",
        guide,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match, f"Router references missing guide section: {title}"
    return match.group(1)


@pytest.mark.parametrize("relative_path", ("AGENTS.md", *PLATFORM_POINTERS))
def test_platform_entrypoints_route_without_unconditional_full_guide_reads(
    relative_path: str,
) -> None:
    text = _read(relative_path)
    assert "AGENT_GUIDE.md" in text  # supporting reference stays discoverable
    assert not re.search(
        r"before responding to (?:ANY|EVERY) user message", text, re.IGNORECASE
    )
    if relative_path != "AGENTS.md":
        assert "AGENTS.md" in text, f"{relative_path} bypasses the task router"
    # Every Markdown link in a platform wrapper must resolve from its directory.
    for target in re.findall(r"\]\(([^)]+\.md)\)", text):
        assert (REPO_ROOT / relative_path).parent.joinpath(target).is_file()


def test_router_distinguishes_inspection_resume_and_new_production() -> None:
    router = _read("AGENTS.md")
    routes = [line for line in router.splitlines() if line.startswith("| ")]
    maintenance = next(line for line in routes if "Maintenance, debugging" in line)
    assert "Do not start production" in maintenance
    resume = next(line for line in routes if "Exact approved resume" in line)
    assert "Approved Production Resume" in resume
    assert "checkpoints, canonical artifacts and decision log" in resume
    production = next(line for line in routes if "New actionable" in line)
    assert "Run preflight" in production
    assert "proposal approvals before generation" in production
    onboarding = next(line for line in routes if "Vague first request" in line)
    assert "skills/meta/onboarding.md" in onboarding
    assert "does not authorize generation or spend" in onboarding
    reference = next(line for line in routes if "supplied as inspiration" in line)
    assert "video-reference-analyst.md" in reference
    assert "Source footage" in reference and "source_media_review" in reference
    for section in re.findall(r"\*\*([^*]+)\*\*", router):
        _guide_section(section)


def test_exact_resume_reuses_choices_without_bypassing_authority() -> None:
    resume = _guide_section("Approved Production Resume")
    for required in (
        "project.json",
        "pipeline_defs/",
        "decision_log.json",
        "get_next_stage(pipeline_dir, project_id, pipeline_type)",
        "metadata.partial_progress",
        "remaining authorized budget",
        "Do not infer missing approval",
        "only the exact gate/scope",
        "awaiting_human",
        "approval_policy",
        "Assets approval precedes full render",
        "current execution conditions",
        "additional unapproved",
        "appended decision-log entry before execution",
        "No resume approval by itself authorizes publishing",
        "FAIL or NOT TESTED",
    ):
        assert required in resume
    assert "Do not\n   repeat onboarding, generic provider/setup menus" in resume
    assert "not an unchanged resume" in resume
    assert "do not overwrite history" in resume
    assert "current\n   stage director" in resume and "`agent_skills`" in resume


def test_conditional_loading_preserves_production_and_caption_gates() -> None:
    router = _read("AGENTS.md")
    for required in (
        "All video production uses a pipeline",
        "manifest-selected director skill",
        "validate against their schemas",
        "human_approval_default",
        "human_approved=True",
        "Assets approval precedes full render",
        "Production approval does not authorize publishing",
        "docs/caption-link-quality.md",
        "exact caption/package bytes",
        "asset, source and website release",
        "FAIL or NOT TESTED",
    ):
        assert required in router
    human_gate = _guide_section("Human Checkpoint Protocol")
    assert "manifest value is binding" in human_gate
    assert "END YOUR TURN" in human_gate
    assert "Approval is per-gate" in human_gate
    caption_gate = _guide_section("Caption website acceptance")
    assert "exact source formula/media match" in caption_gate
    assert "FAIL or NOT TESTED blocks handoff readiness" in caption_gate
    runtime_gate = _guide_section("Present Both Composition Runtimes (HARD RULE)")
    assert "MUST present both options" in runtime_gate
    assert "wait for explicit user approval" in runtime_gate
    assert "retains the recorded runtime and shortlist" in runtime_gate
    delivery_gate = _guide_section("Hub-bound MT episode identity")
    assert "LOCAL_ONLY" in delivery_gate
    assert "still requires novelty evidence reads and normal production" in delivery_gate
    assert "does not authorize Hub delivery or publishing" in delivery_gate
    assert "intent cannot\nlater acquire a Hub plan" in delivery_gate
