import unittest

from simulation.catalog import resolve_oid, validate_semantic_value


class SemanticCatalogTests(unittest.TestCase):
    def test_resolves_only_approved_scalar_and_indexed_semantics(self):
        self.assertEqual(resolve_oid("sysLocation", None), ("1.3.6.1.2.1.1.6.0", 4))
        self.assertEqual(resolve_oid("ifOperStatus", 2), ("1.3.6.1.2.1.2.2.1.8.2", 2))
        with self.assertRaisesRegex(ValueError, "unknown_semantic"):
            resolve_oid("1.3.6.1.4.1.999", None)
        with self.assertRaisesRegex(ValueError, "index_required"):
            resolve_oid("ifOperStatus", None)
        with self.assertRaisesRegex(ValueError, "index_forbidden"):
            resolve_oid("sysLocation", 1)

    def test_rejects_wrong_types_enums_ranges_and_oversized_text(self):
        for name, index, value, code in (
            ("ifAdminStatus", 1, 3, "invalid_enum"),
            ("ifOperStatus", 1, "down", "invalid_type"),
            ("sysUpTime", None, -1, "invalid_range"),
            ("ifAlias", 1, "x" * 129, "value_too_long"),
        ):
            with self.subTest(name=name, value=value), self.assertRaisesRegex(ValueError, code):
                validate_semantic_value(name, index, value)

    def test_accepts_values_used_by_the_initial_scenarios(self):
        for name, index, value in (
            ("sysLocation", None, "Murat Bey Demo Lab"),
            ("sysUpTime", None, 300),
            ("ifAdminStatus", 2, 1),
            ("ifOperStatus", 2, 2),
            ("ifAlias", 4, "Demo-Uplink"),
            ("endpointReachable", None, False),
        ):
            validate_semantic_value(name, index, value)

    def test_virtual_reachability_is_validated_but_never_resolved_to_an_oid(self):
        validate_semantic_value("endpointReachable", None, True)
        with self.assertRaisesRegex(ValueError, "virtual_semantic"):
            resolve_oid("endpointReachable", None)
        with self.assertRaisesRegex(ValueError, "invalid_type"):
            validate_semantic_value("endpointReachable", None, 1)


if __name__ == "__main__":
    unittest.main()
