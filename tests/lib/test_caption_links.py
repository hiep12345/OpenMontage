"""No sockets: fail-closed final bytes, public identity and replay boundaries."""
import copy
import base64
from datetime import datetime, timezone
import json

import pytest

from lib import caption_links as links
from lib.distribution_hub import HubError, bytes_digest, digest
from scripts.hub_contract_fixture import fixture

ORIGIN = links.ORIGIN
URL = ORIGIN + "/mix/historical-asphaltum-50-25-3/"
RELEASE = "a" * 64


def review():
    return {"name": "Named reviewer", "checkedAt": datetime.now(timezone.utc).isoformat(),
            "semantic": "PASS", "browser": "PASS", "evidence": ["review/desktop.png", "review/mobile.png", "review/source.json"]}


def website(path="/mix/historical-asphaltum-50-25-3/", eligible=True):
    source = b'{"source":"synthetic-test-only"}'
    target = {"path": path, "title": "Asphaltum & source", "canonical": ORIGIN + path,
              "identity": path.split("/")[-2], "sourceReceiptPath": "/provenance/test.json",
              "sourceReceiptSha256": bytes_digest(source)[7:], "publicationEligible": eligible}
    catalog = {"schemaVersion": 1, "recipeRelease": "b" * 64, "websiteRelease": RELEASE, "targets": [target]}
    html = (f'<title>Asphaltum &amp; source</title><link rel="canonical" href="{ORIGIN}{path}">'
            f'<meta name="mixtherapy-caption-identity" content="{target["identity"]}">'
            f'<meta name="mixtherapy-website-release" content="{RELEASE}"><main>Public recipe</main>')
    responses = {ORIGIN + path: html.encode(), ORIGIN + "/provenance/test.json": source,
                 ORIGIN + "/caption-link-targets.json": json.dumps(catalog).encode()}
    return responses, catalog


def linked_item():
    item = fixture()["payload"]["items"][0]
    item["youtube"] = {"title": "Recipe", "description": URL}
    fields = links.seal_fields(links.package_fields(item)) + item["captionLinkQa"]["fields"]
    fields.sort(key=lambda f: f["id"])
    current = links.check_website([URL], getter=website()[0].__getitem__)
    body = {**{k: v for k, v in item["captionLinkQa"].items() if k != "receiptHash"},
            "fields": fields, "reviewer": review(), **current}
    item["captionLinkQa"] = {**body, "receiptHash": digest(body)}
    return item


def reseal(qa):
    qa["receiptHash"] = digest({k: v for k, v in qa.items() if k != "receiptHash"})


@pytest.mark.parametrize("value", [
    "https://mixtherapy.space/mix/%2e%2e/", "https://mixtherapy.space/mix/../", "https://mixtherapy.space//mix/a/",
    "https://mixtherapy.space\\@evil.example/mix/a/", "https://user:password@mixtherapy.space/mix/a/?utm_source=facebook",
    "https://mixtherapy.space/mix/a/#caption", "https://mixtherapy.space:443/mix/a/",
    " https://mixtherapy.space/mix/a/", "https://mixtherapy.space/mix/\na/", "https://mixtherapy.space/mix/%61/",
    "http://mixtherapy.space/mix/a/", "https://mixtherapy.space@evil.example/mix/a/", None,
])
def test_unsafe_raw_urls_fail_before_http(value):
    with pytest.raises(HubError):
        links.check_website([value], getter=lambda _: pytest.fail("Unsafe URL issued HTTP"))


