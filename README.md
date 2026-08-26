# LibreNMS Natural-Language Hybrid PoC

LibreNMS verilerine doğal dille erişmenin güvenilir olup olmadığını araştıran,
yerel Qwen modeliyle hazırlanmış read-only bir proof of concept.

Bu depo production LibreNMS entegrasyonu değildir. Cihaz çözümleme, katalog
filtreleme, backend araç sınırları ve LLM sentezi arasındaki mimari sınırı
ölçmek için hazırlanmış PoC, fixture, test ve deney kayıtlarını içerir.

## Güncel yaklaşım

Projenin temel kararı şudur:

> Qwen doğal dili anlar; resolver kimliği çözer; backend neyin doğru olduğunu
> belirler.

```text
Kullanıcı sorgusu
        |
        v
Qwen semantic planner
(intent + ham cihaz referansı + structured filtreler)
        |
        v
Katı plan doğrulama
        |
        v
Resolver v5
(unique / ambiguous / no_match)
        |
        v
Read-only backend araçları
        |
        +--> Atomik gerçek: deterministik cevap
        |
        +--> Investigation: sabit kanıt kümesi + bounded LLM synthesis
```

### Sorumluluk sınırları

| Katman | Sorumluluk | Yapmadığı şey |
|---|---|---|
| Qwen planner | Doğal dil intent'i, route'u, açık referansı ve ürün filtrelerini structured JSON'a çevirmek | Cihaz seçmek veya operasyonel durum iddia etmek |
| Plan doğrulayıcı | Schema, tip, route–intent ve alan tutarlılığını kontrol etmek | Türkçe regex/kelime listeleriyle planı onarmak |
| Resolver v5 | Hostname/SKU/model kimliği, katalog variant'ları, structured filtreler ve ambiguity | Serbest Türkçe intent çözmek |
| Backend | Status, port, alarm ve event gerçeklerini sağlamak | LLM kararına göre veri uydurmak |
| Synthesis | Yalnızca alınmış Level-1 kanıtını yorumlamak | Araç kapsamını genişletmek veya write işlemi yapmak |

## Korunan güvenlik ve doğruluk kuralları

- Sistem read-only araçlarla sınırlıdır.
- Atomik `up/down/unknown` gerçekleri LLM tarafından yeniden yorumlanmaz.
- Ambiguous referanslarda rastgele cihaz seçilmez; clarification üretilir.
- Eşleşme yoksa cihaz veya model uydurulmaz.
- Eksik katalog alanları UNKNOWN olarak korunur.
- Device-set cevapları backend çağrısı olmadan canlı durum yazmaz.
- Investigation yalnızca sabit `device + ports + alerts + events` kanıt kümesini kullanır.
- Synthesis girdisi alınan ve alınmayan kaynakların coverage manifestosunu taşır.
- Geçersiz planner çıktısı resolver veya backend'e ulaşmaz.

## Proje yapısı

| Yol | İçerik |
|---|---|
| [`librenms-hybrid-poc/`](librenms-hybrid-poc/) | Semantic planner, orchestration PoC'si, yerel inventory ve hedefli offline testler |
| [`hybrid-gold-v3/`](hybrid-gold-v3/) | Kaynak doğruluğu düzeltilmiş katalog, synthetic backend, Gold/Generated acceptance varlıkları ve resolver v4/v5 |
| [`sut-results/`](sut-results/) | Gerçek yerel SUT ile daha önce alınmış çalışma izleri ve raporlar |
| [`4b-verification-results/`](4b-verification-results/) | Qwen 4B doğrulama kayıtları |
| [`9b-integration-results/`](9b-integration-results/) | Qwen 9B karşılaştırma kayıtları; 4B baseline yerine geçmez |
| [`holdout-results/`](holdout-results/) | Dondurulmuş hidden-holdout çalışma kayıtları |
| [`emr43-results/`](emr43-results/) | EMR-43 adversarial deney ve patch kanıtları |
| [`librenms-prompt-eval/`](librenms-prompt-eval/) | Tarihsel prompt evaluation deneyleri |
| [`docs/superpowers/specs/`](docs/superpowers/specs/) | Güncel mimari karar belgeleri |
| [`docs/superpowers/plans/`](docs/superpowers/plans/) | Uygulama planları |

## Önemli dosyalar

