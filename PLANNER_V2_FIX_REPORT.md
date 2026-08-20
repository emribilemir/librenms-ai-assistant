# planner_v2 düzeltmesi — bulgular ve ölçümler

## 1. Ne bozuktu

v5 mimarisi uygulandıktan sonra Gold 35/40, Generated 14/16 kaldı ve
`V5_RUN_REPORT.md` doğru davranıp **DO_NOT_COMMIT** dedi, hiçbir şeyi yamamadı.

Sonrasında `librenms-hybrid-poc/planner_v2.py` içine bir kelime listesi eklendi
(`_RETRIEVAL_STEMS`, `_SET_NOUN_STEMS`, `_ACTION_STEMS` + `_has_direct_retrieval_cue`).
Bu yama 5 testi geçiriyordu ama:

- `LIBRENMS_PLANNER_CATALOG_RESOLVER_OWNERSHIP_REVIEW.md` bu üç sabiti isim isim
  örnek gösterip "handwritten intent classifier" diyor (Invariant 2, 11, 12).
- `librenms-architecture-v5-first-pass.tar/LUNA_MECHANICAL_ONLY.md` açıkça
  "do not add regexes, SKU literals, tests, fixtures, expected outputs, or
  prompt workarounds" diyor.
- Yamadan sonra suite bir daha koşulmadı; `v5-results/` skorları yamadan
  ÖNCEKİ koda ait, yani bayat.
- Guard yanlış da ateşliyordu: `48G'lerin alarmlarını göster` de dışarı itiliyordu.

Ayrıca 2 vaka (GOLD-012, GEN-011) hiç düzeltilmemişti.

## 2. Gerçek kök nedenler

**A. Fiil, küme sinyali değildir.** `_SET_CUES` içinde "göster/getir/listele"
vardı. Fiil bir şeyin döndürüleceğini söyler, öznenin bir cihaz kümesi olduğunu
söylemez. Küme sinyali koleksiyon isminden gelir (cihazları, switchleri).
Bu yüzden `J9774A portlarını göster` device_set sanılıyordu.

**B. Sıkıştırma, facet ile kesin kimliği aynı şeye çeviriyordu.**
`_catalog_reference()` sorguyu `_compact()` ile sıkıştırırken boşluk ve tireyi
siliyordu, dolayısıyla kullanıcının yazdığı `2530 48G` ile katalogdaki kanonik
model `2530-48G` aynı stringe düşüyordu. Sonuç: "2530 ailesi + 48 port" sorusu
tek bir model adına çöküyor ve PoE'li J9772A eleniyordu.

Bunun iki SKU dönmesi gerektiği uydurma bir beklenti değil, `SELFTEST_REPORT.md`
içinde yazılı kural:
> broad phrase `2530 48G` must still return both J9772A and J9775A

Kanıt: `2530-48G` verildiğinde v4 de v5 de tek sonuç döndürüyor. Yani resolver
doğru çalışıyordu, ona yanlış girdi veriliyordu.

**C. `48G` facet olarak parse edilmiyordu**, ve `_PORT_COUNT_RE` sonundaki
`(?!\w)` yüzünden `48 portlu` de eşleşmiyordu.

## 3. Yapılan değişiklik

Tek dosya: `librenms-hybrid-poc/planner_v2.py`

1. `_SET_CUES` sadece koleksiyon isimlerine indirildi, fiiller çıkarıldı.
2. `_RETRIEVAL_STEMS` / `_SET_NOUN_STEMS` / `_ACTION_STEMS` ve
   `_has_direct_retrieval_cue()` tamamen silindi.
3. `_catalog_reference()` ayırıcı-duyarlı hale getirildi: SKU'lar (tek token)
   sıkıştırılmış eşleşiyor, model adları kendi ayırıcı yapısıyla token
   sınırında eşleşiyor.
4. `48G/24G/8G` kısaltması port_count facet'ine çevriliyor; `48 portlu` de
   eşleşiyor.

Resolver, fixture, gold/generated case, beklenen sonuç, prompt, Modelfile —
hiçbirine dokunulmadı.

## 4. Ölçümler

### LLM gerektirmeyen (modelden bağımsız, kesin)

| Kontrol | Sonuç |
|---|---|
| Gold+Generated device_set vakaları, uçtan uca | 11/11 |
| Suite dışı küme ifadeleri (24G, 8 portlu, poesiz, ProCurve modelleri…) | 8/8 |
| Tekil/retrieval ifadeleri Qwen'e bırakılıyor mu | 8/8 |
| Deterministik yolun yanlış yakaladığı vaka | 0 |
| 56 vakada routing farkı (yamalı sürüme göre) | 0 |
| `test_resolver.py` | 47/47 |
| `test_units.py`, `test_resolver_contract.py` | değişiklik öncesiyle birebir aynı |

### Uçtan uca koşu — DİKKAT: qwen3.5:9b üstünde

`qwen3.5:4b` kurum ağından indirilemedi (Cloudflare R2 erişimi kapalı, 9 deneme).
Bu yüzden koşu `librenms-qwen-9b` ile yapıldı: SYSTEM promptu, TEMPLATE,
RENDERER, PARSER ve 4 PARAMETER Emir'in modeliyle birebir; **tek fark base model**.

| Suite | 9b + yama | 4b (v5-results) |
|---|---|---|
| Gold | 39/40 | 35/40 |
| Generated | 16/16 | 14/16 |
| Legacy | 52/56 | 55/56 |

