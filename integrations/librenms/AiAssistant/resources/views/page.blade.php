<link rel="stylesheet" href="{{ asset('plugins/ai-assistant/ai-assistant.css') }}">
<div id="root"></div>
<script>
window.__LIBRENMS_AI_ASSISTANT__ = {!! $identity_json !!};
</script>
<script type="module" src="{{ asset('plugins/ai-assistant/ai-assistant.js') }}"></script>
