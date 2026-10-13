---
name: video-download
description: |
  Download video and audio from YouTube and 1000+ sites using yt-dlp. No API keys needed.
  Use when: (1) Downloading a video from YouTube or other sites, (2) Extracting audio from a video URL,
  (3) Downloading subtitles/captions from a video, (4) Getting video metadata without downloading.
---

# video-download

Download video and audio from URLs using yt-dlp directly. No wrapper scripts needed.

## Prerequisites

- **yt-dlp**: `brew install yt-dlp` or `pip install yt-dlp`
- **ffmpeg**: `brew install ffmpeg` or `apt install ffmpeg` (required for merging video+audio streams)

Use the existing project-managed executable first. Installation or updates are
environment changes: diagnose a relevant missing tool or extractor defect before
changing dependencies, follow the project toolchain, and preserve unrelated versions.
The installer-specific update commands below are optional remedies after that check.

## Commands

### Download best quality

```bash
yt-dlp "URL" -o "%(title)s.%(ext)s" --merge-output-format mp4
```

### Download specific resolution

```bash
# 720p
yt-dlp "URL" -f "bestvideo[height<=720]+bestaudio/best[height<=720]" --merge-output-format mp4

# 1080p
yt-dlp "URL" -f "bestvideo[height<=1080]+bestaudio/best[height<=1080]" --merge-output-format mp4
```

### Audio only

```bash
yt-dlp "URL" -x --audio-format mp3 --audio-quality 0
```

### Download subtitles

```bash
# Download video with English subtitles
yt-dlp "URL" --write-subs --sub-langs en --merge-output-format mp4

# Download video with multiple subtitle languages
yt-dlp "URL" --write-subs --sub-langs "en,es,fr" --merge-output-format mp4

# Download only subtitles (no video)
yt-dlp "URL" --write-subs --sub-langs en --skip-download
```

### Get metadata (no download)

```bash
yt-dlp "URL" --dump-json --no-download
```

### List available formats

```bash
yt-dlp "URL" -F
```

### Specify output directory

```bash
yt-dlp "URL" -o "./downloads/%(title)s.%(ext)s" --merge-output-format mp4
```

## Quality Presets

| Quality | Format flag |
|---------|-------------|
| Best | `-f "bestvideo+bestaudio/best"` (default) |
| 1080p | `-f "bestvideo[height<=1080]+bestaudio/best[height<=1080]"` |
| 720p | `-f "bestvideo[height<=720]+bestaudio/best[height<=720]"` |
| 480p | `-f "bestvideo[height<=480]+bestaudio/best[height<=480]"` |
| Worst | `-f "worstvideo+worstaudio/worst"` |

## Output Template Variables

Common variables for `-o` templates:

| Variable | Description |
|----------|-------------|
| `%(title)s` | Video title |
| `%(ext)s` | File extension |
| `%(id)s` | Video ID |
| `%(uploader)s` | Channel/uploader name |
| `%(upload_date)s` | Upload date (YYYYMMDD) |
| `%(duration)s` | Duration in seconds |
| `%(resolution)s` | Video resolution |

## Tips

- Always use `--merge-output-format mp4` to avoid ending up with `.webm` or `.mkv` files.
- Use `--no-download` with `--dump-json` for metadata-only queries; it skips media download but still makes network requests and may use local configuration/cache. Do not describe it as offline or universally free of side effects.
- For HTTP failures, inspect the actual status and extractor message first. Authentication, permissions, rate limits, unavailable content and network failures are not evidence that the executable needs updating. Preserve authorized access and do not bypass restrictions.
- Use `-f "bestvideo[height<=720]+bestaudio"` to save bandwidth when full resolution is not needed.
- yt-dlp automatically handles rate limiting and retries.
- The `--dump-json` output includes `title`, `duration`, `uploader`, `view_count`, `description`, `formats`, `subtitles`, and much more.

## Troubleshooting

- **"yt-dlp: command not found"**: Check the project-managed executable and PATH first. Install only through the relevant authorized toolchain if it is actually missing.
- **"ffmpeg: command not found"**: Check the selected executable and PATH; install through the authorized toolchain only if required and absent. Separate video/audio streams require a working merger.
- **Confirmed stale extractor**: Check the installed version and relevant upstream fix. Update only when that evidence and project authority support it: use `yt-dlp -U` for a supported standalone installation or the project's package manager for its pinned dependency. Rerun the affected lookup; a successful update is not proof of authorized content access.
