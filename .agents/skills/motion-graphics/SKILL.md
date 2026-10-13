---
name: motion-graphics
description: Build a short unnarrated motion graphic when HyperFrames and this workflow are selected. Use for kinetic type, charts, logo stings or overlays; preserve approved runtime, source, brand and production gates.
metadata:
  {
    "tags": "orchestrator, motion-graphics, kinetic-type, data-viz, logo-reveal, lower-thirds, news, tweet, webpage, asset-fusion, short-form, overlay, no-narration",
  }
---

# motion-graphics — dispatch entry

> **Confirm the route before Step 0.** This skill makes a **short, design-led, unnarrated motion graphic** (motion is the message; ~under 10s, no voice-over). A **longer, multi-scene, or narrated** treatment → `/general-video`; a **narrated video of a website** → `/website-to-video`; a **topic explainer** → `/faceless-explainer`; a **product promo** → `/product-launch-video`; **captions on existing footage** → `/embedded-captions`. **Out of scope**: live / at-render-time data, or footage it can't capture. Unsure motion-first-vs-narrated? **Read `/hyperframes` first.**

A short design-led motion graphic. **Asset-first**: decide the asset strategy and source real material _before_ designing the shot, then design the shot around what you have, then compose by reusing catalog capabilities. All artifacts go to `PROJECT_DIR = videos/<project-name>/` (created in Step 0); all paths below are relative to it.

| Phase    | Execution                                                             | Primary artifact                                                 | Detailed flow                 |
| -------- | --------------------------------------------------------------------- | ---------------------------------------------------------------- | ----------------------------- |
| init     | Bash                                                                  | `hyperframes.json`                                               | Step 0                        |
| plan     | direct work / optional worker — **decide search?** + classify + asset strategy             | `shot-plan.json` (draft: category, `asset_needs` queries, brief) | `agents/director.md` (Part 1) |
| source ◇ | Bash — media-use resolve (**skip if `asset_needs` is empty**)         | `assets/` + `assets/index.md`                                    | `phases/source/guide.md`      |
| design   | direct work / optional worker — shot design around resolved assets                         | `shot-plan.json` (final: block(s) + layout + motion + positions) | `agents/director.md` (Part 2) |
| build    | direct work / optional worker — reuse-first composition                                    | `compositions/index.html`                                        | `agents/builder.md`           |
| render   | Bash — `hyperframes render` (MP4, or `--format webm/mov` for overlay) | `renders/video.mp4`                                              | Step 5                        |
| verify   | Bash — `lint` / `inspect` -> targeted repair on failure               | (fixes in place)                                                 | `agents/finalize.md`          |

`◇ source` runs only when the chosen category declares assets. Pure code/text categories (e.g. `kinetic-type`, most `charts`/`stat`) have `asset_needs: []` and skip straight from plan to design.

## Categories — split by the search decision

`plan`'s **first decision is: does this need a search?** That fork splits the categories into two groups; then the specific category is picked — for search-driven, **by the type of content the search returns**. Each category is one `categories/<id>/module.md` (its planning + build rules); the shared motion vocabulary lives in `references/motion-vocabulary.md` (→ `hyperframes-animation` rules/blueprints + registry blocks).

**Form categories — no search; the user supplies the content:**

| Category       | Intent                                         | Leans on                                                                    |
| -------------- | ---------------------------------------------- | --------------------------------------------------------------------------- |
| `kinetic-type` | punchy line / quote / title, motion-first text | `caption-*` blocks + animation rules                                        |
| `stat`         | single hero number / count-up + ring           | `apple-money-count` / `rules/{counting-dynamic-scale, stat-bars-and-fills}` |
| `charts`       | bar / line / pie / race / % from data          | `data-chart` block                                                          |
| `logo-reveal`  | logo sting / brand lockup (user logo)          | `logo-outro` / `rules/svg-path-draw`                                        |
| `lower-thirds` | name / title bars, callouts, social overlays   | `caption-*` + registry overlay blocks                                       |

**Search-driven categories — search first, then animate by content type** (the RWA path):

