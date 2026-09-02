<?php

namespace App\Plugins\AiAssistant;

use App\Plugins\Hooks\MenuEntryHook;
use App\Models\User;

/** Adds the assistant entry to LibreNMS's native v2 plugin menu. */
class Menu extends MenuEntryHook
{
    public function authorize(User $user): bool
    {
        $authenticatedUser = auth()->user();

        return $authenticatedUser instanceof User
            && $authenticatedUser->can('global-read');
    }
}
