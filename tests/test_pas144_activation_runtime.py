from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from caddy_activation import ActivationError, ActivationManager
from caddy_execution_store import ExecutionStore, ExecutionStoreError
from caddy_runtime_readback import CaddyRuntime, RuntimeReadbackError, sha256_json


class FakeTransport:
    def __init__(self, config: dict, *, mismatch_after_load: bool = False) -> None:
        self.config = config
        self.mismatch_after_load = mismatch_after_load
        self.calls = []

    def __call__(self, method: str, url: str, body: bytes | None, content_type: str | None):
        self.calls.append((method, url, content_type))
        if method == "GET" and url.endswith("/config/"):
            return 200, json.dumps(self.config).encode()
        if method == "POST" and url.endswith("/load"):
            incoming = json.loads((body or b"{}").decode())
            self.config = {"mismatch": True} if self.mismatch_after_load else incoming
            return 200, b""
        return 404, b"{}"


def candidate(tmp_path: Path, value: dict) -> Path:
    path = tmp_path / "candidate.json"
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    return path


def test_runtime_requires_loopback_admin_api():
    with pytest.raises(RuntimeReadbackError, match="loopback"):
        CaddyRuntime("http://caddy.internal:2019")


def test_runtime_status_hashes_live_config():
    transport = FakeTransport({"apps": {"http": {"servers": {"srv0": {}}}}})
    status = CaddyRuntime(transport=transport).status()
    assert status["admin_api"] == "AVAILABLE"
    assert status["server_count"] == 1
    assert status["config_sha256"] == sha256_json(transport.config)


def test_execution_store_round_trip_and_corruption(tmp_path: Path):
    store = ExecutionStore(tmp_path / "evidence")
    store.put("abc", {"status": "COMPLETED"})
    assert store.get("abc")["status"] == "COMPLETED"
    (tmp_path / "evidence" / "abc.json").write_text("{bad", encoding="utf-8")
    with pytest.raises(ExecutionStoreError, match="corrupt"):
        store.get("abc")


def test_dry_run_detects_change_without_mutation(tmp_path: Path):
    transport = FakeTransport({"old": True})
    manager = ActivationManager(
        runtime=CaddyRuntime(transport=transport),
        store=ExecutionStore(tmp_path / "evidence"),
        candidate_path=candidate(tmp_path, {"new": True}),
        mutation_enabled=False,
    )
    result = manager.dry_run()
    assert result["status"] == "CHANGE"
    assert result["mutation_performed"] is False
    assert all(call[0] != "POST" for call in transport.calls)


def test_apply_disabled_by_default(tmp_path: Path):
    manager = ActivationManager(
        runtime=CaddyRuntime(transport=FakeTransport({})),
        store=ExecutionStore(tmp_path / "evidence"),
        candidate_path=candidate(tmp_path, {}),
        mutation_enabled=False,
    )
    with pytest.raises(ActivationError, match="disabled"):
        manager.apply(idempotency_key="same")


def test_apply_readback_and_idempotency(tmp_path: Path):
    transport = FakeTransport({"old": True})
    manager = ActivationManager(
        runtime=CaddyRuntime(transport=transport),
        store=ExecutionStore(tmp_path / "evidence"),
        candidate_path=candidate(tmp_path, {"new": True}),
        mutation_enabled=True,
    )
    first = manager.apply(idempotency_key="same")
    second = manager.apply(idempotency_key="same")
    assert first["status"] == "COMPLETED"
    assert second["execution_id"] == first["execution_id"]
    assert sum(1 for call in transport.calls if call[0] == "POST") == 1


def test_idempotency_conflict_fails_closed(tmp_path: Path):
    transport = FakeTransport({"old": True})
    path = candidate(tmp_path, {"one": 1})
    manager = ActivationManager(
        runtime=CaddyRuntime(transport=transport),
        store=ExecutionStore(tmp_path / "evidence"),
        candidate_path=path,
        mutation_enabled=True,
    )
    manager.apply(idempotency_key="same")
    path.write_text(json.dumps({"two": 2}), encoding="utf-8")
    with pytest.raises(ActivationError, match="different candidate"):
        manager.apply(idempotency_key="same")


def test_readback_mismatch_triggers_rollback(tmp_path: Path):
    original = {"old": True}
    transport = FakeTransport(original.copy(), mismatch_after_load=True)
    manager = ActivationManager(
        runtime=CaddyRuntime(transport=transport),
        store=ExecutionStore(tmp_path / "evidence"),
        candidate_path=candidate(tmp_path, {"new": True}),
        mutation_enabled=True,
    )
    with pytest.raises(ActivationError, match="readback"):
        manager.apply(idempotency_key="mismatch")
    record = manager.store.get(manager.store.list_ids()[0])
    assert record["rollback_status"] in {"ROLLED_BACK", "ROLLBACK_FAILED"}


def test_manual_rollback_restores_pre_state(tmp_path: Path):
    transport = FakeTransport({"old": True})
    manager = ActivationManager(
        runtime=CaddyRuntime(transport=transport),
        store=ExecutionStore(tmp_path / "evidence"),
        candidate_path=candidate(tmp_path, {"new": True}),
        mutation_enabled=True,
    )
    record = manager.apply(idempotency_key="apply")
    transport.config = {"unexpected": True}
    restored = manager.rollback(record["execution_id"])
    assert restored["rollback_status"] == "ROLLED_BACK"
    assert transport.config == {"old": True}