- [`librenms-hybrid-poc/hybrid_poc.py`](librenms-hybrid-poc/hybrid_poc.py): planner, resolver ve backend orchestration akışı
- [`librenms-hybrid-poc/planner_v2.py`](librenms-hybrid-poc/planner_v2.py): yalnız structured plan schema/validation sözleşmesi
- [`hybrid-gold-v3/resolver_candidate_v5.py`](hybrid-gold-v3/resolver_candidate_v5.py): structured katalog filtreleme ve identity resolution
- [`hybrid-gold-v3/catalog_ingest.py`](hybrid-gold-v3/catalog_ingest.py): model metnini katalog facet'lerine dönüştürme
- [`hybrid-gold-v3/dummy_backend.py`](hybrid-gold-v3/dummy_backend.py): gerçek araç çağrılarını kaydeden read-only SpyBackend
- [`librenms-hybrid-poc/test_semantic_planner.py`](librenms-hybrid-poc/test_semantic_planner.py): yeni sahiplik sınırının küçük offline testleri
- [`LIBRENMS_PLANNER_CATALOG_RESOLVER_OWNERSHIP_REVIEW.md`](LIBRENMS_PLANNER_CATALOG_RESOLVER_OWNERSHIP_REVIEW.md): planner/catalog/resolver sahiplik incelemesi
- [`docs/superpowers/specs/2026-08-26-semantic-planner-deterministic-core-rag-design.md`](docs/superpowers/specs/2026-08-26-semantic-planner-deterministic-core-rag-design.md): onaylanan güncel tasarım

## Veri kaynağı ve provenance

Kaynak Excel yalnızca `Brand` ve `Model` alanlarını içerir. Gerçek
kaynak-destekli kimlikler sekiz HP ProCurve SKU/model kaydıdır:

```text
J4850A, J9772A, J9774A, J9775A,
J9776A, J9780A, J9783A, JL357A
```

`lab-<sku>-NN` biçimindeki hostname'ler, device ID'ler, status, port, alarm ve
event değerleri synthetic fixture'dır. Production cihazı veya İSBAK gerçek
operasyon verisi olarak yorumlanmamalıdır.

## Hızlı doğrulama

Yeni semantic-planner sahiplik sınırını ağ veya LLM olmadan kontrol etmek için:

```bash
python3 librenms-hybrid-poc/test_semantic_planner.py -v
```

Mevcut hedefli suite dokuz küçük offline test içerir. Planner schema, invalid
plan davranışı, resolver v5 structured filtre aktarımı ve device-set truth
sınırını doğrular.

Yerel Ollama ile tarihsel PoC harness'ini çalıştırmak için:

```bash
python3 librenms-hybrid-poc/hybrid_poc.py \
  --model librenms-qwen \
  --cases librenms-hybrid-poc/t46_v2_cases.json \
  --temps 0.0 \
  --out /tmp/librenms-hybrid-results.json
```

Bu komut yerel `http://localhost:11434` Ollama servisine ihtiyaç duyar.

## Güncel doğrulama durumu

Semantic-planner sahiplik değişikliğinden sonra:

- hedefli offline testler: **9/9**
- değiştirilen Python dosyaları: syntax/import kontrolü başarılı
- Gold/Generated/Legacy ve LLM suite'leri: kullanıcının süre/maliyet tercihi nedeniyle yeniden çalıştırılmadı

Depodaki eski skorlar kendi commit, model ve runtime bağlamlarına aittir. Son
mimari değişiklik için yeni sonuç gibi sunulmamalıdır.

## Bilinen sınırlar ve ertelenen işler

- RAG, B planı olarak ertelendi. İleride katalog ve doküman bağlamı için
  retrieval eklenebilir; canlı status/port/alarm/event verisi yine backend'den
  gelmelidir.
- `speed_mbps` filtresi mevcut schema'da yoktur; kaynak veri yeterli olmadan
  tahmin edilmeyecektir.
- Multi-device port/alarm/event fan-out desteklenmez; çoklu eşleşmede
  clarification tercih edilir.
- Structured findings, evidence ID'leri ve grounding validator sonraki ayrı
  mimari aşamadır.
- Bu çalışma production deployment, write operation veya gerçek LibreNMS API
  bağlantısı içermez.

## Mimari karar

Projenin güncel hedefi prompt'u veya Python keyword kurallarını sürekli
büyütmek değildir. Model doğal dili structured plana çevirir; kritik kimlik,
filtre, izin ve operasyonel gerçek kararları doğrulanabilir katmanlarda kalır.
Bu sınır yeterli kaliteyi sağlamazsa çalışma dürüstçe PoC/fizibilite sonucu
olarak kapatılabilir.
