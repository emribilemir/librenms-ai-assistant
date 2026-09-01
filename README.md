# LibreNMS Natural-Language Hybrid PoC

LibreNMS verilerine doğal dille, güvenli ve doğrulanabilir biçimde erişmenin
uygulanabilirliğini araştıran read-only bir proof of concept.

Proje; yerel Qwen modeliyle doğal dil planlama, deterministik cihaz çözümleme,
LibreNMS `/api/v0` sorguları ve kanıta dayalı cevap üretimi arasındaki sınırları
test eder. Production uygulaması veya write yetkili bir LibreNMS istemcisi
değildir.

## Temel yaklaşım

> Qwen isteği yapılandırır; resolver kimliği çözer; LibreNMS operasyonel
> gerçeği sağlar; Python kritik kararları doğrular.

```text
Kullanıcı sorgusu
        |
        v
Qwen semantic planner
(route + intent + ham referans + structured filtreler)
        |
        v
Strict plan validation
        |
        v
Resolver v5
(unique / ambiguous / no_match)
        |
        v
Read-only LibreNMS backend
        |
        +--> Direct read: deterministik cevap
        |
        +--> Investigation: typed findings -> Qwen claims -> validation/judge
                                               |
                                               +--> güvenli fallback
```

### Sorumluluk sınırları

| Katman | Sorumluluk | Yapmadığı şey |
|---|---|---|
| Qwen planner | Doğal dili doğrulanabilir structured plana dönüştürmek | Cihaz seçmek veya backend verisi olmadan durum iddia etmek |
| Plan doğrulayıcı | Schema, tip, route–intent ve alan tutarlılığını kontrol etmek | Kullanıcı cümlesini regex kurallarıyla yeniden yorumlamak |
| Resolver v5 | Hostname, SKU, model ve katalog filtrelerini çözmek | Belirsiz eşleşmede rastgele cihaz seçmek |
| LibreNMS backend | Cihaz, port, alarm ve event gerçeklerini sağlamak | Write endpointi çağırmak veya veri tahmin etmek |
| Grounding katmanı | Bulguları sabit referanslarla paketlemek ve claim'leri doğrulamak | Kanıtta bulunmayan kök neden üretmek |

## Desteklenen sorgu kapsamı

- Tekil cihaz veya cihaz seti için canlı durum
- Cihaz modeli, hostname, uptime, location ve işletim sistemi
- Port admin/oper durumu, hız ve açıklama
- Belirli port veya structured port filtreleri
- Aktif alarm ve event listeleri
- Son durum değişimi ve zaman pencereli event sorguları
- Sabit kanıt kümesiyle güncel veya tarihsel investigation
- Marka, aile, port sayısı ve PoE gibi katalog filtreleriyle cihaz seti çözümleme

Örnekler:

```text
lab-j9772a-01 açık mı?
lab-j9772a-01'in modeli ne?
lab-j9772a-01 ne kadar süredir açık?
lab-j9772a-01 port 2'nin hızı ne?
lab-j9772a-01'in down portları hangileri?
lab-j9772a-01 son 30 dakikada status değiştirdi mi?
lab-j9772a-01'de ne sorun var?
```

## Depo yapısı

| Yol | İçerik |
|---|---|
| [`librenms-hybrid-poc/`](librenms-hybrid-poc/) | Güncel planner, orchestration ve backend adapter giriş noktaları |
| [`librenms-hybrid-poc/tests/`](librenms-hybrid-poc/tests/) | 90 testlik offline regression suite |
| [`librenms-hybrid-poc/fixtures/`](librenms-hybrid-poc/fixtures/) | PoC inventory, prompt ve acceptance girdileri |
| [`librenms-hybrid-poc/hybrid-gold-v3/`](librenms-hybrid-poc/hybrid-gold-v3/) | Katalog ingest, resolver v4/v5, synthetic backend ve Gold/Generated acceptance varlıkları |
| [`docs/history/`](docs/history/) | Tarihsel inceleme ve düzeltme raporları |
| [`docs/INSTALLATION.md`](docs/INSTALLATION.md) | Opsiyonel Debian, SSH, sudo ve SNMPSim kurulum rehberi |
| [`docs/lab/`](docs/lab/) | Ayrıntılı tarihsel LibreNMS ve SNMPSim lab notları |
| [`docs/superpowers/specs/`](docs/superpowers/specs/) | Onaylanmış mimari tasarım belgeleri |
| [`docs/superpowers/plans/`](docs/superpowers/plans/) | Uygulama planları |