| Returned content | Category       | Animation                                                      |
| ---------------- | -------------- | -------------------------------------------------------------- |
| webpage / link   | `webpage`      | webpage / UI animation (scroll, reveal, cursor, callouts)      |
| news article     | `news`         | headline reveal + source card + key-fact callouts              |
| tweet            | `tweet`        | animated tweet card                                            |
| image / entity   | `asset-fusion` | the asset's geometry _becomes_ the chart (RWA diegetic fusion) |

Build order: one at a time, coverage-first (rough is fine). `kinetic-type` ported from the prototype; the rest follow.

## Prerequisites

Use the installed runtime on the current supported host, including a verified Windows path. Check Node, FFmpeg and the pinned CLI with `doctor`; do not run macOS package commands on other hosts. Bash snippets need the equivalent shell syntax.

Optional keys (local fallbacks if unset) — only needed by categories that source/generate assets via media-use:

| Key                                 | Used for                                                    | Fallback                        |
| ----------------------------------- | ----------------------------------------------------------- | ------------------------------- |
| `GEMINI_API_KEY` / `GOOGLE_API_KEY` | image generation (media-use resolve)                        | skip generate / search-only     |
| (asset_scout / search providers)    | `webpage`/`news`/`tweet` + `asset-fusion` real-asset search | category degrades to asset-free |

## Flow

### Step 0 — Initialize

cwd is the agent workspace root; write all artifacts under `PROJECT_DIR = videos/<project-name>/`. `<project-name>`: use the dir the user gave, else a short kebab-case name from the intent (`<subject>-motion`). Not the workspace basename or a timestamp.

Only when `$PROJECT_DIR/hyperframes.json` is absent:

```bash
PROJECT_DIR="${MOTION_GRAPHICS_DIR:-videos/<project-name>}"
mkdir -p "$(dirname "$PROJECT_DIR")"
npx hyperframes init "$PROJECT_DIR" --non-interactive --example=blank
```

Before init, follow the pinned no-skill-update contract in `../hyperframes/SKILL.md`; never refresh skills as a side effect.

**Constraints:** never `hyperframes init` in the workspace root; never nest another `hyperframes/` inside `PROJECT_DIR`; every Bash command (master + subagents) is a `(cd "$PROJECT_DIR" && ...)` subshell — never bare `cd`.

### Step 1 — Plan (Director Part 1)

