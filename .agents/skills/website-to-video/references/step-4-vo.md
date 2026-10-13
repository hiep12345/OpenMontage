# Step 4: Voiceover, timing and captions

Use the approved brief, SCRIPT.md and STORYBOARD.md, including existing narration, voice, music, caption and duration choices. Ask only about a material unresolved choice. Existing approval for the selected render/provider and budget remains valid; additional paid auditions, retries, provider changes or changed creative scope must fit that authorization.

## When narration is not selected

Skip TTS and transcription. Carry the approved beat durations into Step 5 as scene start/duration values, preserving the intended pacing. Reuse the selected music/SFX decision, including silence if intentional. If music is unresolved, settle that choice before sourcing or generating a track. Record a provided track's path, provenance/license and timing needs; determine BPM only when beat synchronization needs it.

## Select the available voice capability

Reuse the selected provider and voice. If selection is still needed, describe only capabilities actually available through the current native tools or OpenMontage registry (`tools/tool_registry.py`, relative to the repository root). Inspect the selected adapter's schema and configuration authority before invocation. Registered audio adapters live under `tools/audio/`; examples include `elevenlabs_tts.py` and `piper_tts.py`. Their existence does not prove credentials, models or dependencies are ready.

Configure credentials privately through the supported provider/settings or environment mechanism. Check availability without printing secrets, reading key values into logs, or requesting keys in chat. Do not invent a HeyGen REST version, expiry deadline, timestamp guarantee or fallback based on old examples. Check current native capability or official documentation when those details matter.

A local/offline run is possible only when the chosen executable, dependencies, voice model and any transcription model are already installed and work without network access. Do not use `npx` to implicitly install packages/models, download dependencies or switch to a cloud service. An unavailable selected capability is a reported blocker for that operation; continue independent script/timing preparation.

## Prepare the spoken script

Save the exact text passed to TTS as `narration.txt` in the task's project output directory, distinct from the creative SCRIPT.md. Preserve approved meaning, wording and language. Make pronunciation substitutions only where supported by a measured problem or the user's pronunciation direction; record the substitution so captions can retain readable, faithful wording. Do not assume a provider always mispronounces technical terms or that punctuation produces a fixed pause.

Use the selected engine's confirmed pronunciation/pause controls if needed. Check its actual support before using SSML. A short pronunciation or timing sample is useful when there is a real unresolved risk and the approved budget covers it. Reuse existing samples and an approved voice; there is no compulsory two-voice audition or paid test before every narration.

Estimate script length from the planned pacing, then use measured audio to refine timing. A short sample is an estimate, not proof of the full narration's duration. Preserve intended quiet or visual-only beats; do not fill every silence merely to satisfy a formula.

## Generate and inspect narration

Generate the approved script with the selected adapter into a task-owned `narration.wav` or `narration.mp3`, preserving existing artifacts unless replacement is authorized. Record the provider/model/voice and exact input, accepted job ID when asynchronous, and resulting artifact path. For parallel authorized jobs, persist each accepted handle separately before polling.

Use bounded status polling and the selected adapter's actual terminal states and transport timeouts. A slow command or local timeout is not proof that a remote job failed. Retain its handle, reconcile status, and resume without another generation request. An uncertain POST outcome must be reconciled before resubmitting. Do not kill after an arbitrary 60 seconds, change voice/model flags or switch provider as an automatic recovery action. Any new paid generation remains within the existing spend authorization.

Listen to the full audio for missing words, language, pronunciation, pauses and clipping. Keep `narration.txt` as the submitted text; record any observed spoken deviation separately and resolve it before caption acceptance. Measure the actual file duration with an installed probe, for example from the output directory:

```bash
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 narration.wav
```

Use the real filename/format. This local read-only probe does not install tooling or create a paid job.

## Obtain and validate timestamps

If the selected adapter returns word timestamps, inspect the actual response schema and time units before mapping them to the project's `transcript.json` records: `{text, start, end}`, in seconds. Retain the raw timing source. Do not infer a provider's field names or alignment support from its brand.

If usable timestamps are absent, use the approved available transcription/alignment capability on the actual narration artifact. For an installed HyperFrames workflow, consult [transcription](../../hyperframes-media/references/transcribe.md) only when needed and verify its command/dependencies before execution. An offline requirement includes the transcription model; it does not permit an automatic cloud fallback.

Check timestamps for finite values, ordered words, `0 <= start <= end`, and bounds within the measured audio duration (allowing only understood rounding). Listen at beat boundaries and spot-check alignment against the exact audio, especially repeated words and pronunciation substitutions. Transcription may omit or invent words; correct the aligned record using the audio without silently rewriting the approved script. Keep displayed captions faithful to what is spoken while retaining readable spelling and punctuation.

## Map actual timing to storyboard beats

Locate each beat's narration span using sequential alignment through the script; matching the first occurrence of a repeated word is insufficient. Record actual start/end times in STORYBOARD.md and derive each scene's start/duration for Step 5.

Preserve intended transitions, visual-only intervals and breathing room. Add padding only where it fits without unintended overlap or cutting off the next spoken phrase. Word onsets can guide cuts but do not mandate hard cuts for every style. Include the audio's real leading/trailing silence, music tails and the approved CTA hold when determining the final duration; the last word alone is not the audio duration.

Reconcile measured timings against the approved duration and beat structure before building. Within the brief's flexibility, adjust visual timing to the audio and record the decision. If satisfying the target requires material script cuts, a new generation, altered pacing or a changed CTA/beat structure, resolve that change within the user's authorization before proceeding with it. There is no universal percentage tolerance, automatic proportional rescaling or fixed CTA cap.

## Captions and handoff

Reuse the approved caption choice and style. Ask only if that choice is unresolved. If captions are selected, use the validated transcript for the caption composition in Step 5; consult [caption authoring](../../hyperframes-media/references/captions/authoring.md) for the selected HyperFrames workflow. Inspect legibility, placement, clipping and synchronization in the final render, including mobile-safe areas when relevant.

Hand off the final narration artifact and measured duration, exact `narration.txt`, validated `transcript.json` when applicable, music/SFX source decisions, and STORYBOARD.md with final beat start/duration and transition/CTA timing. These timings drive Step 5 scene slots and audio placement. Clearly identify any unresolved audio or alignment issue rather than presenting an estimate as verified timing.