### Önemli dosyalar

- [`hybrid_poc.py`](librenms-hybrid-poc/hybrid_poc.py): planner, resolver,
  backend ve synthesis orchestration
- [`live_query.py`](librenms-hybrid-poc/live_query.py): gerçek LibreNMS API'si
  için komut satırı giriş noktası
- [`planner_v2.py`](librenms-hybrid-poc/planner_v2.py): structured plan schema,
  normalizasyon ve strict validation
- [`librenms_backend.py`](librenms-hybrid-poc/librenms_backend.py): read-only
  LibreNMS `/api/v0` adapter'ı
- [`investigation_grounding.py`](librenms-hybrid-poc/investigation_grounding.py):
  typed findings, claim doğrulama, judge ve güvenli fallback sözleşmeleri
- [`utility_facts.py`](librenms-hybrid-poc/utility_facts.py): deterministik cihaz,
  port ve event fact seçicileri
- [`resolver_candidate_v5.py`](librenms-hybrid-poc/hybrid-gold-v3/resolver_candidate_v5.py):
  structured katalog filtreleme ve identity resolution
- [`emr52_acceptance_queries.json`](librenms-hybrid-poc/fixtures/emr52_acceptance_queries.json):
  güncel canlı acceptance sorguları

## Hızlı başlangıç

Proje çekirdek akışında Python standard library kullanır. Depoyu klonlayıp
offline testleri doğrudan çalıştırabilirsiniz:

```bash
git clone https://github.com/emribilemir/isbaklibrenms.git
cd isbaklibrenms
python3 -m unittest discover -s librenms-hybrid-poc -p 'test_*.py' -v
```

Offline suite, harici LibreNMS veya Ollama bağlantısı gerektirmez. Backend
adapter testleri yalnızca process içinde açılan localhost test sunucusunu
kullanır.

## Opsiyonel uçtan uca lab kurulumu

Offline testler için Debian, UTM, macOS, LibreNMS veya SNMPSim gerekmez.
Gerçek LibreNMS discovery/poller/API zincirini fiziksel cihaz olmadan denemek
isteyenler opsiyonel lab ortamını kurabilir:

```text
SNMPSim -> LibreNMS discovery/poller -> LibreNMS API -> Hybrid PoC
```

- [Kurulum rehberi](docs/INSTALLATION.md): Debian/Linux hazırlığı, SSH, sudo,
  firewall, native servis kontrolleri ve SNMPSim kurulumu
- [Ayrıntılı lab günlüğü](docs/lab/librenms_native_lab_kurulum_ve_snmpsim_notlari_v2.md):
  doğrulanmış UTM + Debian 13 ARM64 kurulumunun tarihsel adımları ve sorunları

macOS/UTM yalnız doğrulanmış referans ortamdır; zorunlu değildir. Eşdeğer bir
Linux sunucu veya VM ve herhangi bir SSH istemcisi kullanılabilir.

## Yerel Ollama ile PoC harness'i

Yerel `http://localhost:11434` adresinde uygun model çalışıyorsa:

```bash
python3 librenms-hybrid-poc/hybrid_poc.py \
  --model librenms-qwen \
  --cases librenms-hybrid-poc/fixtures/t46_v2_cases.json \
  --temps 0.0 \
  --out /tmp/librenms-hybrid-results.json
```

## Gerçek LibreNMS API ile canlı sorgu

Read-only kullanım için legacy `/api/v0` token'ını environment üzerinden
sağlayın. Gerçek token'ı repoya veya shell history'ye yazmayın.

