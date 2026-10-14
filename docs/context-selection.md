# Lean stage context

`lib/stage_context_selection.py` is a pure selection helper. It does not read a
vault, start production, write receipts, call providers or grant approvals.
It supplies the version 1.1 selection used by the owner's maintained stage-context
consumer. Presence of this helper alone is not production-gate activation in a
checkout without that consumer; runtime integration must be checked separately.

The agent reads the selected director, pipeline-wide contracts, current stage,
ordered stage approval rail and actual required/optional inputs. Brief, reference,
source review, approved proposal and predecessor-owned frozen decisions remain
available where present. A later stage must not lose the agreed provider/runtime
merely because its manifest omitted the proposal from its declared inputs.

Other predecessor outputs stay in their source checkpoints and are opened when
a concrete decision needs them. They do not become mandatory application items
only because an earlier stage produced them. Their fingerprints still bind the
existing transitive freshness checks; changed upstream data requires reinspection
before dependent preparation, budget reservation or submission. Full manifest and AGENTS hashes
still bind current source versions; guidance repeats the production boundaries
with an explicit source reference. The complete native AGENTS instructions still
apply. Unknown guidance layouts fall back to full text.

The consumer reads a reusable feedback journal once per build. With no channel,
content kind, video format or tags it skips automatic sibling feedback discovery;
local and explicitly selected sources remain validated. No persistent cache is
introduced: later calls must see new feedback, supersession, expiry and source
changes. This is existing scoped feedback reuse, not a new knowledge registry.

New owner runs use policy 1.1. Existing 1.0 policies keep their original packet
reconstruction and receipt meaning; reinitialization does not migrate them.
No existing production is migrated merely to benefit from smaller packets.
Application, semantic review, approval, budget and prepared-request gates remain
the responsibility of the installed consumer and existing checkpoint/tool code.

Focused helper verification:

```text
python -m pytest tests/lib/test_stage_context_selection.py -q
```

Helper tests establish selection contracts. Integrated consumer tests are also
required before owner activation. Smaller serialized packets do not by themselves
prove better creative output, lower rework, token savings or lower billing.
