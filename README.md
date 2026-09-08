# LibreNMS AI Assistant — Natural-Language Hybrid PoC

LibreNMS verilerine doğal dille, güvenli ve doğrulanabilir biçimde erişmenin
uygulanabilirliğini araştıran read-only bir proof of concept.

Proje; yerel Qwen modeliyle doğal dil planlama, deterministik cihaz çözümleme,
LibreNMS `/api/v0` sorguları, native LibreNMS eklentisi ve kanıta dayalı cevap
üretimi arasındaki sınırları test eder. Tüm LibreNMS erişimi read-only kalır.

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

## Native Assistant UI

PoC yalnızca bir CLI değildir. [`chat-ui/`](chat-ui/) altında React 19, Vite 8
ve [assistant-ui](https://www.assistant-ui.com/) primitive'leriyle geliştirilen
chat deneyimi, [`integrations/librenms/AiAssistant/`](integrations/librenms/AiAssistant/)
üzerinden LibreNMS'in kendi oturum ve sayfa kabuğuna gömülür.

Arayüzde bugün çalışan başlıca özellikler:

- LibreNMS oturumundan imzalı kullanıcı kimliğiyle açılan native eklenti sayfası
- Kalıcı sohbet geçmişi, arama, yeni sohbet ve güvenli silme akışı
- Streaming yanıt, iptal/tekrar deneme ve aynı sohbette sıralı mesaj kuyruğu
- Canlı envanterden cihaz seçici ve sorguya hazır başlangıç önerileri
- Cihaz ve port sonuçları için okunabilir tablolar; alarm sonuçları için özet kartlar
- Event sorguları için zaman, önem seviyesi, mesaj ve `up -> down` geçişlerini
  ayıran kompakt timeline
- Doğrulanmış `device`, `port`, `alerts` ve `events` LibreNMS deep-link'leri
- Investigation sırasında planner, resolver, tool ve finding aşamalarını gösteren
  işlem durumu; Demo Modu'nda ayrıntılı inspector
- Allowlist'teki birden fazla hedefi seçebilen Demo Kontrolleri; senaryo çalıştırma,
  seçili hedefi resetleme ve sonucu doğrudan **Sormayı dene** kartına taşıma
- Klavye odağı, erişilebilir isimler, boş/tek event durumları ve güvenli hata halleri

```text
LibreNMS plugin page
        |
        v
React + assistant-ui ExternalStoreRuntime
        |
        v
Signed /v1 chat API + SSE
        |
        v
Hybrid planner / resolver / read-only LibreNMS backend
```

Normal sohbet ve LibreNMS okumaları salt okunurdur. Lab fixture'larını değiştiren
Demo Kontrolleri ayrıca `AI_DEMO_MODE_ALLOWED=1` ve imzalı `demo_control`
capability'si ister; yalnız `AI_DEV_AUTH=1` deployed uygulamada bu yetkiyi açmaz.

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
| [`chat-ui/`](chat-ui/) | React + assistant-ui tabanlı native sohbet, structured sonuçlar ve demo arayüzü |
| [`integrations/librenms/AiAssistant/`](integrations/librenms/AiAssistant/) | LibreNMS plugin sayfası, imzalı identity köprüsü ve dağıtım sözleşmesi |
| [`librenms-hybrid-poc/`](librenms-hybrid-poc/) | Güncel planner, orchestration ve backend adapter giriş noktaları |
| [`librenms-hybrid-poc/tests/`](librenms-hybrid-poc/tests/) | Hybrid, chat, güvenlik ve ops offline regression suite'i |
| [`librenms-hybrid-poc/fixtures/`](librenms-hybrid-poc/fixtures/) | PoC inventory, prompt ve acceptance girdileri |
| [`librenms-hybrid-poc/hybrid-gold-v3/`](librenms-hybrid-poc/hybrid-gold-v3/) | Dondurulmuş Gold/Generated değerlendirme varlıkları ve uyumluluk girişleri |
| [`simulation/`](simulation/) | Allowlist tabanlı, hedef-seçilebilir demo senaryoları |
| [`scripts/`](scripts/) | Tek komutluk lab başlatma, sağlık ve kapatma girişleri |
| [`ops/systemd/`](ops/systemd/) | Guest içinde unprivileged, boot-persistent SNMPSim servisi |
| [`docs/history/`](docs/history/) | Tarihsel inceleme ve düzeltme raporları |
| [`docs/INSTALLATION.md`](docs/INSTALLATION.md) | Opsiyonel Debian, SSH, sudo ve SNMPSim kurulum rehberi |
| [`docs/lab/`](docs/lab/) | Ayrıntılı tarihsel LibreNMS ve SNMPSim lab notları |

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
- [`resolver_v5.py`](librenms-hybrid-poc/resolver_v5.py): aktif structured katalog
  filtreleme ve identity resolution
- [`catalog_ingest.py`](librenms-hybrid-poc/catalog_ingest.py): aktif katalog ingest
  ve identity index yardımcısı
- [`emr52_acceptance_queries.json`](librenms-hybrid-poc/fixtures/emr52_acceptance_queries.json):
  güncel canlı acceptance sorguları

## Hızlı başlangıç

Chat servisi test bağımlılıklarını kurduktan sonra offline suite'i çalıştırın:

```bash
git clone https://github.com/emribilemir/isbaklibrenms.git
cd isbaklibrenms
python3 -m venv .venv
.venv/bin/python -m pip install -r librenms-hybrid-poc/requirements-chat-service.txt
.venv/bin/python -m unittest discover -s librenms-hybrid-poc -p 'test_*.py' -v
```

Offline suite, harici LibreNMS veya Ollama bağlantısı gerektirmez. Backend
adapter testleri yalnızca process içinde açılan localhost test sunucusunu
kullanır.

Assistant UI test ve production build'i:

```bash
cd chat-ui
npm ci
npm test -- --runInBand
npm run build
```

Build çıktısı `chat-ui/dist/` altında oluşur ve native eklentinin yüklediği
statik asset'lere dağıtılır. Ayrıntılı eklenti adımları için
[`integrations/librenms/AiAssistant/docs/deployment.md`](integrations/librenms/AiAssistant/docs/deployment.md)
dosyasına bakın.

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

Lab yapılandırması makineye özeldir ve repoya girmez. Önce `.env.example`
dosyasını `.env` olarak kopyalayıp SSH, LibreNMS ve backend alanlarını doldurun.
Ardından canonical yaşam döngüsünü kullanın:

```bash
./scripts/lab-up
./scripts/lab-status
./scripts/lab-down
```

`lab-up`, isteğe bağlı UTM başlatma, bounded SSH bekleme, LibreNMS servisleri,
boot-persistent SNMPSim ve launchd backend kurulumunu birlikte yürütür.
`lab-status`; servisleri, tek unprivileged responder sürecini, 8 up / 3 down
baseline envanterini, LibreNMS API/web ve backend health endpointini doğrular.
SQLite çalışma verisi varsayılan olarak kullanıcının state dizininde tutulur.
Demo mutation endpointleri yalnız imzalı `demo_control` capability'sine sahip
operator kimliğine açıktır; global-read kullanıcıların normal sohbet erişimi
değişmez.

### Kısa sunum akışı

1. `./scripts/lab-status` ile servisler ve `8 up / 3 down` baseline'ını gösterin.
2. LibreNMS içindeki **AI Assistant** sayfasında model/durum sorgusu çalıştırın.
3. Down port, aktif alarm ve son event sorgularındaki structured sonuçları açın.
4. Bir investigation çalıştırıp işlem aşamalarını ve doğrulanmış deep-link'leri gösterin.
5. Yetkili Demo Modu'nda ikinci hedefi seçin; bir senaryo çalıştırın, **Sormayı dene**
   kartını kullanın ve aynı seçili hedefi **Laboratuvarı sıfırla** ile baseline'a döndürün.

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

`live_query.py`, Gold planner sözleşmesini, runtime `resolver_v5`'i ve gerçek
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

## Doğrulama

CI her push ve pull request'te tam offline Python suite'ini, frontend unit
testlerini, production build'i, LibreNMS plugin contract testlerini ve dar bir
secret-pattern kontrolünü çalıştırır. Canlı UTM kabulü ise yalnız Codex in-app
browser ile, `lab-status` yeşil olduktan sonra yürütülür.

EMR-82 tesliminde doğrulanan mevcut kapsam: **196 Python testi**, **98 Assistant
UI testi**, **9 LibreNMS plugin contract testi** ve başarılı Vite production
build. Canlı kabulde iki allowlist hedefi, ikinci hedefte senaryo/reset akışı,
structured event timeline ve `8 up / 3 down` lab baseline'ı doğrulandı.

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

- [Planner/catalog/resolver sahiplik incelemesi](docs/history/LIBRENMS_PLANNER_CATALOG_RESOLVER_OWNERSHIP_REVIEW.md)
- [Planner v2 düzeltme raporu](docs/history/PLANNER_V2_FIX_REPORT.md)

## Arayüz kaynağı

Chat yüzeyi [assistant-ui](https://www.assistant-ui.com/) primitive'leri üzerine
kuruludur; LibreNMS'e özgü veri güvenliği, görsel dil ve kontroller bu depoda
uygulanır.
