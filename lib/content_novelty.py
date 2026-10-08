"""Evidence-aware, offline retrieval and shared producer intents. No model/provider calls."""
import hashlib
import json
import os
import re
import sqlite3
import time
import unicodedata
from fractions import Fraction
from pathlib import Path

VERSION = "content-novelty-v1"
HASH = re.compile(r"^sha256:[a-f0-9]{64}$")
FIELDS = {"schemaVersion", "familyId", "variantId", "productionId", "purpose", "question", "takeaway", "storyBeats", "recipeKeys", "templateFamily", "applicationContext", "scriptHash", "primaryFileSha256", "nativeClipSha256", "experimentRef", "parentVariantId", "differenceReason"}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return "sha256:" + hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def normalized_text(text):
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def normalize_recipe(manufacturer, product_line, ingredients):
    """Proportional exact ratios; caller supplies source paint identities, never RGB guesses."""
    if not isinstance(manufacturer, str) or not manufacturer.strip() or not isinstance(product_line, str) or not product_line.strip():
        raise ValueError("Manufacturer and product line required")
    amounts = {}
    for ingredient in ingredients:
        item, pigment = ingredient["item"], ingredient["pigment"]
        if not isinstance(item, str) or not item.strip() or not isinstance(pigment, str) or not pigment.strip():
            raise ValueError("Source ingredient identity required")
        part = Fraction(str(ingredient["parts"]))
        if part <= 0 or part.numerator.bit_length() > 128 or part.denominator.bit_length() > 128:
            raise ValueError("Invalid exact part ratio")
        key = (normalized_text(item), normalized_text(pigment))
        amounts[key] = amounts.get(key, Fraction(0)) + part
    if not amounts or len(amounts) > 12:
        raise ValueError("Recipe needs 1-12 source paints")
    anchor = amounts[sorted(amounts)[0]]
    return digest({"manufacturer": normalized_text(manufacturer), "line": normalized_text(product_line),
                   "parts": [[*k, str(amounts[k] / anchor)] for k in sorted(amounts)]})


def source_formula_key(formula):
    """Use the retained source's manufacturer/line/item identities without guessed aliases."""
    return normalize_recipe(formula["medium"]["brand"], formula["medium"]["product_line"],
        [{"item": p["item_number"], "pigment": "+".join(sorted(p["pigment_codes"])), "parts": p["parts"]}
         for p in formula["inputs"]])


def validate_identity(identity):
    if not isinstance(identity, dict) or set(identity) != FIELDS or type(identity["schemaVersion"]) is not int or identity["schemaVersion"] != 1:
        raise ValueError("Invalid contentIdentity v1")
    widths = {"familyId": 180, "variantId": 180, "productionId": 180, "question": 300, "takeaway": 400,
              "templateFamily": 120, "applicationContext": 200, "experimentRef": 300, "parentVariantId": 300, "differenceReason": 300}
    empty = {"question", "takeaway", "templateFamily", "applicationContext"}
    nullable = {"experimentRef", "parentVariantId", "differenceReason"}
    def text(value, width, allow_empty=False):
        # JS contract counts UTF-16 code units.
        if not isinstance(value, str) or value != value.strip() or len(value.encode("utf-16-le")) // 2 > width or (not value and not allow_empty) or re.search(r"[\x00-\x1f]", value):
            raise ValueError("Invalid creative identity text")
    for key, width in widths.items():
        if key in nullable and identity[key] is None:
            continue
        text(identity[key], width, key in empty)
    for key, maximum, width in (("storyBeats", 12, 200), ("recipeKeys", 8, 71), ("nativeClipSha256", 12, 71)):
        values = identity[key]
        if not isinstance(values, list) or len(values) > maximum or any(not isinstance(v, str) for v in values) or len(set(values)) != len(values):
            raise ValueError("Invalid creative identity list")
        for value in values:
            text(value, width)
            if key != "storyBeats" and not HASH.fullmatch(value):
                raise ValueError("Invalid typed identity hash")
    for key in ("scriptHash", "primaryFileSha256"):
        if identity[key] is not None and (not isinstance(identity[key], str) or not HASH.fullmatch(identity[key])):
            raise ValueError("Invalid typed identity hash")
    if identity["purpose"] not in {"TEST", "PRODUCTION", "REMAKE", "UNKNOWN"}:
        raise ValueError("Invalid production purpose")
    if identity["purpose"] == "TEST" and not identity["experimentRef"]:
        raise ValueError("TEST requires experimentRef")
    if identity["purpose"] == "REMAKE" and (not identity["parentVariantId"] or not identity["differenceReason"]):
        raise ValueError("REMAKE requires lineage and reason")
    if identity["parentVariantId"] == identity["variantId"] or len(canonical(identity).encode("utf-8")) > 8192:
        raise ValueError("Invalid creative identity lineage or size")
    return identity


