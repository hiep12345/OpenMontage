---
name: website-to-video
description: Turn an authorized website capture into a video when HyperFrames and this site-showcase workflow are selected. Preserve the approved assets, brand, runtime and production gates; generic website/video requests use the project router.
---

> Use [media-use](../media-use/SKILL.md) only if the HeyGen catalog is the selected asset source. Preserve supplied/approved assets and provenance.

# Website to HyperFrames

Capture a website, then produce a professional video from it.

> **Confirm the selected route before Step 0.** Use the [OpenMontage router](../../../AGENTS.md) for an unresolved website, product, explainer or source-footage request. This package supports an approved website capture/showcase using HyperFrames. Other upstream workflows are intentionally excluded from this checkout; their slash-command names are not callable local routes. Preserve the approved runtime, provider, assets, music, budget and manifest approvals. Read the [runtime selector](../../../skills/meta/animation-runtime-selector.md) only when runtime selection is unresolved.

Users say things like:

- "Turn this website into a 15-second social clip for Instagram"
- "Make a 30-second site tour / showcase from https://..."
- "Capture our homepage and build a video from its own visuals"

The workflow has 7 steps. Each produces an artifact that gates the next. By default it's collaborative — gates marked 💬 stop and ask the user. If the user signals autonomous mode ("decide for me", "surprise me"), 💬 user-preference gates are skipped; see step-2-brief.md for how that propagates.

**Autonomous mode is NOT "skip all gates."** Choose only preferences actually delegated within the current brief. Reuse bound voice, music, captions, provider and budget choices; general autonomy does not override manifest approvals, change providers or authorize extra spending. The following quality checks still apply:

- Asset Audit (Step 3) — viewing contact sheets and justifying USE/SKIP for each asset
- Relevant beat source and rendered-state review (Step 5)
- Applicable completion checks (Step 6), with rendered-state and audio/motion evidence or explicit NOT TESTED
- Honest disclosure section (Step 6) — "What I did NOT verify" must appear in your final summary

If you find yourself reasoning "auto mode says bias toward action, so I'll skip X" — and X is a verification gate, not a preference question — that reasoning is wrong. Bias toward action applies to deciding _what to build_, not to deciding _whether to verify_.

---

## Step 0: Capture & Understand the Brand

**Read:** [references/step-0-capture.md](references/step-0-capture.md)

Capture the site, then read the extracted data to understand the **brand and product** — what it does, who it's for, what voice it speaks in, what mood it lives in. The captured assets are a brand toolkit for later, not the building blocks the video is made from.

Check audio access only after a provider/audio route is needed. Follow
[media preflight](../hyperframes-media/SKILL.md), reuse approved assets and provider
choices, and never require signup for an unrelated brief or offline run.

**Gate:** Site content and brand summary are grounded in the captured source;
provider access is checked when required by the selected route.

---

## Step 1: Brand Identity

**Read:** [references/step-1-design.md](references/step-1-design.md)

Write DESIGN.md — a brand cheat sheet covering the visual identity: colors, typography, component styles, layout principles. Use `design-styles.json` for exact computed values.

**Speed option:** For fast-pacing videos (billboard-per-beat), DESIGN.md can be a 50-line summary of colors + fonts + do's/don'ts — not a 300-line document. The sub-agent prompt in Step 5 pastes brand values directly, so DESIGN.md depth only matters for complex compositions.

**Gate:** `DESIGN.md` exists (any length) with at minimum: color palette, font choices, and do's/don'ts.

---

## Step 2: Strategy & Messaging

**Read:** [references/step-2-brief.md](references/step-2-brief.md), [references/capabilities.md](references/capabilities.md) (scan the Table of Contents — deep-dive sections only as needed)

Align with the user on **what the video must communicate** before talking visuals or assets. Parse the user's prompt — they probably already gave you the video type and style. Ask only what's missing: the ONE thing this video must say, the narrative arc, and the audience.

**Gate:** Video type, duration, format, and — critically — the message and narrative arc are locked. Without those, Step 3 can't write a concept-first storyboard.

---

## Step 3: Storyboard + Script 💬

**Read:** [references/step-3-storyboard.md](references/step-3-storyboard.md)

Write the storyboard concept-first: message → narrative arc → beats that serve the arc → techniques per beat → brand accents pass at the end. Then write the narration script to match. Present both to the user with a beat-by-beat summary. Iterate until they approve.

**Gate:** `STORYBOARD.md` + `SCRIPT.md` exist AND the user has approved the plan.

---

## Step 4: VO, Timing + Captions 💬

