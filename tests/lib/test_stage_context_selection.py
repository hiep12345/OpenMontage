"""Selection contracts, independent of optional owner production integrations."""
from copy import deepcopy

import pytest

from lib.stage_context_selection import (
    CONTEXT_VERSIONS, DEFAULT_CONTEXT_VERSION, has_content_scope,
    production_guidance, stage_inputs, stage_manifest,
)
from lib.pipeline_loader import load_pipeline


CANONICAL = {"script": "script", "scene_plan": "scene_plan", "compose": "render_report"}


@pytest.mark.parametrize("stage", ["research", "proposal", "script", "scene_plan", "assets", "edit", "compose", "publish"])
def test_cinematic_selection_preserves_pipeline_contract_and_current_stage(stage):
    original = load_pipeline("cinematic")
    before = deepcopy(original)
    selected = stage_manifest(original, stage)
    assert selected["stages"] == [next(row for row in original["stages"] if row["name"] == stage)]
    assert [row["name"] for row in selected["stage_order"]] == [row["name"] for row in original["stages"]]
    for key, value in original.items():
        if key != "stages":
            assert selected[key] == value
    for row, source in zip(selected["stage_order"], original["stages"]):
        for key in ("checkpoint_required", "human_approval_default"):
            if key in source:
                assert row[key] == source[key]
    selected["stages"][0]["name"] = "changed"
    assert original == before


def test_compose_retains_approved_runtime_proposal_and_frozen_decisions():
    selected = stage_inputs(load_pipeline("cinematic"), "compose", CANONICAL)
    assert selected["proposal_packet"] == "proposal"
    assert selected["decision_log"] == "proposal"
    assert selected["edit_decisions"] == "edit"
    assert selected["asset_manifest"] == "assets"
    assert "research_brief" not in selected
    assert "render_report" not in selected


def test_selected_secondary_outputs_resolve_to_latest_predecessor():
    manifest = {"stages": [
        {"name": "rig", "produces": ["rig", "pose_library"]},
        {"name": "poses", "produces": ["pose_library"]},
        {"name": "scene_plan", "required_artifacts_in": ["rig", "pose_library"], "produces": ["scene_plan"]},
    ]}
    selected = stage_inputs(manifest, "scene_plan", CANONICAL)
    assert selected["rig"] == "rig"
    assert selected["pose_library"] == "poses"
    assert "scene_plan" not in selected


def test_current_output_cannot_be_its_own_context():
    selected = stage_inputs(load_pipeline("cinematic"), "proposal", CANONICAL)
    assert "proposal_packet" not in selected
    assert "decision_log" not in selected
    assert selected["research_brief"] == "research"


@pytest.mark.parametrize("profile,expected", [
    ({}, False), ({"provider": "x", "model": "y"}, False),
    ({"tags": []}, False), ({"channel": "home"}, True),
    ({"content_kind": "household"}, True), ({"video_format": "reel"}, True),
    ({"tags": ["reading"]}, True),
])
def test_cross_run_feedback_requires_content_selector(profile, expected):
    assert has_content_scope(profile) is expected


def test_guidance_preserves_complete_binding_section():
    text = "# Project\n\nRouting\n\n## Binding production boundaries\n\n- Spend needs approval.\n- Keep receipts.\n\n## Recovery\n\nOther text.\n"
    assert production_guidance(text) == "## Binding production boundaries\n\n- Spend needs approval.\n- Keep receipts.\n\n"


@pytest.mark.parametrize("text", ["# Project\n- Keep approvals.\n", "", "## Other heading\nRules.\n"])
def test_unknown_guidance_layout_falls_back_to_full_source(text):
    assert production_guidance(text) == text


def test_default_and_legacy_versions_remain_distinct():
    assert DEFAULT_CONTEXT_VERSION == "1.1"
    assert CONTEXT_VERSIONS == {"1.0", "1.1"}