@pytest.mark.parametrize("query,status", [
    ("utm_source=facebook&utm_medium=social&utm_campaign=caption_recipe_memory_v1&utm_content=mt-content-70195f63590c6588", 200),
    ("utm_content=exact%20caption&redirect=elsewhere", 200),
    ("redirect=elsewhere", 302),
])
def test_attribution_query_is_sealed_and_requested_exactly_without_credentials(query, status, monkeypatch):
    url = URL + "?" + query
    responses, _ = website()
    responses[url] = responses.pop(URL)
    calls = []
    class Response:
        status_code = 200
        def __init__(self, value):
            self.url = value
            self.status_code = status if value == url else 200
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def iter_content(self, size):
            yield responses[self.url]
    class Session:
        trust_env = True
        def get(self, value, **options):
            assert not self.trust_env and options == {"timeout": 15, "allow_redirects": False, "stream": True}
            calls.append(value)
            return Response(value)
        def close(self):
            pass
    monkeypatch.setattr(links.requests, "Session", Session)
    if status != 200:
        with pytest.raises(HubError, match="HTTP/redirect"):
            links.check_website([url])
        assert calls == [ORIGIN + "/caption-link-targets.json", url]
        return
    result = links.check_website([url])
    assert calls == [ORIGIN + "/caption-link-targets.json", url, ORIGIN + "/provenance/test.json",
                     ORIGIN + "/caption-link-targets.json"]
    assert result["checks"][0]["url"] == url
    assert links.seal_fields([{"id": "pinterest:link", "text": url}])[0]["urls"] == [url]
    item = linked_item()
    item["youtube"]["description"] = url
    qa = item["captionLinkQa"]
    qa["fields"] = sorted([f for f in qa["fields"] if f["id"].startswith("file:")] +
                          links.seal_fields(links.package_fields(item)), key=lambda f: f["id"])
    qa["checks"] = result["checks"]
    reseal(qa)
    assert links.validate_qa(item) is qa


@pytest.mark.parametrize("slug,eligible", [
    ("historical-asphaltum-50-25-3", True), ("historical-terra-rosa-16-50-41", False),
    ("historical-cobalt-violet-15-40-2", False), ("historical-smalt-100-8-3", False),
    ("historical-raw-sienna-50-20-1", False), ("modern-paynes-gray-warm-tint-10-2-15", False),
    ("modern-medium-violet-ultramarine-2-5-3", False), ("modern-permanent-violet-ultramarine-5-2-1", False),
    ("modern-deep-olive-hansa-100-10-1", False), ("modern-warm-red-tint-1-2-3", False),
])
def test_restored_routes_require_publication_eligibility(slug, eligible):
    path = "/mix/" + slug + "/"
    responses, _ = website(path, eligible)
    if eligible:
        assert links.check_website([ORIGIN + path], getter=responses.__getitem__)["checks"][0]["identity"] == slug
    else:
        with pytest.raises(HubError, match="approved"):
            links.check_website([ORIGIN + path], getter=responses.__getitem__)


@pytest.mark.parametrize("mutate", [
    lambda c: c.pop("recipeRelease"), lambda c: c.update(recipeRelease=True), lambda c: c.update(websiteRelease=[]),
    lambda c: c["targets"].append(copy.deepcopy(c["targets"][0])), lambda c: c["targets"].append(None),
    lambda c: c["targets"][0].update(sourceReceiptPath=None),
    lambda c: c["targets"][0].update(sourceReceiptPath="/provenance/../secrets.json"),
    lambda c: c["targets"][0].update(canonical=ORIGIN + "/"),
    lambda c: c["targets"][0].update(path="/mix/historical-asphaltum-50-25-3/?utm_source=test"),
])
def test_malformed_catalog_fails_safely(mutate):
    responses, catalog = website()
    mutate(catalog)
    responses[ORIGIN + "/caption-link-targets.json"] = json.dumps(catalog).encode()
    with pytest.raises(HubError):
        links.check_website([URL], getter=responses.__getitem__)


def test_public_page_and_source_must_match_and_catalog_stay_stable():
    for member, data in [(URL, b"<title>Page not found</title><main>404</main>"),
                         (ORIGIN + "/provenance/test.json", b"changed source")]:
        responses, _ = website()
        responses[member] = data
        with pytest.raises(HubError):
            links.check_website([URL], getter=responses.__getitem__)
    responses, _ = website()
    calls = []
    def changed(url):
        calls.append(url)
        return b"changed" if url.endswith("caption-link-targets.json") and len(calls) > 1 else responses[url]
    with pytest.raises(HubError, match="changed during"):
        links.check_website([URL], getter=changed)


