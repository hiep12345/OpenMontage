# OpenMontage

Use this router first. `AGENT_GUIDE.md` is a supporting reference: read only the
named sections needed for the task, not the full guide on every message. Reuse
instructions already read while their source and task scope remain applicable.

## Route the request

| Request | Required next step |
|---------|--------------------|
| Maintenance, debugging, tests, audits, status, or read-only inspection | Inspect the relevant source, records and checks. Read `PROJECT_CONTEXT.md` or relevant guide sections when needed. Do not start production, onboarding, capability menus or music selection just to answer. |
| Exact approved resume of an existing production | Read **Approved Production Resume** in `AGENT_GUIDE.md`. Recover the project, manifest, checkpoints, canonical artifacts and decision log; continue from the next authorized step. |
| New actionable video production | Read **Rule Zero — All Production Goes Through a Pipeline**, **Mandatory Preflight**, **Decision Communication Contract**, **User-Facing Planning Protocol** and **Project Directory Convention** in `AGENT_GUIDE.md`, plus the selected pipeline manifest. Run preflight and obtain the required proposal approvals before generation. |
| Vague first request or capability exploration | Read `skills/meta/onboarding.md` for discovery. A vague request does not authorize generation or spend. |
| Video URL/file supplied as inspiration | Read **Reference Video Entry Point** in `AGENT_GUIDE.md` and `skills/meta/video-reference-analyst.md`; inspect the reference before proposing a production. Source footage to edit instead uses `source_media_review` and the appropriate footage-led pipeline. |

An existing run takes the resume route only when its identity, approved scope
and evidence match. A materially changed brief or reference needs the relevant
planning/analysis and new authority; an unrelated maintenance question does not
restart a production. Ask only for missing information that prevents progress.

## Binding production boundaries

- The agent orchestrates from manifests, stage skills and records; Python tools
  provide capabilities and persistence. All video production uses a pipeline.
- Before stage work, read its manifest-selected director skill and the relevant
  **Stage Agents**, **Reviewer Protocol**, **Human Checkpoint Protocol** and
  **Communication Protocol** sections. Canonical artifacts and checkpoints must
  validate against their schemas; preserve history and partial progress.
- Before calling a tool, inspect its current registry contract and read its
  referenced `agent_skills` in `.agents/skills/`. Load relevant used skills, not
  the whole catalog. Availability does not authorize a provider/runtime swap.
- Manifest `human_approval_default` is binding. Stop at an unapproved gate;
  never mark it completed without `human_approved=True`. Reuse recorded approval
  only for its exact scope; an early approval does not cover later gates absent
  an explicit recorded `approval_policy`. Assets approval precedes full render.
- Preserve approved provider, model, runtime, music and sample/batch choices.
  Announce paid/consequential calls and verify authorized spend. Material changes,
  additional unapproved spend and substitutions require approval and an appended
  decision-log entry. Production approval does not authorize publishing.
- For link-bearing social packaging or Hub readiness, read
  `docs/caption-link-quality.md`: QA must bind the exact caption/package bytes,
  asset, source and website release. FAIL or NOT TESTED blocks readiness and new
  publishing approval. For new Hub-bound MT episodes, also read
  **Hub-bound MT episode identity** in `AGENT_GUIDE.md` and `docs/content-delivery.md` before
  reservation/generation. Review exact renders/files; preserve historical receipts.
  Explicitly local-only MT production follows that document's `LOCAL_ONLY`
  reservation scope; it does not authorize Hub delivery or publishing.
