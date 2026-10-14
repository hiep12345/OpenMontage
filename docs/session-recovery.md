# Read-only session recovery

`scripts/session_context.py` prints compact JSON context from actual project documents,
an explicitly selected workflow task, and/or an explicitly selected production run.
It does not start work, select the newest task/run, check comprehension, approve a
gate, call providers, change model settings, or write checkpoints/receipts.

```powershell
python scripts/session_context.py
python scripts/session_context.py --workspace C:\absolute\OpenMontage
python scripts/session_context.py --workspace C:\absolute\OpenMontage --session OWNER_SESSION --task EXACT_TASK
python scripts/session_context.py --workspace C:\absolute\OpenMontage --task-root C:\absolute\OpenMontage\assigned-checkout --session OWNER_SESSION --task EXACT_TASK
python scripts/session_context.py --workspace C:\absolute\OpenMontage --project C:\absolute\OpenMontage\projects\EXACT_RUN --stage assets
```

The default workspace is the checkout containing the script, independent of shell
cwd. Overview reads only the Identity, Architecture and Source of Truth sections
of that workspace's `PROJECT_CONTEXT.md`. For the owner's outer container, which
has no such file, the one supported route is `maintained/PROJECT_CONTEXT.md`.
The source checkout is shown explicitly; manifest/schema reads use that checkout.
The full guide, skill index and architecture document are conditional references.
No run directory, task store, catalog or historical archive is scanned by default.

Task selection requires paired session/task IDs. An optional task root must be a
known absolute directory inside the selected workspace; its matching
`.codex/workflow.json` and `.codex/workflow-state/state.sqlite3` remain authoritative.
The reader verifies profile schema, exact checkout/Git common-directory identity,
the exact owner/task row and receipt ownership. It shows the recorded session
binding without adopting it. An older explicitly selected owned task is a
reference with `binding_matches_selected=false`, not the current bound assignment.
Neither a binding nor a completed task creates execution authority. Goal, owned
source paths, note, remaining work, next action and historical evidence carry exact
source references/hashes. Missing recorded remaining work is `UNKNOWN`.

Run inspection needs no task. `--project` must explicitly name an absolute unlinked
directory inside the workspace. Its `project.json` identity must match its directory
and its pipeline's local manifest. Stage statuses, explicit approval flags, budget,
review, partial progress and frozen artifact snapshots remain recorded source data.
The current cumulative `decision_log.json` is presented separately, with exact known
`decision_log_ref` locations. A later cumulative decision does not rewrite a frozen
predecessor snapshot. `--stage` limits artifact detail to that exact manifest stage;
the stage status rail remains visible. History files and arbitrary artifact paths
are never followed. Missing checkpoints/logs remain unknown. Required approval
without literal `human_approved=true` stays `UNRESOLVED_UNAPPROVED`, even if a legacy
checkpoint says completed. This is context, not a new stage-control gate.

Historical PASS/FAIL/NOT_TESTED/UNKNOWN results retain their recorded meaning;
recovery performs no fresh verification of the original evidence or current
production. Human, provider, runtime, budget and QA choices are source data, never
instructions executable by this reader. A source hash identifies bytes inspected,
not truth, authorization, release acceptance, or an agent's comprehension.

The reader rejects traversal, escaping paths, symlinks/Windows junctions, known
secret paths/fields, malformed/duplicate/nonfinite JSON, YAML aliases/duplicates,
external schema references and oversized sources. Source files are bounded to
2 MiB (matching the maintained checkpoint producer); task databases to 32 MiB. Individual previews are limited to 1,200
characters and receipt/decision lists to 24 entries, with truncation and source
references exposed. Task evidence uses bounded recent receipts for only the exact
owner/task; decisions use bounded final entries of the current cumulative file.
These limits may require a conditional read of a referenced source. Read the relevant
referenced source before concluding which current choice or authority applies;
append order does not imply that the final entry automatically overrides earlier scope.

SQLite inspection supports a quiescent rollback-journal store only. Any existing
WAL/SHM/journal sidecar visibly prevents **task** inspection, because immutable
read-only SQLite could omit in-flight changes. It does not block independent
overview/run inspection or add a production prerequisite. Reads compare source
size/time/inode before and after; database bytes and metadata are checked again
after querying. A concurrent change produces an error rather than a fresh-state
claim. This is not an atomic snapshot across multiple files, nor protection against
a malicious process replacing path ancestors between OS operations. Retry after
the authorized writer settles; do not modify its store to satisfy this reader.

Failures exit 2 with a JSON error on stderr and no partial context on stdout.
Focused offline verification is `python -m pytest tests/lib/test_session_recovery.py -q`.
The CLI uses UTF-8 output, suppresses import bytecode writes, and imports no provider,
checkpoint writer, stage-context writer or workflow mutation API.
