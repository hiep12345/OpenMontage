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

This is an agent-operated acceptance gate. The producer transport and Hub API
do not automatically consume this receipt. It adds no timer, background posting
or scheduled-worker website check. Automation/HTTP, browser review and public
publishing evidence remain distinct.
