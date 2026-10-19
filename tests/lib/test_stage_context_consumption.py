"""Offline consumption/handoff checks; none establish model comprehension or AV QA."""
import json

import pytest

from lib import stage_context as sc
from lib.checkpoint import init_project
from scripts.stage_context import main
from tests.contracts.test_phase0_contracts import sample_artifact
from tests.lib.test_stage_context import make_project, script, decisions


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return str(path)


def test_full_selected_inline_content_readable_without_context_mutation(tmp_path):
    text = "prefix\n" + "á" * sc.TEXT_LIMIT + "\nIMPORTANT omitted ending"
    project = make_project(tmp_path, profile={"channel": "decor", "knowledge": [
        {"id": "long", "version": "1", "text": text, "scope": {"channel": ["decor"]}}]})
    before = sc.build_stage_context(project, "script")
    assert "IMPORTANT" not in next(i["content"] for i in before["items"] if i["id"] == "knowledge:long")
    page = sc.read_context_item(project, "script", "knowledge:long",
        context_hash=before["context_hash"], offset=sc.TEXT_LIMIT, limit=1000)
    assert "IMPORTANT omitted ending" in page["content"]
    assert page["next_offset"] is None
    assert page["sha256"] == sc.hashlib.sha256(text.encode()).hexdigest()
    assert sc.build_stage_context(project, "script") == before


def test_safe_file_reference_pages_and_stale_source(tmp_path):
    project = make_project(tmp_path, profile={"knowledge": [
        {"id": "source", "version": "1", "path": "long.md", "scope": {"stages": ["script"]}}]})
    (project / "knowledge").mkdir()
    path = project / "knowledge/long.md"
    path.write_text("begin" + "x" * sc.TEXT_LIMIT + "end", encoding="utf-8")
    context = sc.build_stage_context(project, "script")
    first = sc.read_context_item(project, "script", "knowledge:source", context_hash=context["context_hash"], limit=10)
    assert first["content"] == "beginxxxxx" and first["next_offset"] == 10
    path.write_text("changed source", encoding="utf-8")
    with pytest.raises(sc.StageContextError, match="stale context"):
        sc.read_context_item(project, "script", "knowledge:source", context_hash=context["context_hash"])


@pytest.mark.parametrize("offset,limit", [(-1, 1), (0, 0), (0, sc.TEXT_LIMIT + 1), (True, 2)])
def test_page_bounds_fail_visibly(tmp_path, offset, limit):
    project = make_project(tmp_path)
    context = sc.build_stage_context(project, "script")
    with pytest.raises(sc.StageContextError, match="offset"):
        sc.read_context_item(project, "script", "director", context_hash=context["context_hash"], offset=offset, limit=limit)


def test_item_reader_cannot_select_arbitrary_path(tmp_path):
    project = make_project(tmp_path)
    context = sc.build_stage_context(project, "script")
    with pytest.raises(sc.StageContextError, match="not selected"):
        sc.read_context_item(project, "script", "../../.env", context_hash=context["context_hash"])


def test_missing_selector_is_visible_and_does_not_guess_or_mutate(tmp_path, capsys):
    project = make_project(tmp_path, profile={"provider": "browser"})
    before = (project / "project.json").read_bytes()
    assert main(["--project", str(project), "inspect", "--stage", "script"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["consumption"]["automatic_feedback"] == "skipped_missing_content_selector"
    assert result["consumption"]["warnings"]
    assert result["context"]["items"][0]["content"]  # actual selected director, not hashes alone
    assert result["consumption"]["media_quality"] == "NOT_TESTED"
    assert (project / "project.json").read_bytes() == before
    assert main(["--project", str(project), "context", "--stage", "script"]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["stage"] == "script"  # compatible JSON
    assert "WARNING" in captured.err


def test_matching_feedback_is_selected_after_explicit_actual_profile(tmp_path):
    prior = make_project(tmp_path, "prior", profile={"channel": "small_space_big_mood"})
    feedback = sc.append_feedback(prior, {"text": "Keep the functional change visible",
        "scope": {"channel": ["small_space_big_mood"]}, "authority": "owner", "author": "fixture", "polarity": "negative"})
    current = make_project(tmp_path, profile={"provider": "browser"})
    old = sc.build_stage_context(current, "script")
    assert not old["discovery"]["feedback_projects"]
    sc.configure_profile(current, {"channel": "small_space_big_mood", "content_kind": "functional_household"})
    selected = sc.build_stage_context(current, "script")
    assert next(i for i in selected["items"] if i["id"] == "feedback:" + feedback["id"])["applicability"] == "applicable"
    assert not sc.consumption_status(selected)["warnings"]
    assert selected["context_hash"] != old["context_hash"]


def test_explicit_handoff_rejects_unchanged_template_and_preserves_no_completion(tmp_path, capsys):
    project = init_project("run", title="Offline fixture", pipeline_type="framework-smoke", pipeline_dir=tmp_path,
                           stage_context_profile={"content_kind": "offline_fixture"})
    artifact = sample_artifact("research_brief")
    context = sc.build_stage_context(project, "research")
    app = sc.application_template(context, artifact)
    base = ["--project", str(project), "handoff", "--stage", "research",
            "--artifacts", save(tmp_path / "artifacts.json", {"research_brief": artifact}),
            "--application", save(tmp_path / "application.json", app)]
    assert main(base) == 1
    assert "Invalid application decision" in capsys.readouterr().err
    assert not (project / "checkpoint_research.json").exists()
    assert sc._events(project, "application") == []
    app.update(reviewer="synthetic fixture witness", decisions=decisions(context))
    save(tmp_path / "application.json", app)
    assert main(base + ["--status", "completed", "--human-approved"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "completed"
    assert "no media-quality" in result["scope"]
    checkpoint = json.loads((project / "checkpoint_research.json").read_text())
    assert checkpoint["artifacts"]["research_brief"] == artifact


def test_script_handoff_needs_real_assessment_input_not_auto_pass(tmp_path, capsys):
    project = make_project(tmp_path)
    artifact = script()
    context = sc.build_stage_context(project, "script")
    app = sc.application_template(context, artifact)
    app.update(reviewer="synthetic witness", decisions=decisions(context))
    command = ["--project", str(project), "handoff", "--stage", "script",
               "--artifacts", save(tmp_path / "artifacts.json", {"script": artifact}),
               "--application", save(tmp_path / "application.json", app)]
    assert main(command) == 1
    assert "explicit --review" in capsys.readouterr().err
    review = sc.review_template(project, "script", artifact)
    command += ["--review", save(tmp_path / "review.json", review)]
    assert main(command) == 1
    assert "NOT_TESTED" in capsys.readouterr().err
    assert sc._events(project, "application") == []
    assert not (project / "checkpoint_script.json").exists()


def test_cli_read_item_returns_needed_content(tmp_path, capsys):
    project = make_project(tmp_path)
    context = sc.build_stage_context(project, "script")
    assert main(["--project", str(project), "read-item", "--stage", "script", "--id", "director",
                 "--context-hash", context["context_hash"], "--limit", "30"]) == 0
    page = json.loads(capsys.readouterr().out)
    assert page["content"] == context["items"][0]["content"][:30]
    assert page["authority"] == "trusted_director"
