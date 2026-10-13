---
name: azure-text-to-speech
description: Use when Azure Speech narration is explicitly requested or selected by the approved OpenMontage workflow. Follow the selected adapter contract and existing provider, voice, source and spend approvals; generic media requests use the project router.
license: MIT
compatibility: Requires internet access and an Azure AI Speech resource (AZURE_SPEECH_KEY + AZURE_SPEECH_REGION).
metadata: {"openclaw": {"requires": {"env": ["AZURE_SPEECH_KEY", "AZURE_SPEECH_REGION"]}, "primaryEnv": "AZURE_SPEECH_KEY"}}
---

# Azure AI Speech — Text-to-Speech

Generate narration with **Azure neural TTS** — high-quality multilingual voices,
SSML prosody control, and express-as styles, served synchronously by the REST
`/cognitiveservices/v1` endpoint (no token exchange, Blob storage, or job
polling). In OpenMontage this is exposed through the `azure_tts` tool
(`capability=tts`, `provider=azure`). Use `azure_tts` only for selected and authorized Azure work. Credential presence
does not establish entitlement. Preserve offline or exact-provider choices;
Piper, faster-whisper, ElevenLabs and other routes require their own authority.

> Docs: [REST text to speech](https://learn.microsoft.com/azure/ai-services/speech-service/rest-text-to-speech) · [Voice gallery](https://speech.microsoft.com/portal/voicegallery)

## Setup

Same Speech resource as `azure_stt` — **one key/region unlocks both directions**
(STT and TTS). Create a **Speech** resource in the
[Azure portal](https://portal.azure.com); copy the key and region from its
**Keys and Endpoint** page.

```bash
export AZURE_SPEECH_KEY=your_speech_resource_key
export AZURE_SPEECH_REGION=eastus        # your resource's region
# export AZURE_TTS_ENDPOINT=https://...  # optional: full custom TTS host
#   (the TTS host is https://<region>.tts.speech.microsoft.com — a different
#    subdomain than the STT endpoint, hence the separate override var)
```

`azure_tts` reports `AVAILABLE` once `AZURE_SPEECH_KEY` plus either
`AZURE_SPEECH_REGION` or `AZURE_TTS_ENDPOINT` are set.

## Using it in a pipeline

Route through `tts_selector` as usual (it auto-discovers `azure_tts`), or call
the provider tool directly when the user has approved Azure:

```python
from tools.tool_registry import registry
registry.discover()
tts = registry._tools["azure_tts"]

result = tts.execute({
    "text": "Every design decision in this dashboard has a reason.",
    "voice": "andrew",                 # alias or full Azure short name
    "rate": "-4%",                     # slightly slower for narration
    # "style": "narration-professional",  # for voices that support styles
    "output_path": "projects/my-video/assets/audio/seg_001.mp3",
    "output_format": "mp3",            # or "wav" (48kHz PCM) for mixing
})
```

If `azure_tts` is unavailable (no key) or errors, fall back per its declared
chain: `elevenlabs_tts` → `openai_tts` → `piper_tts`.

## Voice selection

Curated shortlist (aliases accepted by the `voice` param):

| Alias | Voice | Character |
|-------|-------|-----------|
| `andrew` | en-US-AndrewMultilingualNeural | warm, confident, conversational — the default; founder/explainer register |
| `brandon` | en-US-BrandonMultilingualNeural | deeper, measured |
| `ava` | en-US-AvaMultilingualNeural | confident, bright female |
| `guy` | en-US-GuyNeural | authoritative |
| `jenny` | en-US-JennyNeural | friendly, clear |

Any valid Azure voice short name may be passed verbatim (e.g.
`de-DE-KatjaNeural`); the *Multilingual* voices handle non-English text well —
set `locale` to match the text's language for correct SSML.

## Parameters that matter

- **`rate` / `pitch`** — SSML prosody. Narration usually reads best slightly
  slowed (`"-4%"` to `"-8%"`); leave pitch at `"0%"` unless correcting a voice.
- **`style`** — express-as style for voices that support it
  (`narration-professional`, `calm`, `newscast`). Unsupported styles are
  silently ignored by Azure, so listen to a sample before batch runs.
- **`output_format`** — `mp3` (48kHz/192kbit) for delivery, `wav` (48kHz PCM)
  when the segment feeds `audio_mixer` for further processing.
- Determinism: a fixed voice + SSML re-renders effectively identical audio —
  safe to regenerate individual segments without re-recording the whole set.

## Cost

Azure neural TTS Standard tier bills roughly **$16 per 1M characters** (~$0.016
per 1k chars; a 150-word narration segment ≈ $0.015). The tool reports
per-call `cost_usd` for the cost tracker. See
[Azure AI Speech pricing](https://azure.microsoft.com/pricing/details/cognitive-services/speech-services/) for current rates.

## Limits & tips

- One `execute` call = one narration segment. Generate per script section (the
  asset stage convention) rather than one giant paragraph — smaller segments
  align cleanly to scene timings and are cheap to regenerate.
- The synchronous endpoint caps a request at 10 minutes of audio — far above
  any segment OpenMontage generates.
- Text is XML-escaped automatically; do not pre-escape or wrap in SSML — pass
  plain text plus the `rate`/`pitch`/`style` params.
- Verify quality: listen to the first generated segment before batch-running a
  full script (voice/style fit is a creative decision — surface it at the
  proposal stage per the Decision Communication Contract).