**v5'te kırık olan 7 vakanın 7'si de geçti:** GOLD-012, GOLD-017, GOLD-019,
GOLD-020, GOLD-030, GEN-007, GEN-011.

BU SAYILAR 4b SONUÇLARININ YERİNE GEÇMEZ. Farklı base model = farklı SUT.
Legacy zaten bunu kanıtlıyor: 9b T07/T20/T48/T52'de kalıyor (4b'de hepsi
geçiyordu), buna karşılık T46'yı geçiyor (4b'de kalıyordu). `eval_runner.py`
projeden hiçbir şey import etmiyor, yani bu farklar saf model davranışı.

Gold'daki tek hata GOLD-014 (`"25"` -> `unsupported`, beklenen `no_match`) de
model kaynaklı: yamadan önceki ve sonraki planner ikisi de bu sorgu için `None`
dönüyor (LLM'e bırakıyor), ve bu davranış `sut-results/RUN_REPORT.md` satır
119'da zaten belgelenmiş.

### Grounding taraması (yeni ölçüm)

Sentez çıktıları bugüne kadar hiç değerlendirilmemişti (20 dosyada ~100 case
export edilmiş, puanlanmış sıfır). Harici judge için API erişimi yok, ama
`tool_evidence` + `final_answer` birlikte durduğu için mekanik kontrol mümkün.

`grounding_check.py`: cevapta geçen hostname / SKU / port / severity kanıtta
var mı, ve sistem promptu kural 15 (log serbest metnini alıntılama) ihlal
edilmiş mi.

Sonuç — **düzeltilmiş koşuların hepsi temiz:**

    EMR-43 gold (4b, 40/40 koşusu)  7/7
    EMR-43 generated (4b)           3/3
    EMR-43 e2e (4b)                 6/6
    v5 gold / generated (4b)        7/7, 3/3
    SUT gold / generated (4b)       7/7, 3/3
    9b gold / generated             7/7, 3/3

Yani production modelin sentez çıktılarında desteklenmeyen varlık/port/severity
iddiası bulunamadı.

SINIRLARI: Bu tarama semantik kalite ÖLÇMEZ. Olumsuzlamayı anlamaz, alıntı ile
başka kelimelerle anlatmayı ayırt etmez. `judge_questions` içindeki "kullanıcının
niyetini cevaplıyor mu", "kanıt yetersizken belirsizliği koruyor mu" soruları
hâlâ gerçek bir harici judge istiyor. Bu tarama onun yerine geçmez, sadece
uydurma taramasıdır.

## 5. Açık kalan kararlar (Emir'e)

1. **4b'de doğrulama koşusu — KISMEN YAPILDI.** Ayrıntı:
   `4b-verification-results/`. Production model (`librenms-qwen`, base blob
   SHA'sı Emir'inkiyle aynı) kuruldu ve kontrollü A/B koşuldu:

   | Suite | Yamasız | Yamalı | Düzelen | Bozulan |
   |---|---|---|---|---|
   | Gold | 37/40 | 38/40 | GOLD-012 | yok |
   | Generated | 14/16 | 15/16 | GEN-011 | yok |

   Yamanın hedeflediği 7 vakanın 7'si de geçiyor, sıfır regresyon.

   AMA bu koşu 40/40 sorusunu kapatmıyor: bu ortam Emir'in kayıtlı
   baseline'ını üretemiyor (yamasız kod 35/40 değil 37/40 veriyor).
   Kalan GOLD-031 / GOLD-034 / GEN-015 hataları yamalı ve yamasız kodda
   aynen mevcut. Fark ortam kaynaklı; en olası sebep ollama sürümü
   (bu makinede server 0.32.7, client 0.32.13 uyarısı). Emir'in sürümü
   öğrenilip eşitlenmeli.

2. **Filtre şemasında hız alanı yok.** `2530 8G` üç model döndürüyor, oysa
   "8 port 1G" tam okunsa tek model olmalı. `DEVICE_FILTER_SCHEMA`'da
   brand/family/port_count/poe var, speed yok. Ownership dokümanı bunu açık
   karar maddesi bırakmış, o yüzden tek taraflı eklenmedi. `2530 48G` için fark
   yaratmıyor (48 portlu 2530'ların ikisi de G modeli).

3. **İki bayat test dosyası.** `test_units.py` içindeki
   `schema.required_present` v5'in eklediği `device_filters`'ı bilmiyor.
   `test_resolver_contract.py` resolver'a ham Türkçe cümle veriyor, oysa v5
   bunu planner'a taşıdı. İkisi de v4 döneminden kalma. Test düzenlemek hem
   bundle talimatının hem ownership dokümanının yasakladığı şey olduğu için
   dokunulmadı.

4. **device_set cevabı backend çağrısı olmadan durum iddia ediyor.** SUT ilk
   koşusunda GOLD-024, `tool_calls: []` ile `lab-j9783a-01 (up)` cevabını
   üretmiş. Bilgi envanterden geliyor, uydurma değil — ama "hangi durum
   iddiaları backend çağrısı gerektirir" bir ürün kararı.

5. **Harici judge hiç koşulmadı.** Sentez kalitesi ölçülmemiş. Model boyutunun
   gerçekten önem taşıyabileceği tek yer burası.
