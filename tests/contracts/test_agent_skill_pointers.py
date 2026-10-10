"""Every `agent_skills` pointer a tool advertises must resolve to a real skill.

AGENT_GUIDE.md makes Layer 3 mandatory:

    Every generation tool has an `agent_skills` field listing its Layer 3
    skills. [...] Read them before writing prompts. Layer 3 is not optional.

A pointer that resolves to nothing cannot be read, so the mandated step is
silently skipped — and `tts_selector` republishes the list to its caller as
`required_agent_skills`, propagating the dead name.

The registry is iterated rather than named so a newly added tool is covered
the moment it is discovered.
"""

from pathlib import Path

import pytest

from tools.tool_registry import registry

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLS_ROOT = REPO_ROOT / ".agents" / "skills"


def _discovered_tools() -> list[tuple[str, list[str]]]:
    registry.discover()
    pairs: list[tuple[str, list[str]]] = []
    for name, tool in sorted(registry._tools.items()):
        try:
            info = tool.get_info()
        except Exception:  # a tool that cannot introspect is another test's problem
            continue
        pairs.append((name, list(info.get("agent_skills") or [])))
    return pairs


TOOLS = _discovered_tools()
POINTERS = [(name, skill) for name, skills in TOOLS for skill in skills]


def _resolves(skill: str) -> bool:
    return (SKILLS_ROOT / skill / "SKILL.md").exists() or (
        SKILLS_ROOT / f"{skill}.md"
    ).exists()


def test_registry_actually_discovered_tools() -> None:
    assert TOOLS, "registry.discover() found no tools"


def test_some_tools_declare_layer_three_skills() -> None:
    """Guard against the parametrized test below silently covering nothing."""
    assert POINTERS


@pytest.mark.parametrize(("tool", "skill"), POINTERS, ids=lambda v: str(v))
def test_agent_skill_pointer_resolves(tool: str, skill: str) -> None:
    """Regression: four pointers named skills that do not exist.

    - hyperframes_compose -> `website-to-hyperframes`, renamed upstream to
      `website-to-video` (recorded in .agents/skills/hyperframes/PROVENANCE.md)
    - openai_tts, tts_selector -> `openai-docs`, never vendored
    - screen_capture_selector -> `screen-demo`, which names the Layer 2
      pipeline directory rather than a Layer 3 skill
    """
    assert _resolves(skill), (
        f"{tool} advertises agent_skill {skill!r}, but neither "
        f".agents/skills/{skill}/SKILL.md nor .agents/skills/{skill}.md exists"
    )


@pytest.mark.parametrize("name", ("video_trimmer", "video_stitch", "showcase_card", "audio_mixer"))
def test_local_media_tools_do_not_require_external_generation_setup(name: str) -> None:
    """Local processing must not instruct callers to bootstrap a cloud toolkit."""
    tool = registry._tools[name]
    info = tool.get_info()
    assert "ffmpeg" in info["agent_skills"]
    assert "video-toolkit" not in info["agent_skills"]
    assert tool.provider == "ffmpeg"
    assert "cmd:ffmpeg" in tool.dependencies


@pytest.mark.parametrize("host", (".agents", ".claude"))
def test_remotion_router_links_resolve_in_the_actual_checkout(host: str) -> None:
    import re

    entrypoint = REPO_ROOT / host / "skills/remotion/SKILL.md"
    text = entrypoint.read_text(encoding="utf-8")
    targets = re.findall(r"\]\(([^)]+)\)", text)
    assert targets, "Remotion guidance must expose its current supporting sources"
    for target in targets:
        if target.startswith("https://"):
            continue
        assert (entrypoint.parent / target).is_file(), f"Dead reference: {target}"
    assert "remotion-official" not in text
