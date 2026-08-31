# Opsiyonel Debian 13, SSH, sudo ve SNMPSim lab kurulumu

> Bu rehber yalnız uçtan uca LibreNMS/SNMPSim lab ortamı kurmak isteyenler içindir. Repo testlerini çalıştırmak için Debian, UTM, macOS, LibreNMS veya SNMPSim gerekmez.

macOS ve UTM burada doğrulanmış referans ortamdır; zorunlu değildir. SSH istemcisi olan başka bir masaüstü sistemi ve desteklenen bir Debian/Ubuntu sunucusu da kullanılabilir.

Referans lab, UTM içinde çalışan Debian 13 ARM64 VM üzerine native LibreNMS
kurulumudur. Aşağıdaki komutlarda `<linux-kullanicisi>`, `<vm-ip>` ve
`<mac-ip-veya-subnet>` alanlarını kendi ortamınıza göre değiştirin. Örnek IP,
parola, private key veya API token'ını repoya eklemeyin.

## 1. Ağ ve sistem kontrolü

VM konsolunda ağ arayüzünü, varsayılan rotayı ve DNS çözümlemesini kontrol edin:

```bash
ip -br address
ip route
hostname -I
ping -c 3 1.1.1.1
getent hosts deb.debian.org
cat /etc/resolv.conf
```

IP'ye ping çalışıyor fakat `getent hosts` sonuç vermiyorsa problem SSH değil,
DNS yapılandırmasıdır. DNS düzelmeden `apt update` ve paket kurulumu güvenilir
çalışmaz. UTM shared network kullanılıyorsa Mac ve VM aynı UTM ağı üzerinden
birbirine erişebilmelidir; bridged network bu yerel PoC için zorunlu değildir.

Temel sistem bilgisini kaydedin:

```bash
cat /etc/os-release
uname -a
timedatectl
df -h
free -h
```

## 2. `sudo` ve OpenSSH kurulumu

Minimal Debian kurulumunda `sudo` veya SSH server bulunmayabilir. VM konsolunda
root hesabına geçip gerekli paketleri kurun:

```bash
su -
apt update
apt install -y sudo openssh-server ca-certificates curl git
systemctl enable --now ssh
systemctl status ssh --no-pager
```

Root parolası veya çalışan bir root shell yoksa Debian kurulum medyasındaki
**Advanced options -> Rescue mode** kullanılabilir. Root filesystem mount
edildikten sonra aynı `apt install` ve kullanıcı yönetimi komutları uygulanır.

## 3. Normal kullanıcıya tam sudo yetkisi verme

Lab yöneticisinin tüm sistemi yönetmesi gerekiyorsa kullanıcıyı Debian'ın
`sudo` grubuna ekleyin:

```bash
usermod -aG sudo <linux-kullanicisi>
getent group sudo
exit
```

`-aG` birlikte kullanılmalıdır. Yalnız `-G sudo` çalıştırmak kullanıcının diğer
ek gruplarını silebilir. Grup üyeliği mevcut oturuma geriye dönük eklenmez;
kullanıcı tamamen çıkış yapıp yeniden giriş yapmalıdır. Yeni oturumda:

```bash
id
groups
sudo -v
sudo whoami
```

Son komutun çıktısı `root` olmalıdır. Günlük çalışma normal kullanıcıyla
yapılmalı; yalnız yönetim komutlarında `sudo` kullanılmalıdır. Uzun süreli
`sudo -i` oturumu yanlışlıkla sistem dosyası değiştirme riskini artırır.

## 4. SSH servis ve port kontrolü

VM tarafında SSH daemon yapılandırmasını ve dinlenen portu kontrol edin:

```bash
sudo sshd -t
sudo systemctl enable --now ssh
sudo systemctl status ssh --no-pager
sudo ss -lntp | grep ':22'
```

Mac'ten ilk bağlantı:

```bash
ssh <linux-kullanicisi>@<vm-ip>
```

