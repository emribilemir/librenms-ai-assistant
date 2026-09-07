# EMR-77 demo ve investigation doğrulama rehberi

Demo Kontrolleri yalnız doğrulanmış UTM laboratuvar hedeflerini değiştirir. Web
arayüzü ve CLI aynı `simulation/run.py` yürütücüsünü kullanır; kullanıcıdan
hostname, dosya yolu, OID veya shell komutu kabul edilmez.

## Güvenli hedef seçimi

Üretim allowlist'i şu anda yalnız fixture sahipliği, yazma yetkisi ve Port 2
OID'leri canlı ortamda doğrulanmış hedefi içerir:

| Hedef kimliği | Hostname | LibreNMS device_id | Desteklenen senaryolar |
|---|---|---:|---|
| `lab-j9772a-01` | `lab-j9772a-01` | 1 | Altı senaryonun tamamı |

Inventory'de bulunan fakat fixture'ı güvenli biçimde değiştirilemeyen cihazlar
seçicide gösterilmez. Yeni hedef eklemek için fixture sahipliği/yazma yetkisi,
gerekli OID'ler, SNMP endpoint'i ve LibreNMS `device_id` eşleşmesi birlikte
doğrulanmalıdır.

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

1. Cihazı ve Port 2'yi `up/up` durumunda poll eder.
2. Fixture'ı geçici olarak çevrimdışı/çevrimiçi yaparak gerçek LibreNMS device
   down ve up eventleri üretir.
3. Port 2'yi `admin=up / oper=down` durumuna getirir ve gerçek interface eventini
   doğrular.
4. Seçili cihaz için tanımlı gerçek aktif alarmı varsa proof listesine ekler;
   yoksa alarm kontrolünü açıkça `unavailable` gösterir.

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
`Demo Kontrolleri` drawer'ı hedef seçiciyi, yalnız seçili hedefin desteklediği
senaryoları, proof checklist'ini, düşük profilli `Sormayı dene` aksiyonunu ve
ayrı reset aksiyonunu gösterir.

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
```

Doğrulanmış baseline:

```text
device status=up
location=Test Lab
port 2 ifAdminStatus=up
port 2 ifOperStatus=down
```

Reset offline fixture adını geri getirir, gerekirse responder'ı tek instance
olarak başlatır, exact OID değerlerini düzeltir, discovery ve poller çalıştırır
ve sonucu gerçek LibreNMS API verisiyle doğrular.

## Son canlı kabul

7 Eylül 2026 tarihinde Codex in-app browser ile masaüstü UTM kabulü tamamlandı.
`lab-j9772a-01` üzerinde Port 2 `admin up / oper down`, interface event `#259`,
aktif warning alarm `#133`, gerçek device down/up geçmiş kanıtı ve tüm
inspection-metadata kontrolleri doğrulandı. Önerilen soru normal sohbetten bir
kez gönderildi; ardından laboratuvar arayüzden baseline'a sıfırlandı.
