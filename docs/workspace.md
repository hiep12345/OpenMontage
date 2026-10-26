# Optional local workspace binding

An ordinary public clone runs without owner data or a binding. Shared production
workspaces can select one local `.codex/openmontage-workspace.json` in the outer
workspace. This is an OpenMontage tool configuration, not native Codex configuration,
automatic instruction activation or permission to switch the executing checkout.
Keep the marker, private source names and owner paths out of public Git history.

`lib.workspace.resolve_workspace(repo_root)` accepts an exact checkout or outer
workspace. Discovery uses only the validated Git common directory's canonical
checkout parent and its exact marker. `OPENMONTAGE_WORKSPACE_CONFIG` explicitly
selects that same marker. There is no ancestor, sibling repository, chat or catalog
scan. Invalid bindings fail visibly. All configured paths are absolute, canonical
and local; links are rejected. The canonical source and common Git directory must
match the selected repository, and the workspace must own that source checkout.

The marker has `schema_version: 1`, `workspace_id`, `workspace_root`,
`git_common_dir`, `canonical_source_dir`, `projects_dir`, and optional
`legacy_projects_dirs`, `owner_context`, `private_skills_dir`, `private_skill_names`
and `resources_dir`. Production roots must be distinct and nonoverlapping. Legacy
roots preserve existing run locations; duplicate run IDs are ambiguous and fail.
A binding does not move data or make two writable copies acceptable. Task roots
and native session/task ownership remain separately and explicitly selected.

Run `python -B scripts/session_context.py` from any cwd via the selected script
path. Recovery reports binding identity and its source hash, selected owner
context sections and, for a worktree, a separate canonical project overview and
instruction reference. Owner objectives remain source-bound and expose their
paragraphs, with explicit truncation when needed. Read applicable full sections
before dependent work. Missing owner context is shown as `MISSING`; a public
clone reports `NOT_CONFIGURED`. Neither status grants or removes unrelated
maintenance authority. Missing required context blocks only dependent work.

Canonical owner instructions may add photo, generated-video, reference-input,
channel-direction and media-review contracts absent from a public checkout.
Recover their exact local sources and verify that the executing checkout supports
them. Keep photo workflow separate from video-only review gates. Preserve all
approval, budget, provider, source-media and publication boundaries. Loading owner
context does not supply missing code or silently execute canonical checkout code.

Stage context can consume an explicitly selected private package with an existing
scoped knowledge declaration:

```json
{"id":"selected-owner-method","version":"1","private_skill":"owner-method",
 "scope":{"channel":["assigned-channel"],"stages":["script"]}}
```

Supply this under `stage_context_profile.knowledge` at initialization or explicit
profile configuration. Declare exactly one of `text`, `path` or `private_skill`.
An applicable `private_skill` must appear in the binding's exact allowlist; the
reader uses only `<private_skills_dir>/<name>/SKILL.md`. It records actual content,
canonical source path and SHA-256 through the existing context/`read-item` flow.
An out-of-scope private declaration is visibly inapplicable and is not read.
An explicit manifest director skill matching an allowlisted package also reads
that canonical `SKILL.md`. A selected missing package fails; local copies or public
code are never a fallback. Other manifest directors keep their repository path.
Read only the selected skill and needed conditional references. No global skill
installation or native discovery is implied, and reading bytes proves neither
application nor media quality.
