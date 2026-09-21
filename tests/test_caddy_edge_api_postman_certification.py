from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


generator = load_script("generate_caddy_edge_certification_postman")
certifier = load_script("certify_caddy_edge_api")

PUBLIC = certifier.load_json(certifier.PUBLIC_PATH)
WEBHOOKS = certifier.load_json(certifier.WEBHOOK_PATH)
CHAIN = certifier.load_json(certifier.CHAIN_PATH)
COLLECTION = certifier.load_json(certifier.COLLECTION_PATH)
ENVIRONMENT = certifier.load_json(certifier.ENV_PATH)


def test_generated_postman_artifacts_are_deterministic() -> None:
    assert COLLECTION == generator.render_collection(PUBLIC, WEBHOOKS)
    assert ENVIRONMENT == generator.render_environment()


def test_postman_safe_environment_defaults_to_loopback_and_disabled() -> None:
    values = {row["key"]: row["value"] for row in ENVIRONMENT["values"]}
    assert values["base_url"].startswith("https://127.0.0.1:")
    assert values["RUN_CADDY_EDGE_CERTIFICATION"] == "false"
    for key in ("access_token", "automation_token", "odoo_token", "n8n_token"):
        assert values[key] == ""


def test_edge_registries_cover_api_private_database_and_webhook_boundaries() -> None:
    report = certifier.validate_registries(PUBLIC, WEBHOOKS)
    assert report["canonical"] == 4
    assert report["pending"] >= 5
    assert report["webhooks"] >= 2
    assert report["database_public_exposure"] == 0


def test_postman_covers_api_webhook_private_and_pending_negative_paths() -> None:
    report = certifier.validate_postman(COLLECTION, ENVIRONMENT)
    assert report["api"] == "PASS"
    assert report["webhook"] == "PASS"
    assert report["private"] == "PASS"
    assert report["pending_count"] >= 5
    assert report["webhook_wrong_method_count"] >= 2


def test_pas162_chain_is_explicitly_pending_not_false_pass() -> None:
    state = certifier.chain_state(CHAIN, certifier.sha256_file(certifier.COLLECTION_PATH))
    assert state["required_digest"] == "9c32daecd4a15104c6f9ff60ce19c8f7e78707fb31d9fd9fcb55b1b8dfa3512b"
    assert state["middleware_digest"] == state["required_digest"]
    assert state["digest_match"] is False
    assert state["postman_match"] is False


def test_collection_has_no_embedded_secret_values() -> None:
    text = json.dumps(COLLECTION)
    environment = {row["key"]: row["value"] for row in ENVIRONMENT["values"]}
    assert "Bearer eyJ" not in text
    assert "sk-" not in text
    assert environment["access_token"] == ""
    assert environment["automation_token"] == ""
