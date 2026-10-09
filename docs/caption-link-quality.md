# Website links before packaging and Hub handoff

Follow the shared [caption-link ownership and acceptance contract](https://github.com/hiep12345/distribution-hub/blob/main/docs/caption-link-quality.md).

The production owner is accountable for every final caption/description and
platform link field. Record the website owner, reviewer and assigned operator
in the checkpoint. Obtain an exact deployed route for the promised recipe;
never invent a slug or substitute the homepage for an exact-recipe promise.

Before sealing or handing off a link-bearing package:

1. Extract all URLs from the final destination files/fields and bind their UTF-8
   hashes, content/production ID, asset hash and distribution/package revision.
2. In the maintained Mix-Therapy website checkout, run
   `npm run verify:caption:links -- --caption <absolute-caption-path>` from
   `apps/web`, repeating `--caption` for each exact file. Retain its JSON output
   beside the production QA receipt. Structured platform link fields must also
   be covered in the URL inventory; do not certify only the Facebook file.
3. Require HTTP 200 and the intended public page. Unknown recipe slugs, 404,
   soft 404, redirects, login walls and unavailable checks stop readiness.
   Inspect intentional equivalent redirects and off-site URLs separately.
4. Compare exact source paints/ratios and page claims with the inspected video
   or image. Inspect rendered desktop/mobile states and exercise the promised
   primary action. The HTTP tool does not perform this semantic/browser review.
5. Save reviewer identity, time, website release, exact URLs and separate HTTP,
   content and browser PASS/FAIL/NOT TESTED verdicts with screenshots/logs.
   FAIL or NOT TESTED blocks declaring the package ready and its Hub handoff.
6. Recheck after material changes, a relevant deploy or a later-day resume.
   The assigned operator opens the exact caption link again immediately before
   publishing or approving a schedule through Hub's existing controls.

Ask the website owner to repair a missing exact page from verified source
material. Preserve failed receipts and old caption bytes; a corrected package
uses a new revision. Do not edit/delete/re-ingest existing Hub jobs, claims,
approvals or social posts to conceal the failure. Their separate authorization
and permanent request controls remain authoritative.

The maintained producer and Hub now require the sealed `captionLinkQa` v1
receipt for MT packages containing owned website URLs or caption/metadata files. The producer
checks exact final package fields and file hashes; `handoff()` also reads the
UTF-8 files. A named reviewer supplies semantic and rendered-browser PASS with
dated evidence. HTTP success never supplies either human verdict. The pilot
automatically checks owned-authority `mixtherapy.space` candidates only:
external companion URLs remain sealed in the exact caption inventory and need
their separate review, while owned encoded paths,
fragments, redirects, credentials, login walls and unknown routes fail closed.
The public catalog must carry both `recipeRelease` and the expanded
`websiteRelease` digest that binds rendered pages and publication eligibility.
Restored correction pages can be healthy HTTP pages while remaining ineligible
for captions. Unsafe owned authorities (HTTP, credentials or lookalikes) are
selected and rejected before HTTP. External-only website receipts carry
NOT_APPLICABLE, null website release and no checks. Metadata JSON inventories
decode string values while hashing exact original file bytes, so escaped
newlines or slashes cannot change the caption URL set.
Attribution queries are retained exactly in final seals and HTTP requests;
catalog identity and canonical checks use the route pathname. External-only
structured packages without caption files need no website receipt. Caption
files still require sealed evidence with NOT_APPLICABLE website verdicts.
Explicit `pinterest:link` fields and JSON string values under `link` preserve
terminal URL punctuation (only surrounding whitespace is trimmed); prose
captions retain their sentence-punctuation extraction rules.
No physical paint match or inspected-video match follows from HTTP.

Prepare a new receipt-bearing payload with:

```powershell
python -m lib.caption_links --payload reviewed-payload.json --root final-bundle --review named-review.json --output reviewed-payload-with-links.json
```

Prepare `lib.caption_links.review_scope(item, root)` for each exact final item.
The review JSON contains those exact `schemaVersion`, `contentId`, `assetHash`,
`distributionRevision` and sealed `fields`, plus the reviewed `websiteRelease`
and `reviewer`. The nested reviewer has exactly `name`, `checkedAt`
(timezone-aware ISO timestamp), `semantic`, `browser`, and `evidence`
(nonempty references for linked captions). Supply an array of scoped reviews
for a batch. Unscoped reviewer notes are rejected; an old PASS note cannot
silently certify changed final bytes, source bindings, or website contents.
Linked reviews and HTTP checks expire after 24 hours. The receipt seals final
field IDs, UTF-8 SHA-256 values, URL inventories, content ID, asset hash,
distribution revision, website release and source-receipt hashes. Preserve the
original payload and failed receipts; never reseal under an uncertain permanent
idempotency key.

`HubClient.ingest()` checks the current website immediately before a potentially
new metadata POST, combining repeated URLs into one check per batch. A positive
exact origin/actor/body/key response permits unchanged replay in that client.
An accepted durable `handoff()` checkpoint resumes byte verification/readback
without requiring a new website review. An unknown metadata POST still might
create data, so explicit exact-key reconciliation requires fresh evidence.
Read-only `inspect()` remains available when website QA fails.

`ExportBundle.caption_review_scope(inputs)` returns the exact final file seals
and video asset hash before packaging. Add `websiteRelease` and the explicit
`reviewer` object to that scope and supply it as `caption_link_review`. Owned
URLs require matching field/asset seals and fresh HTTP; missing or NOT_TESTED
review fails before export writes. Successful exports retain
`metadata/caption-link-qa.json` and its receipt hash. Files are written as exact
UTF-8 bytes with LF newlines, including the final description with chapters.
Use a new `export_dir` for every revision: prior export metadata and evidence
are preserved. Ordinary exports without owned URLs remain offline.

Bounded `HubClient.adopt_package(request, snapshot, root=...)` and
`adopt_media(request, snapshot, packages, root=...)` adapters send already
canonical packages and manifests. Generic package adoption uses schema 3,
legacy TikTok schema 2, and media adoption schema 2, all with exact
`captionLinkQa` (null for non-MT or unlinked MT without caption files).
Package-only proofs cover the selected target's fields. Pinterest adds its
destination manifest caption files; media adoption covers all original stored
packages plus the supplied manifest caption files. Proof content/asset/revision
remain bound to the snapshot's original source, including when Pinterest has
different destination bytes. Pass the local root when MT caption files exist.
The expected profile/source hashes and the complete QA are immutable request
bindings. The Hub owns canonical package normalization, atomic adoption and
exact permanent-key replay; these adapters never invent media or retry unknown
mutations.

This adds no timer, background posting or scheduled-worker website check.
Automation/HTTP, browser review, source/formula verification, physical matching
and public publishing evidence remain distinct.
