# Distribution Hub delivery

The optional `distribution_hub` tool verifies reviewed metadata and delivers
immutable files to the Hub. It does not generate media, select destinations,
approve QA, upload to social providers, schedule or publish. Existing offline
`export_bundle` behavior and the generic `publish` capability are unchanged.
The tool is discovered under the dedicated `distribution_handoff` capability.

An administrator provisions `DISTRIBUTION_HUB_ORIGIN` (an HTTPS origin without
path/query), `DISTRIBUTION_HUB_CLIENT_ID`, and `DISTRIBUTION_HUB_CLIENT_SECRET`
for the dedicated `content-ingest` Cloudflare Access principal. Availability
checks configuration only, not network reachability. Credentials never belong in
an input artifact or committed file. Redirects are rejected and response bodies
are excluded from errors. The client introduces no new dependency or background
process. Its zero generation cost does not claim that Hub hosting/storage is free.

## Reviewed inputs and explicit operations

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

The BaseTool wrapper exposes the same `operation` names (`inspect`, `readiness`,
`ingest`, `deliver`). Read operations take `channel`, `content_id`, optional
`expected`; readiness/delivery also require `target`, and delivery requires `root`.
Ingest takes `payload`. Every operation returns `ToolResult`. It is discoverable
through the normal registry and optional when service configuration is missing.

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

## Offline contract fixture

`scripts/hub_contract_fixture.py --content-type photo|video` emits deterministic
JSON with `schemaVersion:1`, `payload` (one schema-v2 ingest item), `files`
(path/hash/size/MIME/base64), `archive` (actual ZIP hash/base64), and `expected`
(channel/content/targets/manualTargets). The small PNG and format-like MP4 bytes,
Drive URL and QA score are synthetic normalizer fixtures, never production or
visual-review evidence. Both types select fb-ig and explicitly manual Pinterest.

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
