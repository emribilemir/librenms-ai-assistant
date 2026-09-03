import copy
import json
from pathlib import Path
import tempfile
import unittest

from simulation.catalog import SEMANTIC_CATALOG
from simulation.manifest import (
    ManifestValidationError,
    load_manifest,
    manifest_sha256,
    public_manifest,
    validate_manifest,
)


VALID_MANIFEST = {
    "version": 1,
    "targets": [
        {
            "id": "lab-j9772a-01",
            "hostname": "lab-j9772a-01",
            "agent_address": "127.0.0.11",
            "agent_port": 1611,
            "fixture": "lab-j9772a-01",
            "baseline_active": True,
            "capabilities": ["location"],
        }
    ],
    "scenarios": [
        {
            "id": "location-change",
            "name": "Konum değişikliği",
            "description": "Cihaz konumunun değişimini doğrular.",
            "device": "lab-j9772a-01",
            "precondition": "Cihaz erişilebilir ve başlangıç konumunda.",
            "mutation": {
                "kind": "snmprec_values",
                "values": [
                    {"semantic": "sysLocation", "index": None, "value": "Murat Bey Demo Lab"}
                ],
            },
            "expected_snmp": [
                {"semantic": "sysLocation", "index": None, "value": "Murat Bey Demo Lab"}
            ],
            "poll_mode": "poller",
            "expected_librenms_surface": [
                {"kind": "device", "field": "location", "value": "Murat Bey Demo Lab"}
            ],
            "expected_api_evidence": [
                {"resource": "device", "selector": {"hostname": "lab-j9772a-01"}}
            ],
            "example_questions": ["lab-j9772a-01 cihazı hangi konumda?"],
            "expected_answer_semantics": ["device_identity", "location"],
            "reset_state": "baseline",
        }
    ],
}


