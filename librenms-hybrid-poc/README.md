# LibreNMS Hybrid PoC

Bu klasör, doğal dil sorgusunu read-only LibreNMS operasyonlarına bağlayan
hybrid orchestration PoC'sini içerir. Production entegrasyonu değildir; yerel
Ollama modeli ve fixture inventory ile mimari sınırı ölçer.

## Güncel akış

```text
Kullanıcı sorgusu
  -> Qwen semantic planner
  -> strict structured-plan validation
  -> resolver v5
  -> read-only backend
  -> deterministik doğrudan cevap veya bounded investigation synthesis
```

### Qwen'in sorumluluğu

Qwen doğal dili aşağıdaki alanlara dönüştürür:

```json
{
  "request_type": "atomic_fact | ports | alerts | events | device_set | device_set_status | investigation | historical_investigation | unsupported",
  "intent": "device_status | device_ports | device_alerts | device_events | device_set | device_set_status | investigation | historical_status | unsupported | unknown",
  "device_query": "ham hostname/SKU/model referansı veya null",
  "device_filters": {
    "brand": "string veya null",
    "family": "string veya null",
    "port_count": "integer veya null",
    "poe": "boolean veya null"
  },
  "event_window": "investigation rotalarında default_24h | relative | absolute"
}
```

Qwen cihaz seçmez ve operasyonel durum iddia etmez.

### Python'ın sorumluluğu

[`planner_v2.py`](planner_v2.py) doğal dil ayrıştırmaz. Yalnızca:

- gerekli alanları,
- enum ve tipleri,
- route–intent uyumunu,
- device-set filtre sözleşmesini,
- gerekli explicit device referansını

doğrular. Geçersiz plan resolver veya backend'e gönderilmez.

### Resolver ve backend

Resolver v5 açık hostname/SKU/model referanslarını ve structured katalog
filtrelerini çözer. Ambiguous sonuçlarda tek cihaz seçmez. Backend status,
port, alarm ve event gerçeklerinin tek kaynağıdır.

Atomik durum cevapları deterministik üretilir. Investigation rotası raw backend
JSON'unu Qwen'e vermez. Backend verisi önce `investigation_grounding.py`
tarafından stable evidence ref'leri taşıyan typed findings'e çevrilir. Qwen bu
paketten doğal Türkçe claim'ler üretir; ayrı bir Qwen judge bütün claim'leri
bağlı findings karşısında doğrular. Mekanik veya semantic doğrulama geçmezse
reddedilen metin gösterilmez ve doğrulanmış bulgu listesine dönülür.

Current investigation varsayılan olarak son 24 saatin eventlerini alır.
Relative veya absolute zaman ifadelerinde doğrulanmış `from/to` değerleri
LibreNMS eventlog API'sine gönderilir. Direct `status/ports/alerts/events`
rotaları synthesis ve judge çağırmaz.

`device_set_status` rotasında resolver yalnız hostname setini üretir.
Orchestrator her hostname için ayrı `get_device(hostname=...)` çağrısı yapar;
gerçek backend `device_id` ve `status` değerlerini kullanarak UP/DOWN gruplarını
deterministik özetler. Fixture status ve synthetic device ID backend gerçeği
olarak kullanılmaz.

## Dosyalar

| Dosya | Amaç |
|---|---|
| [`hybrid_poc.py`](hybrid_poc.py) | Planner, resolver, backend ve synthesis orchestration |
| [`librenms_backend.py`](librenms_backend.py) | Gerçek read-only LibreNMS `/api/v0` backend adapter'ı |
| [`live_query.py`](live_query.py) | Gold planner + resolver v5 + gerçek LibreNMS backend canlı giriş noktası |
| [`planner_v2.py`](planner_v2.py) | Structured plan schema ve strict validation |
| [`investigation_grounding.py`](investigation_grounding.py) | Deterministic finding builder, claim/judge kontratları ve güvenli fallback |
| [`resolver.py`](resolver.py) | Eski PoC inventory resolver'ı; compatibility ve tarihsel karşılaştırma |
| [`inventory.json`](inventory.json) | PoC inventory fixture'ı |
| [`production_baseline_system.txt`](production_baseline_system.txt) | Tarihsel direct-LLM baseline prompt'u |
| [`test_semantic_planner.py`](test_semantic_planner.py) | Güncel sahiplik sınırı için küçük offline testler |
| [`test_live_backend.py`](test_live_backend.py) | API adapter ve gerçek backend `device_id` handoff regression testleri |
| [`test_investigation_grounding.py`](test_investigation_grounding.py) | Finding, zaman penceresi, event parser ve truncation testleri |
| [`test_grounded_synthesis.py`](test_grounded_synthesis.py) | Generator, judge, fallback ve route isolation testleri |
| [`test_resolver.py`](test_resolver.py) | Eski resolver'ın offline testleri |
| `comparison*.md`, `results*.json` | Daha önceki deney snapshot'ları |

## Hızlı offline test

Repo kökünden:

```bash
python3 -m unittest discover -s librenms-hybrid-poc -p 'test_*.py' -v
```

Bu testler Ollama veya ağ kullanmaz.

## Yerel Ollama ile PoC

```bash
python3 librenms-hybrid-poc/hybrid_poc.py \
  --model librenms-qwen \
  --cases librenms-hybrid-poc/t46_v2_cases.json \
  --temps 0.0 \
  --out /tmp/librenms-hybrid-results.json
```

Varsayılan Ollama endpoint'i `http://localhost:11434`, planner ve synthesis için
`think=false` kullanılır.

## Gerçek LibreNMS API ile canlı sorgu

Mac Terminal'de legacy `/api/v0` token'ını process environment'a aktar:

```bash
export LIBRENMS_TOKEN
export LIBRENMS_BASE_URL="http://192.168.64.3/api/v0"
```

Ardından:

```bash
python3 librenms-hybrid-poc/live_query.py "lab-j9775a-01 açık mı?"
python3 librenms-hybrid-poc/live_query.py "J4850A cihazları açık mı?"
```

`live_query.py` explicit olarak `planner_schema="gold"`,
`resolver_candidate_v5.py` ve `LibreNMSBackend` kullanır. Resolver yalnızca
kimlik/katalog çözümü yapar. İlk `get_device(hostname=...)` çağrısından dönen
gerçek LibreNMS `device_id`, sonraki ports/alerts/events çağrılarının kimliği
olur; fixture `device_id` backend truth olarak kullanılmaz.

Offline adapter testi:

```bash
cd librenms-hybrid-poc
python3 -m unittest -v test_semantic_planner.py test_live_backend.py
```

## Sınırlar

- Gerçek LibreNMS entegrasyonu read-only `/api/v0` adapter ile vardır; write endpointleri kullanılmaz.
- Device-set cevapları backend çağrısı olmadan canlı durum yazmaz.
- RAG uygulanmadı; B planı olarak ertelendi.
- EMR-45 doğrulamasında Gold 40/40, Generated 16/16 ve Legacy 55/56 baseline
  korundu. Legacy'deki tek hata önceden bilinen T46 conciseness vakasıdır.
- Canlı LibreNMS acceptance koşusu için `LIBRENMS_TOKEN` ve erişilebilir VM
  gerekir; token yoksa offline backend sözleşme testleri kullanılmalıdır.
