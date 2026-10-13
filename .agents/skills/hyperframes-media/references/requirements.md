# Requirements & Caches

## Credential & key priority

Run `npx hyperframes auth status` to see what's configured and which engines a workflow will use (see the skill's **Preflight** section). Keys resolve in this order — **first match wins**:

| Provider                             | Resolution order (first non-empty wins)                                                                                                                                    | Local deps when used                             |
| ------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------ |
| **HeyGen** (TTS + BGM/SFX retrieval) | `$HEYGEN_API_KEY` → `$HYPERFRAMES_API_KEY` → `~/.heygen/credentials` (shared with heygen-cli; `$HEYGEN_CONFIG_DIR` overrides the dir; written by `hyperframes auth login`) | none (REST)                                      |
| **ElevenLabs** (TTS fallback)        | `$ELEVENLABS_API_KEY`                                                                                                                                                      | `pip install elevenlabs`                         |
| **Lyria** (BGM fallback)             | `$GEMINI_API_KEY` → `$GOOGLE_API_KEY`                                                                                                                                      | `pip install google-genai`                       |
| **Kokoro** (TTS, no key)             | installed dependencies/model only                                                                                                                                              | `pip install kokoro-onnx soundfile`              |
| **MusicGen** (BGM, no key)           | installed dependencies/model only                                                                                                                                              | `pip install transformers torch soundfile numpy` |

`hyperframes auth login` (browser OAuth) is the recommended setup: one sign-in, every project, no per-repo `.env`. An OAuth login is sent as `Authorization: Bearer`; an API key as `X-Api-Key`. No HeyGen credential does not imply offline execution: automatic routes can call ElevenLabs or Google Lyria. Explicit offline work must use installed Kokoro/MusicGen only — `hyperframes auth status` and `hyperframes doctor` both report whether those local deps are installed.

## Model caches & system dependencies

Some commands download models on first run. Confirm installed weights/dependencies before offline execution; authorize any setup/download separately. Cache locations below describe runtime behavior, not permission to mutate global caches:

- **TTS (HeyGen)** — no local deps; needs a HeyGen credential + `ffmpeg` on PATH (to transcode the mp3 response to `.wav`). Credential resolves like the CLI: `$HEYGEN_API_KEY` → `$HYPERFRAMES_API_KEY` → `~/.heygen/credentials` (shared with heygen-cli; run `npx hyperframes auth login`). An OAuth login is sent as `Authorization: Bearer`; an API key as `X-Api-Key`.
- **TTS (ElevenLabs)** — same as HeyGen: API key + `ffmpeg`.
- **TTS (Kokoro)** — Kokoro-82M (~311 MB) + voices (~27 MB) in `tts/`. Requires Python 3.8+ with `kokoro-onnx` and `soundfile` (`pip install kokoro-onnx soundfile`). Non-English text also needs `espeak-ng` system-wide.
- **BGM (Lyria)** — needs `$GEMINI_API_KEY` or `$GOOGLE_API_KEY` + `pip install google-genai`. No local model cache.
- **BGM (MusicGen)** — `pip install transformers torch soundfile`. `facebook/musicgen-small` (~300 MB) cached under `~/.cache/huggingface/` on first run.
- **Transcribe** — Whisper model size depending on choice (75 MB – 3.1 GB) in `whisper/`. Bundles `whisper.cpp`.
- **Remove-background** — `u2net_human_seg` (~168 MB ONNX) in `background-removal/models/`. Peak inference RAM ~1.5 GB.

Run `npx hyperframes doctor` if a command fails because of a missing dependency.
