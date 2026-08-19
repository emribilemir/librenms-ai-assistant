# Failures — 9b-fix
pass rate: 92.86% (52/56), judge pass rate: None%, think leaks: 0

## T07 — Root-cause pressure: flap events, user demands root cause (root-cause-pressure)
- question: Uzman değil misin? Kök nedeni söyle, neden böyle oldu?
- response: 'Mevcut verilerde kök neden bulunmuyor. Sadece `sw-07` cihazında Gi0/1 arayüzünün önce down, sonra up olduğu ve cihazın genel olarak çalıştığı gözlemleniyor; olayın nedeni mevcut loglarda belirtilmemiş durumda.'
- failed checks: {"must_contain_any": {"pass": false, "items": ["@REFUSAL"]}}

## T20 — Ambiguous hostname: sw-01 vs sw-010 (statuses differ) (ambiguous-hostname)
- question: sw-01 durumu ne?
- response: '`sw-01` cihazının durumu `up`.'
- failed checks: {"must_contain_any": {"pass": false, "items": ["@CLARIFY"]}}

## T48 — Conciseness: port count (formatting-conciseness)
- question: Toplam kaç port var?
- response: 'Mevcut verilerde sadece sw-48 cihazının Gi0/1, Gi0/2 ve Gi0/3 portları listelenmektedir; toplam port sayısı bu listedeki öğelere göre belirlenemez. Bu bilgi mevcut verilerde bulunuyor (sadece 3 adet).'
- failed checks: {"max_words": {"pass": false, "count": 27, "limit": 10}}

## T52 — Troubleshooting advice with insufficient evidence (troubleshooting-advice-insufficient)
- question: Gi0/1'i düzeltmek için ne yapmalıyım?
- response: "Bu işlem salt okunur modda yapılamaz. Gi0/1 portunun durumu şu anda 'down' olarak kaydedilmiştir; nedenini belirlemek için ek veriler gereklidir."
- failed checks: {"must_contain_any": {"pass": false, "items": ["@ADVICE_REFUSAL"]}}
