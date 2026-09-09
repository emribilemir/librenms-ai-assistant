# EMR-86 live acceptance — 9 Eylül 2026

## Sonuç

EMR-86 masaüstü LibreNMS/UTM ortamında kabul edildi. Backend manifesti 11 lab
cihazının tamamında port, event ve investigation aksiyonlarını destekliyor;
frontend aynı capability matrisini ayrı bir hedef listesi hard-code etmeden
gösteriyor. J9772A dışındaki üç model ailesinde gerçek SNMPSim mutasyonu,
LibreNMS discovery/poller sonucu, interface eventi, investigation kanıtı ve
reset doğrulandı.

## Kök neden ve düzeltme

EMR-86 öncesinde yalnız iki J9772A fixture'ında standart IF-MIB port kayıtları
vardı. Runner da yalnız bu iki hedefe `test_port_index` ve sabit bir LibreNMS
`test_port_id` veriyordu. Diğer dokuz cihaz bu nedenle backend capability
matrisinde port/event/investigation aksiyonlarını desteklemiyor görünüyordu.

Runner artık allowlistteki her fixture'a yalnız eksik bounded IF-MIB satırlarını
idempotent ve atomik biçimde ekliyor. Model ve sistem OID'leri korunuyor. Her
senaryo gerçek `port_id` değerini seçili hedefin `device_id + ifIndex`
eşleşmesinden çalıştırma anında çözüyor; başka hedefe fallback veya sabit port
kimliği kullanılmıyor. Canlı kabulde aynı `ifIndex=2` için çözülen farklı
LibreNMS kimlikleri JL357A'da `9`, J4850A'da `10`, J9774A'da `11` oldu.

Baseline-down hedefler mevcut sekiz kalıcı endpoint'e eklenen tek, allowlisted
SNMPSim endpoint ile yalnız senaryo süresince açılıyor. Reset, normal responder
listesini yeniden kurup hedefi tekrar down poll ediyor. SSH çalıştırmaları yalnız
canonical `ssh librenms-vm '<command>'` sözleşmesini kullanıyor.

## Canlı model matrisi

| Hedef / model | Port ve event kanıtı | Investigation kanıtı | Reset |
|---|---|---|---|
| `lab-jl357a-01` / JL357A | Port down ve up geçti; interface event `#358` | Device `#360/#361`, port `#362` | `Test Lab`, admin up / oper down, status up |
| `lab-j4850a-01` / J4850A | Port down geçti; interface event `#369` | Device `#371/#372`, port `#373` | `Test Lab`, admin up / oper down, status up |
| `lab-j9774a-01` / J9774A | Port up geçti; interface event `#380` | Device `#382/#383`, port `#384` | `Test Lab`, admin up / oper down, status up |
| `lab-j9775a-01` / J9775A | Baseline down hedefte port-down geçti | Geçici endpoint ile erişilebilir | Reset sonrası status down |

Son tüm-hedef durum kontrolü `1,2,4,5,6,8,9,11=up` ve `3,7,10=down`
sonucunu verdi. Böylece üç intentional baseline-down hedef korunurken diğer
sekiz hedef yeniden çevrimiçi baseline'a döndü.

## Codex in-app browser kabulü

Canlı kabul yalnız Codex in-app browser'da yapıldı. Demo Modu açıldıktan sonra
drawer 11 hedefi gösterdi; üç baseline-down hedef seçicide açıkça işaretlendi.
`lab-j4850a-01` seçildiğinde altı aksiyonun tamamı etkin durumdaydı.

Arayüzden `Port olayı oluştur` çalıştırıldı ve poll sonucu başarıyla gösterildi.
`Bu durumu AI'a sor` normal sohbet/SSE akışını kullandı; yanıt 20 canlı event
içinde bu turun `#393` (down→up), `#394` (up→down) ve `#395` (down→up)
interface kayıtlarını görünür kıldı. Aynı hedef drawer'daki reset ile tekrar
başlangıç durumuna döndürüldü.

İlk canlı yenileme sırasında stable asset URL'sinin eski `emr81` cache anahtarını
taşıdığı saptandı. Plugin görünümünün JS/CSS sürümü `20260909-emr86` olarak
güncellendi ve yeni URL'nin yüklendiği in-app browser'da aksiyon POST'u ile
yeniden doğrulandı.

## Otomatik doğrulama ve dağıtım

- Python servis/runner testleri: 206 passed, 27 subtests passed.
- Assistant UI: 9 suite, 101 test passed.
- LibreNMS plugin contract: 9 passed.
- Vite production build: başarılı; yalnız mevcut 500 kB chunk-size uyarısı var.
- `git diff --check`: başarılı.

Dağıtılan frontend asset SHA-256 değerleri:

- `ai-assistant.js`: `3f5690303050bb9b1ac178339696070b9e9894d38c3c3635e2458b02a1c672c4`
- `ai-assistant.css`: `6367d2359f9ec19fb83afe16e7abda2cd1327be86ad21718c13e13af12f9683e`

Rollback noktaları:

- SNMPSim fixture'ları: `/opt/snmpsim-lab/backups/emr-86-before`
- VM plugin/assets: `/opt/librenms/.ai-assistant-backups/20260909-emr86`

Frontend deployment temiz bir `HEAD` staging ağacına yalnız EMR-86
`DemoControls.jsx` değişikliği eklenerek üretildi; çalışma ağacındaki ilişkisiz
frontend değişiklikleri canlı pakete dahil edilmedi.
