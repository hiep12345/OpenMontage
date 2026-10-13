# Idea Director — Talking Head Pipeline

## When to Use

You are starting a talking-head video project. You have raw footage of a person speaking. Your job is to analyze the footage, understand what it contains, and build a brief that captures the content's essence and production goals.

Unlike the explainer pipeline (which starts from a topic), you start from existing footage. The brief documents what you're working with and what the final video should look like.

## Runtime Selection (`render_runtime` and pipeline constraints)

The supported plan uses `render_runtime = "remotion"` (preferred — uses `TalkingHead` + `remotion_caption_burn`) or `"ffmpeg"` (for source-footage concat with no composition). **HyperFrames is NOT a valid runtime on this pipeline in Phase 1** — the TalkingHead composition and word-level caption burn have no HyperFrames parity yet.

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

## Prerequisites

| Layer | Resource | Purpose |
|-------|----------|---------|
| Schema | `schemas/artifacts/brief.schema.json` | Artifact validation |
| Inputs | Raw footage file path | Source material |
| Tools | `ffprobe` (via shell) | Footage metadata extraction |

## Process

### Step 1: Inspect the Footage

Use ffprobe to extract metadata:
- Duration
- Resolution
- Frame rate
- Audio channels and codec
- File size

This tells you what you're working with — quality, length, format.

### Step 2: Quick Content Assessment

Watch/scan the footage mentally (or sample frames if frame_sampler is available):
- What is the person talking about?
- How long is the raw footage?
- What's the intended platform? (Ask the user if unclear)
- Is there good audio? Background noise?

### Step 3: Build the Brief

Create a brief artifact documenting:
- **Title**: Descriptive title based on footage content
- **Hook**: What makes this worth watching?
- **Key points**: Main topics covered in the footage
- **Tone**: Match the speaker's actual tone (casual, professional, educational)
- **Style**: Derive the overlay/look direction from the footage, speaker persona, audience, and platform. `clean-professional` is a safe fallback, not the default answer to every talking-head brief.
- **Target platform**: Where this will be published
- **Target duration**: May be shorter than raw footage (trimmed)

### Step 4: Self-Evaluate

| Criterion | Question |
|-----------|----------|
| **Accuracy** | Does the brief reflect what's actually in the footage? |
| **Completeness** | Are all required brief fields present? |
| **Platform fit** | Is the target platform appropriate for this content? |

### Step 5: Submit

Validate the brief against the schema and persist via checkpoint.

---

## Gate Reminder (Binding)

This stage gates on human approval (`human_approval_default: true`). After review passes:
checkpoint with `status="awaiting_human"`, present the summary (the Backlot board renders
the artifact), and **END YOUR TURN**. Do not start the next stage in the same response.
Approval is per-gate — an earlier "go ahead" does not cover this gate.
