# EMR-85 live acceptance — 8 Eylül 2026

## Sonuç

EMR-85, masaüstü LibreNMS/UTM ortamında Codex in-app browser ile kabul edildi.
Demo Kontrolleri sağ drawer olarak çalışıyor, backend manifestindeki 11 hedefi
gösteriyor ve desteklenmeyen aksiyonları hedef bazında açıklamayla devre dışı
bırakıyor.

## Kök neden ve düzeltme

`lab-j9772a-02` investigation başarısızlığı frontend kaynaklı değildi. Eski
runner interface eventini sabit `reference=2` ile arıyordu. Bu değer ilk
hedefte tesadüfen hem SNMP `ifIndex` hem LibreNMS `port_id` olduğu için sorun
gizlenmişti. İkinci hedefte Port 2'nin gerçek LibreNMS `port_id` değeri 6'dır.
Hedef manifestine `test_port_index` ve `test_port_id` ayrımı eklendi; event
doğrulaması artık hedefe ait gerçek port kimliğini kullanıyor.

Canlı tur ayrıca production assetinin kaynak değişikliğinden önce paketlendiğini
ortaya çıkardı. Bu eski paket genel senaryolarda CTA'yı `expected_investigation`
olmadan çalıştırmıyordu. Güncel kaynak yeniden build edilip dağıtıldı ve temiz
in-app browser sekmesinde doğrulandı.

## Canlı akışlar

| Hedef / model | Mutasyon ve poller | AI sorgusu | Reset |
|---|---|---|---|
| `lab-j9772a-02` / J9772A | Investigation geçti; interface event `#336`, `reference=6` | Normal SSE sohbeti güncel port, alarm ve geçmiş geçişi döndürdü | Geçti |
| `lab-jl357a-01` / JL357A | Location `EMR-55 Demo Lab`; poll tamamlandı | `lab-jl357a-01 location: EMR-55 Demo Lab.` | `Test Lab`, status up |
| `lab-j4850a-01` / J4850A | Location `EMR-55 Demo Lab`; poll tamamlandı | `lab-j4850a-01 location: EMR-55 Demo Lab.` | `Test Lab`, status up |

Ek olarak `lab-j9775a-01` seçicisinde baseline-kapalı açıklaması, altı disabled
senaryo ve status down durumunu koruyan reset doğrulandı. Demo Modu kapatılınca
açık drawer ve kenar tutamacı birlikte kaldırıldı. Tarayıcı warning/error kaydı
boştu.

## Otomatik doğrulama

- Python: 201 passed, 27 subtests passed.
- Assistant UI: 9 suite, 101 test passed.
- LibreNMS plugin contract: 9 passed.
- Vite production build: başarılı; yalnız mevcut 500 kB chunk-size uyarısı var.
- `git diff --check`: başarılı.

Final frontend asset SHA-256 değerleri:

- `ai-assistant.js`: `78d5c0a00f8f0723fda0649f775183467354376e13b73d7046459fda7fc37986`
- `ai-assistant.css`: `6367d2359f9ec19fb83afe16e7abda2cd1327be86ad21718c13e13af12f9683e`

Rollback noktaları:

- Mac runtime: `~/Library/Application Support/LibreNMSAiAssistant/.runtime-backups/20260908T173648Z-emr85-final`
- VM asset: `/opt/librenms/.ai-assistant-backups/20260908T173714Z-emr85-final`

LibreNMS core çalışma ağacı deployment sonrasında temiz kaldı.
