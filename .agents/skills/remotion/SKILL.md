---
name: remotion
description: OpenMontage Remotion composition conventions. Use when authoring or debugging a composition whose approved render runtime is Remotion.
---

# OpenMontage Remotion

Use the existing project composition and approved runtime. For framework APIs,
read the relevant topic in [remotion-best-practices](../remotion-best-practices/SKILL.md).

## Find the current contract

- For OpenMontage artifact-to-render mappings, composition profiles and scene
  conventions, read the applicable section of [the Remotion core reference](../../../skills/core/remotion.md).
- For operation inputs and runtime dispatch, inspect the current
  [video_compose tool](../../../tools/video/video_compose.py). Inspect the
  selected renderer in `remotion-composer/src/` before importing components.
- For stock composition IDs and their current props, inspect
  [Root.tsx](../../../remotion-composer/src/Root.tsx); for bespoke composition,
  follow the existing approved project-local entry instead.

Use the selected composition/profile's fps and dimensions. Convert seconds to
frames with that fps; do not impose 30fps on a different approved profile.
Keep scene duration separate from total composition duration when animating a
scene. The core reference describes this boundary and existing scene examples.

This checkout does not provide the external toolkit's `lib/components/`,
`lib/transitions/` or `showcase/transitions` gallery. Do not import those paths
or bootstrap another toolkit to satisfy an OpenMontage render. Preserve the
approved runtime, assets, manifest, checkpoint, QA and spend boundaries from
the project router; a failed render does not authorize a runtime substitution.

When adopting Remotion for a new commercial deployment, check its current
[license terms](https://www.remotion.dev/license). This does not add a new gate
to routine maintenance of an existing approved runtime.
