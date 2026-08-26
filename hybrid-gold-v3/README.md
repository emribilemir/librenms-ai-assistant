# LibreNMS Hybrid Gold v3

`hybrid-gold-v3`, LibreNMS doğal dil hybrid PoC'sinin kaynak doğruluğu
düzeltilmiş acceptance varlıklarını, synthetic backend'ini ve resolver
adaylarını içerir.

## Veri kaynağı

Kaynak Excel yalnızca `Brand` ve `Model` sütunlarını içerir. Elli satırdan
sekiz benzersiz HP ProCurve model kimliği çıkarılmıştır. Kaynakta gerçek
hostname, device ID, status, port, alarm veya event verisi yoktur.

Kaynak-destekli kimlikler:

```text
J4850A, J9772A, J9774A, J9775A,
J9776A, J9780A, J9783A, JL357A
```

`lab-<sku>-NN` hostname'leri ve bütün operasyonel değerler açıkça synthetic
fixture'dır; production/gerçek cihaz olarak anlatılmamalıdır.

## Acceptance akışı

```text
user query
  -> semantic planner / intent
  -> structured plan validation
  -> resolver
  -> route selection
  -> SpyBackend tool calls
  -> optional Qwen investigation
  -> answer
```

Harness; resolution, route, gerçek backend çağrıları, argümanlar ve LLM
invocation davranışını deterministik olarak kontrol eder. Investigation
semantiği external judging için dışa aktarılır; yerel Qwen kendisini puanlamaz.

## Resolver sürümleri

- [`resolver_candidate_v4.py`](resolver_candidate_v4.py): dondurulmuş,
  doğrulanmış compatibility resolver'ı.
- [`catalog_ingest.py`](catalog_ingest.py): model adlarından structured katalog
  facet'leri ve identity variant'ları üretir.
- [`resolver_candidate_v5.py`](resolver_candidate_v5.py): v4'ün güvenli kimlik
  davranışını korur; structured `brand`, `family`, `port_count`, `poe`
  filtrelerini uygular; UNKNOWN ve ambiguity bilgisini kaybetmez.

Resolver v5 serbest Türkçe intent çözmez. Doğal dil planner'a, structured
filtreleme resolver'a aittir.

## Merkezi kanıt çifti

Doğrudan gerçek:

```text
J9774A up mı?
```

Beklenen yol: kimlik çözümü → `get_device` → deterministik cevap → synthesis
LLM yok.

Investigation:

```text
J9774A up gözüküyor ama ben tepki alamıyorum.
```

Beklenen yol: aynı kimlik → `get_device + get_ports + get_alerts + get_events`
→ grounded Qwen synthesis.

Fixture kasıtlı olarak overall status `up`, port 8 admin-up/oper-down, aktif
alarm ve uyumlu event kayıtları içerir.

## Önemli dosyalar

| Dosya | Amaç |
|---|---|
| [`source_catalog.json`](source_catalog.json) | Excel'den türetilmiş kaynak-destekli model vocabulary |
| [`dummy_inventory.json`](dummy_inventory.json) | Gerçek SKU/model kimliklerine bağlı synthetic lab örnekleri |
| [`dummy_backend_data.json`](dummy_backend_data.json) | Synthetic operasyonel fixture'lar |
| [`backend_capabilities.json`](backend_capabilities.json) | Read-only backend capability sözleşmesi |
| [`orchestration_policy.json`](orchestration_policy.json) | Route-to-tool acceptance politikası |
| [`gold_cases.json`](gold_cases.json) | 40 elle hazırlanmış architecture acceptance vakası |
| [`generated_cases.json`](generated_cases.json) | 16 wording robustness varyantı |
| [`dummy_backend.py`](dummy_backend.py) | Araç çağrılarını ve argümanlarını kaydeden SpyBackend |
| [`run_gold.py`](run_gold.py) | Deterministik acceptance harness |
| [`reference_adapter.py`](reference_adapter.py) | Harness self-test adapter'ı; gerçek SUT değildir |
| [`sut_adapter_template.py`](sut_adapter_template.py) | Gerçek local PoC adapter sözleşmesi |

## Harness kullanımı

```bash
python3 hybrid-gold-v3/run_gold.py --help
```

`--resolver`, `--adapter`, `--cases`, `--inventory`, `--out` ve
`--external-out` seçenekleriyle çalışır. Resolver veya adapter seçmeden önce
hangi mimari snapshot'ın ölçüldüğü açıkça kaydedilmelidir.

## Sonuçların yorumlanması

Depodaki Gold/Generated sonuç dosyaları üretildikleri resolver, planner, model
ve runtime snapshot'ına aittir. Güncel semantic-planner sahiplik değişikliğinden
sonra full LLM/regression suite yeniden çalıştırılmadığı için eski skorlar yeni
mimarinin sonucu gibi sunulmamalıdır.
