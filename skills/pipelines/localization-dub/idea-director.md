# Idea Director - Localization Dub Pipeline

## When To Use

Use this pipeline when the user has a source video and wants translated deliverables: subtitles, dubbed audio, or localized videos in one or more target languages.

Your first responsibility is to define what kind of localization is actually required, because subtitle-only, dubbed-audio, and lip-synced translation are different jobs.

## Runtime Selection (`render_runtime` and pipeline constraints)

The supported plan uses `render_runtime = "remotion"` (composed deliverables with per-locale caption burn / lip-sync) or `"ffmpeg"` (pure subtitle-burn over source with no composition). **HyperFrames is NOT a valid runtime on this pipeline in Phase 1** — localization depends on Remotion's caption stack and, for dubbed-with-lip-sync, on the Remotion TalkingHead pipeline.

Follow `AGENT_GUIDE.md` → "Composition Runtime Selection" as the canonical
contract. Preserve an exact authorized `render_runtime`, including a new actionable
brief with exact choices, without a runtime menu or repeat approval. When runtime
choice is unresolved, compare Remotion and HyperFrames only when both are viable
for this brief; record actual alternatives and constraint evidence in a
`render_runtime_selection` decision. An unavailable or incompatible authorized
runtime is a concrete blocker; do not substitute it silently. Preserve the
manifest's proposal/asset approval gates, authorized spend, material-change
approval and separate publication approval.

Explain the constraint when it affects this request; do not claim HyperFrames is
available without evidence or request repeat approval for an already authorized
supported runtime.

## Reference Inputs

- `docs/localization-dubbing-best-practices.md`
- `skills/creative/short-form.md`
- `skills/creative/long-form.md`

## Process

### 1. Define The Localization Scope

Capture:

- source language,
- target languages,
- review owner,
- whether glossary or legal review is required,
- whether the user needs subtitles, dubbed audio, lip-sync, or a mix.

### 2. Classify The Source

Record the source mode:

- `single_speaker`
- `multi_speaker`
- `voiceover_led`
- `speaker_led_on_camera`

Also record whether on-screen text or motion graphics will need manual replacement or coverage.

### 3. Pick Deliverables That Match Reality

Possible deliverables:

- subtitle package only,
- dubbed video without lip sync,
- lip-synced localized video,
- per-language export bundle.

### 4. Build The Brief

Recommended metadata keys:

- `source_language`
- `target_languages`
- `deliverable_mode_map`
- `glossary_terms`
- `protected_terms`
- `review_requirements`
- `timing_risks`

### 5. Quality Gate

- localization scope is explicit,
- target outputs are realistic,
- glossary and review requirements are captured,
- risk increases from speaker count or visible mouths are surfaced.

## Common Pitfalls

- Calling every translation request a dubbing request.
- Ignoring glossary control until after audio is generated.
- Promising lip sync on visually difficult source footage without warning.

---

## Gate Reminder (Binding)

This stage gates on human approval (`human_approval_default: true`). After review passes:
checkpoint with `status="awaiting_human"`, present the summary (the Backlot board renders
the artifact), and **END YOUR TURN**. Do not start the next stage in the same response.
Approval is per-gate — an earlier "go ahead" does not cover this gate.
