"""Offline contract checks for the LibreNMS AI Assistant local plugin.

These checks deliberately inspect the deployable source rather than a guest.
They protect the native LibreNMS v2 plugin boundary and must stay runnable on
the repository's standard Python runtime.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from pathlib import Path
import sys
import unittest


PLUGIN = Path(__file__).resolve().parents[1]
REPOSITORY = PLUGIN.parents[2]
OFFICIAL_SETTINGS_HOOK = Path("/private/tmp/librenms-inspect.eLIkd2/repo/app/Plugins/Hooks/SettingsHook.php")
sys.path.insert(0, str(REPOSITORY / "librenms-hybrid-poc"))

from chat_service.auth import IdentityVerifier  # noqa: E402


def read(relative: str) -> str:
    return (PLUGIN / relative).read_text(encoding="utf-8")


class AiAssistantPluginContractTests(unittest.TestCase):
    def test_native_menu_and_page_hooks_gate_global_read_access(self) -> None:
        """A permission regression must make the AI page unreachable from the menu."""
        menu = read("Menu.php")
        page = read("Page.php")
        self.assertIn("class Menu extends MenuEntryHook", menu)
        self.assertIn("class Page extends PageHook", page)
        self.assertIn("$authenticatedUser->can('global-read')", menu)
        self.assertIn("$authenticatedUser->can('global-read')", page)
        self.assertIn("plugin/AiAssistant", read("resources/views/menu.blade.php"))

    def test_page_uses_only_a_root_nonsecret_config_and_fixed_assets(self) -> None:
        """A browser must receive a signed identity, never the shared signing key."""
        page = read("resources/views/page.blade.php")
        self.assertIn('id="root"', page)
        self.assertIn("data-ai-assistant-config", page)
        self.assertNotIn("window.__LIBRENMS_AI_ASSISTANT__", page)
        self.assertIn("JSON_HEX_TAG", read("Page.php"))
        self.assertIn("ai-assistant.css", page)
        self.assertIn("ai-assistant.js", page)
        self.assertIn("'/ai-api/v1'", read("Page.php"))
        self.assertNotIn("shared_secret", page)
        self.assertNotIn("AI_ASSISTANT_SHARED_SECRET", page)

    def test_page_signs_the_exact_v1_identity_contract(self) -> None:
        """Changing claims, TTL, HMAC input, or secret length breaks service authentication."""
        page = read("Page.php")
        for claim in ("'sub'", "'name'", "'iss' => 'librenms'", "'aud' => 'ai-assistant'", "'iat'", "'exp' => $iat + 3600"):
            self.assertIn(claim, page)
        self.assertIn('return "v1.$encoded.$signature"', page)
        self.assertIn("hash_hmac('sha256', $encoded, $secret, true)", page)
        self.assertIn("strlen($secret) !== 32", page)
        self.assertIn("$settings['shared_secret']", page)
        self.assertNotIn("base64_decode", page)

    def test_reference_plugin_token_roundtrips_through_the_current_python_verifier(self) -> None:
        """A signer drift must make an independently built plugin token unverifiable."""
        secret = b"0123456789abcdefghijklmnopqrstuv"
        issued = 1_700_000_000
        payload = {"sub": "42", "name": "NOC Operator", "iss": "librenms", "aud": "ai-assistant", "iat": issued, "exp": issued + 3600}
        encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()).rstrip(b"=")
        signature = base64.urlsafe_b64encode(hmac.new(secret, encoded, hashlib.sha256).digest()).rstrip(b"=")
        token = f"v1.{encoded.decode()}.{signature.decode()}"

        identity = IdentityVerifier(secret, clock=lambda: issued).verify(token)
        self.assertEqual((identity.sub, identity.name), ("42", "NOC Operator"))

    def test_settings_two_phase_contract_keeps_configured_status_without_returning_secret(self) -> None:
        """The official SettingsHook invokes data twice, so final view data must stay configured."""
        official = OFFICIAL_SETTINGS_HOOK.read_text(encoding="utf-8")
        self.assertIn("$this->data($app->call($this->data(...)", official)
        settings = read("Settings.php")
        self.assertIn("_ai_assistant_stored_settings", settings)
        self.assertIn("'secret_configured'", settings)
        self.assertIn("'shared_secret'", settings)
        self.assertNotIn("'settings' => $storedSettings", settings)
        settings_view = read("resources/views/settings.blade.php")
        self.assertIn('name="settings[shared_secret]"', settings_view)
        self.assertNotIn('value="{{', settings_view)

        stored = {"shared_secret": "0123456789abcdefghijklmnopqrstuv"}
        first = {"_ai_assistant_stored_settings": stored}
        second = {"secret_configured": len(first["_ai_assistant_stored_settings"]["shared_secret"]) == 32}
        self.assertEqual(second, {"secret_configured": True})

    def test_startup_documentation_matches_current_factory_and_raw_secret_environment(self) -> None:
        """A runbook drift must not point deployment at a missing ASGI callable or env name."""
        app = (REPOSITORY / "librenms-hybrid-poc/chat_service/app.py").read_text(encoding="utf-8")
        docs = read("docs/deployment.md")
        self.assertIn("def create_app", app)
        self.assertIn('os.environ.get("AI_ASSISTANT_SHARED_SECRET", "").encode()', app)
        self.assertIn("AI_ASSISTANT_SHARED_SECRET", docs)
        self.assertNotIn("AI_ASSISTANT_SHARED_SECRET_BASE64", docs)
        self.assertIn("uvicorn chat_service.app:create_app --factory", docs)
        self.assertIn("exact 32-character ASCII secret", docs)

    def test_php_boundary_excludes_ai_orchestration(self) -> None:
        """A local plugin can render/sign only; orchestration belongs to the Mac service."""
        php = "\n".join(read(name) for name in ("Menu.php", "Page.php", "Settings.php"))
        for forbidden in ("planner", "resolver", "qwen", "PipelineAdapter", "FastAPI", "Uvicorn", "curl_", "Guzzle"):
            self.assertNotIn(forbidden.lower(), php.lower())

    def test_deployment_manifest_and_scripts_target_only_plugin_paths(self) -> None:
        """A packaging regression must not drift into LibreNMS core sources or Vite config."""
        manifest = json.loads(read("deployment-manifest.json"))
        self.assertEqual(manifest["plugin_source_destination"], "/opt/librenms/app/Plugins/AiAssistant/")
        self.assertEqual(manifest["asset_destination"], "/opt/librenms/html/plugins/ai-assistant/")
        self.assertEqual(manifest["assets"], ["ai-assistant.js", "ai-assistant.css"])
        package = read("scripts/package-assets.sh")
        deploy = read("scripts/deploy-plugin.sh")
        self.assertIn("ai-assistant.js", package)
        self.assertIn("ai-assistant.css", package)
        self.assertIn('"$LIBRENMS_ROOT/html/plugins/ai-assistant"', package)
        self.assertIn('"$PLUGIN_DIR/../../.."', package)
        self.assertIn('"$LIBRENMS_ROOT/app/Plugins/AiAssistant"', deploy)
        self.assertIn("package-assets.sh", deploy)
        self.assertIn("mktemp -d", deploy)
        self.assertIn("rsync -a --delete-delay", deploy)
        self.assertIn("restore_backup", deploy)
        self.assertNotIn("package.json", deploy)
        self.assertNotIn("vite.config", deploy)

    def test_nginx_proxy_preserves_sse_and_routes_to_mac_service(self) -> None:
        """A proxy regression must fail before it can buffer a production SSE stream."""
        nginx = read("nginx/ai-assistant.conf")
        for directive in (
            "location ^~ /ai-api/",
            "proxy_pass http://192.168.64.1:8765/;",
            "proxy_http_version 1.1;",
            "proxy_buffering off;",
            "proxy_cache off;",
            "proxy_read_timeout 360s;",
            "proxy_set_header Connection \"\";",
            "X-Accel-Buffering no",
        ):
            self.assertIn(directive, nginx)
        self.assertIn("server-context include", nginx)
        self.assertEqual(self._upstream_uri("/ai-api/v1/threads"), "/v1/threads")

    @staticmethod
    def _upstream_uri(path: str) -> str:
        """Nginx proxy_pass with a trailing slash replaces the location prefix."""
        prefix = "/ai-api/"
        if not path.startswith(prefix):
            raise ValueError("outside AI proxy location")
        return "/" + path[len(prefix):]


if __name__ == "__main__":
    unittest.main()