@pytest.mark.parametrize("mutate", [
    lambda q: q.update(fields=None), lambda q: q.update(fields=[None]),
    lambda q: q["fields"][0].update(sha256=[]), lambda q: q["fields"][0].update(urls=[{}]),
    lambda q: q.update(checks=[None]), lambda q: q.update(websiteRelease=[]),
    lambda q: q.update(reviewer={}), lambda q: q["reviewer"].update(semantic="NOT_TESTED"),
    lambda q: q.update(extra="unexpected"), lambda q: q.update(schemaVersion=True),
    lambda q: q.update(checkedAt="2020-01-01T00:00:00Z"),
])
def test_malformed_or_unreviewed_qa_fails_closed(mutate):
    item = linked_item()
    mutate(item["captionLinkQa"])
    reseal(item["captionLinkQa"])
    with pytest.raises(HubError):
        links.validate_qa(item)


def test_final_field_edit_and_url_omission_invalidate_review():
    item = linked_item()
    assert links.validate_qa(item) is item["captionLinkQa"]
    item["youtube"]["description"] += " changed"
    with pytest.raises(HubError, match="changed after"):
        links.validate_qa(item)
    item = linked_item()
    next(f for f in item["captionLinkQa"]["fields"] if f["id"] == "youtube:description")["urls"] = []
    reseal(item["captionLinkQa"])
    with pytest.raises(HubError):
        links.validate_qa(item)


def test_direct_ingest_fresh_checks_once_then_positive_exact_replay(monkeypatch):
    from test_distribution_hub import setup, handoff
    payload, _, transport, client = setup()
    item = linked_item()
    payload["payload"]["items"] = [item]
    transport.snapshot = handoff(item)
    calls = []
    current = links.check_website([URL], getter=website()[0].__getitem__)
    def check(urls):
        calls.append(urls)
        return current
    monkeypatch.setattr(links, "check_website", check)
    client.ingest(payload["payload"])
    assert calls == [[URL]]
    monkeypatch.setattr(links, "check_website", lambda _: pytest.fail("Accepted replay repeated HTTP"))
    client.ingest(payload["payload"])
    assert len([c for c in transport.calls if c[0] == "POST"]) == 2


def test_direct_ingest_blocks_changed_release_before_mutation(monkeypatch):
    from test_distribution_hub import setup
    payload, _, transport, client = setup()
    payload["payload"]["items"] = [linked_item()]
    monkeypatch.setattr(links, "check_website", lambda _: {"websiteRelease": "c" * 64, "checks": []})
    with pytest.raises(HubError, match="changed after"):
        client.ingest(payload["payload"])
    assert not [c for c in transport.calls if c[0] == "POST"]


def test_direct_ingest_freezes_exact_reviewed_body_before_callback(monkeypatch):
    from test_distribution_hub import setup, handoff
    payload, _, transport, client = setup()
    item = linked_item()
    payload["payload"]["items"] = [item]
    transport.snapshot = handoff(item)
    original = copy.deepcopy(payload["payload"])
    check = links.check_website([URL], getter=website()[0].__getitem__)
    monkeypatch.setattr(links, "check_website", lambda _: check)
    client.ingest(payload["payload"], _before_send=lambda: item["youtube"].update(description="Edited concurrently"))
    sent = next(c[2]["data"] for c in transport.calls if c[0] == "POST")
    assert json.loads(sent) == original


