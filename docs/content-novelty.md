# MT content preflight

Use the maintained `content_novelty` capability or
`python scripts/content_novelty.py check --identity PATH --delivery-plan PLAN --channel MT --reserve`
before new generation. The JSON identity uses the strict v1 contract documented
by `lib/content_novelty.py`: family/variant/production IDs, purpose, viewer
question and takeaway, story beats, template/application, recipe/file/script/
native-clip hashes, experiment reference and remake lineage. Unknown values
remain empty/null as permitted; do not fabricate scripts or publication proof.
TEST requires an experiment reference; REMAKE requires a parent and reason.
New Hub-bound MT reservations also require the sealed proposal delivery plan
described in [content-delivery.md](content-delivery.md). The plan records one
episode and its intended file/destination mapping before generation and is
stored immutably with the reservation. Final identity ingest must match that
exact plan and a finished intent before any Hub request.

For explicitly local-only MT generation, replace `--delivery-plan PLAN` with
`--local-only` while retaining `check --reserve`, the same identity and registry,
and live Hub novelty coverage. No destinations are invented. LOCAL_ONLY is
bound atomically to a new intent and cannot later acquire Hub delivery scope.
The default remains Hub-bound; historical intents keep their original meaning.
This flag is not an offline mode, generation approval or publishing permission.

The client fetches every all-status Hub page, verifies the entire snapshot digest
and refreshes the derived local index. A shared registry defaults to
`~/.codex/state/openmontage-content-novelty.sqlite`; all accounts and runners on
this host must use that path. Import retained JSON once with
`python scripts/content_novelty.py import-retained --packet PATH`.
Historical status never becomes TEST, uploaded or public by inference.

The report supplies deterministic exact-file/script, shared-native-clip,
declared-parent, recipe and topic candidates. Read its bounded `candidate` and
`matches`, then judge the viewer takeaway and demonstration using cited evidence.
The default comparison context is at most 16,000 UTF-8 bytes, with explicit
omitted counts. It is not a measured token cap or a semantic clearance. Expand
relevant missing evidence when necessary. SHADOW / REVIEW_REQUIRED is intentional;
do not announce CLEAR from an empty shortlist. No paid embedding or generation
API is called. Cached reports bind identity, complete revision and retained facts.

Before one Flow submission, checkpoint account/project/prompt/settings/cost and
transition the reserved intent using its expected version:
`python scripts/content_novelty.py transition --production-id ID --expected-version 1 --state GENERATING`.
A timeout becomes SUBMITTED_UNKNOWN; reconcile the existing card before using
`--reconciled` to finish/cancel. Running submissions also require reconciliation
before cancellation. No timer expires these reservations. Tests remain recorded
but do not block independent random TEST runs. This ledger coordinates one host;
it does not operate Flow or prove multi-host scheduling safety.

Repeat `check --stage PRE_DELIVERY` with the finished script and file hashes.
Schema-v2 ingest carrying `contentIdentity` refreshes this report automatically;
MT batches must also pass their reserved `delivery_plan`.
Identity-bound delivery also verifies the current Hub source and creative hash
before writing bytes. Legacy calls remain supported but do not gain creative
coverage. Keep operator publishing approval separate from novelty review.

Access reuses the existing content-ingest principal through environment variables
or an independent Windows current-user DPAPI configuration at
`~/.codex/private/openmontage/hub-client.json` (override with
`DISTRIBUTION_HUB_CONFIG`). Its exact fields are `origin` and absolute
`credentialStore`; the store contains encrypted credentials, never cleartext.
Partial environment configuration fails rather than silently selecting another
principal. This helper loads no retired runtime or database. Hosting/storage
costs remain the existing Hub costs, separate from video generation.