class ManifestValidationTests(unittest.TestCase):
    def test_validates_minimal_manifest_and_builds_stable_records(self):
        manifest = validate_manifest(copy.deepcopy(VALID_MANIFEST))

        self.assertEqual(manifest.version, 1)
        self.assertEqual(manifest.scenarios[0].poll_mode, "poller")
        self.assertEqual(manifest.scenarios[0].expected_snmp[0].semantic, "sysLocation")
        self.assertRegex(manifest_sha256(manifest), r"^[0-9a-f]{64}$")

    def test_loads_json_from_a_path(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scenarios.json"
            path.write_text(json.dumps(VALID_MANIFEST), encoding="utf-8")
            self.assertEqual(load_manifest(path).scenarios[0].id, "location-change")

    def test_rejects_unknown_keys(self):
        raw = copy.deepcopy(VALID_MANIFEST)
        raw["surprise"] = True
        self.assert_error(raw, "unknown_key")

    def test_rejects_duplicate_scenario_ids(self):
        raw = copy.deepcopy(VALID_MANIFEST)
        raw["scenarios"].append(copy.deepcopy(raw["scenarios"][0]))
        self.assert_error(raw, "duplicate_scenario_id")

    def test_rejects_unknown_devices_and_modes(self):
        raw = copy.deepcopy(VALID_MANIFEST)
        raw["scenarios"][0]["device"] = "missing-device"
        self.assert_error(raw, "unknown_device")

        raw = copy.deepcopy(VALID_MANIFEST)
        raw["scenarios"][0]["poll_mode"] = "everything"
        self.assert_error(raw, "unsupported_poll_mode")

    def test_rejects_unsupported_mutations_and_control_material(self):
        raw = copy.deepcopy(VALID_MANIFEST)
        raw["scenarios"][0]["mutation"]["kind"] = "script"
        self.assert_error(raw, "unsupported_mutation_kind")

        for key, value, code in (
            ("oid", "1.3.6.1.4.1.999", "raw_oid_forbidden"),
            ("path", "/tmp/fixture", "path_forbidden"),
            ("command", "touch /tmp/pwned", "shell_string_forbidden"),
        ):
            raw = copy.deepcopy(VALID_MANIFEST)
            raw["scenarios"][0]["mutation"][key] = value
            self.assert_error(raw, code)

        raw = copy.deepcopy(VALID_MANIFEST)
        raw["scenarios"][0]["mutation"]["values"][0]["value"] = "$(touch /tmp/pwned)"
        self.assert_error(raw, "shell_string_forbidden")

    def test_requires_reset_and_explicit_expected_snmp(self):
        raw = copy.deepcopy(VALID_MANIFEST)
        raw["scenarios"][0].pop("reset_state")
        self.assert_error(raw, "reset_state_required")

        raw = copy.deepcopy(VALID_MANIFEST)
        raw["scenarios"][0]["expected_snmp"] = []
        self.assert_error(raw, "expected_snmp_required")

    def test_wraps_semantic_validation_errors(self):
        raw = copy.deepcopy(VALID_MANIFEST)
        raw["scenarios"][0]["mutation"]["values"][0]["value"] = "x" * 129
        self.assert_error(raw, "semantic_value_invalid")

    def test_requires_endpoint_membership_for_unreachable_device(self):
        raw = copy.deepcopy(VALID_MANIFEST)
        raw["scenarios"][0]["expected_snmp"] = [
            {"semantic": "endpointReachable", "index": None, "value": False}
        ]
        self.assert_error(raw, "device_down_requires_endpoint_membership")

    def test_hash_uses_canonical_validated_content(self):
        reversed_raw = {
            "scenarios": copy.deepcopy(VALID_MANIFEST["scenarios"]),
            "targets": copy.deepcopy(VALID_MANIFEST["targets"]),
            "version": 1,
        }
        first = manifest_sha256(validate_manifest(copy.deepcopy(VALID_MANIFEST)))
        second = manifest_sha256(validate_manifest(reversed_raw))
        self.assertEqual(first, second)

        changed = copy.deepcopy(VALID_MANIFEST)
        changed["scenarios"][0]["mutation"]["values"][0]["value"] = "Başka Lab"
        changed["scenarios"][0]["expected_snmp"][0]["value"] = "Başka Lab"
        self.assertNotEqual(first, manifest_sha256(validate_manifest(changed)))

    def test_public_projection_exposes_only_browser_safe_fields(self):
        result = public_manifest(validate_manifest(copy.deepcopy(VALID_MANIFEST)))
        scenario = result["scenarios"][0]
        for field in (
            "id",
            "name",
            "description",
            "device",
            "precondition",
            "poll_mode",
            "expected_librenms_surface",
            "expected_api_evidence",
            "example_questions",
            "expected_answer_semantics",
        ):
            self.assertIn(field, scenario)

        serialized = json.dumps(result, ensure_ascii=False)
        for forbidden in (
            "agent_address",
            "agent_port",
            "fixture",
            "mutation",
            "expected_snmp",
            "oid",
            "path",
            "command",
            "reset_state",
        ):
            self.assertNotIn(forbidden, serialized)

    def assert_error(self, raw, code):
        with self.assertRaises(ManifestValidationError) as caught:
            validate_manifest(raw)
        self.assertEqual(caught.exception.code, code)
        self.assertTrue(str(caught.exception).startswith(code))


class ProductionManifestTests(unittest.TestCase):
    manifest_path = Path(__file__).resolve().parents[1] / "scenarios.json"

    def test_declares_the_frozen_scenario_set(self):
        manifest = load_manifest(self.manifest_path)
        self.assertEqual(
            {scenario.id for scenario in manifest.scenarios},
            {
                "device-up-to-down",
                "device-down-to-up",
                "port-admin-up-oper-up",
                "port-admin-up-oper-down",
                "port-down-to-up-transition",
                "port-alias-change",
                "location-change",
                "uptime-reset",
                "single-down-port",
                "event-producing-port-transition",
            },
        )
        self.assertEqual({target.id for target in manifest.targets}, {"lab-j9772a-01", "lab-j9775a-01"})

    def test_every_scenario_has_explicit_observation_and_answer_contracts(self):
        manifest = load_manifest(self.manifest_path)
        for scenario in manifest.scenarios:
            with self.subTest(scenario=scenario.id):
                self.assertTrue(scenario.example_questions)
                self.assertTrue(scenario.expected_api_evidence)
                self.assertTrue(scenario.expected_librenms_surface)
                self.assertTrue(scenario.expected_answer_semantics)
                self.assertTrue(scenario.expected_snmp)
                self.assertEqual(scenario.reset_state, "baseline")
                for semantic_value in (*scenario.mutation_values, *scenario.expected_snmp):
                    self.assertIn(semantic_value.semantic, SEMANTIC_CATALOG)

    def test_device_down_uses_endpoint_membership_not_an_oid(self):
        manifest = load_manifest(self.manifest_path)
        scenario = next(item for item in manifest.scenarios if item.id == "device-up-to-down")
        self.assertEqual(scenario.mutation_kind, "endpoint_membership")
        self.assertIs(scenario.endpoint_active, False)
        self.assertEqual(scenario.expected_snmp[0].semantic, "endpointReachable")
        self.assertIs(scenario.expected_snmp[0].value, False)

    def test_manifest_identity_is_stable_across_loads(self):
        first = manifest_sha256(load_manifest(self.manifest_path))
        second = manifest_sha256(load_manifest(self.manifest_path))
        self.assertRegex(first, r"^[0-9a-f]{64}$")
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
