# Background music (BGM)

Retain the supplied or approved bed. Use the shared engine only when its current
routing can enforce the selected provider and spend. A HeyGen credential does not
authorize retrieval; absence does not authorize generation. Do not switch providers
or omit required music after failure without the applicable authority.

Google Lyria RealTime is cloud generation requiring network access and credentials.
MusicGen is local only after dependencies and weights are installed. Offline means
no Lyria call, no remote retrieval and no automatic package/model downloads. If the
engine cannot enforce that route, use the approved registered local adapter or
report the missing capability. See [preflight](../SKILL.md).

## Driving it from the request

`audio_request.json` → `bgm: { mode?, query?, prompt? }`:

- **`mode`** — `retrieve | generate | none`. Omit for **auto** (retrieve when credentialed, else generate). An **explicit** `retrieve` is strict: no credential ⇒ skip, never a detached generate (so a caller with no `wait-bgm` step, e.g. product-launch, can't get a pending job it won't await).
- **`query`** — the mood, used for retrieval and as a fallback prompt seed (e.g. a storyboard's `music:` field, falling back to `message` → `arc` → `"calm cinematic underscore"`).
- **`prompt`** — an explicit full prompt for generation; omit and the engine infers one (see Mood inference). Optional `blob` / `archetype` / `arc` feed that inference.

## HeyGen retrieval (when selected)

`searchSounds(query, "music", { limit: 5 })` → `GET /audio/sounds?query=<mood>&type=music&limit=5`. Take the top result (ranked by `score`), download its presigned `audio_url` → `assets/bgm/track.mp3`. Synchronous. No match → omit only if the brief makes BGM optional; otherwise block acceptance. Cue written to `audio_meta.json`:

```jsonc
{
  "path": "assets/bgm/track.mp3",
  "volume": 0.8,
  "mode": "retrieve",
  "query": "calm cinematic underscore",
  "duration_s": 42.0,
}
```

`volume` is 0.8 under narration, 0.9 for a silent film (no voice). `bgm_pending` is `false` — the file is on disk when the engine returns.

## Generation behavior and completion

The bundled engine may start a detached process. Persist its job/process metadata,
then run the skill-relative `scripts/wait-bgm.mjs` before assembly. Inspect its
`ready | failed | timeout | disabled` outcome and the actual media. A timeout
requires reconciliation with the same job, not another generation request.

Inspect `scripts/lib/bgm.mjs` and `scripts/lyria-recipe.py` only when using that
selected engine. Its Lyria/MusicGen auto-detection and dependency installation are
not authorization. Do not execute a route that could violate the approved offline,
provider or installation boundary. For MusicGen, looping one short seed to cover
longer durations is a derivation to disclose, not a newly generated full-length song.

## Mood inference (the generate prompt)

`inferBgmPrompt()` in `scripts/lib/bgm.mjs`: an explicit `prompt` wins; otherwise industry-keyword **base** → narrative-**archetype** shape → emotional-**arc** tiebreaker.

| Match in `blob` / `query`                              | Base prompt                                                                 | BPM |
| ------------------------------------------------------ | --------------------------------------------------------------------------- | --- |
| `crypto / nft / web3 / defi / token / blockchain`      | atmospheric electronic, deep bass, futuristic synths, restrained percussion | 100 |
| `finance / fintech / bank / payment / invest / wealth` | calm cinematic, soft strings, subtle piano, restrained percussion           | 92  |
| `creative / agency / design / studio / art / brand`    | playful electronic, warm pads, light percussion                             | 115 |
| _(default: SaaS / tech / platform)_                    | uplifting corporate tech, bright modern piano with synth pads               | 108 |

Archetype then reshapes the arc — PAS → "MINOR to MAJOR" build; BAB / future-pacing → aspirational rising; feature-cascade → +10 BPM driving; demo-loop → −8 BPM minimal. The emotional arc breaks remaining ties (tension→relief, excitement, trust/reassurance).

## Lyria knobs (direct recipe use)

The engine bakes BPM / scale into the **prompt text** (via the inference above) and passes only `--output` / `--duration` / `--prompt` to the recipe. If you invoke `scripts/lyria-recipe.py` directly you can also set: `--bpm` (90–110 calm, 110–130 energetic), `--brightness` (0–1, ≥0.7 promotional), `--density` (0–1, higher = fuller), `--scale` (`MAJOR` / `MINOR` / `PENTATONIC` / …), `--negative-prompt` (styles to exclude). MusicGen ignores all of these — put the mood in the prompt.

## Failure modes

| Failure                                       | Behavior                                                                                 |
| --------------------------------------------- | ---------------------------------------------------------------------------------------- |
| No music match (retrieve)                     | `bgm: null`, anomaly logged. Render proceeds without BGM.                                |
| Explicit `retrieve`, no credential            | Skipped (no silent generate fallback). Choose another mode only within explicit provider/spend authority.     |
| Neither Lyria nor MusicGen can run (generate) | `bgm` disabled with a `pip install …` hint. Voice + SFX still render.                    |
| Generate still rendering at assemble time     | `bgm_pending: true`; `wait-bgm.mjs` waits/checks and writes `bgm_status.json` first.     |
| Generate crashed                              | `wait-bgm.mjs` → `bgm_status.json { status: "failed" }`; the `<audio>` track is omitted. |

Required BGM failure blocks final acceptance. Optional omissions must be disclosed.
