---
name: acestep
description: Use when ACE-Step music prompting or a supported ACE-Step workflow is explicitly requested or selected by the approved OpenMontage workflow. Follow the selected adapter contract and existing provider, voice, source and spend approvals; generic media requests use the project router.
---

# ACE-Step prompting and execution

For execution inspect `tools/tool_registry.py` and the registered tool's current
schema. [ComfyUI](../comfyui/SKILL.md) documents `comfyui_music`: the bundled
workflow is ACE-Step v1, not 1.5. A selected 1.5/custom graph needs API-format
workflow JSON, its actual output node, installed models and provenance. Do not
replace the selected version silently. This checkout has no `tools/music_gen.py`
standalone CLI; `tools/audio/music_gen.py` is a different registered adapter.

Reuse approved vocals, duration and spend. Probe duration and listen to the source;
requested duration and prompt controls are not proof of actual output. Use the
chosen adapter's fields for seed/BPM/lyrics only where its schema supports them.

## Prompt Engineering

### Caption Writing — Layer Dimensions

Write captions by layering multiple descriptive dimensions rather than single-word descriptions.

**Dimensions to include:**
- **Genre/Style**: pop, rock, jazz, electronic, lo-fi, synthwave, orchestral
- **Emotion/Mood**: melancholic, euphoric, dreamy, nostalgic, intimate, tense
- **Instruments**: acoustic guitar, synth pads, 808 drums, strings, brass, piano
- **Timbre**: warm, crisp, airy, punchy, lush, polished, raw
- **Era**: "80s synth-pop", "modern indie", "classical romantic"
- **Production**: lo-fi, studio-polished, live recording, cinematic
- **Vocal**: breathy, powerful, falsetto, raspy, spoken word (or "instrumental")

**Good**: "Slow melancholic piano ballad with intimate female vocal, warm strings building to powerful chorus, studio-polished production"
**Bad**: "Sad song"

### Key Principles

1. **Specificity over vagueness** — describe instruments, mood, production style
2. **Avoid contradictions** — don't request "classical strings" and "hardcore metal" simultaneously
3. **Repetition reinforces priority** — repeat important elements for emphasis
4. **Sparse captions = more creative freedom** — detailed captions constrain the model
5. **Use metadata params for BPM/key** — don't write "120 BPM" in the caption, use its BPM field if supported, otherwise state tempo in the prompt

### Lyrics Formatting

**Structure tags** (use in lyrics, not caption):
```
[Intro]
[Verse]
[Chorus]
[Bridge]
[Outro]
[Instrumental]
[Guitar Solo]
[Build]
[Drop]
[Breakdown]
```

**Vocal control** (prefix lines or sections):
```
[raspy vocal]
[whispered]
[falsetto]
[powerful belting]
[harmonies]
[ad-lib]
```

**Energy indicators:**
- UPPERCASE = high intensity ("WE RISE ABOVE")
- Parentheses = background vocals ("We rise (together)")
- Keep 6-10 syllables per line within sections for natural rhythm

**Example — Tech Product Jingle:**
```
[Verse]
Build it better, ship it faster
Every feature tells a story

[Chorus - anthemic]
THIS IS YOUR PLATFORM
Your vision, your stage
Digital Samba, every page

[Outro - fade]
(Build it better...)
```

## Video integration

Generate or select one approved bed for related scenes, retain the provider source,
and derive separately named masters as needed. For narration, start with a quiet
instrumental bed and assess speech intelligibility by listening. A 0.15 mix level
is an example, not a loudness guarantee. Keep requested and measured duration
separate; never claim sub-second duration fidelity without probing.
