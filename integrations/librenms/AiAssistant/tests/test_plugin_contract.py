"""Offline contract checks for the LibreNMS AI Assistant local plugin.

These checks deliberately inspect the deployable source rather than a guest.
They protect the native LibreNMS v2 plugin boundary and must stay runnable on
the repository's standard Python runtime.
"""

from __future__ import annotations

import json
from pathlib import Path
import unittest


PLUGIN = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (PLUGIN / relative).read_text(encoding="utf-8")


class AiAssistantPluginContractTests(unittest.TestCase):
    def test_native_menu_and_page_hooks_gate_global_read_access(self) -> None:
        """A permission regression must make the AI page unreachable from the menu."""
        menu = read("Menu.php")
        page = read("Page.php")
        self.assertIn("class Menu extends MenuEntryHook", menu)
        self.assertIn("class Page extends PageHook", page)
        self.assertIn("$user->can('global-read')", menu)
        self.assertIn("$user->can('global-read')", page)
        self.assertIn("plugin/AiAssistant", read("resources/views/menu.blade.php"))

    def test_page_uses_only_a_root_nonsecret_config_and_fixed_assets(self) -> None:
        """A browser must receive a signed identity, never the shared signing key."""
        page = read("resources/views/page.blade.php")
        self.assertIn('id="root"', page)
        self.assertIn("window.__LIBRENMS_AI_ASSISTANT__", page)
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
        self.assertIn("base64_decode", page)

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


if __name__ == "__main__":
    unittest.main()
