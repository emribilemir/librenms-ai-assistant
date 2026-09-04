# EMR-55 minimal simulation runner

Bu CLI yalnız mevcut UTM içindeki `lab-j9772a-01` SNMPSIM fixture'ını ve
LibreNMS `device_id=1` kaydını kullanır. Frontend, yeni API, run store veya
genel amaçlı orchestration katmanı içermez.

## Ön koşullar

- UTM erişimi: `ssh -i ~/.ssh/codex_utm emir@192.168.64.3`
- `sudo -n -u librenms true` başarılı olmalı.
- `/opt/snmpsim-lab/data/lab-j9772a-01/public.snmprec` dosyası `emir`
  tarafından yazılabilir olmalı.
- Yerel shell'de mevcut read-only LibreNMS ayarları yüklenmiş olmalı:

```bash
set -a
source librenms-hybrid-poc/.env.runtime
set +a
```

## Kullanım

```bash
python3 simulation/run.py port-down
python3 simulation/run.py port-up
python3 simulation/run.py location-change
python3 simulation/run.py device-down-up
python3 simulation/run.py port-down-up-event
```

| Scenario | Canlı doğrulama | Örnek AI sorusu |
|---|---|---|
| `port-down` | Port 2 `admin=up oper=down` | `lab-j9772a-01 port 2 ne durumda?` |
| `port-up` | Port 2 `admin=up oper=up` | `lab-j9772a-01 port 2 ne durumda?` |
| `location-change` | Location `EMR-55 Demo Lab` | `lab-j9772a-01'in konumu neresi?` |
| `device-down-up` | Device down ve ardından up event'i | `lab-j9772a-01 en son ne zaman down oldu?` |
| `port-down-up-event` | Yeni Port 2 transition event'i | `lab-j9772a-01 son eventlerini göster` |

Port ve location kayıtları SNMPSIM tarafından hot-reload edilir. Device
down/up senaryosu yalnız hedef fixture'ın adını geçici olarak
`offline.snmprec` yapar. Responder PID'i `librenms` kullanıcısı ve exact command
prefix'iyle çözülür; PID hardcode edilmez ve broad `pkill -f` kullanılmaz.
Mevcut launcher root privilege-drop flag'leri içerdiği için passwordless
`librenms` restart'ında aynı responder ve `devices-up.txt` girdileri doğrudan
kullanılır; VM launcher dosyası değiştirilmez.

`port-down-up-event` çıktısı gerçek LibreNMS eventlog kaydının `event id`,
`timestamp` ve `message` alanlarını gösterir. Aynı alanlar LibreNMS içinde
`Devices > Eventlog` ekranından doğrulanabilir.

## Reset

Her demo sonrasında baseline'a dönün:

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

Reset, offline fixture adını geri getirir, gerekirse responder'ı tek instance
olarak başlatır, exact OID değerlerini düzeltir, discovery ve poller çalıştırır
ve sonucu gerçek LibreNMS API verisiyle doğrular.
