---
name: ltx2
description: Use when LTX video prompting or a supported LTX workflow is explicitly requested or selected by the approved OpenMontage workflow. Follow the selected adapter contract and existing provider, voice, source and spend approvals; generic media requests use the project router.
---

# LTX video prompting

Use the approved registered adapter: this checkout includes `ltx_video_local`,
`ltx_video_modal`, `ltx_api_video`, and `comfyui_video` under `tools/video/`.
Inspect `tools/tool_registry.py` and that adapter's schema before a call; their
models, parameters and resource requirements differ. For a ComfyUI graph read
[ComfyUI](../comfyui/SKILL.md), preserving model-stack and output-node provenance.
The former `tools/ltx2.py` and `docker/modal-ltx2/app.py` standalone examples are
not shipped here and must not be executed or recreated as an implicit setup step.

Verify current model access, pricing, licensing, duration/frame constraints and
hardware against the selected adapter and official source when used. Keep the
approved model/runtime/spend. Probe and inspect generated clips before acceptance.

## Prompting Guide

LTX-2 responds well to cinematographic descriptions. Layer these dimensions:

- **Camera:** "Slow dolly forward", "Aerial drone shot", "Tracking shot", "Static wide angle"
- **Lighting:** "Golden hour", "Cinematic lighting", "Neon-lit", "Soft diffused light"
- **Motion:** "Timelapse of...", "Slow motion", "Gentle camera drift", "Gradually transitions"
- **Style:** "Shot on 35mm film", "Documentary style", "Clean minimal aesthetic"
- **Negative:** Always implicitly avoids "worst quality, blurry, jittery, watermark, text, logo"

Keep prompts under 200 words. Be specific about the scene.

### Good Prompts

```
# Atmospheric b-roll
"Aerial drone shot slowly flying over turquoise ocean waves breaking on white sand, golden hour sunlight, cinematic"

# Product/tech scene
"Close-up of hands typing on a mechanical keyboard, shallow depth of field, soft desk lamp lighting, cozy atmosphere"

# Abstract background
"Dark moody abstract background with flowing blue light streaks, subtle geometric grid, bokeh particles floating, cinematic tech atmosphere"

# Animate a portrait
"Professional headshot, subtle natural head movement, confident warm expression, studio lighting, shallow depth of field"

# Animate a slide/screenshot
"Gentle subtle particle effects floating across a presentation slide, soft ambient light shifts, very slight camera drift"
```

### Bad Prompts

```
# Too vague
"A cool video"

# Too many competing ideas
"A cat riding a skateboard while juggling fire on the moon during a thunderstorm"

# Describing text/UI (model can't render text reliably)
"A website showing the text 'Welcome to our platform'"
```
