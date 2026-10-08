import sys
import json
import pytest
import requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.publishers.distribution_hub import DistributionHub
from tools.base_tool import ToolStatus
from tools.tool_registry import ToolRegistry


def test_optional_tool_discovery():
    registry = ToolRegistry()
    import tools.publishers.distribution_hub as module
    registry.register_module(module)
    assert registry.get("distribution_hub").supports["social_publication"] is False
    assert registry.get_by_capability("publish") == []
    assert registry.get_by_capability("distribution_handoff")[0].name == "distribution_hub"


def test_unavailable_without_service_auth(monkeypatch, tmp_path):
    monkeypatch.setenv("DISTRIBUTION_HUB_CONFIG", str(tmp_path / "missing-config.json"))
    for key in ("DISTRIBUTION_HUB_ORIGIN", "DISTRIBUTION_HUB_CLIENT_ID", "DISTRIBUTION_HUB_CLIENT_SECRET"):
        monkeypatch.delenv(key, raising=False)
    tool = DistributionHub()
    assert tool.get_status() == ToolStatus.UNAVAILABLE
    assert not tool.execute({"operation": "inspect"}).success


def test_availability_does_not_connect_or_reveal_credentials(monkeypatch):
    monkeypatch.setenv("DISTRIBUTION_HUB_ORIGIN", "https://hub.example")
    monkeypatch.setenv("DISTRIBUTION_HUB_CLIENT_ID", "private-id")
    monkeypatch.setenv("DISTRIBUTION_HUB_CLIENT_SECRET", "private-secret")
    tool = DistributionHub()
    assert tool.get_status() == ToolStatus.AVAILABLE
    info = str(tool.get_info())
    assert "private-id" not in info and "private-secret" not in info
    error = tool.execute({"operation": "unknown"})
    assert not error.success and "private-secret" not in error.error


def test_wrapper_delegates_reviewed_inputs(monkeypatch):
    class Client:
        def inspect(self, channel, content_id, expected=None):
            assert (channel, content_id, expected) == ("MT", "fixture", {"id": "fixture"})
            return {"verified": True}
    monkeypatch.setattr(DistributionHub, "_client", staticmethod(lambda: Client()))
    result = DistributionHub().execute({"operation": "inspect", "channel": "MT", "content_id": "fixture", "expected": {"id": "fixture"}})
    assert result.success and result.data["verified"]


def test_wrapper_passes_same_plan_and_registry_to_reservation_and_ingest(monkeypatch):
    calls = []
    class Client:
        def novelty(self, channel, identity, stage, **kwargs):
            calls.append(("novelty", kwargs))
            return {"reserved": True}
        def ingest(self, payload, **kwargs):
            calls.append(("ingest", kwargs))
            return {"checked": True}
    monkeypatch.setattr(DistributionHub, "_client", staticmethod(lambda: Client()))
    plan = {"planHash": "exact-plan"}
    tool = DistributionHub()
    assert tool.execute({"operation": "novelty", "channel": "MT", "identity": {}, "reserve": True,
                         "delivery_plan": plan, "registry_path": "shared.sqlite"}).success
    assert tool.execute({"operation": "ingest", "payload": {}, "delivery_plan": plan, "registry_path": "shared.sqlite"}).success
    assert all(kwargs["delivery_plan"] is plan for _, kwargs in calls)
    assert calls[0][1]["registry_path"] == calls[1][1]["novelty_registry"] == "shared.sqlite"


@pytest.mark.parametrize("status,code,next_action", [
    (409, "HANDOFF_JOB_STALE", "INSPECT_CURRENT_BINDINGS"),
    (409, "HANDOFF_PACKAGE_REQUIRED", "CHECK_EXACT_PACKAGE"),
    (503, "D1_READ_QUOTA_EXCEEDED", "WAIT_FOR_QUOTA_RESET"),
])
def test_reports_survive_failures_without_private_response(monkeypatch, tmp_path, status, code, next_action):
    from lib.distribution_hub import HubClient
    class Transport:
        def request(self, *args, **kwargs):
            class Response:
                status_code = status
                def json(self):
                    return {"code": code, "error": "private-response"}
            return Response()
    client = HubClient("https://hub.example", "private-id", "private-secret", transport=Transport())
    monkeypatch.setattr(DistributionHub, "_client", staticmethod(lambda: client))
    result = DistributionHub().execute({"operation": "inspect", "channel": "MT", "content_id": "fixture",
                                        "project_dir": str(tmp_path)})
    assert not result.success and result.data["reportPersisted"]
    text = Path(result.data["reportPath"]).read_text(encoding="utf-8")
    report = json.loads(text)
    assert report["errorCode"] == code and report["nextAction"] == next_action
    assert report["failedStep"]["route"] == "/api/ingest/handoff"
    assert report["state"] == "FAILED" and report["publicPublication"] == "NOT_ASSERTED"
    assert all(secret not in text for secret in ["private-response", "private-id", "private-secret"])


