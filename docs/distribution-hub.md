# Distribution Hub delivery

Before a link-bearing package is declared ready, complete
[website link acceptance](caption-link-quality.md) using the exact final captions.
Transport readiness does not prove that a caption's website destination works.

The optional `distribution_hub` tool verifies reviewed metadata and delivers
immutable files to the Hub. It does not generate media, select destinations,
approve QA, upload to social providers, schedule or publish. Existing offline
`export_bundle` behavior and the generic `publish` capability are unchanged.
The tool is discovered under the dedicated `distribution_handoff` capability.

The additive `content_index` and `novelty` operations also expose the
`content_novelty` capability. See [MT content preflight](content-novelty.md) for
all-status Hub retrieval, test/remake identities, shared reservations, protected
access reuse and the required pre-generation/pre-delivery workflow. Novelty
review remains separate from operator approval and public publication.
See [episode delivery plans](content-delivery.md) for the required
pre-generation/final-batch binding on new MT identity ingest.

An administrator provisions `DISTRIBUTION_HUB_ORIGIN` (an HTTPS origin without
path/query), `DISTRIBUTION_HUB_CLIENT_ID`, and `DISTRIBUTION_HUB_CLIENT_SECRET`
for the dedicated `content-ingest` Cloudflare Access principal. Availability
checks configuration only, not network reachability. Credentials never belong in
an input artifact or committed file. Redirects are rejected and response bodies
are excluded from errors. The client introduces no new dependency or background
process. Its zero generation cost does not claim that Hub hosting/storage is free.

Every tool execution first writes a local RUNNING report, then retains its result
in `projects/hub-handoffs/artifacts/hub-handoffs/<run-id>.json`. Pass `project_dir`
to retain it inside a production's ignored project artifacts instead. `reportPath`
and `reportPersisted` are returned even on failure. Reports retain reviewed versions,
bounded request steps, safe HTTP status/code, request/key fingerprints and next
action; they exclude credentials, payload text and response bodies. An interrupted
process leaves RUNNING evidence. Failure to create initial evidence stops before
network activity. Failure to finish evidence never disguises a confirmed mutation
as a retryable failure. A report is diagnostic evidence, not a replay instruction.

Known public codes such as `HANDOFF_JOB_STALE` survive the client unchanged; unknown
codes/bodies remain private. An explicit D1 provider code 7500 may be returned as
`503 D1_READ_QUOTA_EXCEEDED`; generic server failures are not called quota errors.
Network loss, invalid successful JSON and server errors during a mutation leave
its outcome unknown and require exact request reconciliation. There is no automatic
metadata replay. Missing package, stale binding and authorization failures have
separate next actions. These reports do not run database scans or create timers.

## Reviewed inputs and explicit operations

Targets include `facebook`, `instagram`, legacy paired `fb-ig`, `pinterest`,
`youtube`, `x`, `tiktok` and `amz`. CosyRoom Lab uses `channelCode: "CRL"`,
`targets: ["facebook"]`, and omits `manualTargets`. It creates only a Facebook
job; account connection and exact operator publishing approval stay in Hub.
The `manualTargets` field is reserved for explicit manual MT Pinterest delivery;
do not send an empty array for ordinary API targets.
Keep historical `fb-ig` packages and receipts unchanged. Never combine `fb-ig`
with `facebook` or `instagram` in one item or episode plan. Separate Facebook
and Instagram targets can share one reviewed file with distinct job bindings.

For standalone Meta, include a UTF-8 `facebook/caption.txt` or
`instagram/caption.txt` in the archive and exact destination `requiredFiles`.
If the same caption is intentionally shared, Hub also accepts
`handoff/caption.txt`. Avoid competing caption candidates. Seal the actual
files, archive and manifest hashes; do not attach the paired-only
`facebookInstagram` structured video package to a standalone target.

The agent prepares schema-v2 ingest metadata and deliveryManifest v1 after
review. Canonical hashes use UTF-8 JSON with sorted object keys, retained array
ordering, and `sha256:` prefixes. Manifest files, destinations and required-file
paths sort lexically. Each destination binds its selected exact file inventory,
primary asset, QA receipt, distribution revision and package hash. The ZIP hash
must come from the actual reviewed archive bytes. The client checks the manifest
contract; it does not perform semantic QA or download/validate Drive archives.

