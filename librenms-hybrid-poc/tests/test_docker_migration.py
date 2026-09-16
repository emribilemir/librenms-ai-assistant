import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
STAGER = ROOT / "scripts" / "docker-migration-stage"
COMPOSE = ROOT / "ops" / "docker" / "compose.yml"
GATEWAY_CONFIG = ROOT / "ops" / "docker" / "gateway.conf"


class DockerMigrationStagingTests(unittest.TestCase):
    def _backup(self, root: Path, *, corrupt_checksum: bool = False) -> Path:
        backup = root / "backup"
        backup.mkdir()

        with gzip.open(backup / "librenms.sql.gz", "wb") as handle:
            handle.write(b"CREATE TABLE devices (device_id int);\n")

        members = {
            "opt/librenms/rrd/lab-device/port-1.rrd": b"rrd-history",
            "opt/snmpsim-lab/devices-up.txt": b"127.0.0.11|lab-device|J9772A\n",
            "opt/snmpsim-lab/data/lab-device/public.snmprec": b"1.3.6.1|4|lab-device\n",
            "opt/librenms/config.php": b"<?php // legacy config\n",
            "opt/librenms/.env": b"DB_PASSWORD=secret\n",
            "opt/librenms/app/Plugins/AiAssistant/Page.php": b"<?php\n",
            "opt/librenms/html/plugins/ai-assistant/ai-assistant.js": b"app();\n",
            "etc/nginx/sites-enabled/librenms.vhost": b"server {}\n",
        }
        with tarfile.open(backup / "librenms-files.tar.gz", "w:gz") as archive:
            for name, payload in members.items():
                member = tarfile.TarInfo(name)
                member.size = len(payload)
                member.mode = 0o600 if name.endswith(".env") else 0o644
                archive.addfile(member, io.BytesIO(payload))

        checksums = []
        for name in ("librenms.sql.gz", "librenms-files.tar.gz"):
            digest = hashlib.sha256((backup / name).read_bytes()).hexdigest()
            if corrupt_checksum and name == "librenms.sql.gz":
                digest = "0" * 64
            checksums.append(f"{digest}  {name}\n")
        (backup / "SHA256SUMS").write_text("".join(checksums), encoding="utf-8")
        return backup

    def test_stages_verified_backup_into_docker_state_layout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            backup = self._backup(root)
            target = root / "state"

            result = subprocess.run(
                [sys.executable, str(STAGER), str(backup), str(target)],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                gzip.open(target / "import" / "librenms.sql.gz", "rb").read(),
                b"CREATE TABLE devices (device_id int);\n",
            )
            self.assertEqual(
                (target / "librenms" / "rrd" / "lab-device" / "port-1.rrd").read_bytes(),
                b"rrd-history",
            )
            self.assertEqual(
                (target / "snmpsim-lab" / "devices-up.txt").read_text(encoding="utf-8"),
                "127.0.0.11|lab-device|J9772A\n",
            )
            legacy_env = target / "legacy" / "opt" / "librenms" / ".env"
            self.assertEqual(legacy_env.read_text(encoding="utf-8"), "DB_PASSWORD=secret\n")
            self.assertEqual(stat.S_IMODE(legacy_env.stat().st_mode), 0o600)
            self.assertTrue(
                (target / "legacy" / "opt" / "librenms" / "app" / "Plugins" / "AiAssistant" / "Page.php").is_file()
            )
            self.assertTrue(
                (target / "legacy" / "etc" / "nginx" / "sites-enabled" / "librenms.vhost").is_file()
            )
            self.assertFalse((target / "db").exists())
            self.assertFalse((target / "redis").exists())

    def test_refuses_a_backup_with_a_bad_checksum(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            backup = self._backup(root, corrupt_checksum=True)
            target = root / "state"

            result = subprocess.run(
                [sys.executable, str(STAGER), str(backup), str(target)],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("checksum", result.stderr.lower())
            self.assertFalse(target.exists())

    def test_refuses_archive_path_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            backup = self._backup(root)
            archive_path = backup / "librenms-files.tar.gz"
            with tarfile.open(archive_path, "w:gz") as archive:
                payload = b"escape"
                member = tarfile.TarInfo("../../outside")
                member.size = len(payload)
                archive.addfile(member, io.BytesIO(payload))
            digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
            sql_digest = hashlib.sha256((backup / "librenms.sql.gz").read_bytes()).hexdigest()
            (backup / "SHA256SUMS").write_text(
                f"{sql_digest}  librenms.sql.gz\n{digest}  librenms-files.tar.gz\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [sys.executable, str(STAGER), str(backup), str(root / "state")],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unsafe archive member", result.stderr.lower())
            self.assertFalse((root / "outside").exists())


class DockerComposeContractTests(unittest.TestCase):
    def test_gateway_preserves_the_external_port_in_librenms_redirects(self):
        config = GATEWAY_CONFIG.read_text(encoding="utf-8")

        self.assertIn("proxy_set_header Host $http_host;", config)

    def test_compose_preserves_migrated_state_and_loopback_snmpsim_contract(self):
        ruby = subprocess.run(
            [
                "ruby",
                "-rjson",
                "-ryaml",
                "-e",
                "puts JSON.generate(YAML.load_file(ARGV.fetch(0)))",
                str(COMPOSE),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(ruby.returncode, 0, ruby.stderr)
        compose = json.loads(ruby.stdout)
        services = compose["services"]

        self.assertEqual(
            set(services),
            {"db", "redis", "librenms", "dispatcher", "snmpsim", "gateway"},
        )
        self.assertIn("./state/librenms:/data", services["librenms"]["volumes"])
        self.assertIn("./state/librenms:/data", services["dispatcher"]["volumes"])
        self.assertEqual(
            services["librenms"]["environment"].get("APP_KEY"),
            "${LIBRENMS_APP_KEY:?set LIBRENMS_APP_KEY in ops/docker/.env}",
        )
        self.assertEqual(
            services["dispatcher"]["environment"].get("APP_KEY"),
            "${LIBRENMS_APP_KEY:?set LIBRENMS_APP_KEY in ops/docker/.env}",
        )
        self.assertIn("db-data:/var/lib/mysql", services["db"]["volumes"])
        self.assertIn(
            "./state/import/librenms.sql.gz:/docker-entrypoint-initdb.d/00-librenms.sql.gz:ro",
            services["db"]["volumes"],
        )
        self.assertIn("redis-data:/data", services["redis"]["volumes"])
        self.assertEqual(set(compose["volumes"]), {"db-data", "redis-data"})
        self.assertEqual(services["db"]["command"][0], "mariadbd")
        self.assertEqual(services["snmpsim"]["network_mode"], "service:dispatcher")
        self.assertIn("./state/snmpsim-lab:/opt/snmpsim-lab", services["snmpsim"]["volumes"])
        lab_hosts = {
            "lab-j9772a-01:127.0.0.11",
            "lab-j9772a-02:127.0.0.12",
            "lab-j9775a-01:127.0.0.13",
            "lab-j9775a-02:127.0.0.14",
            "lab-jl357a-01:127.0.0.15",
            "lab-j4850a-01:127.0.0.16",
            "lab-j4850a-02:127.0.0.17",
            "lab-j9774a-01:127.0.0.18",
            "lab-j9776a-01:127.0.0.19",
            "lab-j9780a-01:127.0.0.20",
            "lab-j9783a-01:127.0.0.21",
        }
        self.assertEqual(set(services["librenms"]["extra_hosts"]), lab_hosts)
        self.assertEqual(set(services["dispatcher"]["extra_hosts"]), lab_hosts)
        self.assertNotIn("ports", services["librenms"])
        self.assertEqual(services["gateway"]["ports"], ["${LIBRENMS_HTTP_PORT:-8080}:80"])
        self.assertEqual(
            services["gateway"]["environment"],
            {
                "AI_BACKEND_HOST": "${AI_BACKEND_HOST:-host.docker.internal}",
                "AI_BACKEND_PORT": "${AI_BACKEND_PORT:-8765}",
            },
        )
        self.assertIn(
            "./gateway.conf:/etc/nginx/templates/default.conf.template:ro",
            services["gateway"]["volumes"],
        )


if __name__ == "__main__":
    unittest.main()
