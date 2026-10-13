# Idea Director - Avatar Spokesperson Pipeline

## When To Use

Use this pipeline when the deliverable is a presenter-led avatar video: a spokesperson spot, product intro, onboarding message, internal comms update, or short scripted explainer where the speaker remains the visual anchor.

Your first job is to classify the avatar path honestly before anyone writes polished copy for an impossible production setup.

## Runtime Selection (`render_runtime` and pipeline constraints)

The supported plan uses `render_runtime = "remotion"`. **HyperFrames is NOT a valid runtime on this pipeline in Phase 1** — avatar-spokesperson depends on the Remotion `TalkingHead` composition and `remotion_caption_burn`, and neither has HyperFrames parity yet.

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

- `docs/avatar-spokesperson-best-practices.md`
- `skills/creative/storytelling.md`
- `skills/creative/short-form.md`

## Process

### 1. Classify The Avatar Path

Record which production mode the project actually has:

- `platform_avatar`
- `photo_talking_head`
- `presenter_plate_lip_sync`

Also record whether the avatar already exists or still has to be created outside the current run.

### 2. Define The Message Shape

Capture:

- audience,
- core offer or CTA,
- runtime target,
- platform targets,
- whether the video is sales, onboarding, support, or announcement led.

Spokesperson videos work best when they have one clear job.

### 3. Capture Source Reality

The brief should explicitly state:

- whether clean narration is supplied,
- whether TTS is acceptable,
- whether brand backgrounds or overlays exist,
- whether subtitles are required,
- whether multilingual variants are expected.

### 4. Build The Brief

Recommended metadata keys:

- `avatar_path`
- `avatar_exists`
- `narration_source`
- `target_audience`
- `cta_type`
- `background_strategy`
- `deliverable_mix`
- `missing_capabilities`

### 5. Quality Gate

- the avatar path is explicit,
- the message is narrow enough for a spokesperson format,
- missing narration or avatar dependencies are visible early,
- deliverables fit the actual source setup.

## Common Pitfalls

- Treating a generic generated-video request as a deterministic avatar workflow.
- Writing the CTA before confirming the avatar and narration path.
- Planning multiple aspect ratios before the hero layout is proven.

---

## Gate Reminder (Binding)

This stage gates on human approval (`human_approval_default: true`). After review passes:
checkpoint with `status="awaiting_human"`, present the summary (the Backlot board renders
the artifact), and **END YOUR TURN**. Do not start the next stage in the same response.
Approval is per-gate — an earlier "go ahead" does not cover this gate.