```bash
export LIBRENMS_TOKEN="<read-only-token>"
export LIBRENMS_BASE_URL="http://<librenms-host>/api/v0"

python3 librenms-hybrid-poc/live_query.py "lab-j9775a-01 açık mı?"
python3 librenms-hybrid-poc/live_query.py "lab-j9772a-01 port 2 ne durumda?"
python3 librenms-hybrid-poc/live_query.py "lab-j9772a-01'de ne sorun var?"
```

`live_query.py`, Gold planner sözleşmesini, resolver v5'i ve gerçek
`LibreNMSBackend` adapter'ını kullanır. İlk cihaz sorgusundan dönen gerçek
LibreNMS `device_id`, sonraki port/alarm/event çağrılarına aktarılır; fixture
kimliği backend gerçeği olarak kullanılmaz.

## Güvenlik ve doğruluk kuralları

- Backend yalnızca read-only endpointlerle sınırlıdır.
- Token environment üzerinden alınır ve sanitize edilmiş trace'e yazılmaz.
- Atomik durum ve utility fact cevapları LLM tarafından yeniden yorumlanmaz.
- Ambiguous referanslarda clarification üretilir; rastgele cihaz seçilmez.
- Eşleşme veya backend verisi yoksa değer tahmin edilmez.
- Device-set status cevapları her hostname için ayrı canlı backend çağrısı yapar.
- Investigation yalnızca alınmış `device + ports + alerts + events` kanıtını
  kullanır.
- Mekanik veya semantic doğrulama başarısızsa generated cevap atılır ve
  deterministik fallback kullanılır.
- Geçersiz planner çıktısı resolver veya backend'e ulaşmaz.

Kaynak Excel yalnızca marka ve model bilgisi sağlar. `lab-<sku>-NN`
hostname'leri, device ID'ler ve operasyonel durumlar synthetic fixture'dır;
gerçek İSBAK operasyon verisi olarak yorumlanmamalıdır.

## Doğrulama durumu

1 Eylül 2026 tarihinde, güncel doğrulama çalışma ağacında:

- offline unittest discovery: **90/90 başarılı**
- resolver fixture self-test: **47/47 başarılı**

Canlı Ollama/LibreNMS acceptance koşuları model, token ve erişilebilir lab
ortamı gerektirdiği için offline suite'in parçası değildir.

## Yerel deney çıktıları

Harness sonuçları, loglar, comparison raporları ve external-judge export'ları
yeniden üretilebilir çalışma çıktılarıdır; Git tarafından izlenmez. Varsayılan
PoC sonucu işletim sisteminin geçici dizinine yazılır. Kalıcı bir deney kanıtı
gerekiyorsa model, runtime ve commit bilgisiyle ayrı bir release artifact'ı
olarak saklanmalıdır.

## Bilinen sınırlar

- Proje production deployment, write operation veya yetkilendirme yönetimi
  içermez.
- RAG uygulanmadı; katalog ve doküman bağlamı için olası B planıdır.
- Generator ve judge aynı Qwen modelini ayrı çağrılarda kullanır; judge bağımsız
  bir doğruluk kaynağı değildir.
- Investigation kalitesi, backend'in sağladığı veri ve event-window coverage'ı
  ile sınırlıdır.
- Kanıtlanmış kök neden yoksa sonuç `root_cause unknown` sınırında kalır.

## Sonraki yön

Öncelik, doğrulanmış hybrid akışı LibreNMS'in native chat deneyimine read-only
olarak bağlamaktır. Bu entegrasyonun sözleşmesi ve güvenlik sınırları
korunduktan sonra planner, backend ve iki aşamalı investigation zincirindeki
latency ölçülüp optimize edilecektir.

## Tasarım belgeleri

- [Semantic planner, deterministic core ve RAG tasarımı](docs/superpowers/specs/2026-08-26-semantic-planner-deterministic-core-rag-design.md)
- [Semantic planner core uygulama planı](docs/superpowers/plans/2026-08-26-semantic-planner-core.md)
- [Planner/catalog/resolver sahiplik incelemesi](docs/history/LIBRENMS_PLANNER_CATALOG_RESOLVER_OWNERSHIP_REVIEW.md)
- [Planner v2 düzeltme raporu](docs/history/PLANNER_V2_FIX_REPORT.md)
