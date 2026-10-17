# Photographic editorial motion

Read when an approved photographic transformation, interior/material story or
product detail sequence needs editorial motion, especially with the selected
`photographic-editorial` playbook. This is an authoring reference for the existing
animation pipeline and authored HyperFrames route, not a new runtime or pipeline.
It does not apply automatically to unrelated animation or Mix Therapy videos.
Preserve authorized runtime, scope, providers, spend, sample choices and approval
gates. Resolve an unavailable runtime as a blocker, never a silent substitution.

## Inputs and visual truth

Use authorized local photographs with explicit roles: **before**, optional
**intermediate** (furniture/material state), and **after** (finished room/product).
Record file paths, provenance, licenses and role mapping in canonical artifacts.
Optional music must have the required license/authorization and a local file;
music-only or silent output is valid. Narration is not required by this style.
Do not bundle sample photographs, music or private machine paths into the repo.

Compare camera position, geometry, crop and landmarks before selecting motion:

- Same perspective: align images once, keep identical object-fit/crop/scale and
  position, then animate opaque masks to reveal furniture or finishing states.
  Do not zoom one layer during a matched reveal or interpolate room geometry.
- Different perspectives: reveal an intentionally opaque cream editorial page,
  change the underlying room only while fully covered, then lift the page. Make
  the cut legible as editorial storytelling, not evidence of a physical action.

Use terracotta/pale oak/cream and Georgia display with Arial labels as defaults,
adapting to approved brand colors and available local fonts. Derive CSS tokens
with `style_bridge(load_playbook("photographic-editorial"))`; apply them to the
authored `:root`. `render_existing` preserves files and will not apply playbook
tokens for you. Use licensed local font files or available system fallbacks;
never require a font CDN. Reframe layouts for the actual aspect ratio, keeping
labels readable and the room payoff unobstructed.

## Adaptable beat map

This six-beat 1080x1920, 30 fps, 30-second example explains the method; beat
count, timing, resolution and duration follow the approved scene plan.

| Time | Meaningful change | Treatment |
|---|---|---|
| 0–3s | Empty space and invitation | Fixed before hero, short serif title, optional narrow after teaser |
| 3–8s | Furniture gives the room a purpose | Fixed-scale anchored masks reveal intermediate photograph |
| 8–13s | Material relationship becomes visible | Opaque cream page, deliberate terracotta/oak crop, short labels |
| 13–19s | Art and light add character | New opaque page and artwork/pendant crop; switch underlying after view while covered |
| 19–25s | Finished space is understood | Page lifts, invitation resolves, unobstructed room hold |
| 25–30s | Before/after relationship lands | Finished hero with readable before inset and restrained closing title |

For 15s, combine material/detail beats and shorten copy while preserving a real
payoff hold. Extend 15→30s by adding distinct material, art/light or functional
changes and enough time to inspect them. Extend 30→45s only with additional
meaningful details, alternate authorized views or useful room/comparison holds.
Do not merely slow all motion, repeat the same crop or stretch a 15s soundtrack.
Plan audio duration, edit points and fades for the chosen length.

## Authoring contract

