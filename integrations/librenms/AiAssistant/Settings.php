<?php

namespace App\Plugins\AiAssistant;

use App\Plugins\Hooks\SettingsHook;

/** Defines the local plugin's administrator-only shared-secret setting view. */
class Settings extends SettingsHook
{
    /** @param array<string, mixed> $settings */
    public function data(array $settings = []): array
    {
        // LibreNMS's native SettingsHook calls data twice: first with the
        // stored settings, then with the first view-data result.
        if (isset($settings['settings']) && is_array($settings['settings'])) {
            $settings = $settings['settings'];
        }

        $encoded = $settings['shared_secret_base64'] ?? null;
        $secret = is_string($encoded) ? base64_decode($encoded, true) : false;

        return [
            'secret_configured' => is_string($secret) && strlen($secret) === 32,
        ];
    }
}
