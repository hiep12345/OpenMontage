# Plan one episode before generation

For new Hub-bound MT production, capture the delivery contract at proposal time,
before reserving a generation. A lesson is not a new lesson just because it has
four destination captions. The agent still chooses the creative treatment and
destinations with the user through the normal pipeline; this validator only
checks those recorded choices.

Keep `projects/<id>/artifacts/delivery-plan.json` with its `planHash` referenced
by the proposal and decision log. Its strict v1 fields are `schemaVersion: 1`,
`channelCode`, `contentType`, `identity`, `strategy`, `variants`, `planHash`.
`identity` is the strict pre-generation identity from
[content-novelty.md](content-novelty.md), with `primaryFileSha256: null`.

- `SHARED_ASSET`: one planned variant, retaining the base `variantId`, parent
  and difference reason, with all selected targets. Different destination
  captions/packages do not require duplicating the same video or its content ID.
- `PLATFORM_VARIANTS`: two or more intentionally different rendered files.
  Each planned variant has its stable `variantId`, sorted `targets`, and a
  nonempty `differenceReason` describing the actual rendered adaptation. All
  final identities retain the base family/production and use the base variant
  as `parentVariantId`. No destination may appear twice in the episode plan.

Use `facebook` or `instagram` for an independent Meta destination. Use
`targets: ["facebook"]` for CRL Facebook-only delivery; the channel is `CRL`.
`fb-ig` retains the historical paired workflow. Do not combine it with either
standalone target, even across variants of the same episode. A shared asset
may select `["facebook", "instagram"]`; distinct captions do not require
another content identity. See [delivery packaging](distribution-hub.md) for
the exact caption paths and immutable manifest binding.

For example, seal a draft using the existing pre-generation identity:

```python
from lib.content_delivery import seal_plan

plan = seal_plan({
    "schemaVersion": 1, "channelCode": "MT", "contentType": "video",
    "identity": pre_generation_identity,
    "strategy": "PLATFORM_VARIANTS",
    "variants": [
        {"variantId": "lesson-meta", "targets": ["fb-ig"],
         "differenceReason": "Chronological opening and Meta-specific rendered CTA"},
        {"variantId": "lesson-pinterest", "targets": ["pinterest"],
         "differenceReason": "Result-first opening and Pinterest-specific rendered CTA"},
        {"variantId": "lesson-tiktok", "targets": ["tiktok"],
         "differenceReason": "Result-first opening and TikTok-specific rendered CTA"},
        {"variantId": "lesson-youtube", "targets": ["youtube"],
         "differenceReason": "Result-first opening and YouTube-specific rendered CTA"},
    ],
})
```

The base/master ID must differ from these four variant IDs. Reasons describe
planned differences, not a claim that the file has already been reviewed.
Use `SHARED_ASSET` instead if the rendered video is identical for all targets.

The offline CLI loads no credentials and calls no Hub or provider API:

```sh
python scripts/content_delivery.py seal --plan draft-plan.json
python scripts/content_delivery.py validate --plan projects/<id>/artifacts/delivery-plan.json
```

`seal` prints sealed JSON; save it as the plan artifact before continuing.
Reserve generation with that same artifact:

```sh
python scripts/content_novelty.py check --identity projects/<id>/artifacts/content-identity.json --delivery-plan projects/<id>/artifacts/delivery-plan.json --channel MT --reserve
```

The maintained client requires the plan for Hub-bound MT reservations and validates it
before any Hub read. The shared local registry stores the plan atomically with
the generation intent. An exact repeat is idempotent; a different sealed plan
cannot replace the reservation. Never attach a plan after generation starts.
If the plan needs changing, reconcile/cancel the old intent through its existing
expected-version rules and obtain the normal production review for a new
production ID. No timeout authorizes another submission.

For an explicitly local-only MT production, use the same identity, live novelty
evidence and shared intent registry with `--reserve --local-only` instead of a
delivery plan. This does not skip Hub evidence reads or authorize delivery:

```sh
python scripts/content_novelty.py check --identity projects/<id>/artifacts/content-identity.json --channel MT --reserve --local-only
```

The client keyword is `local_only=True`. This flag is valid only for an MT
PRE_GENERATION reservation without a plan; omitting it retains the Hub-bound
requirement. The registry atomically binds LOCAL_ONLY to the new intent. An
exact repeat retains that scope; it cannot acquire a Hub plan even before
generation, and historical intents cannot be relabelled local-only. A later
Hub-bound request needs a separately authorized new production identity and
its normal novelty/remake and plan checks. Existing assets and receipts remain
intact; a new identity is not permission to regenerate or bypass reuse review.

Every maintained ingest checks the manifest production IDs against that same
registry, including legacy packages without `contentIdentity` or a plan. Do not
select a different registry to avoid this binding. Historical unmarked packages
remain supported. A persistent SQLite guard also rejects plan attachment by an
older client. These are cooperative single-host data checks, not a defense
against someone changing the database or a guarantee across separate registries.
For rollback, disable new local-only reservations while retaining the scope-aware
ingest reader and the marker table/trigger for existing rows. Do not downgrade
to an ingest reader that ignores their scope or relabel a retained intent.

# Bind the final batch to the reserved plan

After the existing generation intent is reconciled and `FINISHED`, complete
normal render/file/metadata QA. Copy the planned lesson identity and lineage
into each final package; populate its actual script, primary-file and native-clip
hashes. Plan validation does not establish visual QA. Before ingest, run:

```sh
python scripts/content_delivery.py check --plan projects/<id>/artifacts/delivery-plan.json --payload projects/<id>/artifacts/ingest-payload.json
```

Then pass the same plan to `HubClient.ingest(payload, delivery_plan=plan)` or
the `distribution_hub` tool's `ingest` operation. Use the same `registry_path`
(`novelty_registry` on the client) as the generation reservation. A multi-episode
batch accepts a list of sealed plans; each episode needs its own finished intent.

The client checks all items before Hub requests: complete planned coverage,
unique content IDs and destinations, same lesson/family/production/master,
common native clips for platform variants, distinct rendered hashes, and exact
identity/manifest/asset/selected-job binding. Missing, extra or mismatched variants
block the entire batch. It then reads the immutable reserved plan and finished
intent before novelty reads or the first ingest POST.

The plan is local producer evidence, not an additional Hub payload field. Never
rewrite the sealed payload or its permanent idempotency key. Hub still owns
operational publishing state; every destination retains its exact file and job.
An uncertain ingest requires exact receipt reconciliation, never a fresh key.
Timestamp readback compares the reviewed ISO instant at Hub's UTC millisecond
precision while verifying the complete actual source hash first.

Historical no-identity ingest and existing exact media delivery remain supported.
New MT identity ingest needs its pre-generation plan; old completed productions
cannot be retroactively reserved or resubmitted as a migration. Preserve their
receipts and original metadata. None of these checks authorize social upload,
publication, provider calls or a public status change.
