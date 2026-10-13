---
name: ai-video-gen
description: Select or use an approved AI video generation adapter in OpenMontage. Use for provider comparison or selected generated-clip work; preserve exact provider/model/runtime decisions and route generic video requests through the project pipeline.
allowed-tools: mcp__heygen__*
metadata:
  openclaw:
    requires:
      env_any:
        - HEYGEN_API_KEY
        - FAL_KEY
        - KLING_API_KEY
        - GEMINI_API_KEY
        - GOOGLE_API_KEY
---

# Video Generation (Multi-Gateway)

Generate AI videos from text prompts. Supports multiple providers via four API paths:

| Gateway | Env Variable | Providers | Tool |
|---------|-------------|-----------|------|
| **fal.ai** | `FAL_KEY` | **Seedance 2.0** (standard + fast), Kling v3/v2.1, MiniMax, VEO | `seedance_video`, `kling_video`, `minimax_video`, `veo_video` |
| **HeyGen** | `HEYGEN_API_KEY` | VEO 3.1, Kling Pro, Sora v2, Runway Gen-4, Seedance Pro / Lite (1.x) | `heygen_video` |
| **Kling Official** | `KLING_API_KEY` | Kling official Classic, Turbo, and basic Omni video | `kling_official_video` |
| **Gemini API** | `GEMINI_API_KEY` / `GOOGLE_API_KEY` | Gemini Omni Flash (generation + conversational editing) | `gemini_omni_video` |

**Iterative editing — Gemini Omni.** When the brief calls for *refining an existing clip* (add/remove objects, restyle, change lighting or on-screen text) rather than regenerating, inspect the selected adapter for supported stateful editing. Gemini Omni is one route to evaluate when selection is open. See Layer 3 `gemini-omni` for the authoritative prompting guide (reference-image tags, timecode syntax, edit-prompt rules) before writing any prompt for it.

Use the current registry contract to compare supported routes only when selection
is still open. Configuration alone does not authorize a paid call. Preserve the
approved provider, gateway and model. `video_selector` is useful for an authorized
open selection; inspect its fallback behavior before use. For an exact approved
route use that registered adapter, without silent fallback or premium substitution.
Provider capabilities, model IDs, prices and rankings need a current native/official
check when used; the endpoint examples below are conditional references.

## Authentication

Use whichever configured gateway best matches the user's available providers and cost/quality goals.

- **HeyGen:** Set `HEYGEN_API_KEY` to access the multi-model gateway.
- **fal.ai:** Set `FAL_KEY` to access Kling, MiniMax, and Veo through fal.ai.
- **Kling Official:** Set `KLING_API_KEY` to access Kling's official direct API via `provider="kling_official"`.
- **Gemini API:** Set `GEMINI_API_KEY` or `GOOGLE_API_KEY` to access Gemini Omni video generation and conversational editing.

Do not describe any gateway as the default or top choice without checking the registry and current task fit first.

fal.ai Kling (`kling_video`, `provider="kling"`) and Kling Official (`kling_official_video`, `provider="kling_official"`) are different paths. Do not reuse fal.ai queue URLs, `FAL_KEY`, or image upload behavior when the official provider is selected.

```bash
curl -X POST "https://api.heygen.com/v1/workflows/executions" \
  -H "X-Api-Key: $HEYGEN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"workflow_type": "GenerateVideoNode", "input": {"prompt": "A drone shot flying over a coastal city at sunset"}}'
```

## Default Workflow

1. Call `POST /v1/workflows/executions` with `workflow_type: "GenerateVideoNode"` and your prompt
2. Receive a `execution_id` in the response
3. Persist the accepted execution ID before waiting. Poll with a finite deadline and HTTP timeout; stop on failed/cancelled terminal states. On timeout, reconcile the same job before any resubmission.
4. Use the returned `video_url` from the output

## Execute Video Generation

### Endpoint

`POST https://api.heygen.com/v1/workflows/executions`