Use the generic protocol namespace `sourceSystem: "production-pipeline"`.
It is not producer provenance. New performance records identify the actual
creator separately; retained historical source identities are not renamed.
New ingest requires a genuine existing HTTPS Drive archive reference and ID.
The client validates URL shape, not existence; never invent one for live work.

```python
from lib.distribution_hub import HubClient

# Values come from administrator-provisioned environment, never an artifact.
client = HubClient(origin, client_id, client_secret)
snapshot = client.inspect("MT", content_id, expected=reviewed_item)
status = client.readiness("MT", content_id, "fb-ig", expected=reviewed_item)
# Explicit metadata action; same permanent key/body after an uncertain outcome.
ingest_result = client.ingest(reviewed_payload)
# Explicit immutable file action; root contains the manifest's relative paths.
delivery_result = client.deliver("MT", content_id, "fb-ig", package_root,
                                 expected=reviewed_item)
```

For a reviewed CRL item, use its original content ID and exact Facebook binding:

```python
snapshot = client.inspect("CRL", crl_item["id"], expected=crl_item)
status = client.readiness("CRL", crl_item["id"], "facebook", expected=crl_item)
delivery_result = client.deliver("CRL", crl_item["id"], "facebook", package_root,
                                 expected=crl_item)
```

The BaseTool wrapper exposes the same `operation` names (`inspect`, `readiness`,
`ingest`, `deliver`). Read operations take `channel`, `content_id`, optional
`expected`; readiness/delivery also require `target`, and delivery requires `root`.
Ingest takes `payload` and, for new MT identity batches, the reserved
`delivery_plan` (one sealed plan or a list) and optional shared `registry_path`.
Novelty reservations take one `delivery_plan`. Every operation returns
`ToolResult`. It is discoverable
through the normal registry and optional when service configuration is missing.
An ingest transport loss stops with an unresolved metadata outcome. Inspecting
an existing handoff does not prove that the full batch, actor and permanent key
committed. Resume only with the same reviewed body/key; Hub's receipt ledger
then confirms a completed replay or rejects a conflict. Media descriptor/chunk
readback separately proves the exact immutable bytes after a lost response.

An expected reviewed item binds identity, source revisions, selected targets,
manual intent, package/manifest hashes and exact per-job files. Inspect without
an expected item validates internal current evidence only; it does not certify
that it matches a locally reviewed artifact. Whole `sourceRecordHash` verification
includes additive source fields; do not hash an abbreviated receipt projection.
Verify effective per-job delivery, not just the current global manifest: operator
work may retain an older exact source. Missing package preimages cannot establish
new package-bound delivery. Unavailable unrelated historical destinations do not
invalidate a selected, verified destination.

Delivery validates every local destination member's size/full hash before any
write, rejects unsafe paths/symlinks, computes 8 MiB transport chunks, then sends
only missing indices under the current opaque binding. It does not derive binding
from manifest hash. Interrupted descriptor/chunk writes are inspected before
continuing. An unconfirmed write stops; resume the same exact bytes later.
Final current handoff and readiness must match original source/jobs/binding.
Missing or mismatched local members block delivery; readiness inspection requires
no local archive. No outbox database, timer, automatic ingest replay or core runtime
is required.

Readiness returns content/target/source identity, current job, binding,
manifestHash, per-file descriptor/ready/missingChunks, overall `ready`, and
`publicPublication: "NOT_ASSERTED"`. Delivery adds `uploadedChunks` and
`localFilesVerified`. Metadata receipt, current job readiness, immutable bytes,
operator inspection and public publication remain distinct evidence.

Manual Pinterest intent stays manual regardless of API availability. Historical
manual recovery can return service `403 MANUAL_ONLY`; preserve that guard and
report the unavailable service path. Never relabel it complete using another
destination's access or remove manual intent. Original QA FAIL, unverified audio
and owner acceptance remain their original evidence; byte delivery changes none.

## Verified creative inventory reuse

Creative preflight uses the service-only `GET /api/ingest/content-index/revision?channel=MT` before every reuse.
An unchanged stamp permits reuse of the complete, digest-verified `scope=creative` inventory in the existing novelty registry.
Cache entries bind the exact Hub origin, channel and inventory stamp; corrupt entries are fetched again.
Creative history excludes job states, claims, schedules and unconfirmed upload status. Current handoff/job bindings and media
readback continue through fresh Hub requests. Cached history never grants permission to publish.

