# Failures — probe-pretty
pass rate: 0.0% (0/4), judge pass rate: 0.0%, think leaks: 0

## PV1 — T46 variant: single-field pretty JSON (original fixture) (formatting-conciseness)
- question: sw-46 çalışıyor mu?
- response: 'Hayır, mevcut verilerde sw-46 cihazının durumu bulunmuyor.'
- failed checks: {"must_contain_any": {"pass": false, "items": ["@UP"]}}
- judge: pass=False reason='{"pass": false, "reason": "The response incorrectly claims the device status is unknown instead of confirming it is up based on the provided data."}'

## PV2 — T46 variant: multi-field pretty JSON with collected_at (formatting-conciseness)
- question: sw-46 çalışıyor mu?
- response: 'Hayır, mevcut verilerde sw-46 cihazının durumu yok.'
- failed checks: {"must_contain_any": {"pass": false, "items": ["@UP"]}}
- judge: pass=False reason='{"pass": false, "reason": "The response incorrectly claims the device status is missing when the tool results explicitly show it is \'up\'."}'

## PV3 — T46 variant: single-field compact JSON (formatting-conciseness)
- question: sw-46 çalışıyor mu?
- response: 'Hayır, mevcut verilerde sw-46 cihazının durumu bulunmuyor.'
- failed checks: {"must_contain_any": {"pass": false, "items": ["@UP"]}}
- judge: pass=False reason='{"pass": false, "reason": "The response incorrectly claims the device status is unknown instead of confirming it is up based on the provided data."}'

## PV4 — T46 variant: multi-field compact JSON (formatting-conciseness)
- question: sw-46 çalışıyor mu?
- response: 'Hayır, mevcut verilerde sw-46 cihazının durumu yok.'
- failed checks: {"must_contain_any": {"pass": false, "items": ["@UP"]}}
- judge: pass=False reason='{"pass": false, "reason": "The response incorrectly claims the device status is missing when the tool results explicitly show it is \'up\'."}'
