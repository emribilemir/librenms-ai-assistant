from contextlib import contextmanager
from pathlib import Path
import unittest

from simulation import SemanticValue, load_manifest
from simulation.runner.errors import RunnerError
from simulation.runner.snmprec import (
    apply_semantic_values,
    parse_membership,
    parse_snmprec,
    set_endpoint_active,
)


MANIFEST = load_manifest(Path(__file__).resolve().parents[1] / "scenarios.json")
UP_TARGET = next(target for target in MANIFEST.targets if target.id == "lab-j9772a-01")
DOWN_TARGET = next(target for target in MANIFEST.targets if target.id == "lab-j9775a-01")

SNMPREC = b"""1.3.6.1.2.1.1.3.0|67|1234567
1.3.6.1.2.1.1.5.0|4|lab-j9772a-01
1.3.6.1.2.1.1.6.0|4|Test Lab
1.3.6.1.2.1.2.2.1.7.2|2|1
1.3.6.1.2.1.2.2.1.8.2|2|2
1.3.6.1.2.1.31.1.1.1.18.4|4|Client
"""

INVENTORY = b"""127.0.0.11|lab-j9772a-01|J9772A 2530-48G-PoEP
127.0.0.12|lab-j9772a-02|J9772A 2530-48G-PoEP
127.0.0.13|lab-j9775a-01|J9775A 2530-48G
"""

ACTIVE = b"""127.0.0.11|lab-j9772a-01|J9772A 2530-48G-PoEP
127.0.0.12|lab-j9772a-02|J9772A 2530-48G-PoEP
"""


class SnmprecTransformTests(unittest.TestCase):
    def test_parses_utms_exact_record_shape(self):
        records = parse_snmprec(SNMPREC)
        self.assertEqual(records[0].oid, "1.3.6.1.2.1.1.3.0")
        self.assertEqual(records[0].snmp_type, 67)
        self.assertEqual(records[0].value, 1234567)
        self.assertEqual(records[1].value, "lab-j9772a-01")

    def test_rejects_malformed_duplicate_and_unsafe_records(self):
        cases = (
            (b"\xff", "invalid_encoding"),
            (b"1.3.6|4\n", "invalid_snmprec"),
            (b"1.3.06|4|x\n", "invalid_oid"),
            (b"1.3.6|0|x\n", "invalid_snmp_type"),
            (b"1.3.6|256|x\n", "invalid_snmp_type"),
            (b"1.3.6|67|not-int\n", "invalid_snmp_value"),
            (b"1.3.6|4|x\r\n", "invalid_snmprec"),
            (b"1.3.6|4|x\n1.3.6|4|y\n", "duplicate_oid"),
        )
        for payload, code in cases:
            with self.subTest(code=code), self.assert_runner_error(code):
                parse_snmprec(payload)

    def test_updates_only_resolved_catalog_records_and_preserves_order(self):
        changed = apply_semantic_values(
            SNMPREC,
            (
                SemanticValue("sysLocation", None, "Murat Bey Demo Lab"),
                SemanticValue("ifOperStatus", 2, 1),
            ),
        )
        self.assertEqual(
            changed,
            SNMPREC.replace(b"Test Lab", b"Murat Bey Demo Lab").replace(
                b"1.3.6.1.2.1.2.2.1.8.2|2|2",
                b"1.3.6.1.2.1.2.2.1.8.2|2|1",
            ),
        )
        self.assertTrue(changed.endswith(b"\n"))

    def test_fails_closed_on_missing_type_duplicate_virtual_or_injected_updates(self):
        cases = (
            (
                SNMPREC,
                (SemanticValue("ifAlias", 3, "Missing"),),
                "semantic_oid_missing",
            ),
            (
                SNMPREC.replace(b"1.3.6.1.2.1.1.6.0|4", b"1.3.6.1.2.1.1.6.0|6"),
                (SemanticValue("sysLocation", None, "Lab"),),
                "semantic_type_mismatch",
            ),
            (
                SNMPREC,
                (
                    SemanticValue("sysLocation", None, "One"),
                    SemanticValue("sysLocation", None, "Two"),
                ),
                "duplicate_semantic_update",
            ),
            (
                SNMPREC,
                (SemanticValue("endpointReachable", None, True),),
                "virtual_semantic",
            ),
            (
                SNMPREC,
                (SemanticValue("sysLocation", None, "bad\nvalue"),),
                "semantic_value_invalid",
            ),
        )
        for payload, values, code in cases:
            with self.subTest(code=code), self.assert_runner_error(code):
                apply_semantic_values(payload, values)

    @contextmanager
    def assert_runner_error(self, code):
        with self.assertRaises(RunnerError) as caught:
            yield
        self.assertEqual(caught.exception.code, code)


class MembershipTransformTests(unittest.TestCase):
    def test_parses_exact_inventory_shape(self):
        records = parse_membership(INVENTORY)
        self.assertEqual(records[0].address, "127.0.0.11")
        self.assertEqual(records[0].hostname, "lab-j9772a-01")
        self.assertEqual(records[0].model, "J9772A 2530-48G-PoEP")

    def test_rejects_invalid_or_duplicate_membership(self):
        cases = (
            (b"127.0.0.11|host\n", "invalid_membership"),
            (b"10.0.0.1|host|Model\n", "invalid_membership"),
            (b"127.0.0.11|bad host|Model\n", "invalid_membership"),
            (INVENTORY + INVENTORY.splitlines(keepends=True)[0], "duplicate_membership"),
        )
        for payload, code in cases:
            with self.subTest(code=code), self.assertRaisesRegex(RunnerError, code):
                parse_membership(payload)

    def test_activation_and_deactivation_are_idempotent_and_inventory_ordered(self):
        activated = set_endpoint_active(ACTIVE, INVENTORY, DOWN_TARGET, True)
        self.assertEqual(activated, INVENTORY)
        self.assertEqual(set_endpoint_active(activated, INVENTORY, DOWN_TARGET, True), INVENTORY)

        deactivated = set_endpoint_active(activated, INVENTORY, UP_TARGET, False)
        self.assertEqual(
            deactivated,
            b"127.0.0.12|lab-j9772a-02|J9772A 2530-48G-PoEP\n"
            b"127.0.0.13|lab-j9775a-01|J9775A 2530-48G\n",
        )
        self.assertEqual(set_endpoint_active(deactivated, INVENTORY, UP_TARGET, False), deactivated)

    def test_rejects_targets_or_active_records_absent_from_inventory(self):
        with self.assertRaisesRegex(RunnerError, "target_not_in_inventory"):
            set_endpoint_active(ACTIVE, ACTIVE, DOWN_TARGET, True)
        with self.assertRaisesRegex(RunnerError, "active_target_not_in_inventory"):
            set_endpoint_active(ACTIVE + b"127.0.0.99|unknown|Model\n", INVENTORY, UP_TARGET, True)


if __name__ == "__main__":
    unittest.main()
