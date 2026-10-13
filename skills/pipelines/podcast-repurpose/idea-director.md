# Idea Director - Podcast Repurpose Pipeline

## When To Use

Use this pipeline when the source is a podcast episode, either audio-only or video podcast, and the user wants clips, social assets, or a companion long-form video treatment.

Your first responsibility is to decide what is feasible from the source that actually exists.

## Runtime Selection (`render_runtime` and pipeline constraints)

The supported plan uses `render_runtime = "remotion"` (audiograms and composed outputs) or `"ffmpeg"` (pure-audio-led clip exports). **HyperFrames is NOT a valid runtime on this pipeline in Phase 1** — podcast outputs lean on Remotion's word-level caption stack, which has no HyperFrames parity yet.

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

- `docs/podcast-repurposing-best-practices.md`
- `skills/creative/short-form.md`
- `skills/creative/long-form.md`

## Process

### 1. Classify The Source

Capture the source mode:

- `audio_only`
- `video_podcast`
- `hybrid` (audio plus stills, cover art, guest photos)

Also capture the conversational format:

- solo
- interview
- panel
- narrative / produced show

### 2. Choose Deliverables That Match Reality

Default deliverables should be feasible with the source and tools on hand.

Safe options:

- short-form highlight clips,
- audiogram or caption-led clips,
- quote-led clips,
- one optional full-episode companion layout.

Do not assume a high-production full-episode YouTube treatment unless the source video, branding assets, and optional imagery actually exist.

### 3. Set A Sensible Deliverable Mix

Typical starting point:

- `3-5` highlight clips
- `1-3` quote-led assets if the episode has strong one-liners
- optional long-form companion if the source justifies it

### 4. Respect Platform Differences

- `9:16` for Shorts, Reels, TikTok
- `1:1` for LinkedIn and safer feed repurposing
- `16:9` for YouTube companion video

If the source is audio-only, make that explicit in the brief. Downstream stages should not plan speaker-framed video that does not exist.

### 5. Build The Brief

Use `brief.metadata` for the richer podcast-specific contract:

- `source_mode`
- `show_name`
- `episode_title`
- `episode_number`
- `speakers`
- `conversation_format`
- `deliverable_mix`
- `brand_assets_available`
- `full_episode_companion_feasible`

### 6. Quality Gate

- the deliverable mix matches the actual source,
- clip counts are realistic for the episode length,
- the brief states whether visuals will be source-led, quote-led, or audiogram-led,
- long-form ambitions are scaled to the available assets.

## Common Pitfalls

- Treating audio-only and video-podcast sources as the same production problem.
- Planning too many deliverables from a weak episode.
- Promising a rich full-episode visual treatment without the assets to support it.

---

## Gate Reminder (Binding)

This stage gates on human approval (`human_approval_default: true`). After review passes:
checkpoint with `status="awaiting_human"`, present the summary (the Backlot board renders
the artifact), and **END YOUR TURN**. Do not start the next stage in the same response.
Approval is per-gate — an earlier "go ahead" does not cover this gate.