def test_unknown_ingest_keeps_exact_request_fingerprint_without_replay(monkeypatch, tmp_path):
    from lib.distribution_hub import HubClient, digest
    class Transport:
        calls = 0
        def request(self, *args, **kwargs):
            self.calls += 1
            raise requests.Timeout("private network detail")
    transport = Transport()
    client = HubClient("https://hub.example", "private-id", "private-secret", transport=transport)
    # Isolate the metadata send, retaining the real request and error handling.
    client.ingest = lambda payload, **kw: client._request("POST", "/api/ingest", body=payload, key=payload["idempotencyKey"])
    monkeypatch.setattr(DistributionHub, "_client", staticmethod(lambda: client))
    payload = {"idempotencyKey": "permanent-private-key", "caption": "private content"}
    result = DistributionHub().execute({"operation": "ingest", "payload": payload, "project_dir": str(tmp_path)})
    report_text = Path(result.data["reportPath"]).read_text(encoding="utf-8")
    report = json.loads(report_text)
    assert report["outcomeUnknown"] and report["nextAction"] == "RECONCILE_EXACT_REQUEST"
    assert report["requestFingerprint"] == digest(payload) and transport.calls == 1
    assert all(secret not in report_text for secret in ["private network detail", "permanent-private-key", "private content"])


def test_report_write_failure_stops_before_client_or_send(monkeypatch, tmp_path):
    import tools.publishers.distribution_hub as module
    from lib.hub_diagnostics import HandoffReport
    def fail(*args):
        raise OSError("private path")
    monkeypatch.setattr(HandoffReport, "_write", fail)
    monkeypatch.setattr(DistributionHub, "_client", staticmethod(lambda: pytest.fail("must not create client")))
    result = DistributionHub().execute({"operation": "inspect", "project_dir": str(tmp_path)})
    assert not result.success and result.error == "Cannot persist Hub handoff report; no request sent"


def test_final_report_failure_never_disguises_completed_mutation(monkeypatch, tmp_path):
    from lib.hub_diagnostics import HandoffReport
    class Client:
        def ingest(self, *args, **kwargs):
            return {"receipt": {"created": 1}}
    monkeypatch.setattr(DistributionHub, "_client", staticmethod(lambda: Client()))
    def fail(*args, **kwargs):
        raise OSError("private detail")
    monkeypatch.setattr(HandoffReport, "finish", fail)
    result = DistributionHub().execute({"operation": "ingest", "payload": {}, "project_dir": str(tmp_path)})
    assert result.success and not result.data["reportPersisted"]
    assert json.loads(Path(result.data["reportPath"]).read_text())["state"] == "RUNNING"


def test_each_run_has_its_own_durable_report(monkeypatch, tmp_path):
    class Client:
        def inspect(self, *args, **kwargs):
            return {"verified": True}
    monkeypatch.setattr(DistributionHub, "_client", staticmethod(lambda: Client()))
    inputs = {"operation": "inspect", "channel": "MT", "content_id": "fixture", "project_dir": str(tmp_path)}
    paths = [DistributionHub().execute(inputs).data["reportPath"] for _ in range(2)]
    assert paths[0] != paths[1]
    assert all(json.loads(Path(path).read_text())["state"] == "COMPLETE" for path in paths)


def test_local_exact_file_failure_retains_its_safe_reason(monkeypatch, tmp_path):
    from lib.distribution_hub import HubError
    class Client:
        def deliver(self, *args, **kwargs):
            raise HubError("Exact local file size or hash differs")
    monkeypatch.setattr(DistributionHub, "_client", staticmethod(lambda: Client()))
    result = DistributionHub().execute({"operation": "deliver", "channel": "MT", "content_id": "fixture", "target": "fb-ig",
                                       "root": str(tmp_path), "project_dir": str(tmp_path),
                                       "expected": {"id": "fixture", "sourceRevision": 3, "distributionRevision": 2}})
    report = json.loads(Path(result.data["reportPath"]).read_text())
    assert report["error"] == "Exact local file size or hash differs"
    assert report["reviewedVersions"] == [{"contentId": "fixture", "sourceRevision": 3, "distributionRevision": 2}]


def test_reports_keep_real_fixture_sha256_revisions_and_numeric_job_versions(tmp_path):
    from scripts.hub_contract_fixture import fixture
    from lib.hub_diagnostics import HandoffReport
    item = fixture("photo")["payload"]["items"][0]
    report = HandoffReport({"operation": "inspect", "project_dir": str(tmp_path), "expected": item})
    report.finish(result={"source": {"contentId": item["id"], "sourceRevision": item["sourceRevision"]},
                          "jobs": [{"platformCode": "fb-ig", "version": 3}]})
    saved = json.loads(report.path.read_text())
    assert saved["reviewedVersions"][0]["sourceRevision"] == item["sourceRevision"]
    assert saved["reviewedVersions"][0]["distributionRevision"] == item["distributionRevision"]
    assert saved["versions"][0]["sourceRevision"] == item["sourceRevision"]
    assert saved["versions"][0]["jobs"][0]["version"] == 3


def test_report_revisions_reject_arbitrary_text(tmp_path):
    from lib.hub_diagnostics import HandoffReport
    report = HandoffReport({"operation": "inspect", "project_dir": str(tmp_path),
                            "expected": {"sourceRevision": "private-token", "distributionRevision": "https://private"}})
    saved = json.loads(report.path.read_text())
    assert saved["reviewedVersions"][0]["sourceRevision"] is None
    assert saved["reviewedVersions"][0]["distributionRevision"] is None
