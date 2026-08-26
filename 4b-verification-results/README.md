# qwen3.5:4b doğrulama koşusu — production model

PR #1'in eksik bıraktığı ölçüm. Kod `main` (`86a702a`), resolver v5,
adapter `sut_adapter.py`, `SUT_PLANNER_SCHEMA=gold`.

## Model doğrulaması

`librenms-qwen`, `Modelfile.librenms-qwen` ile kuruldu ve Emir'in modeliyle
karşılaştırıldı:

| Kontrol | Sonuç |
|---|---|
| Base blob SHA | `sha256-81fb60c7daa8…` — **aynı** |
| SYSTEM promptu | 42 satır, **birebir aynı** |
| TEMPLATE / RENDERER / PARSER | **birebir aynı** |
| PARAMETER x4 | `presence_penalty 1.5`, `temperature 0`, `top_k 20`, `top_p 0.95` — **birebir aynı** |
| `system_sha` (legacy runner) | `d320cbd8e984` — Emir'in koşusuyla **aynı** |

## Sonuç: kontrollü A/B, aynı ortam, aynı model

Yamalı ve yamasız kod arka arkaya koşuldu. Yamasız = `d50c87f`
(PR #1 öncesi hali).

| Suite | Yamasız | Yamalı | Düzelen | Bozulan |
|---|---|---|---|---|
| Gold | 37/40 | **38/40** | GOLD-012 | **yok** |
| Generated | 14/16 | **15/16** | GEN-011 | **yok** |

Yama tek yönlü iyileştirme yapıyor, sıfır regresyon. Bu bir çıkarım değil,
doğrudan ölçüm.

Yamanın hedeflediği 7 vakanın 7'si de production modelde geçiyor:
GOLD-012, GOLD-017, GOLD-019, GOLD-020, GOLD-030, GEN-007, GEN-011.

Gold iki kez koşuldu (`gold_results.json`, `gold_results_run2.json`), ikisi de
38/40 ve aynı vakalar — kararsızlık yok.

## ⚠️ Bu koşu 40/40 sorusunu KAPATMIYOR

Bu ortam Emir'in kayıtlı baseline'ını yeniden üretemiyor. Yamasız kod
koşulduğunda `v5-results/`'taki 35/40 değil **37/40** çıkıyor ve farklı
vakalar kalıyor.

| | Gold, yamasız | Kalanlar |
|---|---|---|
| Emir (`v5-results/`) | 35/40 | GOLD-012, 017, 019, 020, 030 |
| Bu ortam | 37/40 | GOLD-012, GOLD-031, GOLD-034 |

Not: `v5-results/` yamasız koşusu, `e3a386a`'daki keyword yamasından ÖNCEKİ
koda ait. Buradaki "yamasız" kontrol ise o keyword yamasını içeriyor — bu
yüzden 017/019/020/030 orada geçiyor. Karşılaştırılabilir olan sütun
"Düzelen / Bozulan"dır.

### Kalan hatalar yamayla ilgili değil

**GOLD-031, GOLD-034, GEN-015** — üçü de yamalı VE yamasız kodda aynen
kalıyor. Üçü de `planner=llm`. Eski ve yeni planner bu üç sorgu için de
`None` dönüyor (deterministik yola girmiyorlar), yani yamanın teması yok.

- GOLD-031: planner `device_query`'yi `"port 8"` olarak çıkarmış (`J9774A`
  yerine) → resolver ambiguous → `clarification`
- GOLD-034 / GEN-015: `intent=unknown` (beklenen `unsupported`)

### Farkın kaynağı ortam, model değil

**T48 ve T52 legacy vakaları bu ortamda hem 4b hem 9b ile kalıyor, Emir'in
koşusunda ikisi de geçiyor.** Model değiştiğinde bile kalıyorlar.
`librenms-prompt-eval/eval_runner.py` projeden hiçbir modül import etmiyor
(sadece standart kütüphane), yani legacy suite `planner_v2`'ye hiç uğramıyor.

En olası sebep ollama sürümü. Bu makinede:

    ollama version is 0.32.7
    Warning: client version is 0.32.13

`RENDERER qwen3.5` ve `PARSER qwen3.5` görece yeni direktifler; sürümler
arası render davranışı değişirse temperature 0'da bile çıktı değişir.
Emir'in sürümü bilinmiyor. **Karşılaştırma yapılırken ortam oynatılmasın
diye sürüm güncellenmedi.**

## Legacy

| | Legacy |
|---|---|
| Emir (`v5-results/`) | 55/56 — kalan: T46 |
| Bu ortam, 4b | 52/56 — kalan: T28, T46, T48, T52 |
| Bu ortam, 9b | 52/56 — kalan: T07, T20, T48, T52 |

Legacy `planner_v2`'ye uğramıyor, dolayısıyla bu farklar bu PR'ın konusu değil.

## Emir'e soru

Hangi ollama sürümüyle koştun? Sürümler eşitlenirse bu ortam senin
baseline'ını üretebilir ve 40/40 sorusu kesin kapanır. Şu an kapanmıyor.

## Dosyalar

| Dosya | Ne |
|---|---|
| `gold_results.json` / `gold_results_run2.json` | yamalı, iki koşu, ikisi de 38/40 |
| `gold_UNPATCHED.json` | kontrol: yamasız kod, aynı ortam, 37/40 |
| `generated_results.json` | yamalı, 15/16 |
| `generated_UNPATCHED.json` | kontrol: yamasız, 14/16 |
| `legacy_results.json` | 52/56 |
| `Modelfile.librenms-qwen` | kurulumda kullanılan, Emir'inkiyle birebir |