**Read:** [references/step-4-vo.md](references/step-4-vo.md)

Reuse the approved narration, music, provider, voice and caption choices. For no narration, carry approved beat timings into Step 5 without TTS or transcription. Otherwise use the authorized available provider and actual audio timings. Ask only about a material unresolved choice; an unavailable provider does not authorize a fallback or additional paid auditions.

**Gate:** Either (a) no narration was requested and storyboard has manual beat timings, or (b) `narration.wav` + `transcript.json` exist and beat timings updated with real durations.

---

## Step 5: Build Compositions

**Read:** The relevant `hyperframes-core` contract and selected runtime references
**Read:** [references/step-5-build.md](references/step-5-build.md)

Build index.html and compositions following the architecture and pacing chosen in the storyboard (Step 3). Build directly or use useful permitted workers; run relevant lint/snapshot checks and inspect the assembled result.

**Gate:** Inspect each beat against DESIGN.md and STORYBOARD.md using rendered states and relevant source; reuse verified unchanged sections. The per-beat checklist lives in [step-5-build.md](references/step-5-build.md).

---

## Step 6: Validate & Deliver

**Read:** [references/step-6-validate.md](references/step-6-validate.md)

Lint, validate, and inspect representative final frames covering each beat, transitions, dense text and endpoints; expand sampling when anomalies appear. Fix issues before delivering. Deliver the localhost Studio project URL — render the requested final MP4 once applicable project gates and existing exact-scope approval are satisfied. Surface that Studio URL **only at handoff** — it is the final, stable preview; the build-phase snapshots are headless, so do not pop a preview mid-build.

**Deliver something you're proud of.** Before handing off, ask yourself: would I post this on social media with my name on it? If not, fix what's wrong.

**Gate:** Applicable checks pass, final rendered states are inspected, audio/motion status is explicit, and the requested final artifact or preview is delivered.

---

## Quick Reference

### Video Types

Typical constraints by video type — use as a starting point, not a formula. Beat count should follow from the content and the narration, not from a target range.

| Type                  | Typical duration | Duration driver    | Narration             |
| --------------------- | ---------------- | ------------------ | --------------------- |
| Social ad (IG/TikTok) | 10–15s           | Platform limit     | Optional              |
| Product demo          | 30–60s           | Script length      | Full narration        |
| Feature announcement  | 15–30s           | Feature complexity | Full narration        |
| Brand reel            | 20–45s           | Music track        | Optional, music focus |
| Launch teaser         | 10–20s           | Hook energy        | Minimal               |

Beat count is not in this table intentionally — it should come from the storyboard, not from "social ad = 3-4 beats." A social ad for a complex product might need 5 well-timed beats. A brand reel with one strong visual thesis might need 3.

### Format

- **Landscape**: 1920x1080 (default)
- **Portrait**: 1080x1920 (Instagram Stories, TikTok)
- **Square**: 1080x1080 (Instagram feed)

### Reference Files

| File                                                                               | When to read                                                                                                                                   |
| ---------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| [step-0-capture.md](references/step-0-capture.md)                                  | Step 0 — capture, understand the brand and product, write strategy-first site summary                                                          |
| [step-1-design.md](references/step-1-design.md)                                    | Step 1 — write DESIGN.md brand cheat sheet (5 sections, 250-350 lines; 50-line fast-path for billboard-style social ads)                       |
| [step-2-brief.md](references/step-2-brief.md)                                      | Step 2 — align on message, narrative arc, audience with user                                                                                   |
| [capabilities.md](references/capabilities.md)                                      | Steps 2 & 5 — upstream capability examples; confirm selected features against the installed runtime and current local skill references |
| [step-3-storyboard.md](references/step-3-storyboard.md)                            | Step 3 — storyboard + script (combined) with user review gate                                                                                  |
| [step-4-vo.md](references/step-4-vo.md)                                            | Step 4 — TTS provider choice, generation, timing                                                                                               |
| [step-5-build.md](references/step-5-build.md)                                      | Step 5 — build index.html + compositions                                                                                                       |
| [step-6-validate.md](references/step-6-validate.md)                                | Step 6 — lint, validate, snapshots (scaled to video length), preview                                                                           |
| [techniques.md](../hyperframes-animation/techniques.md)                           | Steps 3 & 5 — 13 primitive animation techniques with code patterns (adapt, don't copy-paste)                                                   |
| [html-in-canvas-patterns.md](../hyperframes-animation/adapters/html-in-canvas-patterns.md) | Step 5 — complete code patterns for HTML-in-Canvas effects (lives in the hyperframes skill)                                                    |
