from pathlib import Path
import subprocess
import unittest

from simulation import load_manifest
from simulation.runner.errors import RunnerError


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = load_manifest(ROOT / "scenarios.json")
PACKAGING = ROOT / "packaging"
SYSTEMD = ROOT / "systemd" / "snmpsim-lab.service"


class ServiceLauncherTests(unittest.TestCase):
    def test_builds_all_active_endpoints_without_a_shell(self):
        from simulation.runner.snmpsim_service import build_responder_argv

        inventory = (
            b"127.0.0.11|lab-j9772a-01|J9772A\n"
            b"127.0.0.12|lab-j9772a-02|J9772A\n"
            b"127.0.0.13|lab-j9775a-01|J9775A\n"
        )
        active = (
            b"127.0.0.11|lab-j9772a-01|J9772A\n"
            b"127.0.0.12|lab-j9772a-02|J9772A\n"
        )
        argv = build_responder_argv(MANIFEST, active, inventory)
        self.assertEqual(argv[0], "/opt/snmpsim-venv/bin/snmpsim-command-responder")
        self.assertIn("--data-dir=/opt/snmpsim-lab/data/lab-j9772a-01", argv)
        self.assertIn("--agent-udpv4-endpoint=127.0.0.11:1611", argv)
        self.assertIn("--data-dir=/opt/snmpsim-lab/data/lab-j9772a-02", argv)
        self.assertNotIn("/bin/sh", argv)

    def test_rejects_inventory_drift_for_manifest_targets(self):
        from simulation.runner.snmpsim_service import build_responder_argv

        drifted = b"127.0.0.12|lab-j9772a-01|J9772A\n"
        with self.assertRaisesRegex(RunnerError, "manifest_inventory_mismatch"):
            build_responder_argv(MANIFEST, drifted, drifted)

    def test_rejects_active_records_not_in_inventory(self):
        from simulation.runner.snmpsim_service import build_responder_argv

        active = b"127.0.0.12|lab-j9772a-02|J9772A\n"
        inventory = b"127.0.0.11|lab-j9772a-01|J9772A\n"
        with self.assertRaisesRegex(RunnerError, "active_target_not_in_inventory"):
            build_responder_argv(MANIFEST, active, inventory)


class PackagingContractTests(unittest.TestCase):
    def read(self, name):
        return (PACKAGING / name).read_text(encoding="utf-8")

    def test_systemd_unit_is_fixed_hardened_and_librenms_owned(self):
        unit = SYSTEMD.read_text(encoding="utf-8")
        for expected in (
            "User=librenms",
            "Group=librenms",
            "NoNewPrivileges=true",
            "PrivateTmp=true",
            "ProtectSystem=strict",
            "ProtectHome=true",
            "ReadWritePaths=/opt/snmpsim-lab/cache",
            "ExecStart=/usr/bin/python3 -I /opt/librenms-ai-lab/snmpsim-service-entry.py",
        ):
            self.assertIn(expected, unit)
        self.assertNotIn("${", unit)

    def test_forced_key_and_sudoers_allow_one_exact_root_command(self):
        sudoers = self.read("librenms-ai-lab.sudoers")
        exact = "/usr/bin/python3 -I /opt/librenms-ai-lab/runner-entry.py"
        self.assertIn(f"NOPASSWD: {exact}", sudoers)
        self.assertNotIn("ALL=(ALL) ALL", sudoers)
        self.assertNotIn("*", sudoers)

        installer = self.read("install-runner.sh")
        self.assertIn(f'restrict,command="/usr/bin/sudo -n {exact}"', installer)
        self.assertIn('PUBLIC_KEY_FILE="$1"', installer)
        self.assertIn("ssh-ed25519", installer)
        self.assertNotIn("ssh-ed25519 AAAA", installer)

    def test_installer_is_staged_inert_and_captures_baseline(self):
        installer = self.read("install-runner.sh")
        for fixed_root in ("/opt/librenms-ai-lab", "/var/lib/librenms-ai-lab", "/opt/snmpsim-lab"):
            self.assertIn(fixed_root, installer)
        self.assertIn("baseline-capture-entry.py", installer)
        self.assertIn("manifest.sha256", installer)
        self.assertIn("backup", installer)
        self.assertIn('chown -R root:root "$STAGE"', installer)
        self.assertIn('chmod 0755 "$STAGE/simulation/packaging/"*.sh', installer)
        self.assertNotIn("systemctl enable --now", installer)
        self.assertNotIn("systemctl start", installer)
        self.assertNotIn("systemctl stop", installer)
        self.assertNotIn("/opt/librenms/app", installer)

    def test_activation_has_automatic_legacy_rollback(self):
        activation = self.read("activate-runner.sh")
        self.assertIn("rollback_legacy", activation)
        self.assertIn("systemctl enable --now snmpsim-lab.service", activation)
        self.assertIn("/opt/snmpsim-lab/run-up-only.sh", activation)
        self.assertIn("verify-runner.sh", activation)
        self.assertNotIn("eval", activation)

    def test_verify_and_rollback_validate_the_managed_surfaces(self):
        verify = self.read("verify-runner.sh")
        self.assertIn("systemd-analyze verify", verify)
        self.assertIn("sshd -t", verify)
        self.assertIn("manifest.sha256", verify)
        self.assertIn("manual_recovery_required", verify)

        rollback = self.read("rollback-runner.sh")
        self.assertIn("local-reset-entry.py", rollback)
        self.assertIn("run-up-only.sh", rollback)
        self.assertNotIn("rm -rf", rollback)

    def test_all_packaging_scripts_are_valid_bash_without_eval(self):
        scripts = sorted(PACKAGING.glob("*.sh"))
        self.assertEqual(
            [item.name for item in scripts],
            ["activate-runner.sh", "install-runner.sh", "rollback-runner.sh", "verify-runner.sh"],
        )
        for script in scripts:
            with self.subTest(script=script.name):
                result = subprocess.run(
                    ["/bin/bash", "-n", str(script)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotIn("eval", script.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
