"""Pure selection for lean stage context; no IO, activation or authority changes.

The consumer still reads/validates sources and binds full-source hashes. Existing
1.0 production packets must continue using their original reconstruction.
"""
from __future__ import annotations

from copy import deepcopy


DEFAULT_CONTEXT_VERSION = "1.1"
CONTEXT_VERSIONS = frozenset({"1.0", DEFAULT_CONTEXT_VERSION})
CONTENT_SELECTORS = frozenset({"channel", "content_kind", "video_format", "tags"})


def has_content_scope(profile: dict) -> bool:
    """Provider/model alone cannot select reusable cross-run content feedback."""
    return any(profile.get(key) for key in CONTENT_SELECTORS)


def stage_manifest(manifest: dict, stage: str) -> dict:
    """Keep pipeline-wide contracts, current stage and the approval/status rail.

    Other stage details remain in the full source, whose hash the consumer must
    bind. Never mutate the shared cached manifest.
    """
    entries = manifest["stages"]
    current = next(entry for entry in entries if entry["name"] == stage)
    selected = deepcopy({key: value for key, value in manifest.items() if key != "stages"})
    selected["stages"] = [deepcopy(current)]
    selected["stage_order"] = [
        {key: entry[key] for key in ("name", "checkpoint_required", "human_approval_default") if key in entry}
        for entry in entries
    ]
    return selected


def stage_inputs(manifest: dict, stage: str, canonical: dict[str, str]) -> dict[str, str | None]:
    """Select declared inputs plus enduring brief/reference/decision authority.

    Proposal and decision-log retention matters even when a manifest omitted
    them from its input declarations (e.g. cinematic compose runtime checks).
    Names resolve to the most recent predecessor that actually produces them;
    this preserves secondary artifacts and frozen checkpoint provenance.
    """
    entries = manifest["stages"]
    index = next(i for i, entry in enumerate(entries) if entry["name"] == stage)
    current = entries[index]
    owners = {}
    for entry in entries[:index]:
        for name in entry.get("produces", [canonical.get(entry["name"])]):
            if name:
                owners[name] = entry["name"]
    names = dict.fromkeys(
        current.get("required_artifacts_in", []) + current.get("optional_artifacts_in", [])
        + ["brief", "video_analysis_brief", "source_media_review", "proposal_packet", "decision_log"]
    )
    outputs = set(current.get("produces", [])) | {canonical.get(stage)}
    return {name: owners.get(name) for name in names if name not in outputs}


def production_guidance(text: str) -> str:
    """Repeat production boundaries, not routing/onboarding/recovery paragraphs.

    Native AGENTS precedence still applies to the complete file. Unknown layouts
    fall back to the full text rather than silently dropping guidance. The
    consumer must retain the full-source hash and explicit source reference.
    """
    lines = text.splitlines(keepends=True)
    start = next((i for i, line in enumerate(lines) if line.strip() == "## Binding production boundaries"), None)
    if start is None:
        return text
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    return "".join(lines[start:end])
