# App and UI motion patterns — optional reference

Read a matching pattern when an approved app/product promotion or UI-motion
concept needs a concrete brief. Use only the relevant section. An unchanged
approved resume does not require another reference read or approval.

## Sources and evidence limits

Text reviewed on 2026-10-24 from
[`yihui-dev/awesome-opus5-5-videos` at `92aee2f`](https://github.com/yihui-dev/awesome-opus5-5-videos/tree/92aee2f586ac0715cb3cbcb6384834f98a33383d).
The collection provides prompts/post excerpts and links to originals/remakes,
not the original executable projects or a reproducibility guarantee.

| Source | Useful part | Limit when adapting |
|---|---|---|
| [SaaS Launch Video Animation — @Screeendev](https://github.com/yihui-dev/awesome-opus5-5-videos/blob/92aee2f586ac0715cb3cbcb6384834f98a33383d/prompts/screeendev-981790.md), [original post](https://x.com/Screeendev/status/2108333630623981790) | A short product story using interface interaction, cursor, typing and purposeful zooms | The published excerpt is truncated and depends on the author's app repository. Its Remotion mention does not select or replace this run's authorized runtime. |
| [UI Motion Loop Design — @flxrnc](https://github.com/yihui-dev/awesome-opus5-5-videos/blob/92aee2f586ac0715cb3cbcb6384834f98a33383d/prompts/flxrnc-251921.md), [original post](https://x.com/flxrnc/status/2108242454105251921) | Named states, timed beats, cursor/target continuity, deterministic seeking and loop closure | Its 14-second square canvas, frame rate, colors and spring constants are one example, not OpenMontage defaults. A rendered result is not bundled with the prompt. |

These adaptations have not been render-tested with Sol/Astra. The repository's
Opus label is source attribution, not a requirement to change Codex model or
media provider. The repo carries an
[MIT license](https://github.com/yihui-dev/awesome-opus5-5-videos/blob/92aee2f586ac0715cb3cbcb6384834f98a33383d/LICENSE),
while its credits attribute videos/prompts to their creators. Retain attribution;
linked media, app screenshots, logos, fonts and music need their own reuse basis.

## Product promotion: show one real outcome

Use the selected app release and approved source material. Establish one viewer
problem, show a real action, then make its result visible. Tie camera emphasis
and cursor motion to that action rather than animating unrelated interface cards.
Capture or verify a website only within the task's actual owner/access scope;
otherwise obtain the owner's release-bound captures and evidence. Do not invent
features, values, destinations or permission to explore/deploy the app.

Adaptable brief wording:

> Show [audience] how [existing feature] achieves [observable result], using
> [approved interface captures and release]. Fit the story to [duration, aspect
> ratio and safe areas]. Open with the need, demonstrate the decisive interaction,
> hold its result long enough to understand, then end with [approved ending].
> Keep the pointer attached to its interaction target. Use zooms only where they
> improve comprehension; keep important text legible throughout the movement.

The source's 15–30 seconds is a useful starting point for a short launch clip,
not a compulsory duration. Existing website-to-video references cover capture
and authoring when that path is selected; do not introduce another artifact store.

## UI motion: explicit states and time

Name the actual states and transitions from the approved story. Specify relevant
durations, holds, easing and target positions in the canonical script/scene plan;
use the selected runtime's supported timing contract. A continuous morph is useful
only when the depicted objects can retain their identity across those states.

Adaptable brief wording:

> Animate [object] through [states] at [timed beats]. Keep its identity and the
> pointer-to-target relationship continuous. Give each meaningful state a readable
> hold. Use [palette and type] from the approved design. Make the animation seekable
> at any timestamp; use a seamless ending only if the brief actually asks for a loop.

HyperFrames authoring follows its existing paused/seekable timeline contract;
Remotion follows its frame-driven contract when selected. Do not copy a standalone
Canvas `renderAt(t)` entrypoint over the runtime's required integration. Animation
state should derive from the selected time/frame without render-time clocks or
unseeded randomness, as required by that runtime's existing rules.

For a loop of duration T, compare the same phase at t and t+T and inspect the
decoded wrap in motion. The last encoded frame is normally T−1/fps; it need not
be pixel-identical to the first. Use timing/overlap snapshots to diagnose a defect,
not as a substitute for watching the finished movement and relevant audio.

## Apply and learn within the existing run

Use the current script, scene plan and decision evidence to retain the selected
source, adaptation reason, exact output identity and observed corrections.
Existing model/runtime selection, approvals, spend, media review and publication
boundaries remain authoritative. This reference installs nothing and adds no
mandatory benchmark, additional agent, model pass or production request.

Evaluate whether viewers can understand the demonstrated feature, text remains
readable and movement supports the intended result. Review the complete relevant
video/audio under the run's existing requirements. Keep, revise or discard the
adaptation from actual completion/rework and owner feedback; source popularity,
frame checks and offline tests do not establish quality or cost improvements.