def test_package_adoption_versioned_scope_and_positive_replay(monkeypatch):
    from test_distribution_hub import setup, handoff
    _, item, transport, client = setup("video")
    snapshot = handoff(item)
    item.pop("deliveryManifest")
    item["tiktok"] = {"caption": URL}
    body = {**{k: v for k, v in linked_item()["captionLinkQa"].items() if k != "receiptHash"},
            "contentId": item["id"], "assetHash": item["assetHash"], "distributionRevision": item["distributionRevision"],
            "fields": links.seal_fields(links.package_fields(item))}
    qa = {**body, "receiptHash": digest(body)}
    request = {"schemaVersion": 3, "idempotencyKey": "adoption-test-permanent-key", "channelCode": "MT", "contentId": item["id"],
               "expectedProfileRevision": snapshot["profile"]["profileRevision"], "expectedSourceRecordHash": snapshot["sourceRecordHash"],
               "target": "tiktok", "package": item["tiktok"], "captionLinkQa": qa}
    sent = []
    monkeypatch.setattr(client, "_request", lambda method, route, **kwargs: sent.append((route, kwargs)) or {"replayed": False})
    links_check = {"websiteRelease": RELEASE, "checks": qa["checks"]}
    monkeypatch.setattr(links, "check_website", lambda urls, **kwargs: links_check)
    client.adopt_package(request, snapshot)
    assert sent[-1][0] == "/api/ingest/handoff/packages" and sent[-1][1]["body"] == request
    monkeypatch.setattr(links, "check_website", lambda _, **kwargs: pytest.fail("Accepted adoption repeated website check"))
    client.adopt_package(request, snapshot)
    missing = copy.deepcopy(request)
    missing["captionLinkQa"] = None
    with pytest.raises(HubError):
        client.adopt_package(missing, snapshot)


