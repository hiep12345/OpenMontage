import json

import pytest

from lib.hub_access import configured_client
from lib.distribution_hub import HubError


def test_partial_environment_cannot_fall_back_to_another_principal(monkeypatch, tmp_path):
    monkeypatch.setenv("DISTRIBUTION_HUB_ORIGIN", "https://hub.example")
    monkeypatch.delenv("DISTRIBUTION_HUB_CLIENT_ID", raising=False)
    monkeypatch.delenv("DISTRIBUTION_HUB_CLIENT_SECRET", raising=False)
    monkeypatch.setenv("DISTRIBUTION_HUB_CONFIG", str(tmp_path / "unused.json"))
    with pytest.raises(HubError):
        configured_client()


def test_independent_access_validates_origin_before_unlock(monkeypatch, tmp_path):
    for key in ("ORIGIN", "CLIENT_ID", "CLIENT_SECRET"):
        monkeypatch.delenv("DISTRIBUTION_HUB_" + key, raising=False)
    path = tmp_path / "config.json"
    monkeypatch.setenv("DISTRIBUTION_HUB_CONFIG", str(path))
    calls = []
    monkeypatch.setattr("lib.hub_access._unlock", lambda p: calls.append(p) or {"client_id": "id", "client_secret": "secret"})
    path.write_text(json.dumps({"origin": "http://untrusted.example", "credentialStore": str(tmp_path / "encrypted.json")}))
    with pytest.raises(HubError):
        configured_client()
    assert calls == []
    path.write_text(json.dumps({"origin": "https://hub.example", "credentialStore": str(tmp_path / "encrypted.json")}))
    assert configured_client().origin == "https://hub.example"
    assert len(calls) == 1
