# Simulation Lab contracts

Bu dizin, EMR-55 Simulation Lab'in güvenlik sınırını, senaryo kaynağını ve
EMR-59 kapsamında hazırlanmış kısıtlı VM runner paketini tanımlar. Runner
depolanmış ve offline doğrulanmıştır; UTM'ye kurulması/aktive edilmesi EMR-63
canlı kabul adımına kadar yapılmaz.

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
reddeder. Hash, doğrulanmış kayıtlardan bir kez üretilen immutable canonical JSON
bytes üzerinden hesaplandığı için dosya formatından ve key sırasından bağımsızdır.
Duplicate JSON key ve `NaN`/`Infinity` sabitleri parse aşamasında reddedilir.

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

Her `transition`, `failed` ve `recovery_required` çağrısı `known_scenario_ids`
olarak yüklenmiş manifestteki canonical ID kümesini alır. Yeni veya persisted
bir state bu kümede olmayan senaryoya referans verirse fail-closed davranır.

`baseline + reset` ve her state'teki `status` güvenli no-op'tur. `reset`, aktif
senaryo ve son hata bilgisini temizler. Hata state'i istemci action'ı değildir;
yalnız `failed()` ve `recovery_required()` yardımcıları tarafından üretilir.

API/runner tüketicileri şu stabil kodları korur:

- `scenario_already_applied`: aynı senaryoya ikinci apply;
- `reset_required`: reset yapılmadan başka senaryoya geçiş;
- `manual_recovery_required`: otomatik baseline dönüşü tamamlanamadı;
- `invalid_transition`: lifecycle sırası geçersiz;
- `invalid_scenario_id`: eksik veya biçimi geçersiz kimlik;
- `unknown_scenario`: canonical manifestte bulunmayan kimlik;
- `invalid_error_code`: kararsız/free-form hata kodu.

## Kısıtlı VM runner

`runner/` içindeki servis yalnız şu public işlemleri kabul eder:

- `apply`, `poll`, `observe`, `reset`: canonical manifestte bulunan bir
  `scenario_id` ile;
- `status`, `recover`: ayrı control mesajı olarak.

İstek en fazla 4096 byte tek JSON nesnesidir. Her istekte canonical manifest
SHA bulunur. Browser/Mac API tarafından executable, shell, path, IP, hostname,
OID, SNMP tipi veya mutation değeri gönderilemez. Bunların tamamı doğrulanmış
manifest, semantic katalog ve sabit VM layout'undan türetilir.

Her işlem global nonblocking lock alır. Fixture ve membership dosyaları sibling
temporary file + `fsync` + atomic replace ile yazılır. Subprocess çağrıları tam
argv allowlist'i, `shell=False`, process-group timeout/termination ve bounded
temporary output kullanır. Raw stderr veya exception metni transporta çıkmaz.

Apply sonrası SNMP doğrulaması başarısızsa captured baseline otomatik geri
yüklenir. Restore, service health veya baseline reachability kanıtlanamazsa
persisted state `manual_recovery_required` olur; yeni mutationlar yalnız
`recover` başarıyla bitince açılır.

Forced SSH hattının sonucu JSONL'dir. Exit kodları:

| Kod | Anlam |
|---|---|
| `0` | Başarılı işlem/control |
| `2` | Geçersiz istek, conflict veya retry edilmemesi gereken hata |
| `3` | Retry edilebilir runtime/transport hatası |
| `4` | Elle recovery gereken baseline problemi |

## Paketleme ve canlı kurulum sınırı

`packaging/install-runner.sh` yalnız sabit hedeflere runner kopyalar, önceki
managed dosyaları yedekler, dedicated `librenms-ai-lab` hesabının forced key ve
tek-command sudo kuralını kurar ve baseline'ı capture eder. Çalışan legacy
SNMPSIM sürecini durdurmaz; unit'i enable/start etmez.

Canlı EMR-63 rollout sırası aşağıdaki gibidir. Buradaki komutlar ancak VM
değişikliği açıkça onaylandığında kullanılmalıdır:

```bash
# Repo VM'de erişilebilir bir staging dizinindeyken, yalnız public key verilir.
sudo bash simulation/packaging/install-runner.sh /absolute/path/lab-runner.pub

# Installer başarılı olduktan sonra explicit handoff.
sudo /opt/librenms-ai-lab/runner/simulation/packaging/activate-runner.sh

# Unit, sudoers, sshd, SHA, ownership, service ve runner state kontrolü.
sudo /opt/librenms-ai-lab/runner/simulation/packaging/verify-runner.sh
```

Shared secret, LibreNMS API tokenı, private SSH key veya model credential bu
paketin girdisi değildir. Public key tek satırlık `ssh-ed25519` dosyası olarak
verilir ve repoya eklenmez.

Rollback, captured fixture/membership baseline'ını geri yükler, managed unit'i
disable eder ve önceki sabit launcher'ı yeniden başlatır:

```bash
sudo /opt/librenms-ai-lab/runner/simulation/packaging/rollback-runner.sh
```

Managed yüzeyler `/opt/librenms-ai-lab`, `/var/lib/librenms-ai-lab`,
`/opt/snmpsim-lab`, `/etc/systemd/system/snmpsim-lab.service`, tek sudoers
dosyası ve dedicated hesabın `authorized_keys` dosyasıyla sınırlıdır.
`/opt/librenms` kaynak ağacına yazılmaz; yalnız manifestteki hostname ile
LibreNMS discovery/poller entrypointleri çağrılabilir.

## Test

```bash
python3 -m unittest discover -s simulation/tests -p 'test_*.py' -v
```

Bu testler VM'ye, LibreNMS'e, Ollama'ya veya ağa bağlanmaz. Paket shell
dosyalarının syntax'ı ayrıca şöyle doğrulanır:

```bash
bash -n simulation/packaging/*.sh
```

`systemd-analyze verify`, `sshd -t`, canlı service/reachability ve otomatik
legacy rollback kontrolleri Debian VM'deki EMR-63 kabul adımına aittir.