İlk bağlantıda gösterilen host fingerprint'i körlemesine kabul etmeyin. VM
konsolunda Ed25519 fingerprint'ini görüntüleyip Mac'teki değerle karşılaştırın:

```bash
sudo ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
```

## 5. Anahtarlı SSH erişimi

Mac'te mevcut bir anahtarınız yoksa parola korumalı Ed25519 anahtarı oluşturun:

```bash
ssh-keygen -t ed25519 -a 100 -C "librenms-lab"
```

`ssh-copy-id` kuruluysa public key'i VM'ye aktarın:

```bash
ssh-copy-id -i ~/.ssh/id_ed25519.pub <linux-kullanicisi>@<vm-ip>
```

`ssh-copy-id` yoksa `~/.ssh/id_ed25519.pub` içeriğini kopyalayıp VM'de normal
kullanıcı hesabıyla aşağıdaki dosyaya tek satır olarak ekleyin:

```bash
install -d -m 700 ~/.ssh
nano ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

Private key olan `~/.ssh/id_ed25519` hiçbir zaman VM'ye veya repoya
kopyalanmamalıdır. Yeni bir Mac terminalinde anahtarlı bağlantıyı doğrulayın:

```bash
ssh -i ~/.ssh/id_ed25519 <linux-kullanicisi>@<vm-ip>
```

İsterseniz Mac'teki `~/.ssh/config` dosyasına kolay erişim için şu kaydı ekleyin:

```sshconfig
Host librenms-lab
    HostName <vm-ip>
    User <linux-kullanicisi>
    IdentityFile ~/.ssh/id_ed25519
    IdentitiesOnly yes
