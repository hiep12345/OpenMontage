---
name: media-use
description: Resolve and freeze media through the configured HeyGen media-use catalog when that asset source is selected for the project.
---

# media-use

## Project scope

Use this resolver only for the selected HeyGen media-use asset source. Preserve approved or already supplied music, images and icons; needing media does not authorize catalog downloads or replacement of approved assets. Follow project access, licensing and spend authority.

Resolve media needs into frozen local files. One verb, four types, zero context noise.

## When to use

Call `resolve` when the selected catalog source must supply media — background music, sound effects, images, or icons. media-use searches the HeyGen catalog, downloads the best match, freezes it locally, and registers it in a manifest. The agent gets back one line; all search noise stays on disk.

## Resolve

```bash
node <SKILL_DIR>/scripts/resolve.mjs --type <type> --intent "<description>" --project <dir>
```

Returns one line: `resolved <id> → <path> (<type>, <metadata>)`

### Types

| Type    | What it finds       | Provider                                 |
| ------- | ------------------- | ---------------------------------------- |
| `bgm`   | Background music    | HeyGen audio catalog (10k+ tracks)       |
| `sfx`   | Sound effects       | Bundled 19-file library + HeyGen catalog |
| `image` | Photos, backgrounds | HeyGen asset search (75k+ vectors)       |
| `icon`  | Icons, logos        | HeyGen asset search (type=icon)          |

### Examples

```bash
# Background music
node <SKILL_DIR>/scripts/resolve.mjs --type bgm --intent "upbeat tech launch" --project .
# → resolved bgm_001 → .media/audio/bgm/bgm_001.mp3 (bgm, 25s)

# Sound effect
node <SKILL_DIR>/scripts/resolve.mjs --type sfx --intent "whoosh" --project .
# → resolved sfx_001 → .media/audio/sfx/sfx_001.mp3 (sfx, 0.57s)

# Image
node <SKILL_DIR>/scripts/resolve.mjs --type image --intent "gradient tech background" --project .
# → resolved image_001 → .media/images/image_001.jpg (image)

# Icon
node <SKILL_DIR>/scripts/resolve.mjs --type icon --intent "rocket" --project .
# → resolved icon_001 → .media/images/icon_001.png (icon, transparent)
```

### Flags

| Flag            | Description                                |
| --------------- | ------------------------------------------ |
| `--type, -t`    | Media type: bgm, sfx, image, icon          |
| `--intent, -i`  | What you need (natural language)           |
| `--entity, -e`  | Entity name for cache matching (optional)  |
| `--project, -p` | Project directory (default: .)             |
| `--adopt`       | Bulk-import existing assets/ into manifest |
| `--json`        | Output JSON instead of one-line result     |

## How it works

1. Check project `.media/manifest.jsonl` for exact-prompt match
2. Scan existing `assets/` directory for unregistered files matching the need
3. Check global cache `~/.media/` for reusable asset
4. Search via provider (HeyGen audio catalog, HeyGen asset search)
5. Freeze file to `.media/<type>/`, register in manifest, regenerate `index.md`

The agent gets back **one line**. Candidates, scores, provenance stay on disk.

## Adopt existing projects

Most HyperFrames projects already have assets in `assets/`. media-use adopts them:

```bash
node <SKILL_DIR>/scripts/resolve.mjs --adopt --project .
# → adopted 9 assets from assets/
#   bgm_001 → assets/bgm/mango-fizz.mp3 (bgm, 146.6s)
#   image_001 → assets/images/avatar.jpg (image, 400×400)
```

`ffprobe` extracts real duration and dimensions. During resolve, unregistered files in `assets/` matching the intent are adopted on the fly.

## Reading the inventory

After resolve or adopt, read `.media/index.md` for the full inventory:

```
# .media · 4 assets

id         type   dur   dims       path                          description
bgm_001    bgm    25s   —          .media/audio/bgm/bgm_001.mp3  upbeat tech launch
sfx_001    sfx    0.6s  —          .media/audio/sfx/sfx_001.mp3  whoosh
image_001  image  —     1920×1080  .media/images/image_001.jpg   gradient tech background
icon_001   icon   —     200×200    .media/images/icon_001.png    rocket
```

## Cross-project reuse

Assets are cached automatically on resolve. Subsequent resolves for the same prompt hit the global cache at `~/.media/` — no re-download, no provider call. Promote an asset explicitly with `organize --promote <id>` to make it reusable across all projects.

## Files

- `.media/manifest.jsonl` — machine SSOT, one JSON record per line
- `.media/index.md` — agent-readable table (id, type, dur, dims, path, description)
- `~/.media/` — global cross-project reuse cache (content-addressed, SHA-256)

## CLI tools used

| Tool      | Purpose                                    | Required?     |
| --------- | ------------------------------------------ | ------------- |
| `ffprobe` | Probe duration, dimensions, codec on adopt | Yes           |
| `heygen`  | Audio catalog, asset search                | For providers |

Use the existing project-managed `heygen` executable and provisioned credentials
first. Verify that its installed version supports the required provider flags.
Do not update a working pinned installation merely because this skill was loaded.
Installation or upgrade is a task-relevant environment change only when the tool
is missing or its actual version lacks the required capability; use the authorized
platform/toolchain and verify the result. Do not execute an unreviewed downloaded
installer as a routine setup step.

Read credentials from the existing process environment or approved secret store.
Do not print keys, paste them in chat, place them in command arguments or commit
them. A missing credential or selected provider is a concrete blocker; it does
not authorize automatic account setup, another provider or new paid generation.

Requires **heygen >= v0.1.6** — the providers tag requests with the allowlisted `--headers 'X-HeyGen-Client-Source: media-use'` flag, added in v0.1.6. `asset search` is a pre-launch command hidden from `heygen --help`, but it runs. Without a `heygen` on PATH (or a valid key) the providers print a one-line diagnostic to stderr and resolve falls through to "no provider could resolve".
