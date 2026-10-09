"""Exact final-caption website evidence; this module never publishes content."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

import requests

from lib.distribution_hub import HubError, _local_file, _require, bytes_digest, digest

ORIGIN = "https://mixtherapy.space"
MAX_AGE_SECONDS = 86400


def _utf8(value):
    try:
        return value.encode("utf-8")
    except UnicodeError:
        raise HubError("Invalid final caption UTF-8") from None


def _digest(value):
    try:
        return digest(value)
    except (TypeError, UnicodeError, OverflowError):
        raise HubError("Invalid caption evidence") from None


def is_caption_file(file):
    _require(isinstance(file, dict) and isinstance(file.get("path"), str) and isinstance(file.get("mimeType"), str),
             "Invalid caption file descriptor")
    return file["mimeType"] == "text/plain" or (file["mimeType"] == "application/json" and
            bool(re.search(r"(?:^|/)(?:metadata|package)\.json$", file["path"])))


def caption_urls(text):
    values = re.findall(r'https?://[^\s<>"\']+|(?<![\w@/.])mixtherapy\.space(?:/[^\s<>"\']*)?', text, re.I)
    return sorted({v.rstrip(".,;!") if re.match(r"https?://", v, re.I) else "https://" + v.rstrip(".,;!") for v in values})


def website_urls(urls):
    """Owned authority candidates only; keep every URL in the final field seal."""
    selected = set()
    for url in urls:
        authority = re.match(r"^https?://([^/?#]*)", url, re.I)
        if authority and re.search(r"mixtherapy\.space", unquote(authority[1]), re.I):
            selected.add(url)  # Decode only to select unsafe owned candidates, never to repair their URLs.
    return sorted(selected)


def _explicit_link_urls(text):
    value = text.strip()
    return [value] if re.match(r"^https?://", value, re.I) else caption_urls(text)


def _field_urls(field):
    text = field["text"]
    if field["id"] == "pinterest:link":
        return _explicit_link_urls(text)
    if field["id"].startswith("file:") and field["id"].endswith(".json"):
        try:
            value = json.loads(text)
            pending, urls = [(value, None)], set()
            while pending:
                node, key = pending.pop()
                if isinstance(node, dict):
                    pending.extend((v, k) for k, v in node.items())
                elif isinstance(node, list):
                    pending.extend((entry, key) for entry in node)
                elif isinstance(node, str):
                    urls.update(_explicit_link_urls(node) if key == "link" else caption_urls(node))
            return sorted(urls)
        except (ValueError, RecursionError):
            raise HubError("Invalid final metadata JSON") from None
    return caption_urls(text)


def owned_url(value):
    _require(isinstance(value, str) and len(value) <= 2000 and not re.search(r"[\s\\\x00-\x1f\x7f]", value),
             "Caption pilot requires an exact owned HTTPS website URL")
    parsed = urlsplit(value)
    _require(parsed.scheme == "https" and parsed.netloc == "mixtherapy.space" and not parsed.username and
             not parsed.password and "#" not in value and "%" not in parsed.path and
             parsed.path.startswith("/") and not re.search(r"//|(?:^|/)\.{1,2}(?:/|$)", parsed.path) and
             value.split("?", 1)[0] == ORIGIN + parsed.path,
             "Caption pilot requires an exact owned HTTPS website URL")
    return parsed


def seal_fields(fields):
    _require(isinstance(fields, list) and len(fields) <= 100 and all(isinstance(f, dict) and
             set(f) == {"id", "text"} and isinstance(f["id"], str) and 0 < len(f["id"]) <= 240 and
             isinstance(f["text"], str) and len(_utf8(f["text"])) <= 65536 for f in fields) and
             len({f["id"] for f in fields}) == len(fields), "Invalid final caption fields")
    return sorted([{"id": f["id"], "sha256": bytes_digest(_utf8(f["text"])),
                    "urls": _field_urls(f)} for f in fields], key=lambda f: f["id"])


def package_fields(item):
    fields = []
    meta = item.get("facebookInstagram")
    meta = {} if meta is None else meta
    _require(isinstance(meta, dict), "Invalid packaged caption fields")
    for side in ("facebook", "instagram"):
        package = meta.get(side)
        package = {} if package is None else package
        _require(isinstance(package, dict), "Invalid packaged caption fields")
        caption = package.get("caption")
        if isinstance(caption, str):
            fields.append({"id": side + ":caption", "text": caption})
    for target, names in (("youtube", ("title", "description")), ("pinterest", ("title", "description", "altText", "link")),
                          ("x", ("text",)), ("tiktok", ("caption",))):
        package = item.get(target)
        package = {} if package is None else package
        _require(isinstance(package, dict), "Invalid packaged caption fields")
        for name in names:
            if isinstance(package.get(name), str):
                fields.append({"id": target + ":" + name, "text": package[name]})
    return fields


def final_fields(item, root):
    fields = package_fields(item)
    for file in item.get("deliveryManifest", {}).get("files", []):
        if is_caption_file(file):
            data = _local_file(Path(root).resolve(strict=True), file).read_bytes()
            _require(len(data) <= 65536 and bytes_digest(data) == file["sha256"], "Final caption file changed")
            try:
                fields.append({"id": "file:" + file["path"], "text": data.decode("utf-8", errors="strict")})
            except UnicodeError:
                raise HubError("Invalid final caption UTF-8") from None
    return fields


def _fresh(value, now):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return False
        at = parsed.timestamp()
        return at <= now + 300 and now - at <= MAX_AGE_SECONDS
    except (ValueError, AttributeError, TypeError):
        return False


def _timestamp(value):
    try:
        return isinstance(value, str) and datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is not None
    except ValueError:
        return False


def validate_qa(item, root=None, *, now=None, freshness=True):
    """Metadata validation also covers direct ingest; handoff additionally reads bytes."""
    _require(isinstance(item, dict), "Invalid caption source")
    if item.get("channelCode") != "MT":
        _require(item.get("captionLinkQa") is None, "Caption website QA is restricted to MT")
        return None
    qa = item.get("captionLinkQa")
    expected = seal_fields(package_fields(item))
    manifest = item.get("deliveryManifest", {})
    _require(isinstance(manifest, dict) and isinstance(manifest.get("files", []), list), "Invalid caption manifest")
    files = [f for f in manifest.get("files", []) if is_caption_file(f)]
    needs_evidence = bool(website_urls([url for f in expected for url in f["urls"]])) or bool(files)
    if qa is None and not needs_evidence:
        return None
    _require(isinstance(qa, dict) and set(qa) == {"schemaVersion", "contentId", "assetHash", "distributionRevision",
             "fields", "reviewer", "checkedAt", "websiteRelease", "checks", "receiptHash"} and
             type(qa.get("schemaVersion")) is int and qa["schemaVersion"] == 1, "Missing final caption website QA")
    body = {k: v for k, v in qa.items() if k != "receiptHash"}
    at = now if now is not None else datetime.now(timezone.utc).timestamp()
    actual = qa.get("fields")
    _require(isinstance(actual, list) and len(actual) <= 100 and all(isinstance(f, dict) and
             set(f) == {"id", "sha256", "urls"} and isinstance(f["id"], str) and 0 < len(f["id"]) <= 240 and
             isinstance(f["sha256"], str) and bool(re.fullmatch(r"sha256:[a-f0-9]{64}", f["sha256"])) and
             isinstance(f["urls"], list) and len(f["urls"]) <= 20 and all(isinstance(u, str) for u in f["urls"]) and
             f["urls"] == sorted(set(f["urls"])) for f in actual) and actual == sorted(actual, key=lambda f: f["id"]), "Invalid caption seal")
    link_bound = bool(website_urls([u for f in actual for u in f["urls"]]))
    _require(qa.get("receiptHash") == _digest(body) and qa.get("contentId") == item["id"] and
             qa.get("assetHash") == item["assetHash"] and qa.get("distributionRevision") == item["distributionRevision"] and
             _timestamp(qa.get("checkedAt")) and
             (not freshness or not link_bound or _fresh(qa.get("checkedAt"), at)), "Caption website evidence is stale or belongs to another source")
    _require(isinstance(actual, list) and len(actual) == len(expected) + len(files) and
             len({f.get("id") for f in actual if isinstance(f, dict)}) == len(actual), "Caption QA scope differs from final package")
    for field in expected:
        _require(next((f for f in actual if f.get("id") == field["id"]), None) == field, "Final caption changed after review")
    for file in files:
        sealed = next((f for f in actual if f.get("id") == "file:" + file["path"]), None)
        _require(sealed is not None and sealed.get("sha256") == file["sha256"], "Final caption/metadata file lacks review")
    if root is not None:
        _require(actual == seal_fields(final_fields(item, root)), "Receipt omits or changes URLs in final packaged files")
    urls = website_urls([url for field in actual for url in field["urls"]])
    for url in urls:
        owned_url(url)
    review = qa.get("reviewer")
    verdict = "PASS" if urls else "NOT_APPLICABLE"
    _require(isinstance(review, dict) and isinstance(review.get("name"), str) and 0 < len(review["name"].strip()) <= 200 and
             set(review) == {"name", "checkedAt", "semantic", "browser", "evidence"} and
             _timestamp(review.get("checkedAt")) and
             (not freshness or not urls or _fresh(review.get("checkedAt"), at)) and review.get("semantic") == verdict and review.get("browser") == verdict and
             isinstance(review.get("evidence"), list) and len(review["evidence"]) <= 20 and
             (not urls or bool(review["evidence"])) and all(isinstance(e, str) and 0 < len(e.strip()) <= 1000 for e in review["evidence"]),
             "Named semantic and rendered website review is required")
    checks = qa.get("checks")
    _require(isinstance(checks, list) and all(isinstance(c, dict) and set(c) == {"url", "status", "identity", "sourceReceiptSha256"} and
             isinstance(c.get("url"), str) for c in checks) and len(checks) == len(urls) and sorted(c["url"] for c in checks) == urls and
             (_hex(qa.get("websiteRelease")) if urls else qa.get("websiteRelease") is None),
             "Website checks do not cover exact final URLs")
    for check in checks:
        _require(type(check.get("status")) is int and check["status"] == 200 and isinstance(check.get("identity"), str) and 0 < len(check["identity"]) <= 240 and
                 (check.get("sourceReceiptSha256") is None or _hex(check["sourceReceiptSha256"])),
                 "Website check did not pass")
    return qa


def _hex(value):
    return isinstance(value, str) and bool(re.fullmatch(r"[a-f0-9]{64}", value))


def fresh_qa(qa, *, getter=None):
    if qa is None:
        return
    current = check_website(website_urls([url for field in qa["fields"] for url in field["urls"]]), getter=getter)
    _require(current["websiteRelease"] == qa["websiteRelease"] and current["checks"] == qa["checks"],
             "Website changed after final caption review")


def export_qa(fields, asset_hash, review, *, getter=None):
    """Review input must already seal these exact paste-ready bytes and asset."""
    sealed = seal_fields(fields)
    urls = website_urls([u for f in sealed for u in f["urls"]])
    if not urls:
        return None
    _require(isinstance(review, dict) and set(review) == {"schemaVersion", "assetHash", "fields", "websiteRelease", "reviewer"} and
             type(review["schemaVersion"]) is int and review["schemaVersion"] == 1 and review["assetHash"] == asset_hash and
             review["fields"] == sealed and _hex(review["websiteRelease"]), "Exact final export requires a sealed named caption review")
    files = [{"path": f["id"][5:], "mimeType": "text/plain", "sha256": f["sha256"]} for f in sealed]
    item = {"channelCode": "MT", "id": "export:" + digest(sealed)[7:], "assetHash": asset_hash,
            "distributionRevision": digest(sealed), "deliveryManifest": {"files": files}}
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    # Validate the named semantic/browser verdict before accessing the website.
    body = {"schemaVersion": 1, "contentId": item["id"], "assetHash": asset_hash, "distributionRevision": item["distributionRevision"],
            "fields": sealed, "reviewer": review["reviewer"], "checkedAt": now, "websiteRelease": review["websiteRelease"],
            "checks": [{"url": u, "identity": "pending-http", "status": 200, "sourceReceiptSha256": None} for u in urls]}
    validate_qa({**item, "captionLinkQa": {**body, "receiptHash": digest(body)}})
    current = check_website(urls, getter=getter)
    _require(current["websiteRelease"] == review["websiteRelease"], "Website changed after export review")
    body.update(current)
    result = {**body, "receiptHash": digest(body)}
    validate_qa({**item, "captionLinkQa": result})
    return result


class _Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta, self.canonical, self.title, self.main, self.in_title = {}, None, "", False, False
        self.invalid, self.title_count = False, 0

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "meta":
            if values.get("name") in self.meta and values.get("name") in {"mixtherapy-caption-identity", "mixtherapy-website-release"}:
                self.invalid = True
            self.meta[values.get("name")] = values.get("content")
        if tag == "link" and values.get("rel") == "canonical":
            self.invalid |= self.canonical is not None
            self.canonical = values.get("href")
        if tag == "title":
            self.title_count += 1
            self.in_title = True
        if tag == "main":
            self.main = True

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title += data


def check_website(urls, *, getter=None):
    """Fresh public GETs, no credentials, redirect following or arbitrary hosts."""
    _require(isinstance(urls, list) and all(isinstance(u, str) for u in urls), "Invalid caption URLs")
    unique = sorted(set(urls))
    _require(len(unique) <= 20, "Too many caption URLs")
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    if not unique:
        return {"checkedAt": now, "websiteRelease": None, "checks": []}
    for url in unique:
        owned_url(url)
    session = requests.Session()
    session.trust_env = False  # No netrc Authorization or inherited account cookies.

    def get(url, limit):
        owned_url(url)
        if getter is not None:
            data = getter(url)
            _require(isinstance(data, bytes) and len(data) <= limit, "Invalid public website response")
            return data
        try:
            with session.get(url, timeout=15, allow_redirects=False, stream=True) as response:
                _require(response.status_code == 200 and response.url == url, "Website HTTP/redirect check failed")
                parts, size = [], 0
                for part in response.iter_content(65536):
                    size += len(part)
                    _require(size <= limit, "Website response exceeds check limit")
                    parts.append(part)
                return b"".join(parts)
        except requests.RequestException:
            raise HubError("Website unavailable; handoff blocked") from None

    try:
        before = get(ORIGIN + "/caption-link-targets.json", 262144)
        catalog = json.loads(before)
        _require(isinstance(catalog, dict) and type(catalog.get("schemaVersion")) is int and catalog["schemaVersion"] == 1 and
                 _hex(catalog.get("websiteRelease")) and _hex(catalog.get("recipeRelease")) and
                 isinstance(catalog.get("targets"), list) and 0 < len(catalog["targets"]) <= 500, "Invalid website catalog")
        paths = set()
        for target in catalog["targets"]:
            _require(isinstance(target, dict) and set(target) == {"path", "title", "canonical", "identity", "sourceReceiptPath", "sourceReceiptSha256", "publicationEligible"} and
                     isinstance(target["path"], str) and target["path"] not in paths and type(target["publicationEligible"]) is bool and
                     all(isinstance(target[k], str) and 0 < len(target[k]) <= 2000 for k in ("title", "canonical", "identity")), "Invalid website target")
            _require("?" not in target["path"] and "#" not in target["path"], "Invalid website target path")
            owned_url(ORIGIN + target["path"])
            _require(target["canonical"] == ORIGIN + target["path"], "Invalid website canonical")
            source, source_hash = target["sourceReceiptPath"], target["sourceReceiptSha256"]
            _require((source is None and source_hash is None) or (isinstance(source, str) and
                     bool(re.fullmatch(r"/provenance/[a-z0-9-]+\.json", source)) and _hex(source_hash)), "Invalid recipe source")
            paths.add(target["path"])
        checks = []
        for url in unique:
            parsed = owned_url(url)
            matches = [t for t in catalog["targets"] if t.get("path") == parsed.path]
            _require(len(matches) == 1 and matches[0].get("publicationEligible") is True, "Page not approved for caption use")
            target = matches[0]
            page = _Page()
            page.feed(get(url, 1048576).decode("utf-8"))
            _require(not page.invalid and page.title_count == 1 and page.main and page.title == target["title"] and page.canonical == target["canonical"] == ORIGIN + parsed.path and
                     page.meta.get("mixtherapy-caption-identity") == target["identity"] and
                     page.meta.get("mixtherapy-website-release") == catalog["websiteRelease"] and
                     not re.search(r"page not found|sign in required", page.title, re.I), "Wrong page or soft 404")
            source = target.get("sourceReceiptPath")
            source_hash = target.get("sourceReceiptSha256")
            if source is not None:
                _require(source.startswith("/provenance/") and bool(re.fullmatch(r"[a-f0-9]{64}", source_hash or "")), "Invalid recipe source")
                _require(bytes_digest(get(ORIGIN + source, 262144)) == "sha256:" + source_hash, "Deployed recipe source changed")
            checks.append({"url": url, "identity": target["identity"], "status": 200, "sourceReceiptSha256": source_hash})
        _require(get(ORIGIN + "/caption-link-targets.json", 262144) == before, "Website changed during caption QA")
        return {"checkedAt": now, "websiteRelease": catalog["websiteRelease"], "checks": checks}
    except (ValueError, TypeError, KeyError, UnicodeError) as error:
        if isinstance(error, HubError):
            raise
        raise HubError("Invalid public website response") from None
    finally:
        session.close()


def review_scope(item, root):
    return {"schemaVersion": 1, "contentId": item["id"], "assetHash": item["assetHash"],
            "distributionRevision": item["distributionRevision"], "fields": seal_fields(final_fields(item, root))}


def build_qa(item, root, review, *, getter=None):
    scope = review_scope(item, root)
    _require(isinstance(review, dict) and set(review) == set(scope) | {"websiteRelease", "reviewer"} and
             all(review[k] == value for k, value in scope.items()) and type(review["schemaVersion"]) is int,
             "Named review must bind the exact final source and fields")
    fields = scope["fields"]
    urls = website_urls([url for field in fields for url in field["urls"]])
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    body = {"schemaVersion": 1, "contentId": item["id"], "assetHash": item["assetHash"],
            "distributionRevision": item["distributionRevision"], "fields": fields, "reviewer": review["reviewer"],
            "websiteRelease": review["websiteRelease"], "checkedAt": now,
            "checks": [{"url": u, "identity": "pending-http", "status": 200, "sourceReceiptSha256": None} for u in urls]}
    # An unchanged PASS note cannot certify an edited source or caption. Validate
    # the explicit scoped review before fresh HTTP, without overwriting old QA.
    validate_qa({**item, "captionLinkQa": {**body, "receiptHash": _digest(body)}}, root)
    check = check_website(urls, getter=getter)
    _require(check["websiteRelease"] == review["websiteRelease"], "Website changed after named review")
    body.update(check)
    result = {**body, "receiptHash": digest(body)}
    validate_qa({**item, "captionLinkQa": result}, root)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payload", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True, help="Scoped named review JSON (or array for batch); no automatic PASS")
    parser.add_argument("--output", type=Path, required=True, help="New ingest payload; original is preserved")
    args = parser.parse_args()
    _require(args.output.resolve() != args.payload.resolve() and not args.output.exists(), "Use a new output path")
    payload = json.loads(args.payload.read_text(encoding="utf-8"))
    review = json.loads(args.review.read_text(encoding="utf-8"))
    reviews = review if isinstance(review, list) else [review]
    wanted = [item["id"] for item in payload["items"] if item.get("channelCode") == "MT"]
    _require(all(isinstance(r, dict) and isinstance(r.get("contentId"), str) for r in reviews) and
             len(reviews) == len(wanted) and {r["contentId"] for r in reviews} == set(wanted), "Scoped reviews must cover exact MT batch")
    for item in payload["items"]:
        if item.get("channelCode") == "MT":
            item["captionLinkQa"] = build_qa(item, args.root, next(r for r in reviews if r["contentId"] == item["id"]))
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