def test_media_adoption_checks_exact_local_caption_files(monkeypatch, tmp_path):
    from test_distribution_hub import setup, handoff
    data, item, _, client = setup()
    snapshot = handoff(item)
    for file in data["files"]:
        path = tmp_path / file["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(base64.b64decode(file["base64"]))
    request = {"schemaVersion": 2, "idempotencyKey": "media-test-permanent-key", "channelCode": "MT", "contentId": item["id"],
               "expectedProfileRevision": snapshot["profile"]["profileRevision"], "expectedSourceRecordHash": snapshot["sourceRecordHash"],
               "deliveryManifest": item["deliveryManifest"], "captionLinkQa": item["captionLinkQa"]}
    sent = []
    monkeypatch.setattr(client, "_request", lambda method, route, **kwargs: sent.append((route, kwargs)) or {"replayed": False})
    with pytest.raises(HubError, match="local caption files"):
        client.adopt_media(request, snapshot, {})
    assert not sent
    client.adopt_media(request, snapshot, {}, root=tmp_path)
    assert sent[-1][0] == "/api/ingest/handoff/media" and sent[-1][1]["body"] == request
    (tmp_path / "metadata/caption.txt").write_bytes(b"Changed after review")
    with pytest.raises(HubError, match="changed"):
        client.adopt_media(request, snapshot, {}, root=tmp_path)
    assert len(sent) == 1


@pytest.mark.parametrize("legacy", [False, True])
def test_non_mt_package_adoption_sends_explicit_null_proof(monkeypatch, legacy):
    from test_distribution_hub import setup, handoff
    _, item, _, client = setup("video")
    item["channelCode"] = "CRL"
    item["deliveryManifest"]["channelCode"] = "CRL"
    item["deliveryManifest"]["manifestHash"] = digest({k: v for k, v in item["deliveryManifest"].items() if k != "manifestHash"})
    snapshot = handoff(item)
    request = {"schemaVersion": 2 if legacy else 3, "idempotencyKey": "non-mt-adoption-permanent-key", "channelCode": "CRL", "contentId": item["id"],
               "expectedProfileRevision": snapshot["profile"]["profileRevision"], "expectedSourceRecordHash": snapshot["sourceRecordHash"],
               "captionLinkQa": None}
    request.update({"tiktok": {"caption": "Offline package"}} if legacy else {"target": "x", "package": {"text": "Offline package"}})
    sent = []
    monkeypatch.setattr(client, "_request", lambda method, route, **kwargs: sent.append((route, kwargs)) or {"replayed": False})
    monkeypatch.setattr(links, "check_website", lambda *a, **kw: pytest.fail("Unlinked non-MT package accessed website"))
    client.adopt_package(request, snapshot, legacy_tiktok=legacy)
    assert sent[0][0].endswith("tiktok" if legacy else "packages") and sent[0][1]["body"] == request


def test_pinterest_caption_proof_stays_bound_to_original_source(monkeypatch, tmp_path):
    from test_distribution_hub import setup, handoff
    data, source, _, client = setup("video")
    snapshot = handoff(source)
    for file in data["files"]:
        path = tmp_path / file["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(base64.b64decode(file["base64"]))
    manifest = copy.deepcopy(source["deliveryManifest"])
    manifest["asset"]["sha256"] = "sha256:" + "c" * 64  # Synthetic destination rendition; adapter never creates it.
    package = {"title": "Recipe", "description": URL, "altText": "Mix", "link": URL}
    item = {**source, "pinterest": package, "deliveryManifest": manifest}
    qa = {**linked_item()["captionLinkQa"], "contentId": source["id"], "assetHash": source["assetHash"],
          "distributionRevision": source["distributionRevision"], "fields": links.seal_fields(links.final_fields(item, tmp_path))}
    reseal(qa)
    request = {"schemaVersion": 3, "idempotencyKey": "pinterest-adoption-permanent-key", "channelCode": "MT", "contentId": source["id"],
               "expectedProfileRevision": snapshot["profile"]["profileRevision"], "expectedSourceRecordHash": snapshot["sourceRecordHash"],
               "target": "pinterest", "package": package, "delivery": {"manifest": manifest}, "captionLinkQa": qa}
    sent = []
    monkeypatch.setattr(client, "_request", lambda method, route, **kwargs: sent.append(kwargs["body"]) or {"replayed": False})
    monkeypatch.setattr(links, "check_website", lambda *a, **kw: {"websiteRelease": RELEASE, "checks": qa["checks"]})
    client.adopt_package(request, snapshot, root=tmp_path)
    assert sent[0]["captionLinkQa"]["assetHash"] == source["assetHash"] != manifest["asset"]["sha256"]
    bad = copy.deepcopy(request)
    bad["captionLinkQa"]["assetHash"] = manifest["asset"]["sha256"]
    reseal(bad["captionLinkQa"])
    with pytest.raises(HubError, match="another source"):
        client.adopt_package(bad, snapshot, root=tmp_path)
    assert len(sent) == 1


def test_build_qa_requires_scoped_review_and_rejects_material_edits(tmp_path):
    data = fixture()
    item = linked_item()
    for file in data["files"]:
        path = tmp_path / file["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(base64.b64decode(file["base64"]))
    scoped = {**links.review_scope(item, tmp_path), "websiteRelease": RELEASE, "reviewer": review()}
    original = copy.deepcopy(item["captionLinkQa"])
    proof = links.build_qa(item, tmp_path, scoped, getter=website()[0].__getitem__)
    assert proof["fields"] == scoped["fields"] and item["captionLinkQa"] == original
    with pytest.raises(HubError, match="exact final source"):
        links.build_qa(item, tmp_path, review(), getter=lambda _: pytest.fail("Unscoped review accessed website"))
    item["youtube"]["description"] += " material edit"
    with pytest.raises(HubError, match="exact final source"):
        links.build_qa(item, tmp_path, scoped, getter=lambda _: pytest.fail("Changed caption accessed website"))
    item["youtube"]["description"] = URL
    item["assetHash"] = "sha256:" + "c" * 64
    with pytest.raises(HubError, match="exact final source"):
        links.build_qa(item, tmp_path, scoped, getter=lambda _: pytest.fail("Changed source accessed website"))


def test_mixed_caption_preserves_external_inventory_and_checks_owned_only(monkeypatch):
    from test_distribution_hub import setup, handoff
    item = linked_item()
    external = "https://www.youtube.com/@mixtherapy"
    item["youtube"]["description"] = URL + "\nChannel: " + external
    qa = item["captionLinkQa"]
    qa["fields"] = sorted([f for f in qa["fields"] if f["id"].startswith("file:")] +
                          links.seal_fields(links.package_fields(item)), key=lambda f: f["id"])
    reseal(qa)
    assert links.validate_qa(item) is qa
    field = next(f for f in qa["fields"] if f["id"] == "youtube:description")
    assert field["urls"] == sorted([URL, external]) and [c["url"] for c in qa["checks"]] == [URL]
    payload, _, transport, client = setup()
    payload["payload"]["items"] = [item]
    transport.snapshot = handoff(item)
    checked = []
    monkeypatch.setattr(links, "check_website", lambda urls: checked.append(urls) or {"websiteRelease": RELEASE, "checks": qa["checks"]})
    client.ingest(payload["payload"])
    assert checked == [[URL]]


def test_external_only_website_receipt_is_na_without_http(monkeypatch, tmp_path):
    data = fixture()
    item = data["payload"]["items"][0]
    external = "https://www.youtube.com/@mixtherapy"
    item["youtube"] = {"title": "Channel", "description": external}
    for file in data["files"]:
        path = tmp_path / file["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(base64.b64decode(file["base64"]))
    reviewer = {**review(), "semantic": "NOT_APPLICABLE", "browser": "NOT_APPLICABLE", "evidence": []}
    scoped = {**links.review_scope(item, tmp_path), "websiteRelease": None, "reviewer": reviewer}
    monkeypatch.setattr(links.requests, "Session", lambda: pytest.fail("External-only receipt opened HTTP session"))
    qa = links.build_qa(item, tmp_path, scoped)
    assert qa["websiteRelease"] is None and qa["checks"] == []
    assert external in next(f for f in qa["fields"] if f["id"] == "youtube:description")["urls"]


def test_external_only_structured_package_without_files_needs_no_website_qa(monkeypatch):
    item = fixture()["payload"]["items"][0]
    item["deliveryManifest"]["files"] = []
    item["youtube"] = {"title": "Channel", "description": "https://www.youtube.com/@mixtherapy"}
    item.pop("captionLinkQa")
    monkeypatch.setattr(links.requests, "Session", lambda: pytest.fail("External-only package opened HTTP session"))
    assert links.validate_qa(item) is None
    item["youtube"]["description"] = URL
    with pytest.raises(HubError, match="Missing final caption"):
        links.validate_qa(item)


@pytest.mark.parametrize("url", ["http://mixtherapy.space/mix/a/", "https://mixtherapy.space.evil.test/mix/a/",
    "https://mixtherapy.space@evil.test/mix/a/", "https://evil.test@mixtherapy.space/mix/a/",
    "https://mixtherapy.space/mix/%61/", "https://mixtherapy%2espace/mix/a/",
    "https://%6d%69%78%74%68%65%72%61%70%79%2e%73%70%61%63%65/mix/a/"])
def test_unsafe_owned_authority_is_selected_and_rejected(url):
    assert links.website_urls(["https://www.youtube.com/channel/mixtherapy.space", url]) == [url]
    with pytest.raises(HubError):
        links.check_website(links.website_urls([url]), getter=lambda _: pytest.fail("Unsafe candidate issued HTTP"))


def test_explicit_link_keeps_terminal_punctuation_and_prose_keeps_sentence_rules():
    link = URL + "!"
    fields = links.seal_fields([{"id": "pinterest:link", "text": " " + link + " \n"},
                               {"id": "pinterest:description", "text": "Recipe: " + URL + "!"},
                               {"id": "file:metadata/package.json", "text": json.dumps({"nested": [{"link": link}],
                                    "description": "Recipe: " + URL + "!", "empty": {}})}])
    by_id = {f["id"]: f["urls"] for f in fields}
    assert by_id["pinterest:link"] == [link]
    assert by_id["pinterest:description"] == [URL]
    assert by_id["file:metadata/package.json"] == sorted([link, URL])
    with pytest.raises(HubError, match="approved"):
        links.check_website(by_id["pinterest:link"], getter=website()[0].__getitem__)


def test_non_http_explicit_link_falls_back_to_prose_and_json_link_arrays_preserve_urls():
    link = URL + "!"
    fields = links.seal_fields([{"id": "pinterest:link", "text": "Recipe: " + URL + "!"},
                               {"id": "file:metadata/package.json", "text": json.dumps({"link": [link],
                                    "nested": {"link": "Recipe: " + URL + "!"}})}])
    assert fields[0]["urls"] == sorted([link, URL])
    assert fields[1]["urls"] == [URL]
