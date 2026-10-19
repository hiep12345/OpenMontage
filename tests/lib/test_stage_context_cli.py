import json
import os
from pathlib import Path
import subprocess
import sys

from scripts.stage_context import main
from tests.lib.test_stage_context import make_project, script, decisions


def test_cli_stage_entry_and_templates_never_autopass(tmp_path, capsys):
    project = make_project(tmp_path)
    artifact = tmp_path / "script.json"
    artifact.write_text(json.dumps(script()))
    base = ["--project", str(project)]
    assert main(base + ["enter", "--stage", "script"]) == 0
    context = json.loads(capsys.readouterr().out)
    assert context["stage"] == "script"
    assert main(base + ["review-template", "--stage", "script", "--artifact", str(artifact)]) == 0
    template = json.loads(capsys.readouterr().out)
    assert all(check["status"] == "NOT_TESTED" for check in template["checks"])
    assert main(base + ["application-template", "--stage", "script", "--artifact", str(artifact)]) == 0
    packet = json.loads(capsys.readouterr().out)
    assert all(choice["decision"] == "NOT_TESTED" for choice in packet["decisions"])
    packet_file = tmp_path / "application.json"
    packet_file.write_text(json.dumps(packet))
    command = base + ["record-application", "--stage", "script", "--artifact", str(artifact), "--packet", str(packet_file)]
    assert main(command) == 1
    assert "Invalid application decision" in capsys.readouterr().err
    packet.update(decisions=decisions(context), reviewer="fixture reviewer")
    packet_file.write_text(json.dumps(packet))
    assert main(command) == 0
    assert json.loads(capsys.readouterr().out)["artifact_hash"] == packet["artifact_hash"]


def test_cli_feedback_and_configuration_survive_next_invocation(tmp_path, capsys):
    project = make_project(tmp_path)
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({"content_kind": "abstract"}))
    base = ["--project", str(project)]
    assert main(base + ["configure", "--profile", str(profile)]) == 0
    assert json.loads(capsys.readouterr().out)["profile"]["content_kind"] == "abstract"
    packet = tmp_path / "feedback.json"
    packet.write_text(json.dumps({"text": "The rhythm needs a clear landing", "scope": {"content_kind": ["abstract"]}, "author": "owner", "authority": "owner", "polarity": "negative"}))
    assert main(base + ["feedback", "--packet", str(packet)]) == 0
    record = json.loads(capsys.readouterr().out)
    assert main(base + ["feedback-history"]) == 0
    assert json.loads(capsys.readouterr().out) == [record]


def test_subprocess_cli_emits_utf8_even_when_windows_encoding_is_legacy(tmp_path):
    project = make_project(tmp_path)
    command = Path(__file__).resolve().parents[2] / "scripts" / "stage_context.py"
    result = subprocess.run([sys.executable, str(command), "--project", str(project), "context", "--stage", "script"],
                            env={**os.environ, "PYTHONIOENCODING": "cp1252"}, capture_output=True)
    assert result.returncode == 0, result.stderr.decode("utf-8")
    context = json.loads(result.stdout.decode("utf-8"))
    assert any("→" in item["content"] or any(ord(character) > 255 for character in item["content"]) for item in context["items"])