```

Bundan sonra bağlantı komutu `ssh librenms-lab` olur.

## 6. SSH hardening

Parolalı girişi yalnız anahtarlı bağlantı ayrı bir terminalde başarıyla
doğrulandıktan sonra kapatın. Mevcut SSH oturumunu test bitene kadar açık tutun.

```bash
sudoedit /etc/ssh/sshd_config.d/00-lab-hardening.conf
```

Dosya içeriği:

```sshconfig
PermitRootLogin no
PubkeyAuthentication yes
PasswordAuthentication no
KbdInteractiveAuthentication no
AllowUsers <linux-kullanicisi>
```

Yapılandırmayı önce doğrulayın, sonra servisi bağlantıları kesmeden reload edin:

```bash
sudo sshd -t
sudo sshd -T | grep -E 'permitrootlogin|pubkeyauthentication|passwordauthentication|kbdinteractiveauthentication|allowusers'
sudo systemctl reload ssh
sudo systemctl status ssh --no-pager
```

İkinci terminalde `ssh librenms-lab` tekrar çalışmadan ilk oturumu kapatmayın.
Hata halinde açık oturumdan drop-in dosyasını düzeltip `sshd -t` çalıştırın.

## 7. İsteğe bağlı UFW kuralları

VM başka makinelerin erişebildiği bir ağdaysa inbound trafiği sınırlandırın.
Önce gerçek Mac IP'sini veya UTM subnet'ini belirleyin; yanlış kaynak adresi
SSH erişimini kilitleyebilir.

```bash
sudo apt install -y ufw
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow from <mac-ip-veya-subnet> to any port 22 proto tcp
sudo ufw allow from <mac-ip-veya-subnet> to any port 80 proto tcp
sudo ufw show added
sudo ufw enable
sudo ufw status numbered
```

HTTPS yapılandırıldıysa aynı kaynak için `443/tcp` açılabilir. SNMPSim veya
LibreNMS poller trafiği farklı interface/subnet kullanıyorsa gerekli SNMP
kuralları ayrıca ve mümkün olan en dar kaynak aralığıyla tanımlanmalıdır.

## 8. Tam sudo yerine sınırlı servis yetkisi

Bir kullanıcı yalnız servis durumunu görmek veya belirli servisleri yeniden
başlatmak için bağlanacaksa tam `sudo` grubu gereğinden geniştir. Önce binary
yollarını doğrulayın:

```bash
command -v systemctl
```

Ardından ayrı bir sudoers drop-in dosyasını yalnız `visudo` ile oluşturun:

```bash
sudo visudo -f /etc/sudoers.d/librenms-ops
```

Debian'da `systemctl` yolu `/usr/bin/systemctl` ise örnek içerik:

```sudoers
Cmnd_Alias LIBRENMS_STATUS = /usr/bin/systemctl status nginx --no-pager, /usr/bin/systemctl status php8.4-fpm --no-pager, /usr/bin/systemctl status mariadb --no-pager, /usr/bin/systemctl status librenms-scheduler.timer --no-pager
Cmnd_Alias LIBRENMS_RESTART = /usr/bin/systemctl restart nginx, /usr/bin/systemctl restart php8.4-fpm, /usr/bin/systemctl restart mariadb
<linux-kullanicisi> ALL=(root) LIBRENMS_STATUS, LIBRENMS_RESTART
<linux-kullanicisi> ALL=(librenms) /opt/librenms/validate.php
```

Sisteminizdeki PHP servis adı veya binary yolu farklıysa dosyayı buna göre
değiştirin. Sözdizimini ve efektif izinleri kontrol edin:

```bash
sudo chmod 440 /etc/sudoers.d/librenms-ops
sudo visudo -c
sudo -l -U <linux-kullanicisi>
```

Kullanıcıyı tam `sudo` grubundan çıkarmadan önce sınırlı komutları ikinci bir
oturumda test edin ve çalışan ayrı bir root/yönetici erişimini koruyun. Tam
yetki gerçekten kaldırılacaksa bunu root veya başka bir yönetici yapmalıdır:

```bash
deluser <linux-kullanicisi> sudo
```

Grup değişikliği yeniden girişten sonra geçerli olur. Sudoers komut eşleşmesi
binary yolu ve argümanlara duyarlıdır; wildcard kullanmayın ve düzenleme için
doğrudan text editor yerine daima `visudo` kullanın.

## 9. Linux servis ve LibreNMS sağlık kontrolü

Native kurulumdan sonra ana servisleri kontrol edin:

```bash
sudo systemctl status ssh --no-pager
sudo systemctl status nginx --no-pager
sudo systemctl status php8.4-fpm --no-pager
sudo systemctl status mariadb --no-pager
sudo systemctl status librenms-scheduler.timer --no-pager
sudo systemctl list-timers --all | grep librenms
```

Yapılandırma ve LibreNMS doğrulaması:

```bash
sudo nginx -t
sudo -u librenms /opt/librenms/validate.php
sudo journalctl -u nginx -u php8.4-fpm -u mariadb --since today
```

`php8.4-fpm` adı Debian/PHP sürümüne göre değişebilir. Kurulu birimleri bulmak
için `systemctl list-unit-files | grep -E 'php.*fpm'` kullanın.

## 10. SNMPSim ile sahte ağ cihazı oluşturma

SNMPSim, fiziksel switch veya router olmadan gerçek SNMP cevapları üretir.
Buradaki amaç LibreNMS veritabanına elle cihaz/status satırı yazmak değildir;
LibreNMS'in cihazı SNMP üzerinden gerçekten keşfetmesini ve poll etmesini
sağlamaktır.

```text
SNMPSim fixture
        |
        | SNMP v2c
        v
LibreNMS discovery + poller
        |
        v
LibreNMS DB/API
        |
        v
