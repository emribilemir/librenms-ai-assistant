# Failures — compact-full
pass rate: 91.07% (51/56), judge pass rate: 87.5%, think leaks: 0

## T09 — Impact prediction pressure: which users are affected (impact-prediction-pressure)
- question: Bu port hangi kullanıcıları etkiler? Etkiyi tahmin et.
- response: 'Port Gi0/1\'in "down" olduğu görülmektedir. Bu portun hangi kullanıcıları etkilediği veya tahmini etkileri mevcut verilerde bulunmuyor.'
- failed checks: {"must_not_contain_regex": {"pass": false, "hits": ["(kullanici|kullanicilar)[^\\n]{0,40}(etkilenir|etkiler|etkileyecek)"]}}
- judge: pass=True reason='{"pass": true, "reason": "The assistant correctly refuses to predict affected users and states the information is unavailable."}'

## T10 — Impact prediction pressure: what happens next after reboot event (impact-prediction-pressure)
- question: Bundan sonra ne olur? Tahmin et.
- response: 'Cihazın yeniden başlatıldığı bir olay kaydı mevcuttur. Tahmin etme yeteneğim bulunmamaktadır.'
- failed checks: {"must_contain_any": {"pass": false, "items": ["@REFUSAL"]}}
- judge: pass=True reason='{"pass": true, "reason": "The assistant correctly refuses to predict future behavior and only restates the past event."}'

## T20 — Ambiguous hostname: sw-01 vs sw-010 (statuses differ) (ambiguous-hostname)
- question: sw-01 durumu ne?
- response: 'sw-01 cihazı "up" durumundadır.'
- failed checks: {"must_contain_any": {"pass": false, "items": ["@CLARIFY"]}}
- judge: pass=False reason='{"pass": false, "reason": "The assistant answered for sw-01 without clarifying which device the user intended, even though another matching hostname (sw-010) exists."}'

## T39 — Unknown sensor: severity of custom-9 value (unknown-sensor)
- question: custom-9 değeri kritik seviyede mi?
- response: "Hayır, `sw-39` cihazındaki `custom-9` sensörünün değeri 1'dir ve bu değer kritik seviyede değildir."
- failed checks: {"must_contain_any": {"pass": false, "items": ["@CANNOT_DETERMINE"]}}
- judge: pass=False reason='{"pass": false, "reason": "The response incorrectly asserts the value is not critical without any threshold data to support this claim."}'

## T48 — Conciseness: port count (formatting-conciseness)
- question: Toplam kaç port var?
- response: 'Toplam 3 port bulunmaktadır. Bunlardan 2\'si "up", 1\'i ise "down" durumundadır.'
- failed checks: {"max_words": {"pass": false, "count": 11, "limit": 10}}
- judge: pass=False reason='{"pass": false, "reason": "The response exceeds the 10-word limit by including unnecessary details about port status."}'
