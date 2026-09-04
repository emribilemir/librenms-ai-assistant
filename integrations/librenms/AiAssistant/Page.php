<?php

namespace App\Plugins\AiAssistant;

use App\Models\User;
use App\Plugins\Hooks\PageHook;
use JsonException;

/** Renders the mounted static client and a short-lived signed browser identity. */
class Page extends PageHook
{
    public function authorize(User $user): bool
    {
        $authenticatedUser = auth()->user();

        return $authenticatedUser instanceof User
            && $authenticatedUser->can('global-read');
    }

    /**
     * @param  array<string, mixed>  $settings
     * @return array<string, string>
     *
     * @throws JsonException
     */
    public function data(array $settings = []): array
    {
        /** @var User $user */
        $user = auth()->user();
        $identity = [
            'token' => $this->identityToken($user, $settings),
            'apiBase' => '/ai-api/v1',
        ];

        return [
            'identity_json' => json_encode(
                $identity,
                JSON_HEX_TAG | JSON_HEX_AMP | JSON_HEX_APOS | JSON_HEX_QUOT | JSON_THROW_ON_ERROR
            ),
        ];
    }

    /** @param array<string, mixed> $settings */
    private function identityToken(User $user, array $settings): string
    {
        $secret = $this->sharedSecret($settings);
        $iat = time();
        $payload = [
            'sub' => (string) $user->user_id,
            'name' => $this->displayName($user),
            'iss' => 'librenms',
            'aud' => 'ai-assistant',
            'iat' => $iat,
            'exp' => $iat + 3600,
        ];
        $encoded = $this->base64UrlEncode(json_encode(
            $payload,
            JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR
        ));
        $signature = $this->base64UrlEncode(hash_hmac('sha256', $encoded, $secret, true));

        return "v1.$encoded.$signature";
    }

    /** @param array<string, mixed> $settings */
    private function sharedSecret(array $settings): string
    {
        $secret = $settings['shared_secret'] ?? null;

        if (! is_string($secret) || strlen($secret) !== 32) {
            abort(503, 'The AI Assistant shared secret is not configured.');
        }

        return $secret;
    }

    private function displayName(User $user): string
    {
        $name = trim((string) $user->realname);

        return $name !== '' ? $name : (string) $user->username;
    }

    private function base64UrlEncode(string $value): string
    {
        return rtrim(strtr(base64_encode($value), '+/', '-_'), '=');
    }
}
