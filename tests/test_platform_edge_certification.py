from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from scripts.hash_config_tree import config_tree_hash
from scripts.validate_platform_edge_certification import (
    ContractError,
    load_contract,
    validate_contract,
)

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts/platform-edge-certification.v1.json"


class PlatformEdgeCertificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.value = load_contract(CONTRACT)

    def write_contract(self, value: dict) -> Path:
        temporary = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".json",
            delete=False,
        )
        with temporary:
            json.dump(value, temporary, indent=2, sort_keys=True)
            temporary.write("\n")
        self.addCleanup(Path(temporary.name).unlink, missing_ok=True)
        return Path(temporary.name)

    def test_repository_contract_passes(self) -> None:
        result = validate_contract(ROOT, CONTRACT)
        self.assertEqual(result["status"]["sourceContract"], "READY")
        self.assertEqual(result["status"]["runtimeCertification"], "REQUIRED")
        self.assertIs(result["status"]["productionCertified"], False)

    def test_contract_pins_current_deployable_config_digest(self) -> None:
        authority = self.value["configurationAuthority"]
        self.assertEqual(
            config_tree_hash(ROOT / authority["configurationRoot"]),
            authority["configurationSha256"],
        )

    def test_duplicate_json_keys_fail_closed(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".json",
            delete=False,
        ) as temporary:
            temporary.write('{"schema":"first","schema":"second"}\n')
            path = Path(temporary.name)
        self.addCleanup(path.unlink, missing_ok=True)
        with self.assertRaisesRegex(ContractError, "duplicate_json_key:schema"):
            load_contract(path)

    def test_config_digest_drift_fails_closed(self) -> None:
        value = copy.deepcopy(self.value)
        value["configurationAuthority"]["configurationSha256"] = "0" * 64
        with self.assertRaisesRegex(ContractError, "configuration_digest_drift"):
            validate_contract(ROOT, self.write_contract(value))

    def test_platform_cannot_claim_principal_configuration_source(self) -> None:
        value = copy.deepcopy(self.value)
        value["integrationReleaseAuthority"]["principalConfigurationSource"] = True
        with self.assertRaisesRegex(ContractError, "integration_release_authority"):
            validate_contract(ROOT, self.write_contract(value))

    def test_live_effects_cannot_be_enabled_by_source_contract(self) -> None:
        value = copy.deepcopy(self.value)
        value["safetyBoundary"]["externalEffectsAllowed"] = True
        with self.assertRaisesRegex(ContractError, "safety_boundary"):
            validate_contract(ROOT, self.write_contract(value))

    def test_runtime_certification_cannot_be_marked_complete_in_source(self) -> None:
        value = copy.deepcopy(self.value)
        value["status"]["runtimeCertification"] = "PASS"
        value["status"]["productionCertified"] = True
        with self.assertRaisesRegex(ContractError, "status_must_remain_fail_closed"):
            validate_contract(ROOT, self.write_contract(value))


if __name__ == "__main__":
    unittest.main()
