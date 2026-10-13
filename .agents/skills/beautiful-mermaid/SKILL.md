---
name: beautiful-mermaid
description: Render Mermaid diagrams as SVG and PNG using the Beautiful Mermaid library. Use when the user asks to render a Mermaid diagram.
---

# Beautiful Mermaid Diagram Rendering

Render Mermaid diagrams as SVG and PNG images using the Beautiful Mermaid library.

## Dependencies

Use installed Beautiful Mermaid dependencies and an available renderer. Set `SKILL_DIR` to the directory containing this loaded skill; resolve scripts from it.

## Supported Diagram Types

- **Flowchart** - Process flows, decision trees, CI/CD pipelines
- **Sequence** - API calls, OAuth flows, database transactions
- **State** - State machines, connection lifecycles
- **Class** - UML class diagrams, design patterns
- **Entity-Relationship** - Database schemas, data models

## Available Themes

Default, Dracula, Solarized, Zinc Dark, Tokyo Night, Tokyo Night Storm, Tokyo Night Light, Catppuccin Latte, Nord, Nord Light, GitHub Dark, GitHub Light, One Dark.

If no theme is specified, use `default`.

## Common Syntax Patterns

### Flowchart Edge Labels

Use pipe syntax for edge labels:

```mermaid
A -->|label| B
A ---|label| B
```

Avoid space-dash syntax which can cause incomplete renders:

```mermaid
A -- label --> B   # May cause issues
```

### Node Labels with Special Characters

Wrap labels containing special characters in quotes:

```mermaid
A["Label with (parens)"]
B["Label with / slash"]
```

## Workflow

### Step 1: Generate or Validate Mermaid Code

If the user provides a description rather than code, generate valid Mermaid syntax. Consult `references/mermaid-syntax.md` for full syntax details.

### Step 2: Render SVG

Run the rendering script to produce an SVG file:

```bash
bun run "$SKILL_DIR/scripts/render.ts" --code "graph TD; A-->B" --output diagram --theme default
```

Or from a file:

```bash
bun run "$SKILL_DIR/scripts/render.ts" --input diagram.mmd --output diagram --theme tokyo-night
```

Alternative runtimes:
```bash
npx tsx "$SKILL_DIR/scripts/render.ts" --code "..." --output diagram
deno run --allow-read --allow-write --allow-net "$SKILL_DIR/scripts/render.ts" --code "..." --output diagram
```

This produces `<output>.svg` in the current working directory.

### Step 3: Create HTML Wrapper

Run the HTML wrapper script to prepare for screenshot:

```bash
bun run "$SKILL_DIR/scripts/create-html.ts" --svg diagram.svg --output diagram.html
```

This creates a minimal HTML file that displays the SVG with proper padding and background.

### Step 4: Capture PNG when requested

Use an available supported browser or SVG rasterizer. Open the owned HTML wrapper,
wait for fonts/layout, capture at the requested dimensions and inspect the pixels.
Do not assume an `agent-browser` skill or CLI is installed. If no renderer is
available, deliver the SVG and report PNG as not tested/unavailable.



### Step 5: Clean Up Intermediary Files

After verification, remove only task-created disposable intermediary files; retain requested source and final formats.

Files to clean up:
- The HTML wrapper file (e.g., `diagram.html`)
- Any temporary `.mmd` files created to hold diagram code
- Any other files created during the rendering process

```bash
rm diagram.html
```

If a temporary `.mmd` file was created, remove it as well.

## Output

Produce the requested format(s):
- **SVG**: Vector format, infinitely scalable, small file size
- **PNG**: High-resolution raster, captured at 4K (3840×2160) viewport with minimum 1200px diagram width

Files are saved to the current working directory unless the user explicitly specifies a different path.

## Theme Selection Guide

| Theme | Background | Best For |
|-------|------------|----------|
| default | Light grey | General use |
| dracula | Dark purple | Dark mode preference |
| tokyo-night | Dark blue | Modern dark aesthetic |
| tokyo-night-storm | Darker blue | Higher contrast |
| nord | Dark arctic | Muted, calm visuals |
| nord-light | Light arctic | Light mode with soft tones |
| github-dark | GitHub dark | Matches GitHub UI |
| github-light | GitHub light | Matches GitHub UI |
| catppuccin-latte | Warm light | Soft pastel aesthetic |
| solarized | Tan/cream | Solarized colour scheme |
| one-dark | Atom dark | Atom editor aesthetic |
| zinc-dark | Neutral dark | Minimal, no colour bias |

## Troubleshooting

### Theme not applied

Check the render script output for the `bg` and `fg` values, or inspect the SVG's opening tag for `--bg` and `--fg` CSS custom properties.

### Diagram appears cut off or incomplete

- Check edge label syntax — use `-->|label|` pipe notation, not `-- label -->`
- Verify all node IDs are unique
- Check for unclosed brackets in node labels

### Render produces empty or malformed SVG

- Validate Mermaid syntax at https://mermaid.live before rendering
- Check for special characters that need escaping (wrap in quotes)
- Ensure flowchart direction is specified (`graph TD`, `graph LR`, etc.)