Read `skills/core/hyperframes.md` plus the selected Layer 3 HyperFrames core and
animation contracts. Author in `projects/<slug>/hyperframes/`: `index.html`,
`vendor/gsap.min.js`, `assets/` (including optional local audio/fonts). Supply the
approved pinned GSAP distribution locally; no network dependency at render time.
Use full-frame opaque backing below all pages. The following is a small motion
pattern, not a finished six-beat template. Expand it from the approved scene plan.

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<script src="vendor/gsap.min.js"></script>
<style>
  html,body { margin:0; background:#F4ECDF; }
  #room-editorial { position:relative; width:1080px; height:1920px; overflow:hidden; }
  .backing,.room,.room img { position:absolute; inset:0; width:100%; height:100%; }
  .backing { background:#F4ECDF; }
  .room { overflow:hidden; }
  .room img { object-fit:cover; }
</style>
</head>
<body>
<main id="room-editorial" data-composition-id="room-editorial"
      data-width="1080" data-height="1920" data-fps="30" data-start="0" data-duration="30">
  <div class="backing"></div>
  <section id="room-study" class="clip" data-start="0" data-duration="30" data-track-index="0">
    <div class="room"><img src="assets/before.png" alt="Before room"></div>
    <div class="room" id="intermediate"><img src="assets/intermediate.png" alt="Furnished room"></div>
  </section>
</main>
<script>
  window.__timelines = window.__timelines || {};
  const tl = gsap.timeline({paused:true});
  gsap.set('#intermediate', {yPercent:100});
  gsap.set('#intermediate img', {yPercent:-100});
  tl.to('#intermediate', {yPercent:0, duration:2, ease:'power2.inOut'}, 3);
  tl.to('#intermediate img', {yPercent:0, duration:2, ease:'power2.inOut'}, 3);
  window.__timelines['room-editorial'] = tl;
</script>
</body>
</html>
```

The registry key, root `data-composition-id` and `bespoke.composition_id` must
match. Every timed visual/audio element uses `class="clip"`, `data-start`,
`data-duration` and `data-track-index` plus a stable unique `id`; give overlapping
clips distinct tracks. The paired transforms move the clipped wrapper and image
equally in opposite directions: the photograph stays anchored while its visible
area grows. This uses transform-only motion under the existing property contract.
The root's `data-duration` determines the output length; the completed reveal
simply holds from 5–30s in this minimal example. Do not add empty duration-padding
tweens. Expand the example with the approved meaningful beats and keep canonical,
root and audio durations consistent.
Optional audio is a direct child of the composition root, for example
`<audio id="music-bed" class="clip" src="assets/music.wav" data-start="0" data-duration="30"
data-track-index="1" data-volume="0.15"></audio>`. Author any edits/fades into
the local mix; render_existing does not build a mix from edit_decisions.
Use only the paused timeline for state: no autoplay, wall clocks, timers,
unseeded randomness or requestAnimationFrame animation. Set initial states and
explicit transition positions so arbitrary seeks reproduce the same frame.

## Existing artifact and compose route

Canonical `brief`, `script`, `scene_plan`, `asset_manifest`, `edit_decisions` and
decision log remain authoritative. Workspace DESIGN/SCRIPT/STORYBOARD documents
are derived authoring aids. The following minimal edit_decisions object uses the
current schema; a full production also retains its approved canonical artifacts:

```json
{
  "version": "1.0",
  "cuts": [],
  "renderer_family": "animation-first",
  "render_runtime": "hyperframes",
  "composition_mode": "atelier",
  "bespoke": {
    "entry": "projects/room-study/hyperframes/index.html",
    "composition_id": "room-editorial",
    "art_direction": "Fixed room reveals and opaque cream material pages; warm serif editorial hierarchy."
  },
  "metadata": {"playbook": "photographic-editorial"}
}
```

After the manifest's assets approval, call the existing tool (paths are relative
to the repository cwd; choose this project's actual slug):

```python
from tools.video.video_compose import VideoCompose

result = VideoCompose().execute({
    "operation": "render",
    "edit_decisions": edit_decisions,  # canonical object above
    "asset_manifest": asset_manifest,  # canonical local input/provenance records
    "workspace_path": "projects/room-study/hyperframes",
    "output_path": "projects/room-study/renders/final.mp4",
    "playbook_name": "photographic-editorial",
    "profile": "tiktok_vertical",
    "fps": 30,
    "quality": "standard",
})
if not result.success:
    raise RuntimeError(result.error)
```

`VideoCompose` routes the authorized atelier/HyperFrames choice to
`HyperFramesCompose.render_existing` without scaffolding over the authored HTML.
`workspace_path` selects the actual workspace; `bespoke.entry` documents the
entry and does not select a different HTML filename. Keep HTML dimensions, FPS,
duration and all canonical timings consistent with the approved deliverable.

## Review and authority

Run the existing lint/check/validate/render protocol and inspect final rendered
states at the intended output size: crop alignment, masks, opaque coverage,
text wrapping, safe margins, contrast and the unobstructed room payoff. Watch
the complete encoded motion including cuts/holds and listen to the complete
audio for timing, level, clipping, edits and ending. Technical checks and still
images cannot prove temporal or audio quality. Record PASS/FAIL/NOT_TESTED
separately; missing full motion/audio review remains NOT_TESTED. Reusing this
method is not production acceptance, publishing approval or evidence that the
original example passed full motion/audio QA.