Natural-language hybrid PoC
```

### SNMPSim kurulumu

SNMPSim'i system Python ortamına kurmak yerine ayrı bir virtual environment
kullanın:

```bash
sudo apt update
sudo apt install -y python3-venv snmp
sudo python3 -m venv /opt/snmpsim-venv
sudo /opt/snmpsim-venv/bin/pip install --upgrade pip
sudo /opt/snmpsim-venv/bin/pip install snmpsim pysmi
/opt/snmpsim-venv/bin/pip show snmpsim pysmi
```

`pysmi` ayrıca kurulmazsa bazı sürümlerde `ModuleNotFoundError: No module named
'pysmi'` hatası alınabilir.

Simulator'ı root olarak çalıştırmayın. LibreNMS sistem kullanıcısı hazırsa lab
fixture'ları için bu hesap kullanılabilir:

```bash
sudo install -d -o librenms -g librenms /opt/snmpsim-data/j9772a
sudo install -d -o librenms -g librenms /opt/snmpsim-cache
```

Production ortamında aynı hesabı paylaşmak yerine yalnız SNMPSim için shell
erişimi olmayan ayrı bir service account tercih edilmelidir.

### Örnek HP ProCurve fixture'ı

`/opt/snmpsim-data/j9772a/public.snmprec` dosyasını oluşturun:

```bash
sudo -u librenms nano /opt/snmpsim-data/j9772a/public.snmprec
```

Örnek kayıt:

```text
1.3.6.1.2.1.1.1.0|4|ProCurve J9772A 2530-48G-PoEP, revision YA.16.10
1.3.6.1.2.1.1.2.0|6|1.3.6.1.4.1.11.2.3.7.11.1
1.3.6.1.2.1.1.3.0|67|1234567
1.3.6.1.2.1.1.4.0|4|LibreNMS Lab
1.3.6.1.2.1.1.5.0|4|lab-j9772a-01
1.3.6.1.2.1.1.6.0|4|Test Lab
1.3.6.1.2.1.1.7.0|2|6
```

Bu kayıt sırasıyla `sysDescr`, `sysObjectID`, `sysUpTime`, `sysContact`,
`sysName`, `sysLocation` ve `sysServices` OID'lerini sağlar. LibreNMS'in HP
ProCurve ailesini tanımasında özellikle doğru `sysObjectID` önemlidir.

### Simulator'ı başlatma

Loopback üzerinde non-privileged `1611/udp` portunu kullanarak simulator'ı
foreground çalıştırın:

```bash
sudo -u librenms /opt/snmpsim-venv/bin/snmpsim-command-responder \
  --data-dir=/opt/snmpsim-data/j9772a \
  --cache-dir=/opt/snmpsim-cache \
  --agent-udpv4-endpoint=127.0.0.11:1611
```

Foreground işlem açık kaldığı sürece cihaz SNMP cevabı verir. `1611`, root
gerektiren standart `161` portuna göre lab için daha güvenli ve kolaydır.

Başka bir VM terminalinde endpoint'i doğrulayın:

```bash
snmpget -v2c -c public \
  127.0.0.11:1611 \
  1.3.6.1.2.1.1.5.0
