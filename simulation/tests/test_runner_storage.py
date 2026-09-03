import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from simulation import ScenarioPhase, ScenarioState, load_manifest, manifest_sha256
from simulation.runner.errors import RunnerError
from simulation.runner.storage import OwnershipPolicy, RunnerLayout, RunnerStorage


MANIFEST_PATH = Path(__file__).resolve().parents[1] / "scenarios.json"
MANIFEST = load_manifest(MANIFEST_PATH)
MANIFEST_SHA = manifest_sha256(MANIFEST)

INVENTORY = b"""127.0.0.11|lab-j9772a-01|J9772A 2530-48G-PoEP
127.0.0.13|lab-j9775a-01|J9775A 2530-48G
"""
ACTIVE = b"127.0.0.11|lab-j9772a-01|J9772A 2530-48G-PoEP\n"
FIXTURE = b"""1.3.6.1.2.1.1.3.0|67|1234567
1.3.6.1.2.1.1.5.0|4|{hostname}
1.3.6.1.2.1.1.6.0|4|Test Lab
1.3.6.1.2.1.2.2.1.7.2|2|1
1.3.6.1.2.1.2.2.1.8.2|2|2
1.3.6.1.2.1.31.1.1.1.18.4|4|Client
"""


class RecordingOwnership(OwnershipPolicy):
    def __init__(self):
        self.calls = []
        self.verifications = []

    def apply_and_verify(self, path, owner):
        self.calls.append((Path(path), owner, Path(path).stat().st_mode & 0o777))

    def verify(self, path, owner):
        self.verifications.append((Path(path), owner))


class RunnerStorageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.layout = RunnerLayout(
            install_root=root / "install",
            state_root=root / "state",
            snmpsim_root=root / "snmpsim",
            librenms_root=root / "librenms",
        )
        for directory in (
            self.layout.install_root,
            self.layout.state_root,
            self.layout.snmpsim_root / "data",
            self.layout.snmpsim_root / "cache",
            self.layout.librenms_root,
        ):
            directory.mkdir(parents=True)
        (self.layout.snmpsim_root / "devices.txt").write_bytes(INVENTORY)
        (self.layout.snmpsim_root / "devices-up.txt").write_bytes(ACTIVE)
        for target in MANIFEST.targets:
            directory = self.layout.snmpsim_root / "data" / target.fixture
            directory.mkdir()
            (directory / "public.snmprec").write_bytes(
                FIXTURE.replace(b"{hostname}", target.hostname.encode())
            )
        self.ownership = RecordingOwnership()
        self.storage = RunnerStorage(self.layout, self.ownership)

    def tearDown(self):
        self.temporary.cleanup()

    def test_production_layout_is_fixed(self):
        production = RunnerLayout.production()
        self.assertEqual(production.install_root, Path("/opt/librenms-ai-lab"))
        self.assertEqual(production.state_root, Path("/var/lib/librenms-ai-lab"))
        self.assertEqual(production.snmpsim_root, Path("/opt/snmpsim-lab"))
        self.assertEqual(production.librenms_root, Path("/opt/librenms"))

    def test_state_defaults_to_baseline_and_roundtrips_canonical_json(self):
        baseline = self.storage.load_state(MANIFEST)
        self.assertEqual(baseline, ScenarioState(ScenarioPhase.BASELINE, None, MANIFEST_SHA))

        applied = ScenarioState(ScenarioPhase.APPLIED, "location-change", MANIFEST_SHA)
        with patch("simulation.runner.storage.os.fsync") as fsync:
            self.storage.save_state(applied)
        self.assertGreaterEqual(fsync.call_count, 2)
        self.assertEqual(self.storage.load_state(MANIFEST), applied)
        raw = (self.layout.state_root / "state.json").read_bytes()
        self.assertEqual(raw, json.dumps(json.loads(raw), sort_keys=True, separators=(",", ":")).encode() + b"\n")
        self.assertIn((self.layout.state_root / "state.json", "root", 0o600), self.ownership.calls)
        self.assertIn((self.layout.state_root / "state.json", "root"), self.ownership.verifications)

    def test_state_rejects_corruption_stale_sha_and_unknown_scenario(self):
        state_path = self.layout.state_root / "state.json"
        state_path.write_text("not-json", encoding="utf-8")
        with self.assertRaisesRegex(RunnerError, "state_corrupt"):
            self.storage.load_state(MANIFEST)

        state_path.write_text(
            '{"phase":"invalid","phase":"baseline","scenario_id":null,'
            f'"manifest_sha256":"{MANIFEST_SHA}","last_error_code":null}}',
            encoding="utf-8",
        )
        with self.assertRaisesRegex(RunnerError, "state_corrupt"):
            self.storage.load_state(MANIFEST)

        state_path.write_text(
            json.dumps(
                {
                    "phase": "applied",
                    "scenario_id": "location-change",
                    "manifest_sha256": "0" * 64,
                    "last_error_code": None,
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(RunnerError, "manifest_mismatch"):
            self.storage.load_state(MANIFEST)

        state_path.write_text(
            json.dumps(
                {
                    "phase": "applied",
                    "scenario_id": "not-in-manifest",
                    "manifest_sha256": MANIFEST_SHA,
                    "last_error_code": None,
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(RunnerError, "unknown_scenario"):
            self.storage.load_state(MANIFEST)

    def test_global_lock_is_nonblocking(self):
        with self.storage.acquire():
            second = RunnerStorage(self.layout, self.ownership)
            with self.assertRaisesRegex(RunnerError, "lab_busy"):
                with second.acquire():
                    self.fail("second runner acquired the global lock")

    def test_capture_once_and_restore_exact_baseline(self):
        self.storage.capture_baseline(MANIFEST)
        baseline_fixture = (
            self.layout.state_root / "baseline" / "fixtures" / "lab-j9772a-01.snmprec"
        ).read_bytes()

        changed_active = INVENTORY
        changed_fixture = FIXTURE.replace(b"Test Lab", b"Changed").replace(
            b"{hostname}", b"lab-j9772a-01"
        )
        (self.layout.snmpsim_root / "devices-up.txt").write_bytes(changed_active)
        self.storage.write_fixture(MANIFEST.targets[0], changed_fixture)
        self.storage.capture_baseline(MANIFEST)
        self.assertEqual(
            (self.layout.state_root / "baseline" / "fixtures" / "lab-j9772a-01.snmprec").read_bytes(),
            baseline_fixture,
        )

        self.storage.restore_baseline(MANIFEST)
        self.assertEqual((self.layout.snmpsim_root / "devices-up.txt").read_bytes(), ACTIVE)
        self.assertEqual(
            (self.layout.snmpsim_root / "data" / "lab-j9772a-01" / "public.snmprec").read_bytes(),
            baseline_fixture,
        )

    def test_baseline_manifest_mismatch_fails_closed(self):
        self.storage.capture_baseline(MANIFEST)
        (self.layout.state_root / "baseline" / "manifest.sha256").write_text("0" * 64 + "\n")
        with self.assertRaisesRegex(RunnerError, "baseline_manifest_mismatch"):
            self.storage.restore_baseline(MANIFEST)

    def test_symlink_destinations_are_rejected(self):
        target = MANIFEST.targets[0]
        fixture = self.layout.snmpsim_root / "data" / target.fixture / "public.snmprec"
        outside = Path(self.temporary.name) / "outside"
        outside.write_bytes(b"do-not-touch")
        fixture.unlink()
        fixture.symlink_to(outside)
        with self.assertRaisesRegex(RunnerError, "unsafe_path"):
            self.storage.write_fixture(target, FIXTURE.replace(b"{hostname}", target.hostname.encode()))
        self.assertEqual(outside.read_bytes(), b"do-not-touch")

    def test_cache_clear_removes_only_exact_target_dbm_files(self):
        target = MANIFEST.targets[0]
        fixture = self.layout.snmpsim_root / "data" / target.fixture / "public.snmprec"
        prefix = str(fixture.with_suffix("")).replace("/", "_") + ".dbm"
        cache = self.layout.snmpsim_root / "cache"
        expected = {prefix, prefix + "-shm", prefix + "-wal"}
        for name in (*expected, prefix + ".other", "unrelated.dbm"):
            (cache / name).write_bytes(b"cache")

        removed = set(self.storage.clear_target_cache(target))

        self.assertEqual(removed, expected)
        self.assertTrue((cache / (prefix + ".other")).exists())
        self.assertTrue((cache / "unrelated.dbm").exists())


if __name__ == "__main__":
    unittest.main()
