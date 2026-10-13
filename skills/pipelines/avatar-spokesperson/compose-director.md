# Compose Director - Avatar Spokesperson Pipeline

## When To Use

Render the final spokesperson outputs. The bar is simple: the presenter must look stable, speech must be clear, and subtitles or support cards must not crowd the frame.

## Runtime Routing (HARD CONSTRAINT — Remotion only)

Follow `AGENT_GUIDE.md` → "Composition Runtime Selection". Preserve an exact
authorized `render_runtime` and route only through a viable supported path.
An unavailable or incompatible authorized runtime is a concrete blocker; no
silent substitution. Preserve manifest/proposal/asset gates, authorized spend,
material-change approval and separate publication approval.

Phase 1 deferred from HyperFrames. `edit_decisions.render_runtime` must be `"remotion"`. This pipeline depends on the Remotion `TalkingHead` composition and `remotion_caption_burn` — both have no HyperFrames parity in Phase 1.

- If `edit_decisions.render_runtime == "hyperframes"`, stop and surface the pipeline constraint as a concrete blocker. A supported replacement requires applicable authorization and an appended `render_runtime_selection` decision; never silently rewrite the runtime.
- Explain a newly encountered pipeline constraint as a concrete blocker; reuse exact recorded authority for a supported runtime without a repeated menu.
- Pass `proposal_packet`/`brief` to `video_compose.execute()` for in-tool runtime-swap detection.

## Prerequisites

| Layer | Resource | Purpose |
|-------|----------|---------|
| Schema | `schemas/artifacts/render_report.schema.json` | Artifact validation |
| Prior artifacts | `state.artifacts["edit"]["edit_decisions"]`, `state.artifacts["assets"]["asset_manifest"]` | What to render |
| Tools | `video_compose`, `audio_mixer`, `video_stitch`, `audio_enhance` | Render and audio finishing |
| Playbook | Active style playbook | Typography and layout rules |

## Process

### 1. Render The Hero Cut First

Prefer one strong master before derivatives. Compose:

- presenter video,
- subtitles,
- lower-thirds,
- CTA cards,
- mixed narration.

### 2. Keep The Frame Clean

Subtitle and CTA placement matter more here than flashy transitions. Leave the face and mouth region unobstructed.

### 3. Verify Mouth Timing And Audio

If the avatar path used lip sync or audio-driven talking head, check:

- mouth timing,
- face artifacts,
- drift on long sections,
- audio clarity.

### 4. Verify Every Output

Record important findings in:

- `render_report.verification_notes`
- `render_report.warnings`
- `render_report.metadata.variant_notes`

### 5. Quality Gate

- the output file is valid,
- speech is clear,
- subtitles stay readable,
- the presenter remains visually stable.

## Common Pitfalls

- Letting subtitles cover the chin or mouth area.
- Shipping a long lip-sync render without spot-checking drift.
- Making derivative crops that cut off the presenter or CTA.
