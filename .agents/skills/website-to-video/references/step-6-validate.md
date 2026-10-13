# Step 6: Validate and deliver

Verify the assembled project against the approved STORYBOARD.md and DESIGN.md.
Preserve source/media authority and existing project gates. Automated checks,
rendered-frame inspection, motion playback and listening are distinct evidence.

## Structural checks

Use the pinned CLI from the actual project directory:

```bash
npx hyperframes lint <project-dir>
npx hyperframes validate <project-dir>
```

Inspect relevant source for each changed beat and its mount/timing integration.
Reuse evidence for unchanged source; do not repeat a full file read as ceremony.
Confirm referenced assets exist, audio/caption timing uses measured source data,
and compositions mount at the intended start/duration with unique IDs.

The optional diagnostic scripts are resolved from the loaded skill directories:

```bash
node "$ANIMATION_SKILL_DIR/scripts/animation-map.mjs" <project-dir>
node "$SKILL_DIR/scripts/w2h-verify.mjs" <project-dir>
```

`SKILL_DIR` is this website-to-video skill; `ANIMATION_SKILL_DIR` is the sibling
hyperframes-animation directory. Inspect current script options before use.
The legacy w2h report includes heuristic font-size/motion-density thresholds;
these do not override an approved minimalist design or prove visual quality.
Investigate each relevant finding, preserve the raw report, and explain any
inapplicable heuristic. Never weaken an actual project acceptance requirement.

## Rendered frames

Capture representative states for every beat: entrances, readable holds, dense
text, scene boundaries/transitions, the first and final frame. Expand coverage
when defects or timing anomalies appear. There is no fixed screenshot formula.

```bash
npx hyperframes snapshot <project-dir> --at <comma-separated-seconds>
```

Check that the installed snapshot path does not send frames to a cloud reviewer
unless that provider/data use is authorized. Native image inspection is sufficient
for a local review; Gemini-generated descriptions are optional external evidence,
not ground truth. Label any saved descriptions with their actual author/source.

Read the captured pixels. Check blank frames, clipped/truncated text, readable
quantities, hierarchy, spacing, alignment, contrast, source fidelity, visible brand
assets and actual storyboard content. Inspect the assembled page after all workers
finish: isolated worker captures cannot prove transition or mount correctness.
Repair visible defects and recheck affected and adjacent states.

## Motion and audio

Still frames do not establish motion smoothness or audio synchronization. Use a
supported local preview/player or the rendered MP4 to check transitions, holds,
narration intelligibility, SFX cue timing and music balance. Probe audio/video
duration and explain any intentional tail; do not treat file existence or a
provider's requested duration as the measured result.

If playback/listening is unavailable, mark those areas NOT TESTED with the concrete
limitation. Preserve independently completed checks. A missing required audio track
blocks final acceptance; omit optional audio only within the brief and disclose it.

A fresh review can help when risk warrants it and native/project delegation permits.
It is optional, has bounded scope, and follows the shared dispatch reference; do not
spawn a critic solely to satisfy a checklist or bypass a no-child rule.

## Render and handoff

Render the requested final video once applicable project gates are satisfied.
Reuse recorded exact-scope render approval; passing checks alone does not authorize
an unapproved production gate. Publication/upload remains separate authority.

```bash
npx hyperframes render <project-dir> --output <task-owned-output.mp4>
```

Verify the actual final file and report its path, measured duration and source/
release identity. If a preview was requested, provide the supported local preview
as well. Summarize PASS/FAIL/NOT TESTED for structural checks, rendered states,
motion and audio, linking retained evidence rather than pasting large raw logs.
Do not claim physical-device testing or customer usability without such evidence.
