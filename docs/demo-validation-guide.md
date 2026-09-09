# EMR-85/86 demo ve investigation doğrulama rehberi

Demo Kontrolleri yalnız doğrulanmış UTM laboratuvar hedeflerini değiştirir. Web
arayüzü ve CLI aynı `simulation/run.py` yürütücüsünü kullanır; kullanıcıdan
hostname, dosya yolu, OID veya shell komutu kabul edilmez.

## Güvenli hedef seçimi

Backend manifesti 11 SNMPSim fixture'ının tamamı için tek kaynak olarak
kullanılır. Arayüz hedefleri veya destek matrisini ayrıca hardcode etmez:

| Hedef kimliği | Hostname | LibreNMS device_id | Desteklenen senaryolar |
|---|---|---:|---|
| `lab-j9772a-01` | `lab-j9772a-01` | 1 | Altı senaryonun tamamı |
| `lab-j9772a-02` | `lab-j9772a-02` | 2 | Altı senaryonun tamamı |
| `lab-j9775a-01` | `lab-j9775a-01` | 3 | Altı senaryonun tamamı; baseline kapalı |
| `lab-j9775a-02` | `lab-j9775a-02` | 4 | Altı senaryonun tamamı |
| `lab-jl357a-01` | `lab-jl357a-01` | 5 | Altı senaryonun tamamı |
| `lab-j4850a-01` | `lab-j4850a-01` | 6 | Altı senaryonun tamamı |
| `lab-j4850a-02` | `lab-j4850a-02` | 7 | Altı senaryonun tamamı; baseline kapalı |
| `lab-j9774a-01` | `lab-j9774a-01` | 8 | Altı senaryonun tamamı |
| `lab-j9776a-01` | `lab-j9776a-01` | 9 | Altı senaryonun tamamı |
| `lab-j9780a-01` | `lab-j9780a-01` | 10 | Altı senaryonun tamamı; baseline kapalı |
| `lab-j9783a-01` | `lab-j9783a-01` | 11 | Altı senaryonun tamamı |

EMR-86 öncesinde yalnız iki J9772A fixture'ı standart IF-MIB Port 2 kayıtlarını
taşıyor ve yalnız bu iki hedef manifestte `test_port_index/test_port_id` ile
işaretleniyordu. Diğer model fixture'larında port OID'leri yoktu; frontend ise
ek hard-code kullanmadan bu dar backend capability listesini gösteriyordu.

Runner artık her allowlisted hedef için `ifIndex=2`, baseline `admin=up / oper=down`
test-port contract'ını idempotent olarak fixture'a ekler. Model ve sistem OID'leri
korunur; eksik bounded IF-MIB satırları dışında veri değiştirilmez. LibreNMS'nin
discovery sırasında ürettiği `port_id` manifestte sabitlenmez: seçili hedefin
`device_id + ifIndex` eşleşmesinden çalıştırma anında çözülür. Böylece event
doğrulaması başka cihaza veya aynı numaralı başka bir port kimliğine düşmez.

Baseline-down hedefler senaryo süresince mevcut sekiz hedefe eklenen tek bounded
SNMPSim endpoint ile geçici olarak açılır. Reset responder'ı tekrar kalıcı
`devices-up.txt` listesine döndürür ve cihazın intentional down durumunu korur.
Gelecekte gerçekten desteklenemeyen bir hedef eklenirse manifest
`unsupported_scenarios` alanında kısa teknik nedeni taşır; UI bu nedeni butonun
altında gösterir.

## CLI kullanımı

Önce `docs/CODEX_VM_ACCESS.md` sözleşmesini izleyin ve yerel shell'de mevcut
salt-okunur LibreNMS ayarlarını yükleyin. Hedef seçimi `--target` ile allowlist
içinden yapılır:

```bash
python3 simulation/run.py port-down --target lab-j9772a-01
python3 simulation/run.py port-up --target lab-j9772a-01
python3 simulation/run.py location-change --target lab-j9772a-01
python3 simulation/run.py device-down-up --target lab-j9772a-01
python3 simulation/run.py port-down-up-event --target lab-j9772a-01
python3 simulation/run.py investigation-incident --target lab-j9772a-01
python3 simulation/run.py location-change --target lab-j4850a-01
python3 simulation/reset.py --target lab-j4850a-01
```

| Senaryo | Canlı doğrulama | Önerilen soru |
|---|---|---|
| `port-down` | Port 2 `admin=up / oper=down` | `lab-j9772a-01 port 2 ne durumda?` |
| `port-up` | Port 2 `admin=up / oper=up` | `lab-j9772a-01 port 2 ne durumda?` |
| `location-change` | Location `EMR-55 Demo Lab` | `lab-j9772a-01'in location bilgisi ne?` |
| `device-down-up` | Gerçek device down ve up eventleri | `lab-j9772a-01 en son ne zaman down oldu?` |
| `port-down-up-event` | Gerçek Port 2 transition eventi | `lab-j9772a-01 son eventlerini göster` |
| `investigation-incident` | Güncel port sorunu + aktif alarm + tarihsel device geçişi | `lab-j9772a-01 cihazında şu an ne sorun var, son 24 saatte neler olmuş?` |

