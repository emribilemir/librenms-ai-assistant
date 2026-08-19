# 9b entegrasyon koşusu — BASELINE DEĞİLDİR

## Uyarı

Bu klasördeki sayılar `v5-results/`, `emr43-results/` veya `sut-results/`
ile **yan yana konulamaz**. Koşu `qwen3.5:4b` yerine `qwen3.5:9b` üstünde
yapıldı. Farklı base model = farklı SUT.

`qwen3.5:4b` kurum ağından indirilemedi (Cloudflare R2 erişimi kapalı,
9 deneme, üç farklı taşıma yolu). Yamanın entegrasyon davranışını hiç
ölçmeden bırakmamak için en yakın denk modelle koşuldu.

## Model

`librenms-qwen-9b`, `Modelfile.librenms-qwen-9b` ile kuruldu. Emir'in
`librenms-qwen` modelinden **tek farkı base**:

- SYSTEM promptu: birebir aynı (42 satır, `production_baseline_system.txt`)
- TEMPLATE / RENDERER / PARSER: birebir aynı
- PARAMETER presence_penalty 1.5 / temperature 0 / top_k 20 / top_p 0.95: birebir aynı
- FROM: `qwen3.5:9b` (production: `qwen3.5:4b`)

## Sonuçlar

| Suite | 9b + yama | 4b (v5-results) |
|---|---|---|
| Gold | 39/40 | 35/40 |
| Generated | 16/16 | 14/16 |
| Legacy | 52/56 | 55/56 |

v5'te kırık olan 7 vakanın 7'si de geçti: GOLD-012, GOLD-017, GOLD-019,
GOLD-020, GOLD-030, GEN-007, GEN-011.

## Sapmaların hepsi model kaynaklı, yama kaynaklı değil

**GOLD-014** (`"25"` -> `unsupported`, beklenen `no_match`): yamadan önceki ve
sonraki planner bu sorgu için ikisi de `None` dönüyor, yani ikisi de LLM'e
bırakıyor. Bu davranış `sut-results/RUN_REPORT.md` satır 119'da zaten
belgelenmiş.

**Legacy T07 / T20 / T48 / T52**: dördü de 4b'de geçiyordu. Buna karşılık 9b
T46'yı geçiyor, 4b'de kalıyordu. `librenms-prompt-eval/eval_runner.py`
projeden hiçbir modül import etmiyor (sadece standart kütüphane), yani legacy
suite `planner_v2`'ye hiç uğramıyor ve bu farklar saf model davranışıdır.

## grounding_check.py

Sentez çıktıları için deterministik uydurma taraması. Cevapta geçen
hostname / SKU / port / severity kanıtta var mı, ve sistem promptu kural 15
(log serbest metnini alıntılama) ihlal edilmiş mi diye bakar.

Semantik kalite ÖLÇMEZ. Olumsuzlamayı anlamaz, alıntı ile başka kelimelerle
anlatmayı ayırt etmez. `judge_questions` içindeki semantik sorular hâlâ gerçek
bir harici judge istiyor.

Tüm düzeltilmiş koşularda (4b ve 9b) desteklenmeyen iddia bulunamadı.

## Eksik

`qwen3.5:4b` üstünde doğrulama koşusu. Asıl ölçüm odur.
