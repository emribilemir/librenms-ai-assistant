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
  "request_type": "atomic_fact | ports | alerts | events | device_set | investigation | historical_investigation | unsupported",
  "intent": "device_status | device_ports | device_alerts | device_events | device_set | investigation | historical_status | unsupported | unknown",
  "device_query": "ham hostname/SKU/model referansı veya null",
  "device_filters": {
    "brand": "string veya null",
    "family": "string veya null",
    "port_count": "integer veya null",
    "poe": "boolean veya null"
  }
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

Atomik durum cevapları deterministik üretilir. Investigation rotası sabit
`get_device + get_ports + get_alerts + get_events` kanıt kümesini Qwen'e verir.

## Dosyalar

| Dosya | Amaç |
|---|---|
| [`hybrid_poc.py`](hybrid_poc.py) | Planner, resolver, backend ve synthesis orchestration |
| [`planner_v2.py`](planner_v2.py) | Structured plan schema ve strict validation |
| [`resolver.py`](resolver.py) | Eski PoC inventory resolver'ı; compatibility ve tarihsel karşılaştırma |
| [`inventory.json`](inventory.json) | PoC inventory fixture'ı |
| [`production_baseline_system.txt`](production_baseline_system.txt) | Tarihsel direct-LLM baseline prompt'u |
| [`test_semantic_planner.py`](test_semantic_planner.py) | Güncel sahiplik sınırı için küçük offline testler |
| [`test_resolver.py`](test_resolver.py) | Eski resolver'ın offline testleri |
| `comparison*.md`, `results*.json` | Daha önceki deney snapshot'ları |

## Hızlı offline test

Repo kökünden:

```bash
python3 librenms-hybrid-poc/test_semantic_planner.py -v
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

## Sınırlar

- Bu klasör gerçek LibreNMS API entegrasyonu yapmaz.
- Device-set cevapları backend çağrısı olmadan canlı durum yazmaz.
- RAG uygulanmadı; B planı olarak ertelendi.
- Son semantic-planner değişikliğinden sonra pahalı LLM/regression suite'leri
  yeniden çalıştırılmadı. Eski result dosyaları güncel sonuç sayılmamalıdır.
