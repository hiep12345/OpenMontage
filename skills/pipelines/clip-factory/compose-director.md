# Compose Director - Clip Factory Pipeline

## When To Use

Render each clip and platform variant independently. The important behaviors here are consistency, batch resilience, and clear reporting of partial failures.

## Runtime Routing (HARD CONSTRAINT — Remotion or FFmpeg only)

Follow `AGENT_GUIDE.md` → "Composition Runtime Selection". Preserve an exact
authorized `render_runtime` and route only through a viable supported path.
An unavailable or incompatible authorized runtime is a concrete blocker; no
silent substitution. Preserve manifest/proposal/asset gates, authorized spend,
material-change approval and separate publication approval.

This pipeline is Phase 1 deferred from the HyperFrames adoption schedule. `edit_decisions.render_runtime` must be `"remotion"` (default) or `"ffmpeg"` (pure-concat clip jobs with no composition). HyperFrames is NOT a valid runtime here — clip-factory depends on Remotion word-level caption burn, and HyperFrames caption parity is deferred work.

- If `edit_decisions.render_runtime == "hyperframes"`, stop and surface the pipeline constraint as a concrete blocker. A supported replacement requires applicable authorization and an appended `render_runtime_selection` decision; never silently rewrite the runtime.
- Explain a newly encountered pipeline constraint as a concrete blocker; reuse exact recorded authority for a supported runtime without a repeated menu.
- Pass `proposal_packet`/`brief` to `video_compose.execute()` so the in-tool runtime-swap check runs end-to-end.

## Prerequisites

| Layer | Resource | Purpose |
|-------|----------|---------|
| Schema | `schemas/artifacts/render_report.schema.json` | Artifact validation |
| Prior artifacts | `state.artifacts["edit"]["edit_decisions"]`, `state.artifacts["assets"]["asset_manifest"]` | Clip edits and assets |
| Tools | `video_trimmer`, `video_compose`, `audio_mixer`, `color_grade` | Render pipeline |
| Media profiles | `lib/media_profiles.py` | Platform targets |

## Process

### 1. Treat Each Output As Its Own Job

One clip across three platforms is three render jobs. Name and track them explicitly.

### 2. Reuse What Can Be Shared

- shared audio mix where possible,
- shared subtitle styling,
- shared overlay assets,
- shared grading if the source needs it.

### 3. Fail Softly

If one clip or one platform variant fails:

- log it clearly,
- continue the rest of the batch,
- do not block successful exports.

### 4. Verify Every Output

Per render:

- correct duration,
- correct resolution/aspect ratio,
- no black opening frame,
- hook appears on time,
- subtitles render correctly,
- audio is present and consistent.

### 5. Use Render Report Metadata

Recommended metadata keys:

- `job_index`
- `failed_jobs`
- `shared_intermediates`
- `platform_groupings`

## Common Pitfalls

- Rendering sequentially without reason when jobs are independent.
- Treating a failed clip as a reason to stop the batch.
- Letting one platform variant quietly use the wrong framing or subtitle zone.
