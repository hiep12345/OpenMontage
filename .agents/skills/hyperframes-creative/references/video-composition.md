# Video composition guidance

Apply these suggestions only where the approved design leaves choices open. The
design spec can define layout, density, motion and negative space as well as brand
tokens; retain all of those choices. A minimalist frame and a flat background can
be intentional. Do not add decorative elements or focal points to meet a quota.

## Hierarchy and density

Give the message a clear primary focus. Optional background texture, midground
content and foreground accents can add depth when they serve the content, but
remove anything competing with the primary action or readable quantities.

## Color and scale

Preserve the chosen light/dark canvas, palette and fonts. Inspect rendered frames
at the destination size and after encoding: text should remain legible, details
should survive compression, and gradients should not band distractingly. Enlarge
small text or simplify content based on that evidence, not a universal pixel limit.
For a 1080p composition, headline sizes around 64–120px and body around 28–42px
are starting examples; the target viewport and actual reading task decide.

## Motion and framing

Use motion to explain change and guide attention. Ambient animation, contrasting
entrances, split frames and edge alignment are optional techniques. Static holds,
one focal point and centered framing are valid when requested or effective.
Keep animation deterministic under the HyperFrames technical contract and inspect
entrances, transitions and final holds for clipping, hierarchy and readability.
