import sys
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
