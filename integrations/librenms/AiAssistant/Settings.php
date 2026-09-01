<?php

namespace App\Plugins\AiAssistant;

use App\Plugins\Hooks\SettingsHook;

/** Defines the local plugin's administrator-only shared-secret setting view. */
class Settings extends SettingsHook
{
    private const STORED_SETTINGS = '_ai_assistant_stored_settings';

    /** @param array<string, mixed> $settings */
    public function data(array $settings = []): array
    {
        // LibreNMS's native SettingsHook calls data twice. The first result
        // carries settings only to the second call; final view data omits it.
        if (! isset($settings[self::STORED_SETTINGS]) || ! is_array($settings[self::STORED_SETTINGS])) {
            return [self::STORED_SETTINGS => $settings];
        }

        $storedSettings = $settings[self::STORED_SETTINGS];
        $secret = $storedSettings['shared_secret'] ?? null;

        return [
            'secret_configured' => is_string($secret) && strlen($secret) === 32,
        ];
    }
}
