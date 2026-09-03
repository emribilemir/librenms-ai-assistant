# Simulation Lab contracts

Bu dizin, EMR-55 Simulation Lab'in güvenlik sınırını ve senaryo kaynağını
tanımlar. EMR-58 kapsamında VM runner, HTTP API ve React arayüzü içermez.

## Tek kaynak

`scenarios.json`, hedefler ve on tekrar edilebilir senaryo için tek kaynaktır.
Dosya doğrudan runner veya tarayıcı tarafından parse edilmez. Bütün tüketiciler
aynı doğrulayıcıyı kullanır:

```python
from pathlib import Path
from simulation import load_manifest, manifest_sha256, public_manifest

manifest = load_manifest(Path("simulation/scenarios.json"))
deployment_identity = manifest_sha256(manifest)
browser_safe_payload = public_manifest(manifest)
```

`load_manifest` bilinmeyen alanları, serbest OID'leri, path/command girdilerini,
shell sözdizimini, tanımsız semantic değerleri ve resetsiz senaryoları fail-closed
reddeder. Hash, doğrulanmış canonical JSON üzerinden hesaplandığı için dosya
formatından ve key sırasından bağımsızdır.

## Privileged ve public sınırı

EMR-59 runner'ı `Manifest`, `Target` ve `Scenario` immutable kayıtlarını kullanır.
Agent adresi, portu, fixture kimliği, mutation değerleri, exact OID ve reset
ayrıntıları bu privileged tarafta kalır.

EMR-60 API açılışta local ve deployed canonical SHA değerlerini karşılaştırır.
Uyuşmazlıkta mutation kapalı kalır. Tarayıcıya yalnız `public_manifest` sonucu
verilir; UI kaynak JSON'u doğrudan okumaz.

`catalog.py`, desteklenen SNMP semantic adlarını exact OID ve tipe bağlayan kapalı
allowlist'tir. `endpointReachable` sanal bir kontroldür: boolean değer kabul eder
ama OID'ye çözümlenemez ve SNMPREC dosyasına yazılmaz.

## Lifecycle

| Mevcut state | Action | Sonraki state |
|---|---|---|
| `baseline` | `apply` | `applied` |
| `reset` | `apply` | `applied` |
| `applied` | `poll` | `polled` |
| `baseline`, `applied`, `polled` | `observe` | `observed` |
| `observed` | `ai_check` | `ai_verified` |
| `applied`, `polled`, `observed`, `ai_verified`, `failed` | `reset` | `reset` |
| `manual_recovery_required` | `recover` | `reset` |

`baseline + reset` ve her state'teki `status` güvenli no-op'tur. `reset`, aktif
senaryo ve son hata bilgisini temizler. Hata state'i istemci action'ı değildir;
yalnız `failed()` ve `recovery_required()` yardımcıları tarafından üretilir.

API/runner tüketicileri şu stabil kodları korur:

- `scenario_already_applied`: aynı senaryoya ikinci apply;
- `reset_required`: reset yapılmadan başka senaryoya geçiş;
- `manual_recovery_required`: otomatik baseline dönüşü tamamlanamadı;
- `invalid_transition`: lifecycle sırası geçersiz;
- `invalid_scenario_id`: eksik veya biçimi geçersiz kimlik;
- `invalid_error_code`: kararsız/free-form hata kodu.

## Test

```bash
python3 -m unittest discover -s simulation/tests -p 'test_*.py' -v
```

Bu testler VM'ye, LibreNMS'e, Ollama'ya veya ağa bağlanmaz.
