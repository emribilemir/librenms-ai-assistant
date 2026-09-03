from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from simulation import SemanticValue, load_manifest
from simulation.runner.errors import RunnerError
from simulation.runner.processes import ProcessAdapter, ProcessResult, run_fixed
from simulation.runner.storage import RunnerLayout


MANIFEST = load_manifest(Path(__file__).resolve().parents[1] / "scenarios.json")
TARGET = MANIFEST.targets[0]
DOWN_TARGET = MANIFEST.targets[1]
LAYOUT = RunnerLayout.production()


class FakeProcess:
    def __init__(self, stdout=b"ok\n", stderr=b"", returncode=0, timeout_once=False):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.pid = 4242
        self.timeout_once = timeout_once
        self.calls = 0

    def communicate(self, timeout=None):
        self.calls += 1
        if self.timeout_once and self.calls == 1:
            raise subprocess.TimeoutExpired("fixed", timeout)
        return self.stdout, self.stderr


class FixedProcessTests(unittest.TestCase):
    def test_uses_exact_argv_without_shell_and_starts_a_process_group(self):
        process = FakeProcess(stdout=b"Polling device\n")
        with patch("simulation.runner.processes.subprocess.Popen", return_value=process) as popen:
            result = run_fixed(
                ("/usr/bin/systemctl", "restart", "snmpsim-lab.service"),
                30,
                (("/usr/bin/systemctl", "restart", "snmpsim-lab.service"),),
                ("Polling",),
            )
        self.assertEqual(result.exit_code, 0)
        args, kwargs = popen.call_args
        self.assertEqual(args[0], ["/usr/bin/systemctl", "restart", "snmpsim-lab.service"])
        self.assertIs(kwargs["shell"], False)
        self.assertIs(kwargs["start_new_session"], True)
        self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)

    def test_rejects_commands_outside_the_exact_command_allowlist(self):
        with self.assertRaisesRegex(RunnerError, "command_not_allowed"):
            run_fixed(("/bin/sh", "-c", "id"), 5, (("/usr/bin/systemctl",),), ())
        with self.assertRaisesRegex(RunnerError, "command_not_allowed"):
            run_fixed(
                ("/usr/bin/systemctl", "restart", "snmpsim-lab.service", "--now"),
                5,
                (("/usr/bin/systemctl", "restart", "snmpsim-lab.service"),),
                (),
            )

    def test_redacts_sensitive_lines_and_caps_diagnostics(self):
        lines = [b"Password: hidden", b"Authorization bearer hidden"]
        lines.extend(f"Polling line {index}".encode() for index in range(100))
        process = FakeProcess(stdout=b"\n".join(lines) + b"\n")
        with patch("simulation.runner.processes.subprocess.Popen", return_value=process):
            result = run_fixed(("/fixed",), 5, (("/fixed",),), ("Polling",))
        self.assertEqual(len(result.diagnostics), 20)
        self.assertTrue(all(line.startswith("Polling") for line in result.diagnostics))
        self.assertNotIn("hidden", " ".join(result.diagnostics))

    def test_timeout_terminates_the_whole_process_group(self):
        process = FakeProcess(timeout_once=True)
        with (
            patch("simulation.runner.processes.subprocess.Popen", return_value=process),
            patch("simulation.runner.processes.os.killpg") as killpg,
        ):
            result = run_fixed(("/fixed",), 5, (("/fixed",),), ())
        self.assertTrue(result.timed_out)
        killpg.assert_called_once()


class ProcessAdapterTests(unittest.TestCase):
    def test_restart_and_service_checks_use_fixed_systemctl_arrays(self):
        calls = []

        def invoke(argv, timeout, allowed, prefixes):
            calls.append((argv, timeout, allowed, prefixes))
            return ProcessResult(0, 12, (), False)

        adapter = ProcessAdapter(LAYOUT, invoke=invoke)
        adapter.restart_snmpsim()
        self.assertTrue(adapter.service_active())
        self.assertEqual(calls[0][0], ("/usr/bin/systemctl", "restart", "snmpsim-lab.service"))
        self.assertEqual(
            calls[1][0],
            ("/usr/bin/systemctl", "is-active", "--quiet", "snmpsim-lab.service"),
        )

    def test_poll_uses_manifest_hostname_and_exact_mode_order(self):
        calls = []

        def invoke(argv, timeout, allowed, prefixes):
            calls.append(argv)
            return ProcessResult(0, 10, ("Polling complete",), False)

        adapter = ProcessAdapter(LAYOUT, invoke=invoke)
        self.assertEqual(adapter.run_poll(TARGET, "none"), ())
        results = adapter.run_poll(TARGET, "discovery_then_poller")
        self.assertEqual(len(results), 2)
        self.assertEqual(calls[0][-2:], ("-h", "lab-j9772a-01"))
        self.assertEqual(calls[1][-2:], ("-h", "lab-j9772a-01"))
        self.assertIn("/opt/librenms/discovery.php", calls[0])
        self.assertIn("/opt/librenms/poller.php", calls[1])

    def test_poll_failure_is_stable_and_never_forwards_stderr(self):
        def invoke(argv, timeout, allowed, prefixes):
            return ProcessResult(1, 10, ("Polling safe summary",), False)

        with self.assertRaisesRegex(RunnerError, "poll_failed") as caught:
            ProcessAdapter(LAYOUT, invoke=invoke).run_poll(TARGET, "poller")
        self.assertEqual(str(caught.exception), "poll_failed")

    def test_verifies_values_and_endpoint_unreachability(self):
        observed = {
            "1.3.6.1.2.1.1.6.0": ProcessResult(0, 1, ("\"Murat Bey Demo Lab\"",), False),
        }

        def invoke(argv, timeout, allowed, prefixes):
            return observed[argv[-1]]

        adapter = ProcessAdapter(LAYOUT, invoke=invoke)
        result = adapter.verify_snmp(
            TARGET,
            (SemanticValue("sysLocation", None, "Murat Bey Demo Lab"),),
        )
        self.assertTrue(result.success)

        def unreachable(argv, timeout, allowed, prefixes):
            return ProcessResult(1, 1, (), False)

        result = ProcessAdapter(LAYOUT, invoke=unreachable).verify_snmp(
            DOWN_TARGET,
            (SemanticValue("endpointReachable", None, False),),
        )
        self.assertTrue(result.success)


if __name__ == "__main__":
    unittest.main()