Yürütücü her senaryodan önce hedef fixture'ını ve SNMP responder'ı çevrimiçi
duruma getirir. Bir senaryo hata verirse yalnız seçili hedef için best-effort
baseline kurtarması çalışır.

## Investigation-ready incident

`investigation-incident` aşağıdaki kanıtları tek akışta hazırlar:

1. Seçili cihazı ve manifestteki test portunu `up/up` durumunda poll eder.
2. Fixture'ı geçici olarak çevrimdışı/çevrimiçi yaparak gerçek LibreNMS device
   down ve up eventleri üretir.
3. Port 2'yi `admin=up / oper=down` durumuna getirir ve gerçek interface eventini
   doğrular.
4. Seçili cihaz için tanımlı gerçek aktif alarmı varsa proof listesine ekler;
   yoksa alarm kontrolünü açıkça `unavailable` gösterir.

Olay doğrulaması test portunu manifestteki SNMP `ifIndex` ile seçer, ardından
seçili cihaz için API'den dönen gerçek LibreNMS `port_id` değerini kullanır.
Bu kimlik discovery'ye bağlı olduğundan hard-code edilmez.

Önerilen soru normal sohbet akışını tam bir kez kullanır. Sonuç doğrulaması yanıt
metnini, gizli reasoning'i veya ikinci bir LLM judge'ı kullanmaz. Tamamlanan
yanıtın inspection metadata'sında şu alanları deterministik olarak kontrol eder:

- hedef `hostname` ve `device_id`;
- `investigation` route'u;
- `get_device`, `get_ports`, `get_alerts`, `get_events` araçları;
- güncel cihaz, `admin up / oper down` port, varsa aktif alarm ve tarihsel durum
  geçişi finding tipleri;
- senaryonun ürettiği gerçek device down/up event kimlikleri;
- restricted synthesis çağrısı.

## Dev-only web kontrolleri

Servis yalnız `AI_DEMO_MODE_ALLOWED=1` olduğunda demo endpoint'lerini kaydeder.
Kullanıcı ayrıca header'daki `Demo Modu` anahtarını etkinleştirir. Türkçe
`Demo Kontrolleri` sağ drawer'ı hedef seçiciyi, kompakt doğrudan aksiyonları,
seçili hedefte desteklenmeyen aksiyonların nedenini, son işlem özetini,
`Bu durumu AI'a sor` CTA'sını ve ayrı reset aksiyonunu gösterir. Drawer açıkken
sohbet alanı daralır; kapalıyken yalnız ince bir sağ kenar tutamacı kalır.

Web API yalnız şu bounded payload'ları kabul eder:

```json
{"scenario_id":"investigation-incident","target_id":"lab-j9772a-01"}
```

```json
{"target_id":"lab-j9772a-01"}
```

Fazladan alanlar, raw hostname/path/OID değerleri ve allowlist dışı kimlikler
reddedilir.

## Reset

Her demo sonunda drawer'daki `Laboratuvarı sıfırla` aksiyonunu veya CLI'ı
kullanın:

```bash
python3 simulation/reset.py
python3 simulation/reset.py --target lab-j9775a-01
```

Doğrulanmış baseline hedefe bağlıdır:

```text
8 hedef: device status=up
3 hedef: device status=down
location=Test Lab
tüm hedeflerde test Port 2: ifAdminStatus=up, ifOperStatus=down
```

Reset offline fixture adını geri getirir, gerekirse responder'ı tek instance
olarak başlatır, exact OID değerlerini düzeltir, discovery ve poller çalıştırır
ve sonucu gerçek LibreNMS API verisiyle doğrular.

## Son canlı kabul

9 Eylül 2026 tarihinde Codex in-app browser ile masaüstü UTM kabulü yenilendi.
J9772A dışındaki JL357A, J4850A ve J9774A model ailelerinde port mutasyonları,
gerçek interface eventleri, investigation akışları ve reset zinciri geçti.
Baseline-kapalı `lab-j9775a-01` senaryo sırasında geçici olarak açıldı ve reset
sonunda başlangıçtaki down durumuna döndü. Arayüzde J4850A port olayı üretildi;
normal AI sohbeti yeni `#393`–`#395` interface eventlerini gösterdi ve hedef UI
üzerinden tekrar baseline'a sıfırlandı. Ayrıntılar
[`acceptance/2026-09-09-emr-86-live-acceptance.md`](acceptance/2026-09-09-emr-86-live-acceptance.md)
dosyasındadır.