def default_registry():
    return Path(os.environ.get("DISTRIBUTION_NOVELTY_REGISTRY", str(Path.home() / ".codex/state/openmontage-content-novelty.sqlite")))


class NoveltyRegistry:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else default_registry()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=15)
        self.db.execute("PRAGMA busy_timeout=15000")
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS facts(channel TEXT,source TEXT,id TEXT,body TEXT NOT NULL,PRIMARY KEY(channel,source,id));
          CREATE TABLE IF NOT EXISTS snapshots(channel TEXT PRIMARY KEY,revision TEXT NOT NULL,coverage TEXT NOT NULL,checked_at REAL NOT NULL);
          CREATE TABLE IF NOT EXISTS intents(production_id TEXT PRIMARY KEY,channel TEXT NOT NULL,story_key TEXT,identity_hash TEXT NOT NULL,
            body TEXT NOT NULL,state TEXT NOT NULL,version INTEGER NOT NULL);
          CREATE UNIQUE INDEX IF NOT EXISTS live_story_intent ON intents(channel,story_key)
            WHERE story_key IS NOT NULL AND state IN ('PREPARED','GENERATING','SUBMITTED_UNKNOWN');
          CREATE TABLE IF NOT EXISTS intent_events(id INTEGER PRIMARY KEY,production_id TEXT NOT NULL,state TEXT NOT NULL,version INTEGER NOT NULL,body TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS decisions(cache_key TEXT PRIMARY KEY,body TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS delivery_plans(production_id TEXT PRIMARY KEY,channel TEXT NOT NULL,
            plan_hash TEXT NOT NULL,body TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS creative_index_cache(origin TEXT NOT NULL,channel TEXT NOT NULL,
            inventory_revision TEXT NOT NULL,body TEXT NOT NULL,PRIMARY KEY(origin,channel));
        """)

    def close(self):
        self.db.close()

    def cached_inventory(self, origin, channel, inventory_revision):
        row = self.db.execute("SELECT body FROM creative_index_cache WHERE origin=? AND channel=? AND inventory_revision=?",
                              (origin, channel, inventory_revision)).fetchone()
        try:
            return json.loads(row[0]) if row else None
        except (ValueError, TypeError):
            return None

    def cache_inventory(self, origin, snapshot):
        with self.db:
            self.db.execute("INSERT INTO creative_index_cache VALUES(?,?,?,?) ON CONFLICT(origin,channel) DO UPDATE SET "
                            "inventory_revision=excluded.inventory_revision,body=excluded.body",
                            (origin, snapshot["channelCode"], snapshot["inventoryRevision"], canonical(snapshot)))

    def sync(self, snapshot):
        channel = snapshot["channelCode"]
        with self.db:
            self.db.execute("DELETE FROM facts WHERE channel=? AND source='hub'", (channel,))
            self.db.executemany("INSERT INTO facts VALUES(?,?,?,?)", [(channel, "hub", r["id"], canonical(r)) for r in snapshot["items"]])
            self.db.execute("INSERT INTO snapshots VALUES(?,?,?,?) ON CONFLICT(channel) DO UPDATE SET revision=excluded.revision,coverage=excluded.coverage,checked_at=excluded.checked_at",
                            (channel, snapshot["revision"], canonical(snapshot["coverage"]), time.time()))

    def import_retained(self, packet, channel="MT"):
        """Retained JSON facts only; never loads retired code or databases."""
        packet = Path(packet)
        identities = json.loads((packet / "History/content-identities.json").read_text(encoding="utf-8"))["records"]
        usage = json.loads((packet / "History/formula-usage.json").read_text(encoding="utf-8"))
        source_file = packet / "Formulas/source-verified-85.json"
        aliases = {}
        if source_file.exists():
            for formula in json.loads(source_file.read_text(encoding="utf-8"))["formulas"]:
                if formula.get("status") == "SOURCE_VERIFIED":
                    aliases.setdefault("sha256:" + formula["formula_fingerprint"], set()).add(source_formula_key(formula))
        recipes = {}
        for row in usage:
            legacy = "sha256:" + row["formula_fingerprint"]
            recipes.setdefault(row["content_id"], set()).update({legacy, *aliases.get(legacy, set())})
        by_id = {row["content_id"]: row for row in identities}
        for content_id in recipes.keys() - by_id.keys():
            by_id[content_id] = {"content_id": content_id, "title": "", "legacy_status": "UNKNOWN"}
        with self.db:
            for row in by_id.values():
                body = {"id": row["content_id"], "kind": "retained", "title": row["title"], "identity": None,
                        "recipeKeys": sorted(recipes.get(row["content_id"], set())), "legacyIdentity": row.get("identity"),
                        "legacyStatus": row["legacy_status"], "purpose": "UNKNOWN", "publication": "NOT_ASSERTED"}
                self.db.execute("INSERT INTO facts VALUES(?,?,?,?) ON CONFLICT(channel,source,id) DO UPDATE SET body=excluded.body",
                                (channel, "retained", row["content_id"], canonical(body)))
        return {"identities": len(identities), "retainedFacts": len(by_id), "formulaUsageRows": len(usage),
                "sourceFormulaBridges": len(aliases), "purposeInference": "NOT_PERFORMED"}

    def record(self, channel, identity):
        validate_identity(identity)
        body = {"id": "local:" + identity["productionId"] + ":" + digest(identity), "kind": "local", "title": identity["question"],
                "identity": identity, "publication": "NOT_ASSERTED"}
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO facts VALUES(?,?,?,?)", (channel, "local", body["id"], canonical(body)))

    def reserve(self, channel, identity, delivery_plan=None):
        validate_identity(identity)
        if delivery_plan is not None:
            from lib.content_delivery import validate_plan
            validate_plan(delivery_plan, channel=channel, identity=identity)
        meaningful = identity["question"] and identity["takeaway"] and identity["storyBeats"]
        if identity["purpose"] != "TEST" and not meaningful:
            raise ValueError("Production reservation needs its question, takeaway and story beats")
        key = None if identity["purpose"] == "TEST" else digest({k: normalized_text(identity[k]) if isinstance(identity[k], str) else
              sorted(identity[k]) if k == "recipeKeys" else [normalized_text(v) for v in identity[k]]
              for k in ("question", "takeaway", "storyBeats", "recipeKeys", "applicationContext")})
        self.db.execute("BEGIN IMMEDIATE")
        try:
            prior = self.db.execute("SELECT identity_hash,state,channel,version FROM intents WHERE production_id=?", (identity["productionId"],)).fetchone()
            if prior:
                if prior[0] != digest(identity) or prior[1] not in {"PREPARED", "GENERATING", "SUBMITTED_UNKNOWN"} or prior[2] != channel:
                    raise ValueError("Production identity or completed intent cannot be silently replaced")
            if delivery_plan is not None:
                planned = self.db.execute("SELECT channel,plan_hash,body FROM delivery_plans WHERE production_id=?", (identity["productionId"],)).fetchone()
                if planned:
                    if planned != (channel, delivery_plan["planHash"], canonical(delivery_plan)):
                        raise ValueError("Reserved delivery plan cannot be replaced")
                elif prior and prior[1] != "PREPARED":
                    raise ValueError("Cannot attach a delivery plan after generation starts")
                else:
                    self.db.execute("INSERT INTO delivery_plans VALUES(?,?,?,?)", (identity["productionId"], channel, delivery_plan["planHash"], canonical(delivery_plan)))
            if not prior:
                self.db.execute("INSERT INTO intents VALUES(?,?,?,?,?,'PREPARED',1)", (identity["productionId"], channel, key, digest(identity), canonical(identity)))
                self.db.execute("INSERT INTO intent_events(production_id,state,version,body) VALUES(?,'PREPARED',1,?)", (identity["productionId"], canonical(identity)))
            self.db.commit()
            return {"state": prior[1] if prior else "PREPARED", "version": prior[3] if prior else 1,
                    "productionId": identity["productionId"], **({"deliveryPlanHash": delivery_plan["planHash"]} if delivery_plan is not None else {})}
        except sqlite3.IntegrityError:
            self.db.rollback()
            raise ValueError("ACTIVE_INTENT_CONFLICT: another production owns this story") from None
        except Exception:
            self.db.rollback()
            raise

    def verify_delivery_plan(self, plan):
        """Read the immutable pre-generation binding; never retroactively seal it."""
        from lib.content_delivery import validate_plan
        validate_plan(plan)
        row = self.db.execute("SELECT p.channel,p.plan_hash,p.body,i.state FROM delivery_plans p JOIN intents i ON i.production_id=p.production_id WHERE p.production_id=?",
                              (plan["identity"]["productionId"],)).fetchone()
        if row != (plan["channelCode"], plan["planHash"], canonical(plan), "FINISHED"):
            raise ValueError("Delivery requires the exact reserved plan and finished production intent")
        return plan["planHash"]

    def transition(self, production_id, expected_version, state, reconciled=False):
        if state not in {"GENERATING", "SUBMITTED_UNKNOWN", "FINISHED", "CANCELLED"}:
            raise ValueError("Invalid intent state")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute("SELECT state,version FROM intents WHERE production_id=?", (production_id,)).fetchone()
            if not row or row[1] != expected_version or row[0] in {"FINISHED", "CANCELLED"}:
                raise ValueError("Stale or terminal intent transition")
            if row[0] == state:
                raise ValueError("Intent reentry cannot authorize another provider submission")
            if row[0] == "SUBMITTED_UNKNOWN" and not reconciled:
                raise ValueError("UNKNOWN provider submission requires reconciliation")
            if row[0] == "GENERATING" and state == "CANCELLED" and not reconciled:
                raise ValueError("Running provider submission requires reconciliation before cancellation")
            self.db.execute("UPDATE intents SET state=?,version=version+1 WHERE production_id=?", (state, production_id))
            self.db.execute("INSERT INTO intent_events(production_id,state,version,body) VALUES(?,?,?,?)", (production_id, state, expected_version + 1, canonical({"reconciled": reconciled})))
            self.db.commit()
            return expected_version + 1
        except Exception:
            self.db.rollback()
            raise

    def evaluate(self, channel, identity, stage, max_context_bytes=16000):
        validate_identity(identity)
        if stage not in {"PRE_GENERATION", "PRE_DELIVERY"} or type(max_context_bytes) is not int or not 1024 <= max_context_bytes <= 64000:
            raise ValueError("Invalid novelty stage or context budget")
        snapshot = self.db.execute("SELECT revision,coverage FROM snapshots WHERE channel=?", (channel,)).fetchone()
        revision = snapshot[0] if snapshot else "UNAVAILABLE"
        rows = [json.loads(r[0]) for r in self.db.execute("SELECT body FROM facts WHERE channel=? ORDER BY source,id", (channel,))]
        # Merge only exact IDs, keeping both authoritative distribution and retained recipe evidence.
        merged = {}
        for row in rows:
            prior = merged.get(row["id"], {})
            # Hub title/kind/publication remain authoritative when an exact ID also has retained facts.
            authoritative = prior if prior.get("kind") == "hub" else row
            merged[row["id"]] = {**prior, **row, **authoritative, "identity": row.get("identity") or prior.get("identity"),
                                 "legacyStatus": row.get("legacyStatus", prior.get("legacyStatus")),
                                 "recipeKeys": sorted(set(prior.get("recipeKeys", [])) | set(row.get("recipeKeys", [])))}
        stop = {"the", "a", "an", "of", "in", "and", "for", "to", "one", "mix", "mixes", "paint", "color", "colour", "source", "verified", "what", "does"}
        def words(text):
            return set(re.findall(r"\w+", normalized_text(text))) - stop
        query_words = words(" ".join([identity["question"], identity["takeaway"], identity["applicationContext"], *identity["storyBeats"]]))
        matches = []
        for row in merged.values():
            other = row.get("identity") or {}
            if other.get("productionId") == identity["productionId"] and other.get("variantId") == identity["variantId"]:
                continue
            reasons = []
            if identity["primaryFileSha256"] and identity["primaryFileSha256"] == (row.get("primaryFileSha256") or other.get("primaryFileSha256")):
                reasons.append("EXACT_FILE")
            if identity["scriptHash"] and identity["scriptHash"] == other.get("scriptHash"):
                reasons.append("EXACT_SCRIPT")
            if set(identity["nativeClipSha256"]) & set(other.get("nativeClipSha256", [])):
                reasons.append("SOURCE_CLIP_REUSED")
            if identity["parentVariantId"] and identity["parentVariantId"] == other.get("variantId"):
                reasons.append("DECLARED_DERIVATIVE")
            if set(identity["recipeKeys"]) & (set(other.get("recipeKeys", [])) | set(row.get("recipeKeys", []))):
                reasons.append("RECIPE_REUSED")
            candidate_words = words(" ".join([str(row.get("title", "")), other.get("question", ""), other.get("takeaway", ""), other.get("applicationContext", ""), *other.get("storyBeats", [])]))
            overlap = query_words & candidate_words
            if len(overlap) >= 2:
                reasons.append("RELATED_TOPIC")
            if not reasons:
                continue
            card = {"id": row["id"], "title": row.get("title", ""), "reasons": reasons,
                    "purpose": other.get("purpose", "UNKNOWN"), "question": other.get("question", ""), "takeaway": other.get("takeaway", ""),
                    "storyBeats": other.get("storyBeats", []), "distribution": row.get("distribution", []),
                    "publication": row.get("publication", "NOT_ASSERTED"), "metaEvidence": row.get("metaEvidence", []),
                    "legacyStatus": row.get("legacyStatus"), "unknown": not bool(other)}
            matches.append((sum({"EXACT_FILE": 100, "EXACT_SCRIPT": 90, "SOURCE_CLIP_REUSED": 80, "DECLARED_DERIVATIVE": 80, "RECIPE_REUSED": 30, "RELATED_TOPIC": 10}[r] for r in reasons), card))
        matches.sort(key=lambda pair: (-pair[0], pair[1]["id"]))
        selected = []
        used = len(canonical({"candidate": identity, "matches": []}).encode("utf-8"))
        if used > max_context_bytes:
            raise ValueError("Candidate identity exceeds comparison context budget")
        for _, card in matches:
            size = len(canonical({"candidate": identity, "matches": [*selected, card]}).encode("utf-8"))
            if size > max_context_bytes:
                break
            selected.append(card)
            used = size
        report = {"version": VERSION, "stage": stage, "mode": "SHADOW", "status": "REVIEW_REQUIRED",
                  "testAllowed": identity["purpose"] == "TEST", "indexRevision": revision,
                  "coverage": json.loads(snapshot[1]) if snapshot else {"completeHubInventory": False},
                  "candidate": identity, "matches": selected, "matchingRecords": len(matches), "omittedMatches": len(matches) - len(selected),
                  "contextBytes": used, "contextBudgetBytes": max_context_bytes,
                  "limits": ["Recipe reuse is not whole-script duplication", "No semantic model judgment performed", "Unknown historical purpose/publication remains visible", "Byte budget is not a measured tokenizer count"],
                  "nextAction": "Compare viewer takeaway and demonstration; expand relevant omitted/unknown evidence before claiming novelty"}
        key = digest({"version": VERSION, "channel": channel, "identity": identity, "revision": revision,
                      "facts": digest(rows), "stage": stage, "budget": max_context_bytes})
        cached = self.db.execute("SELECT body FROM decisions WHERE cache_key=?", (key,)).fetchone()
        if cached:
            return {**json.loads(cached[0]), "cacheHit": True}
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO decisions VALUES(?,?)", (key, canonical(report)))
        return {**report, "cacheHit": False}


def check_content(client, channel, identity, stage, registry_path=None, reserve=False, delivery_plan=None, snapshot=None):
    registry = NoveltyRegistry(registry_path)
    try:
        snapshot = snapshot if snapshot is not None else client.creative_index(channel, registry_path=registry_path)
        registry.sync(snapshot)
        report = registry.evaluate(channel, identity, stage)
        if reserve:
            if snapshot["active"] != 1:
                raise ValueError("Inactive channel cannot reserve a production")
            report["intent"] = registry.reserve(channel, identity, delivery_plan)
        registry.record(channel, identity)
        return report
    finally:
        registry.close()