### Request Fields

| Field | Type | Req | Description |
|-------|------|:---:|-------------|
| `workflow_type` | string | Y | Must be `"GenerateVideoNode"` |
| `input.prompt` | string | Y | Text description of the video to generate |
| `input.provider` | string | | Video generation provider (default: `"veo_3_1"`). See Providers below. |
| `input.aspect_ratio` | string | | Aspect ratio (default: `"16:9"`). Common values: `"16:9"`, `"9:16"`, `"1:1"` |
| `input.reference_image_url` | string | | Reference image URL for image-to-video generation |
| `input.tail_image_url` | string | | Tail image URL for last-frame guidance |
| `input.config` | object | | Provider-specific configuration overrides |

### Providers

| Provider | Value | Description |
|----------|-------|-------------|
| VEO 3.1 | `"veo_3_1"` | Google VEO 3.1 (default, highest quality) |
| VEO 3.1 Fast | `"veo_3_1_fast"` | Faster VEO 3.1 variant |
| VEO 3 | `"veo3"` | Google VEO 3 |
| VEO 3 Fast | `"veo3_fast"` | Faster VEO 3 variant |
| VEO 2 | `"veo2"` | Google VEO 2 |
| Kling Pro | `"kling_pro"` | Kling Pro model |
| Kling V2 | `"kling_v2"` | Kling V2 model |
| Sora V2 | `"sora_v2"` | OpenAI Sora V2 |
| Sora V2 Pro | `"sora_v2_pro"` | OpenAI Sora V2 Pro |
| Runway Gen-4 | `"runway_gen4"` | Runway Gen-4 |
| Seedance Lite | `"seedance_lite"` | Seedance Lite |
| Seedance Pro | `"seedance_pro"` | Seedance Pro |
| LTX Distilled | `"ltx_distilled"` | LTX Distilled (fastest) |

### curl

```bash
curl -X POST "https://api.heygen.com/v1/workflows/executions" \
  -H "X-Api-Key: $HEYGEN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "workflow_type": "GenerateVideoNode",
    "input": {
      "prompt": "A drone shot flying over a coastal city at golden hour, cinematic lighting",
      "provider": "veo_3_1",
      "aspect_ratio": "16:9"
    }
  }'
```

### TypeScript

```typescript
interface GenerateVideoInput {
  prompt: string;
  provider?: string;
  aspect_ratio?: string;
  reference_image_url?: string;
  tail_image_url?: string;
  config?: Record<string, any>;
}

interface ExecuteResponse {
  data: {
    execution_id: string;
    status: "submitted";
  };
}

async function generateVideo(input: GenerateVideoInput): Promise<string> {
  const response = await fetch("https://api.heygen.com/v1/workflows/executions", {
    method: "POST",
    headers: {
      "X-Api-Key": process.env.HEYGEN_API_KEY!,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      workflow_type: "GenerateVideoNode",
      input,
    }),
  });

  const json: ExecuteResponse = await response.json();
  return json.data.execution_id;
}
```

### Python

```python
import requests
import os

def generate_video(
    prompt: str,
    provider: str = "veo_3_1",
    aspect_ratio: str = "16:9",
    reference_image_url: str | None = None,
    tail_image_url: str | None = None,
) -> str:
    payload = {
        "workflow_type": "GenerateVideoNode",
        "input": {
            "prompt": prompt,
            "provider": provider,
            "aspect_ratio": aspect_ratio,
        },
    }

    if reference_image_url:
        payload["input"]["reference_image_url"] = reference_image_url
    if tail_image_url:
        payload["input"]["tail_image_url"] = tail_image_url

    response = requests.post(
        "https://api.heygen.com/v1/workflows/executions",
        headers={
            "X-Api-Key": os.environ["HEYGEN_API_KEY"],
            "Content-Type": "application/json",
        },
        json=payload,
    )

    data = response.json()
    return data["data"]["execution_id"]
```

### Response Format

