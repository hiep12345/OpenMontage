# OpenMontage - Agent Guide

Start with the request router and binding boundaries in [`AGENTS.md`](AGENTS.md).
This guide is a supporting operating reference, not a required full read on every
message. Read the sections selected by that router and the current stage/tool.
Previously read guidance may be reused while its source and task scope still apply.

For architecture, key files, and conventions see [`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md).

## Session recovery entry

For a new or resumed assigned task, `scripts/session_context.py` provides a
read-only project overview and explicitly selected task/run evidence. Follow
`docs/session-recovery.md`; keep cumulative decisions and partial work separate
from frozen stage receipts. This supplements the approved-resume protocol below
and cannot approve a gate, change a budget or start production.

## Approved Production Resume

An exact approved resume continues an identified run; it is not a new proposal.
Maintenance and read-only inspection of a run do not authorize production.

1. **Recover identity and scope.** Read `projects/<project-id>/project.json`, the
   selected manifest in `pipeline_defs/`, existing checkpoints, canonical artifacts
   and `decision_log.json`. Confirm the requested project, brief, approved assets,
   provider/model, `render_runtime`, composition mode, music, sample/batch mode and
   remaining authorized budget. Do not infer missing approval from a file's existence.
2. **Find the next authorized step.** Use
   `checkpoint.get_next_stage(pipeline_dir, project_id, pipeline_type)` and read that
   stage's checkpoint, including `metadata.partial_progress`. Load valid prior
   artifacts and skip verified completed units; do not overwrite history or regenerate
   completed assets merely because a new message arrived. Read **Stage Agents**,
   **Reviewer Protocol**, **Human Checkpoint Protocol**, **Communication Protocol**
   and `skills/meta/checkpoint-protocol.md` as needed for the recovered stage.
3. **Reuse valid choices and approvals.** Keep the exact approved plan. Do not
   repeat onboarding, generic provider/setup menus, concept proposals, runtime
   shortlists or music choices on every message. The runtime conversation and music
   plan belong to initial selection or a material revision, not an unchanged resume.
   Existing approval covers only the exact gate/scope it approved. An `awaiting_human`
   checkpoint still requires approval unless the current reply explicitly approves
   that artifact or an explicit recorded `approval_policy` covers that gate. An early
   "go ahead" never silently approves later gates. Assets approval precedes full render.
4. **Verify current execution conditions.** Inspect the selected tools' current
   registry contracts, availability and cost before execution. Read the current
   stage director and only the relevant used tools' `agent_skills` before tool calls;
   reuse already-read skills only while their source and scope remain applicable.
   Do not repeat the full preflight menu when the approved path is unchanged and
   still available. A changed capability, expired/missing evidence, budget shortfall
   or blocked approved path requires the relevant recheck and explicit blocker.
5. **Continue within authority.** Announce paid/consequential calls per **Decision
   Communication Contract** and stay within approved spend and sample/batch scope.
   Material provider/model/runtime/music/creative changes or additional unapproved
   spend require approval and an appended decision-log entry before execution.
   Validate stage artifacts/checkpoints and preserve manifest approval and QA gates.
   No resume approval by itself authorizes publishing.

For caption packaging, Hub handoff or publishing readiness, read **Caption website
acceptance** and `docs/caption-link-quality.md`. Retain exact caption/package,
asset/source and website-release binding; recheck evidence when that contract
requires it, including later-day resume. FAIL or NOT TESTED still blocks readiness
and new publishing approval. Preserve historical receipts and distinguish a sealed
accepted replay from a potentially new mutation; the delivery contract decides.
If identity, approval or scope cannot be established, stop the dependent production
action, surface the missing evidence and continue independent inspection.

## First Interaction — Onboarding

When the user's first message is vague, exploratory, or asks what you can do ("make me a video", "what can you do?", "help me create something", "I want to make content"), read the onboarding skill **before** doing anything else:

**Read:** `skills/meta/onboarding.md`

This skill teaches you to run discovery, classify the user's setup, present capabilities in plain language, and offer starter prompts tailored to their available tools. The goal: get the user from "curious" to "making a video" in under 60 seconds.

**Skip onboarding** when the user arrives with a specific, actionable request (e.g., "Make a 60-second explainer about black holes"). Go directly to Rule Zero.

## Reference Video Entry Point

When the user provides a **video URL or local video file as inspiration** — for example:

- "Can you make a video like this?"
- "I love this YouTube Short. Make me something similar."
- "Use this Reel as a reference."

— do **not** treat this as a generic web-search or prompt-writing request.

This is a first-class workflow in OpenMontage.

### Required behavior

1. **Read:** `skills/meta/video-reference-analyst.md`
2. **Run the reference analysis workflow** using the local analysis tools (`video_analyzer`, transcript extraction, scene detection, frame sampling)
3. **Produce a grounded summary** of what the reference is doing:
   - content
   - pacing
   - structure
   - style
   - what makes it work
4. **Then** run normal capability audit and pipeline selection
5. Present **2-3 differentiated concepts** for the user's version — not a carbon copy

### Important distinction

- **Reference-driven request:** "make me something like this" -> use `video-reference-analyst.md`
- **Source-footage request:** "edit this footage" / "cut this into clips" -> use `source_media_review` and the appropriate footage-led pipeline

If a model misses this distinction, it will often fall back to plain search + guesswork. That is incorrect for OpenMontage.

## Rule Zero — All Production Goes Through a Pipeline

**Every video production request MUST go through the pipeline system. No exceptions.**

When the user asks to make, create, produce, or generate any video content — a trailer, explainer, clip, animation, or any other video — the agent must:

1. **Identify the pipeline.** Match the request to one of the pipelines in `pipeline_defs/`. If unclear, ask the user.
2. **Read the pipeline manifest.** `pipeline_defs/<pipeline>.yaml` — know the stages, tools, and quality gates.
3. **Run preflight for a new production.** Verify selected required tools via the registry; present a relevant capability shortlist only for an unresolved choice. For an existing approved run, use **Approved Production Resume** instead of restarting selection.
4. **Execute stage by stage.** For EACH stage, read the stage director skill (`skills/pipelines/<pipeline>/<stage>-director.md`) BEFORE doing any work in that stage.
5. **Use the selected tool guidance.** Read the skills named by the selected tool's `agent_skills` contract before authoring its inputs. Director or tool content already read in the current stage packet counts; reuse it while source and task scope remain applicable. Consult other skills only for a concrete need.

**Do NOT:**
- Write ad-hoc Python scripts to call tools directly
- Skip the pipeline and go straight to API calls
- Generate assets without reading the stage director skill first
- Use a tool without checking its Layer 3 skill for prompting guidance
- Bypass preflight, checkpoints, or review

Skills provide task-specific guidance; their presence or a read receipt does not prove better output. Inspect the resulting artifact against the current brief and relevant acceptance criteria.

## What OpenMontage Is

OpenMontage is an instruction-driven video production system. The AI agent IS the intelligence — it reads instructions (pipeline manifests + stage director skills + meta skills) and drives the pipeline using tools.

```
Agent reads pipeline manifest (YAML) -> reads stage director skill (MD)
-> uses tools (Python BaseTool subclasses) -> self-reviews (meta skill)
-> checkpoints (Python utility) -> presents to human for approval
```

The agent owns creative direction and semantic review. Python supplies tools,
persistence and deterministic contract enforcement, including checkpoint/stage
validation and budget accounting. Manifest policy and recorded authority still
govern production; a successful runtime check is not creative or media approval.

### Caption website acceptance

For any link-bearing social package, read `docs/caption-link-quality.md` before
packaging or reporting Hub handoff readiness. Record a production owner, website
owner and reviewer. Obtain the exact production route from the website owner;
never generate a recipe slug just from its name. Verify URLs extracted from the
final caption files, exact source formula/media match and rendered primary action.
FAIL or NOT TESTED blocks handoff readiness and new publishing approval. A sealed
caption/hash and Hub file readiness do not establish website QA. The linked
checklist defines evidence, rechecks, operator responsibility and repair.

### Hub-bound MT episode identity

Before reserving or generating a new Mix Therapy episode that will go to Hub,
record its delivery plan in `projects/<id>/artifacts/delivery-plan.json` and carry
the sealed `planHash` in the proposal and decision log. Read
`docs/content-delivery.md`. Decide one episode's stable family/production/master
IDs and destination-to-file mapping at proposal time. Caption/package differences
alone use one `SHARED_ASSET` content ID; intentionally different rendered videos
use `PLATFORM_VARIANTS` with planned IDs, reasons and common master lineage.
Do not improvise these identities at packaging time or treat each destination as
a new lesson. Pass this plan to the maintained pre-generation reservation and
final batch ingest. The producer rejects missing, replaced, incomplete or
inconsistent plans before Hub calls. Review the actual renders and exact files
at the normal pipeline gates; plan validation does not establish visual QA or
authorize social publication. Preserve historical requests/receipts; never
retroactively attach a plan to a running or completed production.

An explicitly local-only MT production follows `docs/content-delivery.md` with
`--reserve --local-only` / `local_only=True`. This binds `LOCAL_ONLY` atomically
to the intent and still requires novelty evidence reads and normal production
gates. It does not authorize Hub delivery or publishing, and the intent cannot
later acquire a Hub plan. A later Hub-bound request requires a separately
authorized new production identity and the normal novelty/remake and plan checks;
preserve existing assets and receipts rather than retroactively relabelling them.

Core loop:

1. Select a pipeline.
2. Run preflight.
3. Discover real tools from the registry.
4. Present the user with concepts, tool plan, production plan, and cost.
5. Execute stage by stage with checkpoints.

## Decision Communication Contract

For any meaningful production decision, the agent must communicate the decision before acting. The user should never have to infer which provider, model, or render path was chosen after the fact.

### Announce Before Execution

Before any paid or consequential generation call, state:

- the exact tool name,
- the provider,
- the model or provider variant,
- the reason it was chosen,
- whether it is a sample or a batch run.

### Ask Before Major Changes

The agent must ask the user before changing any major production choice, including:

- switching provider,
- switching model family or provider variant,
- switching from video-led to still-led treatment,
- switching composition engine when that changes the output character,
- dropping narration, music, or other approved creative elements,
- changing from sample mode to batch mode.

Minor prompt refinements inside an already approved provider/model path do not require separate approval unless they materially change the creative direction.

### Re-log Changed Decisions (Binding)

The `decision_log` is the board's Decisions rail and the run's audit trail. It is **append-only history, not a scratchpad.** When a choice you already logged changes mid-run — the user swaps the voice, you switch provider/model/runtime/music, or a fallback overrides an earlier pick — you MUST **append a new `decision_log` entry** for the new choice, reusing the **same `category` AND the same `subject`** (e.g. `category: "voice_selection"`, `subject: "Narration TTS provider"`), with the superseded option moved into `options_considered` and `rejected_because` noting it was changed.

Editing only a downstream artifact (the `asset_manifest`, a prop) while leaving the old decision in the log is a defect: the board keeps showing the stale choice (e.g. `voice → openai_onyx` after the user moved to Chirp3). The board identifies a decision by its **(category, subject) pair** and renders the latest entry for that pair as current (tagged "revised") — so the fix is to append the new entry with an identical `subject`, never to silently mutate the old one or reword the subject (a reworded subject reads as a different decision and both will show). Keeping distinct decisions in one category (e.g. TTS vs image `provider_selection`) is exactly why the pair, not the category alone, is the key. This applies at every stage, not just `idea`.

### Composition Runtime Selection

Preserve a runtime already selected by the user or recorded in an approved brief,
including a new actionable brief with exact choices. Verify its current availability
from `video_compose.get_info()["render_engines"]`; an unavailable selected runtime is
a concrete blocker, not permission to silently substitute another.

When runtime choice is unresolved, compare the relevant available options for this
brief, explain material tradeoffs and recommend one. Present both Remotion and
HyperFrames when they are genuine alternatives for the requested outcome; no full
menu or repeat approval is required after an exact authorized choice. Record the
selected runtime, relevant alternatives and rationale in `decision_log`.

The manifest's approval gates, selected budget and publication boundaries remain
binding. Material changes require the applicable new authorization and an appended
decision entry; existing exact authorization is preserved for unchanged work.

### Composition Authoring Mode — Templated vs Atelier

Orthogonal to *runtime* is *authoring mode*: **how** the composition is built. Present it as its own proposal decision and log it in `decision_log` (`category: "composition_mode"`).

- **Templated** — assemble the stock `cut.type` scene-types (`text_card`, `stat_card`, `bar_chart`, …) into the `Explainer`/`CinematicRenderer` compositions. Fast, cheap, reliable — and the reason most videos look alike. Right for batch output, localization variants, quick drafts, and low-stakes internal clips.
- **Atelier** — hand-author subject-specific scenes and motion, rendered via `composition_mode: "atelier"` (see `video_compose` → `_render_via_atelier`). An explicitly selected series style may retain its palette, typography and motion language; the composition and source-specific choices still belong to this piece.

**Default to atelier for hero work** — marketing, launches, brand pieces, any single-deliverable explainer that must impress. Reuse engine knowledge and an explicitly selected visual method; do not silently substitute stock scenes or copy an unrelated finished composition. Before building, use **`skills/meta/taste-direction.md`** to set or recover the approved design read, then **`skills/meta/bespoke-composition.md`** for art direction, motion principles, engine mechanics and rendering. Review whether the subject, scene development and delivery promise are served. Reusing an authorized series look or revisiting one room is not a failure by itself; unchanged imagery with cosmetic recaptioning still needs a concrete story purpose. For photographic editorial room reveals, load `skills/creative/photographic-editorial-motion.md` only when that approach is selected. Preserve production approvals, assets/licensing and final video/audio acceptance; style reuse grants none of them.

### Escalate Blockers Explicitly

When a blocker occurs, the agent must surface it immediately using this structure:

1. What was attempted
2. What failed
3. Whether the issue is auth, provider access, tool bug, or prompt/design quality
4. What options exist next
5. Which option the agent recommends, with reasoning

Do not continue with a substitute path until the user approves.

### Recommendation Style

When asking the user to choose, do not just list options. The agent should:

- provide the shortlist,
- explain the tradeoffs briefly,
- recommend one option,
- wait for approval before proceeding.

### No Unilateral Substitutions

If the approved path is blocked, the agent may investigate and prepare alternatives, but may not execute those alternatives without user approval.

This applies especially to:

- provider swaps,
- model swaps,
- fallback tools,
- prompt-only substitutes for reference-driven generation,
- still-image animatics in place of true motion.

## Orchestrator

The agent itself orchestrates the production state machine:

`research -> proposal -> script -> scene_plan -> assets -> edit -> compose`

The agent:

1. Reads the pipeline manifest (`pipeline_defs/*.yaml`) to know the process
2. Calls `checkpoint.get_next_stage()` to find where to resume
3. Reads the stage's director skill (`skills/pipelines/<pipeline>/<stage>-director.md`) to know HOW
4. Uses tools (`tools/`) for concrete capabilities
5. Self-reviews using the reviewer meta skill (`skills/meta/reviewer.md`)
6. Checkpoints via the checkpoint protocol (`skills/meta/checkpoint-protocol.md`)
7. Presents to human for approval when `human_approval_default: true`

Infrastructure files:

- `lib/checkpoint.py` — read/write checkpoints, stage validation
- `tools/cost_tracker.py` — budget governance
- `lib/pipeline_loader.py` — manifest loading and helpers

## Project Directory Convention

Every production run uses the selected `PROJECTS_DIR` from `lib/paths.py`
(`OPENMONTAGE_PROJECTS_DIR`, otherwise this checkout's `projects/`). Recover the
assigned root before writing; a different current directory does not select a
different production. Preserve accepted assets, checkpoints and receipts;
gitignored, paid or stochastic outputs are not assumed reproducible.

```
projects/<project-name>/
├── artifacts/          # JSON artifacts from each stage (research_brief, script, scene_plan, etc.)
├── assets/
│   ├── images/         # Generated images (PNG)
│   ├── video/          # Generated video clips (MP4)
│   ├── audio/          # Narration segments + final mix (MP3/WAV)
│   ├── music/          # Background music track (MP3)
│   └── subtitles.srt   # Generated subtitles
└── renders/
    └── final.mp4       # Final rendered video (the deliverable)
```

**Naming convention**: Use kebab-case derived from the video title (e.g., `hidden-math-of-nature`, `how-music-rewires-brain`).

At pipeline initialization, before any stage runs:

1. **Initialize the workspace**: `python -c "from lib.checkpoint import init_project; init_project('<project-id>', title='<Title>', pipeline_type='<pipeline>')"` — creates the layout above and writes `project.json` (the marker the Backlot board reads).
2. **Open the board**: run `python -m backlot open <project-id>`. This starts the Backlot server if needed and opens the user's browser at the project's live board. If the command fails, continue the production — the board is an observer, never a blocker. This is the agent's ONLY board duty; the board derives everything else from disk.

All tools and agents must write outputs to these paths — **always pass an explicit `output_path` under `projects/<project-id>/`**. Assets written to the repo root, cwd, or temp dirs are invisible to the user's board and violate the workspace contract.

**This applies to atelier and HyperFrames-skill runs too**: hand-authored compositions still write the canonical artifacts they have (script or beats-plan, scene_plan-equivalent, asset manifest) plus checkpoints into `projects/<project-id>/`. The board is runtime-agnostic; only runs that skip the artifacts get a degraded board.

For maintenance, use the existing `make test` / `make test-contracts` targets or
`python -B scripts/run_tests.py <pytest arguments>`. Their invocation-owned temp
and cache are cleaned on success; failed/interrupted diagnostics are retained at
the reported path. These are separate from production workspaces. Clean only
owned artifacts after preserving needed evidence; historical fixtures, accepted
media and shared runtimes require their own dependency/owner decision.

## Music Library

Users can place royalty-free music tracks in `music_library/` (gitignored). When music choice is unresolved, the asset director may inspect this folder as one source. Its presence or absence does not authorize API generation or replacement of selected music.

```
music_library/
├── ambient_track.mp3
├── cinematic_epic.mp3
└── ...
```

For an unresolved music choice, suitable local tracks may be offered alongside other authorized options. Reuse an already approved exact track or no-music choice. See the proposal-director and asset-director skills for details.

## Available Pipelines

| Pipeline | Best For | Stability |
|----------|----------|-----------|
| `animated-explainer` | Topic to fully generated explainer | production |
| `talking-head` | Footage-led speaker videos | beta |
| `screen-demo` | Screen recordings and walkthroughs | production |
| `clip-factory` | Many clips from one long source | beta |
| `podcast-repurpose` | Podcast highlights and derivatives | beta |
| `cinematic` | Trailer, teaser, and mood-led edits | production |
| `animation` | Motion-graphics and animation-first videos | production |
| `character-animation` | Local rigged cartoon characters and reusable character acting | beta |
| `hybrid` | Source footage plus support visuals | production |
| `avatar-spokesperson` | Presenter-led avatar or lip-sync videos | production |
| `localization-dub` | Subtitle, dub, and translated variants | beta |
| `framework-smoke` | Test: minimal 2-stage smoke test | test |

> **Beta pipelines** have not been fully audited. They work, but expect rough edges. Mention this when the user selects one.

## Mandatory Preflight

Before creative work on a new production, read the selected manifest, verify its
required tools and the selected provider/runtime, and report relevant blockers or
degraded behavior. Recover exact choices and approvals already supplied by the
user; preflight does not restart their selection. Maintenance and inspection do
not run production preflight. An unchanged approved run follows **Approved
Production Resume**.

Use the selected tool's current registry contract and runtime information. A
configured key or advertised capability is not proof of account access or a
successful provider call. An available fallback does not authorize substitution.
Keep actual manifest approvals and spend boundaries before generation.

For requested capability exploration or when a narrow lookup is insufficient,
`registry.provider_menu_summary()` supplies a compact overview. Interpret only
relevant capabilities and runtime warnings; setup offers are optional and do not
prove a one-minute fix. Full `provider_menu()` / `support_envelope()` dumps are
diagnostic references, not mandatory context for every production.

### Task-Relevant Capability Discovery

Inspect registry contracts for capabilities needed by the selected pipeline.
Use `provider_menu_summary()` only when a narrow lookup is insufficient or the
user asks for broader exploration. Configuration is not proof of provider entitlement or successful calls.
Report relevant unavailable tools, degraded behavior and cost/budget uncertainty.
Preserve exact provider/model choices already authorized in the request or records.

For an unresolved choice or requested exploration, present a concise shortlist
from the registry, with material tradeoffs and a recommendation. Use the detailed
`provider_menu()` only for the relevant capability. Do not make the user review a
full catalog or setup options for unused providers just to continue an approved
task.

### Setup Offers for Relevant Blockers

Offer setup help when a missing capability blocks the requested or selected path,
or the user asks to explore it. Read that tool's current `install_instructions`;
explain the concrete requirement and applicable cost/privacy implications. Keep
secrets in approved local configuration, not chat or diagnostic logs.

An available fallback can proceed only within existing exact authorization.
Otherwise prepare the alternative and obtain the needed decision before its
consequential use. Continue independent authorized work while a genuine blocker
is unresolved. Do not install dependencies, switch provider or add paid samples
merely because a setup option exists.

### Composition Runtimes (Inside video_compose)

`video_compose` has **three** render engines / runtimes. They are parallel, not ranked — the choice is made at proposal and locked in `edit_decisions.render_runtime`. Check which are available:

```bash
python -c "
from tools.tool_registry import registry
registry.discover()
info = registry._tools['video_compose'].get_info()
print('Render engines:', info.get('render_engines'))
print('Remotion note:', info.get('remotion_note'))
print('HyperFrames note:', info.get('hyperframes_note'))
"
```

| Engine | Used For | Requires |
|--------|----------|----------|
| **FFmpeg** | Video-only cuts, concat, trim, subtitle burn | a verified `ffmpeg` binary |
| **Remotion** | React-based composition: still images → animated video, text cards, stat cards, charts, callouts, comparisons, transitions with spring physics, word-level caption burn, TalkingHead avatar | Node.js (`npx`) + `remotion-composer/` + `node_modules` |
| **HyperFrames** | HTML/CSS/GSAP composition: kinetic typography, product promos, launch reels, website-to-video, registry-block-driven scenes, SVG character rigs | Node.js ≥ 22 + FFmpeg + `npx` (consumed via `npx hyperframes`) |

`render_runtime` is **locked at proposal** (`proposal_packet.production_plan.render_runtime`) and **carried through edit_decisions unchanged**. `video_compose` routes based on this field; silent runtime swaps are forbidden. If the chosen runtime becomes unavailable at compose time, surface a structured blocker per "Escalate Blockers Explicitly" above. See `skills/core/hyperframes.md` for the Remotion-vs-HyperFrames decision matrix.

### Critical Rule: Motion-Required Requests

For any request where the deliverable inherently depends on motion rather than static coverage, treat motion as a hard requirement. Examples:

- sci-fi trailers,
- cinematic teasers built from generated clips,
- hype edits,
- avatar or agent videos,
- any brief whose promise depends on moving shots rather than still frames.

For these requests:

- The `render_runtime` chosen at proposal (Remotion, HyperFrames, or FFmpeg) must be confirmed available up front if the planned visual treatment depends on it.
- Still-image fallback is forbidden. Do not quietly convert the job into a Ken Burns teaser, animatic, or slide-based video.
- FFmpeg-only fallback is forbidden when it changes the approved deliverable from motion-led video to still-led video.
- **Silent runtime swap is forbidden.** If `render_runtime="hyperframes"` was locked and HyperFrames is unavailable, do NOT route to Remotion instead. Surface the blocker, propose options, get user approval, log a `render_runtime_selection` decision — then proceed.
- Bubble critical issues immediately. If the chosen runtime is unavailable, fails to render, or provider clip generation fails in a way that blocks the approved treatment, stop and tell the user before proceeding.
- Do not spend more tokens or time on downgraded output unless the user explicitly approves the downgrade as an animatic or proof-of-concept.

**When runtime choice is unresolved and Remotion is a suitable available option**, these are illustrative approaches:
- Explainer videos with `flat-motion-graphics` playbook -> Remotion animated scenes, not Ken Burns
- Data-driven videos -> Remotion stat cards and charts, not static image screenshots
- Any pipeline using still images -> Remotion spring animations, not FFmpeg pan-and-zoom
- **Screen demos of a CLI/terminal/install flow -> `TerminalScene` (synthetic screen recording), not OS-level capture.** See `.agents/skills/synthetic-screen-recording/SKILL.md`. Faster, deterministic, privacy-safe. Use real capture (`screen_recorder`, `cap_recorder`, `playwright-recording`) only when the demo is a real app UI or requires unpredictable live behavior.

### Remotion scene types available in `remotion-composer/`

See `remotion-composer/SCENE_TYPES.md` for the authoritative list and their cut schemas. Current scene types usable via `cut.type`:
`text_card`, `stat_card`, `callout`, `comparison`, `hero_title`, `terminal_scene`, `anime_scene`, `bar_chart`, `line_chart`, `pie_chart`, `kpi_grid`, `progress_bar`. Overlay types include `section_title`, `stat_reveal`, `hero_title`, `provider_chip`.

These stock scene-types are the **templated** path — fast and reliable, but they are why videos look alike. For **hero work, prefer atelier mode** (hand-authored composition) over this catalog; read those types as a *mechanics codex*, not a menu to assemble. See "Composition Authoring Mode" above and `skills/meta/bespoke-composition.md`.

FFmpeg Ken Burns may be considered for an unresolved runtime choice when the requested deliverable permits still-image motion and the actual tool contract supports it. Availability of a fallback does not authorize changing an exact selected runtime or delivery promise. An unavailable authorized runtime is a blocker; report it and resolve the necessary choice before dependent rendering.

When `render_runtime="hyperframes"` is locked and HyperFrames is unavailable (Node < 22, missing `ffmpeg`/`npx`, or `hyperframes doctor` reports issues), that's also a blocker. Do not substitute Remotion or FFmpeg without user approval + a logged `render_runtime_selection` decision.

Routing is automatic — `video_compose` reads `edit_decisions.render_runtime` and dispatches to the matching engine (`_render_via_hyperframes`, `_remotion_render`, or `_render_via_ffmpeg`). Inspect relevant runtime alternatives when the choice is unresolved, and preserve a runtime already selected and authorized. Don't default to Remotion for motion-graphics-heavy concepts that HTML/GSAP would express more naturally, and don't default to HyperFrames for briefs that reuse the existing React scene stack.

## Capability Discovery

OpenMontage uses two layers for capability choice:

- selector tools: capability-level routing such as `tts_selector` and `video_selector`
- provider tools: concrete tools discovered via the registry that call a specific backend

Inspect the selected tool contract before use. The following full catalogs are optional for unresolved choices, exploration or diagnosis:

```bash
python -c "from tools.tool_registry import registry; import json; registry.discover(); print(json.dumps(registry.capability_catalog(), indent=2))"
python -c "from tools.tool_registry import registry; import json; registry.discover(); print(json.dumps(registry.provider_catalog(), indent=2))"
```

For finalist tools inspect:

- `capability`
- `provider`
- `usage_location`
- `supports`
- `fallback_tools`
- `related_skills`

Do not rely on memory or old docs when the registry can answer it.

## Tool Families

**Do not treat remembered tool lists as current availability.** Inspect the selected contracts; broader catalog queries below are optional:

```bash
# See all tools grouped by capability (TTS, video_generation, image_generation, etc.)
python -c "from tools.tool_registry import registry; import json; registry.discover(); print(json.dumps(registry.capability_catalog(), indent=2))"

# See all tools grouped by provider (elevenlabs, openai, ffmpeg, etc.)
python -c "from tools.tool_registry import registry; import json; registry.discover(); print(json.dumps(registry.provider_catalog(), indent=2))"
```

Key capability families to look for in the output:

- **tts** — Text-to-speech providers. Route via `tts_selector`.
- **video_generation** — Video generation providers (cloud, local GPU, stock). Route via `video_selector`.
- **image_generation** — Image generation providers (cloud, local GPU, stock). Route via `image_selector`.
- **music_generation** — Music and sound effect generation.
- **video_post** — Composition, stitching, trimming (FFmpeg-based, always local).
- **audio_processing** — Mixing, enhancement (FFmpeg-based, always local).
- **analysis** — Transcription, scene detection, frame sampling.
- **avatar** — Talking head and lip sync generation.
- **character_animation** — Local character specs, SVG rigs, pose libraries, action timelines, previews, and QA.
- **3d_world_generation** — Local semantic terrain, procedural biome scattering, explicit landmarks, diagnostic passes, and deterministic HyperFrames/Three.js camera fly-throughs. Route through `threejs_world` and read `skills/creative/3d-world-generation.md` plus `.agents/skills/threejs-world-generation/SKILL.md`.
- **3d_asset_acquisition** — Rights-safe GLTF/GLB catalogs for production-tier Three.js worlds. Route through `threejs_asset_catalog`; never substitute blockout primitives for a requested detailed or reference-grade environment.
- **3d_asset_generation** — Unique textured/PBR meshes from text or concept images. Route text-described hero assets through `atlas_3d`, image-conditioned assets and regional object extraction through `fal_3d`, and read `.agents/skills/3d-asset-generation/SKILL.md`. Announce provider/model/unit cost before every first paid call and sample before batching.
- **3d_world_rendering** — Production assembly, terrain, lighting, materials, camera, and image-sequence rendering in Blender. Route through `blender_world`; use Three.js for interactive/blockout review, not as a substitute for Blender when reference-grade scene density is requested.
- **enhancement** — Upscale, background removal, face enhance, color grading.

Each tool in the registry declares `best_for`, `install_instructions`, `runtime` (LOCAL, API, LOCAL_GPU, HYBRID), and `status`. Read these fields — do not assume tool strengths from memory.

### Tool Class Naming Convention

All tool classes use **PascalCase without a "Tool" suffix**. When importing tools in Python:

| Module | Class Name | NOT |
|--------|-----------|-----|
| `tools.audio.music_gen` | `MusicGen` | ~~MusicGenTool~~ |
| `tools.video.video_compose` | `VideoCompose` | ~~VideoComposeTool~~ |
| `tools.audio.audio_mixer` | `AudioMixer` | ~~AudioMixerTool~~ |
| `tools.tts.elevenlabs_tts` | `ElevenLabsTTS` | ~~ElevenLabsTTSTool~~ |
| `tools.analysis.transcriber` | `Transcriber` | ~~TranscriberTool~~ |
| `tools.subtitle.subtitle_gen` | `SubtitleGen` | ~~SubtitleGenTool~~ |

When in doubt, check: `grep "^class " tools/<path>.py`

All tools call via `.execute(params_dict)` (returns `ToolResult` with `.success`, `.data`, `.error`), NOT `.run()`.

### Selector Pattern

Three selector tools abstract multi-provider capabilities. **Selectors auto-discover providers from the registry.** Adding a new provider tool automatically makes it available through the selector — no selector code changes needed.

| Selector | Routes to | How it discovers |
|----------|-----------|-----------------|
| `tts_selector` | All tools with `capability="tts"` (ElevenLabs, Google TTS, OpenAI, Piper, Azure, fish.audio) | `registry.get_by_capability("tts")` |
| `image_selector` | All tools with `capability="image_generation"` (FLUX, Google Imagen, GPT Image, Recraft, etc.) | `registry.get_by_capability("image_generation")` |
| `video_selector` | All tools with `capability="video_generation"` | `registry.get_by_capability("video_generation")` |

Selectors route based on: user preference > availability > discovery order. They adapt input schemas between providers transparently.

## User-Facing Planning Protocol

Recover the requested outcome, exact selected choices, existing authorization,
budget and relevant manifest gates. This applies to new production as well as an
approved resume. A new request with exact choices does not require rediscovering
or reconfirming those choices.

When the brief is open, propose enough distinct directions to resolve it; no fixed
concept count is required. Explain the recommended pipeline/tool path, material
alternatives, cost uncertainty and stage plan. Ask only unresolved decisions that
materially affect the outcome. Record the agreed scope before dependent generation
and preserve the manifest's actual asset/proposal approval gates.

Reuse exact recorded approval for its scope. A materially changed plan, provider,
runtime or budget still requires applicable authorization and append-only decision
history; production approval does not authorize publishing.

### Music Choice

Establish the requested music or no-music choice before dependent asset work.
Reuse a track, provider, voice or no-music choice already authorized for the exact
scope. When the choice is unresolved, inspect only the relevant library, search or
generation capability and offer useful options with licensing/cost implications.
No mandatory tour of every music provider is needed. For an unresolved source
choice, inspect the relevant results from `registry.get_by_capability("music_library")`,
`registry.get_by_capability("music_search")` and
`registry.get_by_capability("music_generation")`; do not silently omit a useful
source category or generate a sample without authorized spend.

If a required selected source is unavailable, report that blocker and prepare
alternatives without silently dropping music or changing provider. Record the
chosen source and its provenance in the proposal/brief for the asset stage.

## Pipeline Asset Expectations

Each pipeline manifest's `tools_available` field declares what tools a stage can use. Use selectors for multi-provider capabilities — the selector handles routing to whatever is available. Read the pipeline manifest for the authoritative list per stage.

## Stage Agents

Each stage produces one canonical artifact that becomes the contract for the next stage. The stage director skill teaches the agent HOW to produce it.

| Stage | Director Skill | Canonical output | Core quality bar |
|------|---------------|------------------|------------------|
| `idea` | `*-director.md` | `brief` | Clear hook, target platform, duration, tone, and user intent |
| `script` | `*-director.md` | `script` | Structured sections, valid timing, coherent narration |
| `scene_plan` | `*-director.md` | `scene_plan` | Ordered scenes, timings, asset requirements |
| `assets` | `*-director.md` | `asset_manifest` | Provenance, paths, model/tool metadata, scene linkage |
| `edit` | `*-director.md` | `edit_decisions` | Concrete cuts, overlays, subtitle/music decisions |
| `compose` | `*-director.md` | `render_report` | Output paths, encoding profile, verification notes |

Stage contract rules:

- A completed or awaiting-human checkpoint must include the stage's canonical artifact.
- Canonical artifacts must validate against the JSON schema in `schemas/artifacts/`.
- Non-canonical outputs such as media files belong in stage-specific directories.
- Tools should record seeds/model versions for reproducibility.

## Reviewer Protocol

The reviewer is a meta skill (`skills/meta/reviewer.md`) — advisory, never directly blocks progression.

- Self-review after every stage execution, before checkpointing.
- Load `review_focus` items from the pipeline manifest for the current stage.
- Maximum two review rounds. After that, pass with warnings and move on.
- Findings categorized: critical (must fix), suggestion (should fix), nitpick (nice-to-have).
- Critical findings -> fix and re-review. Suggestions -> note and proceed.
- Check playbook `quality_rules` as constraints, not suggestions.

## Human Checkpoint Protocol

The checkpoint protocol meta skill (`skills/meta/checkpoint-protocol.md`) teaches the agent when to pause:

- Read `human_approval_default` from the pipeline manifest per stage. **The manifest value is binding** — never re-judge it. `lib/checkpoint.py` enforces this: a gated stage cannot be written `completed` without `human_approved=True`.
- Typical gated stages: `idea`/`proposal`, `script`, `scene_plan`, **`assets`** (review the generated assets scene-by-scene — the Backlot board's filmstrip — before compose locks them in), and `publish` where the pipeline has one. Most pipelines auto-proceed on `edit` and `compose`, but not all (documentary-montage gates `edit`) — the manifest you loaded is the only authority.
- When approval is required: write the checkpoint as `awaiting_human`, present artifact summary, review findings, and cost snapshot — then **END YOUR TURN**. Doing further pipeline work in the same response is a gate violation.
- **Approval is per-gate.** An early "go ahead" never covers later gates; explicit full-run pre-authorization must be recorded as a `decision_log` entry (`category: "approval_policy"`) to count.
- Wait for human to approve, request revision, or abort.

## Communication Protocol

Agents coordinate through canonical JSON artifacts, checkpoints, pipeline manifests, and the tool registry.

Primary files:

- Artifact schemas: `schemas/artifacts/`
- Checkpoint schema: `schemas/checkpoints/checkpoint.schema.json`
- Pipeline manifest schema: `schemas/pipelines/pipeline_manifest.schema.json`
- Pipeline manifests: `pipeline_defs/`
- Style playbooks: `styles/*.yaml` (validated by `schemas/styles/playbook.schema.json`)
- Tool contract: `tools/base_tool.py`
- Tool registry: `tools/tool_registry.py`
- Stage director skills: `skills/pipelines/<pipeline>/<stage>-director.md`
- Meta skills: `skills/meta/*.md`

Checkpoint rules:

- Checkpoints live at `projects/<project_id>/checkpoint_<stage>.json` (the project workspace — this is what the Backlot board watches).
- `status` may be `completed`, `failed`, `awaiting_human`, or `in_progress`.
- Write an `in_progress` checkpoint on entering each stage; during `assets`/`compose`, refresh `metadata.partial_progress` after each completed scene/asset unit — this powers live progress on the board.
- `completed` and `awaiting_human` checkpoints must include the canonical artifact.
- A gated stage (`human_approval_default: true`) can only be written `completed` with `human_approved=True` — the writer raises a GATE VIOLATION otherwise.
- Superseded checkpoints are archived automatically to `projects/<project_id>/history/` — stage re-runs never destroy run history.
- Invalid checkpoints or invalid canonical artifacts are contract violations and should fail fast.

Pipeline manifest rules:

- Pipelines are declarative YAML manifests in `pipeline_defs/`.
- Stages declare: `skill` (director skill path), `produces`, `tools_available`, `review_focus`, `success_criteria`, `human_approval_default`.
- Adding a new pipeline requires a manifest + stage director skills.

Tool rules:

- Every production tool must inherit from `BaseTool`.
- Tool discovery flows through the registry, not ad hoc imports.
- Support-envelope reporting is the source of truth for capability, status, and resource requirements.

## Style Playbooks

| Playbook | Best For |
|----------|----------|
| `clean-professional` | Corporate, educational, SaaS |
| `premium-minimalist` | Investor updates, expert explainers, product narratives |
| `flat-motion-graphics` | Social media, TikTok, startups |
| `minimalist-diagram` | Technical deep-dives, architecture |
| `ink-sketch` (Ink Theater) | Hand-drawn ink-on-white doodle animation; a character that draws itself, walks, dances; contraption explainers |

For custom, atelier, brand, launch, or hero work, read `skills/meta/taste-direction.md` before choosing a playbook. Carry its `taste_profile` into the proposal so later stages can preserve the design read, visual variance, motion intensity, information density, reference strategy, and anti-patterns.

### Hand-drawn "doodle" animation → Ink Theater / Ink Puppet

For any brief that wants a **hand-drawn ink doodle** look — "a sketch that comes to life", "a pencil / stick figure that walks or dances", "a little character that acts out the idea", whiteboard-doodle explainers — use the **Ink Theater** engine + **Ink Puppet** mocap system (`skills/creative/ink-theater.md`, `ink-theater/README.md`). It is a **style + reusable engine, not a new pipeline**: illustration / contraption pieces run on the `animation` pipeline; a mocap character (draws itself → walks / dances / waves via `InkPuppet.choreograph([...])`) runs on `character-animation`. Cross-tool entry points: **`/ink-art`** (create a vector doodle from scratch) and **`/animated-drawing`** (animate a *supplied* drawing with mocap — raster; `skills/creative/animated-drawing.md`). Never hand-tune character motion — the agent only chooses named mocap clips.

## Layer Map

OpenMontage has three instruction layers:

1. `tools/`
   What exists, what is available, cost, runtime, fallback, related skills.
2. `skills/`
   How OpenMontage wants those tools used in pipelines.
3. `.agents/skills/`
   Raw vendor or technology knowledge.

Reading order:

1. registry / tool contract — discover what's available
2. relevant pipeline or creative skill (Layer 2) — know HOW to use it in this context
3. underlying vendor skill (Layer 3) — **mandatory before calling any generation tool**

**Use the narrowest relevant source.** For normal tool use, read the selected contract and its applicable skill sections. Reuse content already read; do not reload the director, provider guidance or catalog merely because another stage or message started.

**Exception: debugging, audits, and verifying the governance contract.** When a skill and a tool disagree, or when something behaves differently than the skill claims, reading the tool source is fair game — that's often the only way to catch a silent-availability bug or a stale doc string. An audit that refuses to look at the implementation will miss exactly the bugs that matter most. If you do read source to debug, consider whether the finding belongs in a skill update afterward so the next agent doesn't need to repeat the dive.

**Layer 3 is not optional for the selected tool.** Follow its current `agent_skills` references when writing prompts or selecting parameters. Other providers and table categories are conditional references. A skill cannot override the approved model, runtime, budget or publication authority; missing or conflicting guidance requires checking the actual contract.

Example: Before calling `kling_video`, read its `agent_skills` → `ai-video-gen` → get Kling-specific prompt structure, camera direction syntax, and quality keywords that the model responds to best.

### Layer 3 skills, by category

The `.agents/skills/` directory is large. When you're not coming in through a tool's `agent_skills` pointer, use this table to find the right file by *what you're trying to do*:

| Category | Skills |
|---|---|
| **Composition runtime** | `remotion`, `remotion-best-practices`, `synthetic-screen-recording` (fake terminal/UI demos via Remotion TerminalScene), `threejs-world-generation` (semantic terrain and free-viewpoint HyperFrames worlds) |
| **Animation knowledge (generic)** | `gsap-core`, `gsap-timeline`, `gsap-plugins` (SplitText / MorphSVG / DrawSVG / MotionPath / Flip / CustomEase), `gsap-utils`, `gsap-react`, `gsap-performance`, `gsap-scrolltrigger`, `gsap-frameworks`, `framer-motion` (Disney 12 principles), `lottie-bodymovin` (Lottie export) |
| **Character animation** | `character-rigging`, `svg-character-animation`, `pose-library-design`, `canvas-procedural-animation`, `character-animation-qa` |
| **Image generation** | `bfl-api`, `flux-best-practices` |
| **Video generation** | `seedance-2-0` (when the selected adapter/model supports the requested cinematic, multi-shot or audio workflow), `gemini-omni` (conversational video editing, reference tags, timecoded beats), `ai-video-gen`, `ltx2` |
| **Audio** | `elevenlabs`, `music`, `sound-effects`, `acestep`, `text-to-speech`, `azure-text-to-speech` (optional cloud TTS — tool `azure_tts`, same Speech key as `azure_stt`), `setup-api-key` |
| **Speech-to-text** | Registered `transcriber` / selected `video-understand` local transcription contract (offline only with required dependencies and weights already installed); `speech-to-text` is ElevenLabs Scribe cloud and applies only when selected, `azure-speech-to-text` (optional cloud STT — tool `azure_stt`, when Azure is selected and actual account access is verified) |
| **Avatar / lip-sync** | `avatar-video`, `heygen`, `create-video`, `faceswap`, `video-translate`, `agents` |
| **Capture** | `playwright-recording` (browser flows), `ffmpeg` (post) |
| **Visualization** | `beautiful-mermaid`, `d3-viz`, `manim-composer`, `manimce-best-practices`, `manimgl-best-practices` |
| **Media editing** | `video-edit`, `video-download`, `video-understand`, `video-toolkit`, `visual-style` |

**When in doubt, read the category's meta routing file first:**
- Picking an animation runtime? → `skills/meta/animation-runtime-selector.md` routes between Remotion primitives, GSAP plugins, framer-motion, Lottie, Manim, D3.
- Picking a screen-recording mode (real capture vs synthetic terminal)? → `pipeline_defs/screen-demo.yaml` + `skills/pipelines/screen-demo/idea-director.md`.

## Quick Lookup

| Question | Where to look |
|----------|---------------|
| What tools exist? | `tools/tool_registry.py` and `registry.support_envelope()` |
| What providers are available for a capability? | `registry.capability_catalog()` |
| What tools exist for a vendor? | `registry.provider_catalog()` |
| How does a tool actually work? | the tool's `usage_location` from the registry |
| How should this pipeline stage behave? | `skills/pipelines/<pipeline>/...` |
| What is the checkpoint/review policy? | `skills/meta/` |

## What Not To Do

- **Do not bypass the pipeline.** Never write ad-hoc scripts to call tools directly. All production goes through pipeline stages with director skills. See Rule Zero.
- **Do not call generation tools without reading their Layer 3 skill.** Check the tool's `agent_skills` field, read the referenced skill, then craft your prompts using that guidance.
- **Do not skip stage director skills.** Before executing any pipeline stage, read its director skill. The skill contains the quality bar, the workflow, and the review criteria.
- Do not use deleted legacy names such as `tts_cloud`, `tts_engine`, or `video_gen`.
- Do not hardcode provider names, API key names, or setup URLs. Read them from the registry's `install_instructions` and `dependencies` fields.
- Do not tell a restricted shared-installation user to add credentials manually, create a `.env`, or export a key. Surface the unavailable provider as an administrator setup request and continue only with centrally provisioned capabilities.
- Before offering a direct vendor credential, check the registry for an available wrapper through an already configured provider (for example, a partner model hosted by fal.ai).
- Do not begin asset generation before user approval on the production plan.
- Do not hide degraded paths. Record substitutions and blocked options explicitly.
- For an unavailable capability that blocks this task, explain the relevant supported alternatives and preserve the authorized provider/runtime. Do not expand an exact approved task into a full provider catalog.
- Use Task-Relevant Capability Discovery at preflight. A provider menu is useful only for an unresolved choice; existing exact authorization does not require another menu.
- Do not change provider, model, or render path without telling the user first and getting approval when the change is material.
