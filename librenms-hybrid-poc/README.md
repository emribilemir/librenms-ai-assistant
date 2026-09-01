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
  -> direct rotalarda deterministik cevap
  -> investigation rotalarında deterministic evidence builder
  -> structured findings
  -> Qwen claim generation
  -> mechanical validation
  -> Qwen judge
  -> doğrulanmış cevap veya deterministic fallback
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
  "port_query": "yalnız ports rotasında explicit port/interface kimliği veya null",
  "port_filters": {
    "admin_status": "up | down | null",
    "oper_status": "up | down | null"
  },
  "event_window": {
    "mode": "investigation rotalarında default_24h | relative | absolute"
  }
}
```

`port_query` ve `port_filters` yalnız `ports / device_ports` planlarında
kullanılır. `event_window` yalnız investigation planlarında kullanılır. Bu iki
contract birbirinin yerine geçmez ve aynı planner şemasında yan yana yaşar.
Qwen cihaz seçmez ve backend kanıtı olmadan operasyonel durum iddia etmez.

Event-window şekilleri tam olarak `{"mode":"default_24h"}`,
`{"mode":"relative","amount":N,"unit":"hour|day|week"}` veya
`{"mode":"absolute","from":"ISO date/datetime","to":"ISO date/datetime"}`
olur. Relative zamanı Qwen hesaplamaz; Python request time'a sabitler.

### Python'ın sorumluluğu

[`planner_v2.py`](planner_v2.py) doğal dil ayrıştırmaz. Yalnızca:

- gerekli alanları,
- enum ve tipleri,
- route–intent uyumunu,
- device-set filtre sözleşmesini,
- port kimliği ile admin/oper filtre sözleşmesini,
- investigation event-window sözleşmesini,
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

`ports` rotasında Qwen yalnız structured port constraint üretir; Python kullanıcı
dilini yeniden parse etmez. `_select_ports()` backend'den gelen portları
`ifName`, `ifIndex` veya `ifDescr` üzerinden explicit `port_query` ile ve
`ifAdminStatus`/`ifOperStatus` üzerinden structured filtrelerle deterministik
seçer. Semantics şöyledir:

- `port 2` yalnız explicit Port 2'yi seçer.
- `down portlar` `oper_status="down"` demektir.
- `aktif ama bağlantısı düşmüş` `admin_status="up"` ve
  `oper_status="down"` demektir.
- `disabled` `admin_status="down"` demektir.

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
| [`fixtures/`](fixtures/) | PoC inventory, baseline prompt ve acceptance girdileri |
| [`tests/`](tests/) | Planner, resolver, backend, grounding ve utility regression testleri |
| [`hybrid-gold-v3/`](hybrid-gold-v3/) | Aktif Gold/Generated acceptance bundle ve resolver v5 |

## Hızlı offline test

Repo kökünden:

```bash
python3 -m unittest discover -s librenms-hybrid-poc -p 'test_*.py' -v
```

Bu testler gerçek Ollama veya harici LibreNMS ağı kullanmaz. Backend adapter
testleri yalnız process içindeki localhost test sunucusunu kullanır.

Güncel full discovery sonucu `90/90`, resolver'ın kendi fixture koşusu ise
`PASS=47 FAIL=0` olarak geçmiştir. Odaklı gruplar:

```bash
cd librenms-hybrid-poc
python3 -m unittest -v tests.test_port_selection
python3 -m unittest -v \
  tests.test_investigation_grounding \
  tests.test_grounded_synthesis
python3 -m unittest -v \
  tests.test_semantic_planner \
  tests.test_live_backend
```

## Yerel Ollama ile PoC

```bash
python3 librenms-hybrid-poc/hybrid_poc.py \
  --model librenms-qwen \
  --cases librenms-hybrid-poc/fixtures/t46_v2_cases.json \
  --temps 0.0 \
  --out /tmp/librenms-hybrid-results.json
```

Varsayılan Ollama endpoint'i `http://localhost:11434`, planner ve synthesis için
`think=false` kullanılır. `--out` verilmezse sonuç sistemin geçici dizinine
yazılır; sonuç, log ve external-judge export'ları repoda takip edilmez.

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
python3 librenms-hybrid-poc/live_query.py "lab-j9772a-01 port 2 ne durumda?"
python3 librenms-hybrid-poc/live_query.py "lab-j9772a-01'in down portları hangileri?"
python3 librenms-hybrid-poc/live_query.py "lab-j9772a-01 aktif ama bağlantısı düşmüş portları hangileri?"
python3 librenms-hybrid-poc/live_query.py "lab-j9772a-01'de ne sorun var?"
```

`live_query.py` explicit olarak `planner_schema="gold"`,
`resolver_candidate_v5.py` ve `LibreNMSBackend` kullanır. Resolver yalnızca
kimlik/katalog çözümü yapar. İlk `get_device(hostname=...)` çağrısından dönen
gerçek LibreNMS `device_id`, sonraki ports/alerts/events çağrılarının kimliği
olur; fixture `device_id` backend truth olarak kullanılmaz.

Son investigation sorgusunda kabul sınırı, yalnız structured findings tarafından
desteklenen Port 2, aktif alarmlar ve event-window içindeki geçmiş status
transition'larının aktarılmasıdır. Kanıttan çıkmayan neden üretilmemeli;
kanıtlanmış kök neden yoksa cevap `root_cause unknown` sınırında kalmalıdır.

## Sınırlar

- Gerçek LibreNMS entegrasyonu read-only `/api/v0` adapter ile vardır; write endpointleri kullanılmaz.
- Device-set cevapları backend çağrısı olmadan canlı durum yazmaz.
- RAG uygulanmadı; B planı olarak ertelendi.
- Generator ve judge şu anda aynı Qwen modelini iki ayrı çağrıda kullanır. Judge
  ek güvenlik katmanıdır, bağımsız bir model değildir ve investigation latency'sine
  ikinci bir LLM çağrısı ekler.
- Mechanical validation veya judge şüphesinde generated metin tamamen atılır;
  Python doğrulanmış findings üzerinden deterministic fallback üretir.
- EMR-45 doğrulamasında Gold 40/40, Generated 16/16 ve Legacy 55/56 baseline
  korundu. Legacy'deki tek hata önceden bilinen T46 conciseness vakasıdır.
- EMR-46 port semantics, EMR-49 grounding ve `event_window` contract'ı ile
  merge-safe biçimde korunur.
- Canlı LibreNMS acceptance koşusu için `LIBRENMS_TOKEN` ve erişilebilir VM
  ile çalışan Ollama gerekir; bunlar yoksa offline backend sözleşme testleri
  kullanılmalıdır.
