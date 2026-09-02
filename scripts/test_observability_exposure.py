#!/usr/bin/env python3
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from validate_observability_exposure import (  # noqa: E402
    CONTRACT_PATH,
    HEADERS_PATH,
    RUNTIME_PATH,
    SITE_PATH,
    ExposureError,
    load_contract,
    load_root_caddy_sources,
    root_caddy_source_paths,
    validate,
)


class ExposureContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = load_contract()
        cls.site = SITE_PATH.read_text(encoding="utf-8")
        cls.runtime = RUNTIME_PATH.read_text(encoding="utf-8")
        cls.headers = HEADERS_PATH.read_text(encoding="utf-8")
        cls.all_sites = load_root_caddy_sources()

    def test_repository_source_is_valid(self) -> None:
        validate(self.contract, self.site, self.all_sites, self.runtime, self.headers)

    def test_root_import_source_inventory_is_complete(self) -> None:
        relative = {str(path.relative_to(ROOT)) for path in root_caddy_source_paths()}
        expected = {"Caddyfile"}
        expected.update(str(path.relative_to(ROOT)) for path in (ROOT / "sites").glob("*.caddy"))
        expected.update(str(path.relative_to(ROOT)) for path in (ROOT / "snippets").glob("*.caddy"))
        self.assertEqual(relative, expected)

    def test_private_native_route_is_rejected(self) -> None:
        injected = self.all_sites + "\nprom.codestra.media { reverse_proxy 127.0.0.1:9090 }\n"
        with self.assertRaises(ExposureError):
            validate(self.contract, self.site, injected, self.runtime, self.headers)

    def test_wildcard_site_address_is_rejected(self) -> None:
        injected = self.all_sites + "\n*.codestra.media { reverse_proxy 127.0.0.1:9090 }\n"
        with self.assertRaises(ExposureError):
            validate(self.contract, self.site, injected, self.runtime, self.headers)

    def test_dynamic_site_address_is_rejected(self) -> None:
        injected = self.all_sites + "\n{$CADDY_PUBLIC_MONITORING_HOST} { reverse_proxy 127.0.0.1:9090 }\n"
        with self.assertRaises(ExposureError):
            validate(self.contract, self.site, injected, self.runtime, self.headers)

    def test_oauth_state_redaction_is_required(self) -> None:
        site = self.site.replace("\t\t\t\tdelete session_state\n", "", 1)
        all_sites = self.all_sites.replace(self.site, site)
        with self.assertRaises(ExposureError):
            validate(self.contract, site, all_sites, self.runtime, self.headers)

    def test_postgres_exporter_public_dns_is_rejected(self) -> None:
        contract = copy.deepcopy(self.contract)
        postgres = next(item for item in contract["privateServices"] if item["service"] == "postgres-exporter")
        postgres["publicDnsHostnameAllowed"] = True
        with self.assertRaises(ExposureError):
            validate(contract, self.site, self.all_sites, self.runtime, self.headers)

    def test_unreviewed_dynamic_site_address_is_rejected(self) -> None:
        injected = self.all_sites + "\n{$CADDY_PUBLIC_MONITORING_HOST} { reverse_proxy 127.0.0.1:9090 }\n"
        with self.assertRaises(ExposureError):
            validate(self.contract, self.site, injected, self.runtime, self.headers)

    def test_wildcard_site_address_is_rejected(self) -> None:
        injected = self.all_sites + "\n*.codestra.media { reverse_proxy 127.0.0.1:9090 }\n"
        with self.assertRaises(ExposureError):
            validate(self.contract, self.site, injected, self.runtime, self.headers)

    def test_missing_oidc_state_redaction_is_rejected(self) -> None:
        site = self.site.replace("\t\t\t\tdelete session_state\n", "", 1)
        all_sites = self.all_sites.replace(self.site, site)
        with self.assertRaises(ExposureError):
            validate(self.contract, site, all_sites, self.runtime, self.headers)

    def test_broad_openbao_range_is_rejected(self) -> None:
        runtime = self.runtime.replace("192.0.2.0/24 198.51.100.0/24", "0.0.0.0/0")
        with self.assertRaises(ExposureError):
            validate(self.contract, self.site, self.all_sites, runtime, self.headers)

    def test_authorization_removal_is_rejected(self) -> None:
        site = self.site.replace("request_header -X-Auth-Request-User", "request_header -Authorization", 1)
        all_sites = self.all_sites.replace(self.site, site)
        with self.assertRaises(ExposureError):
            validate(self.contract, site, all_sites, self.runtime, self.headers)

    def test_live_reload_authorization_is_rejected(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["activation"]["liveCaddyReloadAuthorized"] = True
        with self.assertRaises(ExposureError):
            validate(contract, self.site, self.all_sites, self.runtime, self.headers)


if __name__ == "__main__":
    unittest.main()