Work directly, or delegate when useful and permitted under `../hyperframes-core/references/subagent-dispatch.md`. Context = relevant `agents/director.md` + `## Dispatch context` (`SKILL_DIR` / `PROJECT_DIR` / the user's request / `Schema: <SKILL_DIR>/references/shot-plan-ir.md`). It must:

1. **Decide: does this need a search?** (the first fork)
   - **No** → pick a **form category** (kinetic-type / stat / charts / logo-reveal / lower-thirds); content is user-supplied; `asset_needs: []`.
   - **Yes** → emit a **search plan** into `asset_needs[]` (news / web / tweet / image; two-pole queries). The specific **search-driven category** (webpage / news / tweet / asset-fusion) is confirmed by the content type returned in Step 2, and finalized in Step 3.
2. Write a draft `shot-plan.json` (envelope + chosen form category _or_ search intent + `asset_needs` + a one-paragraph shot brief). Schema: `references/shot-plan-ir.md`.

Validation: `[ -s "$PROJECT_DIR/shot-plan.json" ] && echo ok || echo missing`.

### Step 2 — Source ◇ (Bash: media-use, conditional)

If `shot-plan.json.asset_needs` is non-empty, resolve assets (search / generate / fetch → frozen project-local paths + ledger). See `phases/source/guide.md` (wraps `media-use resolve`; the search-driven categories use the news/web/tweet/image search). If `asset_needs` is empty, **skip to Step 3**.

```bash
# illustrative — see phases/source/guide.md
(cd "$PROJECT_DIR" && node <SKILL_DIR>/phases/source/resolve.mjs --plan ./shot-plan.json --out ./assets)
```

Degrade gracefully: if a selected source/provider is unavailable, report the limitation. Use asset-free design only if consistent with the approved brief; record any authorized change.

### Step 3 — Design (Director Part 2)

Work directly, or optionally delegate with context = `agents/director.md` Part 2 + dispatch context including the resolved `assets/index.md` if Step 2 ran + `catalog-map.md`. Design the shot **around the available assets**: pick the catalog block(s) + the `hyperframes-animation` rules/blueprints, the layout, the motion, beats, and (for `asset-fusion`) the `element_positions` + eyedropper palette. Finalizes `shot-plan.json` (`content.block` + `content.customize` + per-category content).

### Step 4 — Build (Builder, reuse-first)

Work directly, or optionally delegate with context = relevant `agents/builder.md` + dispatch context (`shot-plan.json`, `catalog-map.md`, the category's `module.md`, `references/motion-vocabulary.md`, `references/builder-contract.md`). **Reuse-first**: `npx hyperframes add <block>` + customize in place; hand-author only gaps + the asset-fusion affordance. Output `compositions/index.html` honoring the HF contract (paused GSAP timeline on `window.__timelines`, `class="clip"` + stable ids, `tl.seek(0)`, deterministic).

### Step 5 — Render (Bash)

```bash
(cd "$PROJECT_DIR" && npx hyperframes render . --skill=motion-graphics -q draft -o ./renders/video.mp4)
# transparent overlay variant: --format webm  (or mov)
```

### Step 6 — Verify (Bash → targeted repair on failure)

```bash
(cd "$PROJECT_DIR" && npx hyperframes lint . && npx hyperframes inspect .)
```

Passing checks are structural evidence. Inspect final rendered frames at relevant times, probe duration/audio and review playback as supported. On defects follow `agents/finalize.md` directly or with an allowed bounded worker; repair and recheck. Never change a fixed duration to hide a defect.

### Report + optional preview

Report the final output (`renders/video.mp4`, or the `.webm` / `.mov` overlay variant) + duration. **Don't open a preview during the run.** Offer one only on request, started **after** render so it serves the final file:

```bash
(cd "$PROJECT_DIR" && npx hyperframes preview)   # Studio UI; or `npx hyperframes play` for a shareable link
```

Flags live in the `hyperframes-cli` skill (`references/preview-render.md`).

## Resume table

| State                                                    | Continue from            |
| -------------------------------------------------------- | ------------------------ |
| no `shot-plan.json`                                      | Step 1 (plan)            |
| `shot-plan.json` has `asset_needs`, no `assets/`         | Step 2 (source)          |
| `shot-plan.json` final, no `compositions/index.html`     | Step 3/4 (design+build)  |
| `compositions/index.html` exists, no `renders/video.mp4` | Step 5 (render) + Step 6 |
| `renders/video.mp4` exists                               | Verify exact final media and prior evidence, then report |

## Design notes (maintainers — execution does not read this)

- **Asset-first rationale:** sourcing is front-loaded and informs shot design (the RWA flow: analyze → search → review → compose). the search-driven categories (`webpage`/`news`/`tweet`) and `asset-fusion` both lean on media-use search (news/web/tweet/image), which is media-use's documented RWA lineage.
- **Reuse-first:** the in-ecosystem analog of LLM-generated templates is "compose catalog blocks + `hyperframes-animation` rules". HF's paused GSAP timeline ≙ Remotion's `useCurrentFrame`.
- **Category module contract:** one `categories/<id>/module.md` (planning + build), sharing `references/motion-vocabulary.md` (+ optional eval). Adding a category = drop the folder + register its classifier line in `agents/director.md` + its row in `catalog-map.md`; the phase pipeline is untouched.
- **Directory shape:**
  ```
  videos/<project-name>/
    hyperframes.json  context.log
    shot-plan.json            # the IR (Director output)
    assets/  assets/index.md  # media-use output (if sourced)
    compositions/index.html   # Builder output
    renders/video.mp4
  ```
- **Registration:** in `hyperframes` router — add the "design-led short motion graphic" intent + Workflow description; carve the motion-graphics triggers out of `/general-video`; add reverse Do-NOT-use edges. See `motion-graphics-genre.md` §5-7.
