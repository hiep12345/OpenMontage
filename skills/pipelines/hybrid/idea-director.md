# Idea Director - Hybrid Pipeline

## When To Use

Use this pipeline when the project combines real source media with support visuals: interviews plus diagrams, footage plus overlays, screen recording plus branded graphics, or source-led edits with generated inserts.

Hybrid is not a catch-all. Your first job is to define what stays primary.

## Runtime Selection (`render_runtime`)

Follow `AGENT_GUIDE.md` → "Composition Runtime Selection" as the canonical
contract. Preserve an exact authorized `render_runtime`, including a new actionable
brief with exact choices, without a runtime menu or repeat approval. When runtime
choice is unresolved, compare Remotion and HyperFrames only when both are viable
for this brief; record actual alternatives and constraint evidence in a
`render_runtime_selection` decision. An unavailable or incompatible authorized
runtime is a concrete blocker; do not substitute it silently. Preserve the
manifest's proposal/asset approval gates, authorized spend, material-change
approval and separate publication approval.

For unresolved choices, Remotion fits source footage with React support layers
via `<OffthreadVideo>`; HyperFrames fits HTML/GSAP callouts and typographic
overlays with footage embedded as `<video class="clip">`. Use the anchor medium
and support-layer requirements to explain the recommendation.

## Reference Inputs

- `docs/hybrid-video-best-practices.md`
- `skills/creative/storytelling.md`
- `skills/creative/video-editing.md`

## Process

### 1. Choose The Anchor Medium

Pick the storytelling anchor:

- `talking_head`
- `broll_footage`
- `screen_recording`
- `still_sequence`
- `narration_led_graphics`

### 2. Define Support Layers

Possible support layers:

- subtitles,
- diagrams,
- code visuals,
- stat cards,
- generated inserts,
- narration,
- music.

Each support layer should solve a specific problem, not just decorate the timeline.

### 3. Decide The Deliverable Mix

Common outputs:

- hero cut,
- vertical cutdown,
- square cutdown,
- chaptered version,
- ad variant.

### 4. Build The Brief

Recommended metadata keys:

- `anchor_medium`
- `source_inventory`
- `support_layers`
- `deliverable_mix`
- `missing_capabilities`
- `fallback_policy`

### 5. Quality Gate

- the anchor medium is explicit,
- support layers are justified,
- the deliverable mix fits the source inventory,
- missing capabilities are surfaced early.

## Common Pitfalls

- Calling everything hybrid without defining a primary medium.
- Planning support layers before understanding the source.
- Treating optional generated inserts as guaranteed.

---

## Gate Reminder (Binding)

This stage gates on human approval (`human_approval_default: true`). After review passes:
checkpoint with `status="awaiting_human"`, present the summary (the Backlot board renders
the artifact), and **END YOUR TURN**. Do not start the next stage in the same response.
Approval is per-gate — an earlier "go ahead" does not cover this gate.