```json
{
  "data": {
    "execution_id": "node-gw-v1d2e3o4",
    "status": "submitted"
  }
}
```

## Check Status

### Endpoint

`GET https://api.heygen.com/v1/workflows/executions/{execution_id}`

### curl

```bash
curl -X GET "https://api.heygen.com/v1/workflows/executions/node-gw-v1d2e3o4" \
  -H "X-Api-Key: $HEYGEN_API_KEY"
```

### Response Format (Completed)

```json
{
  "data": {
    "execution_id": "node-gw-v1d2e3o4",
    "status": "completed",
    "output": {
      "video": {
        "video_url": "https://resource.heygen.ai/generated/video.mp4",
        "video_id": "abc123"
      },
      "asset_id": "asset-xyz789"
    }
  }
}
```

## Polling for Completion

```typescript
async function generateVideoAndWait(
  input: GenerateVideoInput,
  maxWaitMs = 600000,
  pollIntervalMs = 10000
): Promise<{ video_url: string; video_id: string; asset_id: string }> {
  const executionId = await generateVideo(input);
  console.log(`Submitted video generation: ${executionId}`);

  const startTime = Date.now();
  while (Date.now() - startTime < maxWaitMs) {
    const response = await fetch(
      `https://api.heygen.com/v1/workflows/executions/${executionId}`,
      { headers: { "X-Api-Key": process.env.HEYGEN_API_KEY! } }
    );
    const { data } = await response.json();

    switch (data.status) {
      case "completed":
        return {
          video_url: data.output.video.video_url,
          video_id: data.output.video.video_id,
          asset_id: data.output.asset_id,
        };
      case "failed":
        throw new Error(data.error?.message || "Video generation failed");
      case "not_found":
        throw new Error("Workflow not found");
      default:
        await new Promise((r) => setTimeout(r, pollIntervalMs));
    }
  }

  throw new Error("Video generation timed out");
}
```

## Usage Examples

### Simple Text-to-Video

```bash
curl -X POST "https://api.heygen.com/v1/workflows/executions" \
  -H "X-Api-Key: $HEYGEN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "workflow_type": "GenerateVideoNode",
    "input": {
      "prompt": "A person walking through a sunlit park, shallow depth of field"
    }
  }'
```

### Image-to-Video

```json
{
  "workflow_type": "GenerateVideoNode",
  "input": {
    "prompt": "Animate this product photo with a slow zoom and soft particle effects",
    "reference_image_url": "https://example.com/product-photo.png",
    "provider": "kling_pro"
  }
}
```

### Vertical Format for Social Media

```json
{
  "workflow_type": "GenerateVideoNode",
  "input": {
    "prompt": "A trendy coffee shop interior, camera slowly panning across the counter",
    "aspect_ratio": "9:16",
    "provider": "veo_3_1"
  }
}
```

### Fast Generation with LTX

```json
{
  "workflow_type": "GenerateVideoNode",
  "input": {
    "prompt": "Abstract colorful shapes morphing and flowing",
    "provider": "ltx_distilled"
  }
}
```

## Best Practices

1. **Be descriptive in prompts** — include camera movement, lighting, style, and mood details
2. **Default to Seedance 2.0 (via `seedance_video`) for cinematic and motion-led work** when `FAL_KEY` is set — single-pass synced audio, multi-shot, lip-sync, director-level camera. Use VEO 3.1 / Sora V2 Pro when the user specifically wants Google or OpenAI motion character; use `ltx_distilled` or `veo3_fast` only when speed is the hard constraint
3. **Use reference images** for image-to-video generation — great for animating product photos or still images
4. **Video generation is the slowest workflow** — allow up to 5 minutes, poll every 10 seconds
5. **Aspect ratio matters** — use `9:16` for social media stories/reels, `16:9` for landscape, `1:1` for square
6. **Output includes `asset_id`** — use this to reference the generated video in other HeyGen workflows
7. **Output URLs are temporary** — download or save generated videos promptly