A batch shares one inventory per channel before ingestion and one after ingestion, while still inspecting each accepted item.
Only an unclassified 404 from the revision endpoint permits compatibility with an older Hub, using fresh legacy inventory reads.
Quota, authentication, invalid response and channel-not-found errors stop the operation; they do not fall back to cached history.
Deploy Hub migration 0079 and the compatible Hub reader before activating this producer version.

Reports include `contentIndexReadCost` from D1 metadata already returned by successful index requests. It covers these responses
only; missing metadata, failed index requests or a truncated trace report unknown rows rather than zero. Synthetic test costs
are not production measurements. All other request and account-wide usage costs remain separate.

## One reviewed handoff and safe resume

Use `operation: "handoff"` with the exact reviewed `payload`, package `root`,
`project_dir`, and the reserved `delivery_plan` / shared `registry_path` where
required. For batches with separate file trees, `roots` maps every content ID to
its exact local root. The tool validates the whole batch and all manifest files
before network activity, checks the authenticated Hub protocol declaration, then
receives metadata, delivers missing immutable files and verifies every selected
destination. It never creates a production plan, approves QA or publishes.

The default checkpoint is a stable key-hash filename inside the project's
`artifacts/hub-handoffs/`; an explicit `checkpoint_path` is also supported. Keep
it across interruption. It contains only hashes and selected job/binding evidence,
not a request body or credential, and binds the Hub origin, service credential ID,
canonical body and delivery plans. An OS lock prevents concurrent execution and
releases when the process exits. Invalid/corrupt or changed request checkpoints
stop. This local evidence is cooperative persistence, not an authorization ledger.

Before POST, the checkpoint becomes `METADATA_UNKNOWN`. A positive response is
persisted as `METADATA_ACCEPTED` before subsequent reads. Ordinary resume never
POSTs an accepted request and refuses an unknown request. After inspecting the
exact original body/key and retained evidence, an explicit caller may pass
`reconcile_metadata: true`; only then may that same request reach Hub's permanent
receipt ledger. Do not set this flag automatically, delete the checkpoint, mint a
new key to work around an unknown outcome, or infer a full receipt from a handoff
readback. Known rejected 4xx requests remain prepared for an explicit later run.

Accepted resumes verify fresh source/job/file bindings and the same reserved
plan. Changed selected jobs stop before file writes; unchanged jobs inspect exact
descriptor/chunk readback and send only missing bytes. `COMPLETE` means that all
selected Hub files were ready at the final checks. A completed run still checks
fresh state on resume; it never asserts social publication or changes operator
ownership. All ordinary executions continue to produce the diagnostic report.

Hub's authenticated `GET /api/ingest` must declare supported contract, ingest,
manifest, descriptor and chunk versions. The new operation fails before mutation
on missing or incompatible declarations; the older explicit operations remain
available. Deploy the compatible Hub declaration before activating this client.

## Offline contract fixture

`scripts/hub_contract_fixture.py --content-type photo|video` emits deterministic
JSON with `schemaVersion:1`, `payload` (one schema-v2 ingest item), `files`
(path/hash/size/MIME/base64), `archive` (actual ZIP hash/base64), and `expected`
(channel/content/targets/manualTargets). The small PNG and format-like MP4 bytes,
Drive URL and QA score are synthetic normalizer fixtures, never production or
visual-review evidence. The default selects fb-ig and explicitly manual Pinterest,
preserving the original fixture. `--meta-target facebook` selects only Facebook
for CRL; `--meta-target instagram` selects only Instagram for MT. Both standalone
variants include the destination caption path and no manual intent. Use the same
target option when validating a snapshot or exercising the localhost fixture.

Feed `fixture.payload` to Hub's real in-memory SQLite normalizer/handoff probe,
then run `--snapshot PATH --content-type photo|video` to validate its raw readback
or `{snapshot:...}` through the actual client verifier. This proves contract
acceptance separately from provider publication and live service access.

`--exercise-origin http://127.0.0.1:PORT --root TEMP` is an explicit synthetic
localhost fixture path. It writes synthetic files under TEMP, ingests the fixture
with synthetic service headers, delivers both targets and reports current
readiness. Only the library's explicit `allow_insecure_loopback=True` enables
HTTP localhost; the production wrapper always requires HTTPS. The test session's
network guard remains enabled, allowing loopback fixtures only.