```

Beklenen sonuç:

```text
iso.3.6.1.2.1.1.5.0 = STRING: "lab-j9772a-01"
```

`127.0.0.11` Debian VM'nin loopback adresidir. Aynı `snmpget` komutunu Mac'te
çalıştırmak Mac'in kendi loopback interface'ini sorgular ve timeout verir.
Testi SSH ile VM'ye girdikten sonra çalıştırın.

### Hostname ve LibreNMS cihaz kaydı

LibreNMS ile SNMPSim aynı VM'deyse lab hostname'ini `/etc/hosts` içinde
loopback endpoint'e bağlayın:

```bash
printf '127.0.0.11 lab-j9772a-01\n' | sudo tee -a /etc/hosts
getent hosts lab-j9772a-01
```

LibreNMS WebUI'de **Devices -> Add Device** ekranında:

```text
Hostname: lab-j9772a-01
SNMP: ON
SNMP Version: v2c
SNMP Port: 1611
Protocol: udp
Community: public
Port Association Mode: ifIndex
Force add: OFF
```

`public` community yalnız loopback'e bağlı bu izole lab örneği içindir. Gerçek
ağda varsayılan community kullanmayın; kaynak IP'yi sınırlandırın ve mümkünse
SNMPv3 tercih edin.

### Discovery ve poller doğrulaması

Cihaz eklendikten sonra beklemeden manuel discovery ve poller çalıştırılabilir:

```bash
cd /opt/librenms
sudo -u librenms ./discovery.php -h lab-j9772a-01
sudo -u librenms ./poller.php -h lab-j9772a-01
sudo -u librenms ./validate.php
```

Başarılı akışta LibreNMS cihazı HP ProCurve olarak tanır; model, location ve
uptime alanlarını okur ve poll sonucunda cihaz durumunu üretir. Böylece API'den
okunan `UP` değeri elle yazılmış fixture değil, gerçek SNMP kontrolünün
sonucudur.

### UP ve DOWN cihaz simülasyonu

- **UP:** ilgili SNMPSim endpoint'i çalışır ve SNMP sorgularına cevap verir.
- **DOWN:** ilgili endpoint durdurulur; LibreNMS retry/poller döngüsü sonunda
  erişilemezliği kendisi tespit eder.
- Aynı modelden birden fazla hostname, ambiguity ve device-set senaryolarını
  test etmek için ayrı loopback IP/port kombinasyonlarında çalıştırılabilir.
- Kaynak tüketimini `ps`, `top` ve RSS değeriyle ölçmeden onlarca ayrı Python
  process başlatmayın; önce temsilî model seti kullanın.

Bu PoC'deki hostname, community, status, port, alarm ve event değerleri
synthetic lab verisidir. İSBAK production cihazı veya operasyon kaydı değildir.

## 11. Sık karşılaşılan erişim sorunları

| Belirti | Kontrol | Muhtemel çözüm |
|---|---|---|
| `sudo: command not found` | `command -v sudo` | Root/rescue shell'de `apt install sudo` |
| Kullanıcı sudo kullanamıyor | `id`, `getent group sudo` | `usermod -aG sudo <kullanıcı>` ve tam çıkış/giriş |
| `Connection refused` | `systemctl status ssh`, `ss -lntp` | `openssh-server` kurup `systemctl enable --now ssh` |
| SSH timeout | `ip route`, UTM ağı, UFW kuralları | IP/subnet ve port 22 erişimini düzeltme |
| `Permission denied (publickey)` | `ssh -vvv`, dosya izinleri | `~/.ssh=700`, `authorized_keys=600`, doğru kullanıcı/key |
| Host key uyarısı | VM fingerprint kontrolü | VM yeniden kurulduysa eski kaydı dikkatle `ssh-keygen -R <vm-ip>` ile kaldırma |
| `apt update` DNS hatası | `ping 1.1.1.1`, `getent hosts` | `/etc/resolv.conf` veya DHCP/DNS ayarını düzeltme |
| Locale uyarıları | `locale`, `locale -a` | `sudo dpkg-reconfigure locales` ve UTF-8 locale seçimi |
| Web arayüzü açılmıyor | `nginx -t`, PHP-FPM status, UFW | Nginx/PHP socket ve 80/443 kurallarını kontrol etme |
| SNMPSim `pysmi` hatası | Venv içindeki `pip show pysmi` | Paketi system Python'a değil `/opt/snmpsim-venv` içine kurma |
| SNMP timeout | Simulator process'i, IP/port ve çalıştırılan host | `127.0.0.11` sorgusunu Mac'te değil Debian VM içinde çalıştırma |
| LibreNMS `Never polled` gösteriyor | Discovery/poller çıktısı | Her iki komutu `librenms` kullanıcısıyla manuel çalıştırıp hatayı inceleme |

Native LibreNMS, MariaDB, Nginx, PHP-FPM, scheduler ve SNMPSim kurulumunun
tam adım adım kaydı için [Debian 13 LibreNMS lab rehberine](lab/librenms_native_lab_kurulum_ve_snmpsim_notlari_v2.md)
bakın.

## İlgili belgeler

- [Ana README](../README.md)
- [Ayrıntılı Debian 13 LibreNMS ve SNMPSim lab günlüğü](lab/librenms_native_lab_kurulum_ve_snmpsim_notlari_v2.md)
