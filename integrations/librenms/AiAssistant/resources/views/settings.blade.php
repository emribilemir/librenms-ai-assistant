<div style="margin: 15px; max-width: 48rem;">
    <h4>AI Assistant settings</h4>
    <p>The shared secret is {{ $secret_configured ? 'configured' : 'not configured' }}. It is never displayed after saving.</p>
    <form method="post" style="margin-top: 15px;">
        @csrf
        <label for="ai-assistant-shared-secret">Shared secret (base64-encoded, exactly 32 decoded bytes)</label>
        <input id="ai-assistant-shared-secret" name="settings[shared_secret_base64]" type="password" autocomplete="new-password" required>
        <p>Replace this value with a newly generated secret when rotating it. Save the identical value in the Mac service environment.</p>
        <button type="submit">Save</button>
    </form>
</div>
