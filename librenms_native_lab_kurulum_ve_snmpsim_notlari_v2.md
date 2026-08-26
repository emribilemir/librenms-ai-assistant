# LibreNMS Native Lab Kurulumu ve Test Cihazı Simülasyonu

**Tarih:** 26 Ağustos 2026  
**Amaç:** UTM içindeki Debian 13 ARM64 sanal makinede LibreNMS'i Docker kullanmadan native kurmak, Mac'ten web arayüzüne ve daha sonra API'ye erişmek, gerçek cihazlar olmadan SNMP ile cevap veren sahte HP ProCurve cihazları üretmek ve LibreNMS'in bunları gerçekten discovery/poller zincirinden geçirmesini sağlamak.

---

## 1. Genel hedef

Bu lab'ın nihai amacı sadece LibreNMS arayüzünü ayağa kaldırmak değil.

Kurmak istediğimiz zincir:

```text
Mac'teki geliştirme ortamı
        |
        | HTTP / LibreNMS API
        v
UTM içindeki Debian 13
        |
        +-- LibreNMS
        |    +-- Nginx
        |    +-- PHP-FPM
        |    +-- MariaDB
        |    +-- Poller / Discovery / Scheduler
        |
        +-- SNMP Simulator
             |
             +-- Sahte HP ProCurve cihazları
```

Böylece ileride doğal dil projesi mock JSON yerine gerçekten LibreNMS API'sinden veri okuyabilecek.

Örnek hedef soru:

```text
"lab-j9772a-01 açık mı?"
```

Bu sorunun cevabı doğrudan hardcode edilmiş bir fixture'dan değil, şu zincirden gelecek:

```text
SNMPSim -> SNMP -> LibreNMS Poller -> LibreNMS DB/API -> doğal dil uygulaması
```

---

# 2. UTM sanal makine kurulumu

## Mimari

Host:

```text
MacBook
Apple Silicon
macOS
```

Guest:

```text
Debian 13
ARM64
```

UTM'de **Virtualize** kullanıldı. Emulate kullanılmadı.

## VM kaynakları

```text
CPU: 2 core
RAM: 2048 MiB
Disk: 20 GiB
Network: UTM Shared Network
```

Shared Directory kullanılmadı.

## Debian kurulumu

Hostname:

```text
librenms
```

Domain boş bırakıldı.

Locale:

```text
en_US.UTF-8
```

Keyboard:

```text
Turkish
```

Timezone:

```text
Europe/Istanbul
```

Normal Debian kullanıcısı:

```text
emir
```

---

# 3. UTM ağ yapısı

UTM **Shared Network** kullanılıyor.

VM'in kullandığımız IP adresi:

```text
192.168.64.3
```

Mac tarafı genellikle:

```text
192.168.64.1
```

Bu yapı sayesinde Mac doğrudan VM'e erişebiliyor:

```bash
ssh emir@192.168.64.3
```

LibreNMS web arayüzü:

```text
http://192.168.64.3
```

Şu an için Shared Network yeterli.

İleride LibreNMS'in gerçek fiziksel LAN üzerindeki switch/router cihazlarına doğrudan SNMP atması gerekirse Bridged Network değerlendirilebilir. Şimdiki local geliştirme ve simulator senaryosu için buna gerek yok.

---

# 4. İlk Debian ağ problemi

Kurulum sırasında VM internete IP üzerinden çıkabiliyordu ancak DNS çözümlemesi çalışmıyordu.

Örneğin internet bağlantısı vardı fakat domain çözümleme başarısızdı.

Geçici olarak `/etc/resolv.conf` içinde DNS sunucuları tanımlandı:

```text
nameserver 1.1.1.1
nameserver 8.8.8.8
```

Bu sayede Debian paket sunucularına erişim sağlandı.

---

# 5. sudo ve SSH düzeltmesi

İlk Debian kurulumundan sonra:

```text
sudo: command not found
```

durumu vardı ve `emir` sudo grubunda değildi.

Sistemi baştan kurmak yerine Debian installer'ın **Rescue Mode** seçeneği kullanıldı.

Root filesystem:

```text
/dev/vda3
```

Rescue ortamında:

```bash
apt install sudo openssh-server
usermod -aG sudo emir
```

uygulandı.

Sonrasında SSH çalıştı:

```bash
ssh emir@192.168.64.3
```

Root shell için:

```bash
sudo -i
```

kullanıldı.

---

# 6. LibreNMS native kurulum başlangıcı

LibreNMS Docker ile değil, doğrudan Debian üzerine native kuruldu.

Önce:

```bash
sudo -i
apt update
apt upgrade -y
```

çalıştırıldı.

## Kurulan temel paketler

```bash
apt install -y \
acl \
ca-certificates \
curl \
fping \
git \
lsb-release \
mariadb-client \
mariadb-server \
mtr-tiny \
nginx-full \
nmap \
php-cli \
php-curl \
php-fpm \
php-gd \
php-gmp \
php-mbstring \
php-mysql \
php-snmp \
php-xml \
php-zip \
python3-command-runner \
python3-dotenv \
python3-pip \
python3-psutil \
python3-pymysql \
python3-redis \
python3-setuptools \
python3-systemd \
rrdtool \
snmp \
snmpd \
unzip \
wget \
whois
```

Daha sonra ayrıca:

```bash
apt install -y traceroute
```

kuruldu.

---

# 7. Locale problemi ve çözümü

SSH sırasında macOS'tan gelen locale nedeniyle aşağıdaki tarz uyarılar görülüyordu:

```text
LC_CTYPE=UTF-8
locale warning
```

Debian tarafında locale düzgün şekilde oluşturuldu:

```bash
sed -i 's/^# *en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen
locale-gen
update-locale LANG=en_US.UTF-8 LC_CTYPE=en_US.UTF-8

export LANG=en_US.UTF-8
export LC_CTYPE=en_US.UTF-8
```

Son durumda:

```text
LANG=en_US.UTF-8
LC_CTYPE=en_US.UTF-8
LC_ALL=
```

`LC_ALL` değerinin boş olması sorun değil.

---

# 8. LibreNMS sistem kullanıcısı

LibreNMS için ayrı sistem kullanıcısı oluşturuldu:

```bash
useradd librenms -d /opt/librenms -M -r -s "$(which bash)"
```

Bu kullanıcı:

```text
librenms
```

LibreNMS uygulama dosyalarını ve background işlemlerini çalıştırmak için kullanılıyor.

---

# 9. LibreNMS kaynak kodunun kurulması

LibreNMS GitHub'dan `/opt` altına clone edildi:

```bash
cd /opt
git clone https://github.com/librenms/librenms.git
```

Sonuç:

```text
/opt/librenms
```

Ownership ve temel izinler:

```bash
chown -R librenms:librenms /opt/librenms
chmod 771 /opt/librenms
```

---

# 10. LibreNMS writable klasörleri ve ACL

Composer sırasında bazı klasörlerin henüz bulunmaması nedeniyle `setfacl` uyarıları görülmüştü.

Gerekli klasörler oluşturuldu:

```bash
mkdir -p /opt/librenms/rrd
mkdir -p /opt/librenms/logs
mkdir -p /opt/librenms/storage
mkdir -p /opt/librenms/bootstrap/cache
```

Ownership tekrar düzeltildi:

```bash
chown -R librenms:librenms /opt/librenms
```

ACL:

```bash
setfacl -d -m g::rwx \
/opt/librenms/rrd \
/opt/librenms/logs \
/opt/librenms/bootstrap/cache \
/opt/librenms/storage

setfacl -R -m g::rwx \
/opt/librenms/rrd \
/opt/librenms/logs \
/opt/librenms/bootstrap/cache \
/opt/librenms/storage
```

---

# 11. Composer kurulumu

`librenms` kullanıcısına geçildi:

```bash
su - librenms
```

Composer wrapper çalıştırıldı:

```bash
./scripts/composer_wrapper.php install --no-dev
```

Başarıyla tamamlandı.

Composer aşağıdaki paketin abandoned olduğunu bildirdi:

```text
influxdb/influxdb-php
```

Bu kurulum açısından fatal bir hata değildi.

---

# 12. Timezone ayarı

Sistem timezone'u:

```bash
timedatectl set-timezone Europe/Istanbul
```

PHP timezone:

```bash
sed -i 's|^;date.timezone =.*|date.timezone = Europe/Istanbul|' \
/etc/php/8.4/fpm/php.ini

sed -i 's|^;date.timezone =.*|date.timezone = Europe/Istanbul|' \
/etc/php/8.4/cli/php.ini
```

Kontroller:

```bash
timedatectl
php -i | grep "date.timezone"
```

Beklenen PHP sonucu:

```text
Europe/Istanbul
```

---

# 13. MariaDB kurulumu ve ayarı

MariaDB server config:

```text
/etc/mysql/mariadb.conf.d/50-server.cnf
```

`[mariadbd]` bölümüne:

```ini
innodb_file_per_table=1
lower_case_table_names=0
```

eklendi.

Servis:

```bash
systemctl enable mariadb
systemctl restart mariadb
systemctl status mariadb --no-pager
```

MariaDB çalıştı:

```text
MariaDB 11.8.6
127.0.0.1:3306
```

---

# 14. LibreNMS veritabanı

MariaDB'ye root olarak girildi:

```bash
mysql -u root
```

LibreNMS database:

```sql
CREATE DATABASE librenms
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;
```

LibreNMS MariaDB kullanıcısı zaten oluşturulmuştu.

İzin:

```sql
GRANT ALL PRIVILEGES ON librenms.* TO 'librenms'@'localhost';
FLUSH PRIVILEGES;
exit
```

Database bağlantısı test edildi:

```bash
mysql -u librenms -p librenms
```

Başarılı sonuç:

```text
MariaDB [librenms]>
```

Burada kullandığımız isimlendirme:

```text
Database: librenms
Database user: librenms
```

Database şifresi bu dokümana yazılmadı.

---

# 15. PHP-FPM LibreNMS pool

Default PHP-FPM pool kopyalandı:

```bash
cp /etc/php/8.4/fpm/pool.d/www.conf \
/etc/php/8.4/fpm/pool.d/librenms.conf
```

Yeni pool adı:

```bash
sed -i 's/^\[www\]/[librenms]/' \
/etc/php/8.4/fpm/pool.d/librenms.conf
```

User ve group:

```bash
sed -i 's/^user = www-data/user = librenms/' \
/etc/php/8.4/fpm/pool.d/librenms.conf

sed -i 's/^group = www-data/group = librenms/' \
/etc/php/8.4/fpm/pool.d/librenms.conf
```

Socket:

```bash
sed -i 's|^listen = .*|listen = /run/php-fpm-librenms.sock|' \
/etc/php/8.4/fpm/pool.d/librenms.conf
```

Servis:

```bash
systemctl restart php8.4-fpm
```

LibreNMS pool process'leri başarıyla çalıştı.

---

# 16. Nginx LibreNMS vhost

Dosya:

```text
/etc/nginx/sites-enabled/librenms.vhost
```

İçerik:

```nginx
server {
    listen 80;
    server_name 192.168.64.3;

    root /opt/librenms/html;
    index index.php;

    charset utf-8;

    gzip on;
    gzip_types text/css application/javascript text/javascript application/x-javascript image/svg+xml text/plain text/xsd text/xsl text/xml image/x-icon;

    location / {
        try_files $uri $uri/ /index.php?$query_string;
    }

    location ~ [^/]\.php(/|$) {
        fastcgi_pass unix:/run/php-fpm-librenms.sock;
        fastcgi_split_path_info ^(.+\.php)(/.+)$;
        include fastcgi.conf;
    }

    location ~ /\.(?!well-known).* {
        deny all;
    }
}
```

Default site kaldırıldı:

```bash
rm /etc/nginx/sites-enabled/default
```

Nginx config test:

```bash
nginx -t
```

Başarılı sonuç:

```text
syntax is ok
test is successful
```

Mac Safari'den:

```text
http://192.168.64.3
```

açıldı ve LibreNMS installer göründü.

Bu noktada şu zincirin çalıştığı kanıtlandı:

```text
Mac -> UTM Network -> Nginx -> PHP-FPM -> LibreNMS
```

---

# 17. LibreNMS system integration

CLI shortcut:

```bash
ln -s /opt/librenms/lnms /usr/bin/lnms
```

Bash completion:

```bash
cp /opt/librenms/misc/lnms-completion.bash \
/etc/bash_completion.d/
```

Cron:

```bash
cp /opt/librenms/dist/librenms.cron \
/etc/cron.d/librenms
```

Scheduler:

```bash
cp /opt/librenms/dist/librenms-scheduler.service \
/opt/librenms/dist/librenms-scheduler.timer \
/etc/systemd/system/

systemctl daemon-reload
systemctl enable --now librenms-scheduler.timer
```

Logrotate:

```bash
cp /opt/librenms/misc/librenms.logrotate \
/etc/logrotate.d/librenms
```

---

# 18. Web installer

Database ekranında:

```text
Database Host: localhost
Database Port: 3306
Database Name: librenms
Database User: librenms
Database Password: <özel şifre>
```

kullanıldı.

Sonrasında LibreNMS web admin kullanıcısı oluşturuldu.

Burada üç farklı kullanıcı kavramını ayırmak önemli:

```text
Debian SSH user:      emir
MariaDB user:         librenms
LibreNMS web admin:   ayrı web admin hesabı
```

Web installer'ın son ekranında:

```text
Update Channel: Daily
Default Theme: Dark
Usage Reports: kapalı
Error Reports: kapalı
```

seçildi ve **Finish Install** yapıldı.

---

# 19. İlk LibreNMS validate sonucu

Validation:

```bash
cd /opt/librenms
sudo -u librenms ./validate.php
```

İlk çalıştırmada temel bileşenler sağlıklıydı ancak:

```text
FAIL Python wrapper cron entry is not present
FAIL Scheduler is not running
WARN You have no devices
```

görüldü.

Cron ve scheduler tekrar yerlerine kopyalanıp etkinleştirildi:

```bash
cp /opt/librenms/dist/librenms.cron /etc/cron.d/librenms

cp /opt/librenms/dist/librenms-scheduler.service \
/opt/librenms/dist/librenms-scheduler.timer \
/etc/systemd/system/

systemctl daemon-reload
systemctl enable --now librenms-scheduler.timer
```

Kontrol:

```bash
cat /etc/cron.d/librenms
systemctl status librenms-scheduler.timer --no-pager
systemctl list-timers --all | grep librenms
```

Scheduler:

```text
active (waiting)
```

durumundaydı.

Bir süre sonra tekrar:

```bash
sudo -u librenms ./validate.php
```

çalıştırıldı.

Sonuç:

```text
[OK] Composer Version
[OK] Dependencies up-to-date
[OK] Database Connected
[OK] Database Schema is current
[OK] SQL Server meets minimum requirements
[OK] lower_case_table_names
[OK] MySQL engine is optimal
[OK] Database collations
[OK] MySQL and PHP time match
[OK] Locks are functional
[OK] Python poller wrapper is polling
[OK] rrd_dir is writable
[OK] rrdtool version ok
```

Kalan tek uyarı:

```text
[WARN] You have no devices.
```

Bu hata değildi. Henüz cihaz eklenmediği için normaldi.

---

# 20. Kurulu LibreNMS sürümleri

Validate çıktısında:

```text
LibreNMS  : 26.9.1-dev.14+08dee672c
DB Schema : 2026_07_30_162514_add_device_refresh_config_permission (397)
PHP       : 8.4.24
Python    : 3.13.5
Database  : MariaDB 11.8.6
RRDTool   : 1.7.2
SNMP      : 5.9.4.pre2
```

görüldü.

---

# 21. Test cihazlarının veri kaynağı

Test cihazları için kullanılan Excel:

```text
device_controller_brand_model_only(3).xlsx
```

Sheet:

```text
Products
```

Kolonlar:

```text
Brand
Model
```

Excel'de toplam:

```text
50 cihaz satırı
8 farklı model
```

bulunuyor.

Model dağılımı:

| Model | Adet |
|---|---:|
| J9772A 2530-48G-PoEP | 23 |
| JL357A 2540-48G-PoE+-4SFP+ | 6 |
| J9783A 2530-8 | 6 |
| J9775A 2530-48G | 6 |
| J9774A 2530-8G-PoEP | 4 |
| J9776A 2530-24G | 2 |
| J9780A 2530-8-PoEP | 2 |
| J4850A 5304XL | 1 |

Excel'de hostname bilgisi yok.

Bu nedenle lab hostname'leri sentetik olarak üretilecek.

İlk örnek:

```text
lab-j9772a-01
```

---

# 22. Neden DB'ye sahte cihaz satırı basmadık?

Test cihazlarını doğrudan LibreNMS MariaDB tablolarına insert etmek mümkün olabilirdi ancak bunu seçmedik.

Sebep:

```text
DB'ye elle insert
    |
    +-- LibreNMS cihazı gerçekten SNMP ile keşfetmemiş olur
    +-- discovery test edilmez
    +-- poller test edilmez
    +-- gerçek cihaz davranışı test edilmez
```

Bizim istediğimiz:

```text
Sahte SNMP cihazı
       |
       v
LibreNMS gerçekten sorgulasın
       |
       v
Discovery + Poller + DB + API
```

Bu nedenle SNMP simulator kullanıldı.

---

# 23. SNMPSim kurulumu

SNMP simulator için sistem Python ortamına paket basmak yerine ayrı virtual environment kullanıldı.

Önce:

```bash
apt install -y python3-venv
```

Virtual environment:

```bash
python3 -m venv /opt/snmpsim-venv
```

SNMPSim:

```bash
/opt/snmpsim-venv/bin/pip install snmpsim
```

Kurulan sürümler arasında:

```text
snmpsim 1.2.2
pysnmp 7.1.29
pyasn1 0.6.4
```

vardı.

---

# 24. SNMPSim pysmi problemi

İlk çalıştırmada:

```text
ModuleNotFoundError: No module named 'pysmi'
```

hatası alındı.

Eksik paket aynı venv'e kuruldu:

```bash
/opt/snmpsim-venv/bin/pip install pysmi
```

Bununla birlikte ilgili Python bağımlılıkları da kuruldu.

---

# 25. İlk sahte cihazın SNMP kaydı

İlk cihaz:

```text
Hostname: lab-j9772a-01
Model: J9772A 2530-48G-PoEP
Simulator IP: 127.0.0.11
SNMP Port: 1611
SNMP Version: v2c
Community: public
```

Data directory:

```bash
mkdir -p /opt/snmpsim-data/j9772a
```

Record:

```text
/opt/snmpsim-data/j9772a/public.snmprec
```

İçerik:

```text
1.3.6.1.2.1.1.1.0|4|ProCurve J9772A 2530-48G-PoEP, revision YA.16.10
1.3.6.1.2.1.1.2.0|6|1.3.6.1.4.1.11.2.3.7.11.1
1.3.6.1.2.1.1.3.0|67|1234567
1.3.6.1.2.1.1.4.0|4|LibreNMS Lab
1.3.6.1.2.1.1.5.0|4|lab-j9772a-01
1.3.6.1.2.1.1.6.0|4|Test Lab
1.3.6.1.2.1.1.7.0|2|6
```

Önemli OID'ler:

```text
sysDescr    1.3.6.1.2.1.1.1.0
sysObjectID 1.3.6.1.2.1.1.2.0
sysUpTime   1.3.6.1.2.1.1.3.0
sysContact  1.3.6.1.2.1.1.4.0
sysName     1.3.6.1.2.1.1.5.0
sysLocation 1.3.6.1.2.1.1.6.0
sysServices 1.3.6.1.2.1.1.7.0
```

---

# 26. SNMPSim root privilege problemi

Simulator ilk kez root olarak çalıştırılmaya çalışıldığında:

```text
snmpsim.error.SnmpsimError:
Must drop privileges to a non-privileged user&group
```

hatası geldi.

Çözüm olarak SNMPSim'in `librenms` user ve group ile çalışması sağlandı.

Gerekirse permissions:

```bash
chown -R librenms:librenms /opt/snmpsim-data

mkdir -p /opt/snmpsim-cache
chown -R librenms:librenms /opt/snmpsim-cache
```

Çalıştırma:

```bash
/opt/snmpsim-venv/bin/snmpsim-command-responder \
  --process-user=librenms \
  --process-group=librenms \
  --data-dir=/opt/snmpsim-data/j9772a \
  --agent-udpv4-endpoint=127.0.0.11:1611
```

Simulator foreground'da çalışıyor.

Bu nedenle o terminal sekmesi açık bırakıldı.

---

# 27. Neden ilk Mac testinde timeout oldu?

İlk test yanlışlıkla macOS terminalinde çalıştırıldı:

```bash
snmpget -v2c -c public \
127.0.0.11:1611 \
1.3.6.1.2.1.1.5.0
```

Sonuç:

```text
Timeout: No Response from 127.0.0.11:1611
```

Sebep:

```text
127.0.0.11 Mac açısından Mac'in loopback adresidir.
```

Simulator ise Debian VM içindedir.

Doğru yöntem önce VM'e SSH ile girmek:

```bash
ssh emir@192.168.64.3
```

ve VM içinde:

```bash
snmpget -v2c -c public \
127.0.0.11:1611 \
1.3.6.1.2.1.1.5.0
```

çalıştırmaktır.

Başarılı sonuç:

```text
iso.3.6.1.2.1.1.5.0 = STRING: "lab-j9772a-01"
```

Bu, ilk sahte SNMP switch'in gerçekten cevap verdiğini kanıtladı.

---

# 28. Test hostname çözümlemesi

LibreNMS'e cihazı güzel bir hostname ile eklemek için `/etc/hosts` içine kayıt eklendi:

```bash
sudo sh -c \
'echo "127.0.0.11 lab-j9772a-01" >> /etc/hosts'
```

Bundan sonra:

```text
lab-j9772a-01
```

VM içinde:

```text
127.0.0.11
```

adresine çözülüyor.

---

# 29. LibreNMS'e ilk sahte cihazın eklenmesi

LibreNMS WebUI içinde:

```text
Devices -> Add Device
```

kullanıldı.

Ayarlar:

```text
Hostname: lab-j9772a-01
SNMP: ON
SNMP Version: v2c
SNMP Port: 1611
Protocol: udp
Port Association Mode: ifIndex
Community: public
Force add: OFF
```

**Add Device** ile cihaz başarıyla eklendi.

---

# 30. LibreNMS'in cihazı doğru tanıması

LibreNMS cihaz ekranında:

```text
System Name: lab-j9772a-01
Operating System: HP ProCurve
Object ID: .1.3.6.1.4.1.11.2.3.7.11.1
Location: Test Lab
IP: 127.0.0.11
Device type: network
Icon: HPE
```

görüldü.

Model açıklaması:

```text
HP ProCurve J9772A 2530-48G-PoEP
YA.16.10
```

olarak işlendi.

Bu önemli çünkü LibreNMS sadece cihazın varlığını kabul etmedi, SNMP bilgisinden HP ProCurve ailesini gerçekten tanıdı.

---

# 31. Discovery ve poller'ın manuel çalıştırılması

Cihaz ilk eklendiğinde:

```text
Uptime: Never polled
```

görünüyordu.

Beklemek yerine manuel discovery çalıştırıldı:

```bash
cd /opt/librenms

sudo -u librenms \
./discovery.php -h lab-j9772a-01
```

Sonra manuel poll:

```bash
sudo -u librenms \
./poller.php -h lab-j9772a-01
```

LibreNMS event çıktısı:

```text
Location: Test Lab
IP: 127.0.0.11
Device type: network
Icon: images/os/hpe.svg
Device status changed to Up from check.
```

Bu satır testin en kritik sonucudur:

```text
Device status changed to Up from check.
```

Yani status sadece DB'ye yazılmış bir değer değil, LibreNMS cihazı kontrol edip **UP** sonucuna ulaştı.

---

# 32. Şu anda çalışan test zinciri

Bugünkü son durumda:

```text
SNMPSim
127.0.0.11:1611
community: public
        |
        | SNMP v2c
        v
LibreNMS
lab-j9772a-01
        |
        +-- HP ProCurve olarak tanındı
        +-- Model bilgisi okundu
        +-- Location okundu
        +-- Poller çalıştı
        +-- Status = UP
```

Dolayısıyla ilk gerçek lab test cihazı:

```text
lab-j9772a-01
```

başarıyla çalışmaktadır.

---

# 33. SNMPSim kaynak tüketimi hakkında

SNMPSim Python tabanlı bir process'tir.

Tek bir simulator instance'ı boşta beklerken CPU kullanımı düşük olur. RAM tarafında Python runtime nedeniyle birkaç on MB seviyesinde kullanım beklenebilir.

Gerçek değeri görmek için:

```bash
ps aux | grep snmpsim | grep -v grep
```

PID alındıktan sonra:

```bash
ps -p PID -o pid,%cpu,%mem,rss,vsz,cmd
```

`rss` yaklaşık resident RAM miktarını KB olarak verir.

Örneğin:

```text
RSS = 50000
```

yaklaşık:

```text
50 MB
```

demektir.

Canlı takip:

```bash
top -p PID
```

---

# 34. Neden 50 ayrı process açmak istemiyoruz?

Excel'de 50 satır olsa da 50 ayrı Python SNMPSim process açmak gereksiz overhead oluşturabilir.

VM:

```text
2 CPU
2 GB RAM
```

olduğu için test lab'ında önce temsilî bir cihaz seti kullanmak daha mantıklı.

Önerilen yaklaşım:

```text
8 farklı modelin tamamını kapsa
+
aynı modelden birkaç tekrar cihaz ekle
+
bazı cihazları UP
+
bazı cihazları DOWN yap
```

Bu sayede doğal dil tarafında aşağıdaki tür sorgular test edilebilir:

```text
"J4850A cihazları"
"48 port ProCurve switchleri"
"PoE'li 48 port switchler"
"PoE'siz 48 port switchler"
"down olan cihazlar"
"lab-j9772a-01 açık mı?"
"aynı modelden kaç cihaz var?"
```

Bütün 50 cihaz ancak gerçekten gerekirse oluşturulabilir.

---

# 35. Önerilen temsilî test inventory

İlk cihaz zaten çalışıyor:

```text
lab-j9772a-01 -> J9772A 2530-48G-PoEP -> UP
```

Genişletmek için düşünülen set:

| Hostname | Model | Planlanan durum |
|---|---|---|
| lab-j9772a-01 | J9772A 2530-48G-PoEP | UP |
| lab-j9772a-02 | J9772A 2530-48G-PoEP | UP |
| lab-j9775a-01 | J9775A 2530-48G | DOWN |
| lab-j9775a-02 | J9775A 2530-48G | UP |
| lab-jl357a-01 | JL357A 2540-48G-PoE+-4SFP+ | UP |
| lab-j4850a-01 | J4850A 5304XL | UP |
| lab-j4850a-02 | J4850A 5304XL | DOWN |
| lab-j9774a-01 | J9774A 2530-8G-PoEP | UP |
| lab-j9776a-01 | J9776A 2530-24G | UP |
| lab-j9780a-01 | J9780A 2530-8-PoEP | DOWN |
| lab-j9783a-01 | J9783A 2530-8 | UP |

Not:

Excel'de `J4850A 5304XL` yalnızca bir satır bulunuyor. İkinci `J4850A` cihazı oluşturulursa bu artık Excel'in birebir kopyası değil, ambiguity ve multi-device resolver testi için bilinçli eklenmiş bir lab fixture'ı olur.

---

# 36. UP ve DOWN cihaz simülasyonu

UP cihaz:

```text
SNMP endpoint çalışıyor
LibreNMS SNMP cevabı alıyor
```

DOWN cihaz için en basit yaklaşım:

```text
o cihazın simulator endpoint'ini çalıştırmamak
```

Böylece LibreNMS poller SNMP cihazına erişemediği için status değişimini gerçek kontrol üzerinden üretir.

Ama bu davranışın poller retry ve ping davranışıyla birlikte kontrollü şekilde kurulması gerekir.

---

# 37. Şu anki ana servisler

LibreNMS VM içinde temel olarak:

```text
nginx
php8.4-fpm
mariadb
librenms-scheduler.timer
```

çalışıyor.

Kontrol:

```bash
systemctl is-active nginx
systemctl is-active php8.4-fpm
systemctl is-active mariadb
systemctl is-active librenms-scheduler.timer
```

Beklenen:

```text
active
active
active
active
```

---

# 38. Hızlı sağlık kontrolü

LibreNMS:

```bash
cd /opt/librenms
sudo -u librenms ./validate.php
```

İlk cihazın SNMP'si:

```bash
snmpget -v2c -c public \
127.0.0.11:1611 \
1.3.6.1.2.1.1.5.0
```

Beklenen:

```text
STRING: "lab-j9772a-01"
```

Discovery:

```bash
sudo -u librenms \
/opt/librenms/discovery.php \
-h lab-j9772a-01
```

Poll:

```bash
sudo -u librenms \
/opt/librenms/poller.php \
-h lab-j9772a-01
```

---

# 39. Mac'ten erişim

SSH:

```bash
ssh emir@192.168.64.3
```

LibreNMS WebUI:

```text
http://192.168.64.3
```

İleride doğal dil uygulamasının kullanacağı LibreNMS API de aynı VM üzerinden erişilebilir olacak.

Planlanan yön:

```text
Mac'teki Python / Qwen uygulaması
        |
        | HTTP
        v
http://192.168.64.3/api/v0/...
```

API token kurulumu henüz bu dökümandaki aşamada yapılmadı.

---

# 40. Güvenlik notları

Bu sistem local geliştirme lab'ıdır.

Şu anda simulator community:

```text
public
```

olarak kullanılıyor.

Bu gerçek production SNMP community olarak düşünülmemeli.

Ayrıca:

- MariaDB şifresi bu dökümanda tutulmuyor.
- LibreNMS web admin şifresi bu dökümanda tutulmuyor.
- Simulator loopback IP'lerde çalışıyor.
- LibreNMS read-only doğal dil uygulaması için ileride API token yetkileri ayrıca sınırlandırılmalı.
- Production cihazlarına geçerken test lab kimlik bilgileri tekrar kullanılmamalı.

---

# 41. Şu anki durum özeti

## Tamamlananlar

```text
[OK] UTM ARM64 Debian VM
[OK] Shared Network
[OK] SSH
[OK] sudo
[OK] DNS
[OK] Locale
[OK] LibreNMS native kurulum
[OK] MariaDB
[OK] LibreNMS database
[OK] PHP-FPM
[OK] Nginx
[OK] Web installer
[OK] LibreNMS admin
[OK] Cron
[OK] Scheduler
[OK] Poller
[OK] RRD
[OK] validate.php kritik hatasız
[OK] Python SNMPSim virtual environment
[OK] pysmi bağımlılığı
[OK] İlk ProCurve SNMP fixture
[OK] SNMP get testi
[OK] LibreNMS cihaz discovery
[OK] LibreNMS device poll
[OK] lab-j9772a-01 status = UP
```

## Henüz yapılmayanlar

```text
[ ] Temsilî cihaz setinin toplu oluşturulması
[ ] Aynı SNMPSim yapısında daha fazla sanal agent
[ ] Kontrollü DOWN cihaz senaryoları
[ ] LibreNMS API token oluşturulması
[ ] Mac'ten LibreNMS API testi
[ ] Doğal dil projesinin mock yerine gerçek API'ye bağlanması
[ ] Device/port/alert/event endpoint testleri
[ ] Test sorgularının gerçek LibreNMS verisine karşı koşturulması
```

---

# 42. Bundan sonraki mantıklı sıra

Önerilen devam sırası:

```text
1. SNMPSim'i tek cihazlık manuel PoC'den çoklu cihaz lab'ına çevir
2. Excel'deki 8 modelin tamamını kapsayan fixture'ları üret
3. UP / DOWN durumlarını bilinçli dağıt
4. LibreNMS'e cihazları toplu ekle
5. Discovery + poll doğrula
6. LibreNMS API token oluştur
7. Mac'ten curl ile API'yi test et
8. Doğal dil backend'ini gerçek LibreNMS endpoint'ine bağla
9. Planner / resolver / deterministic atomic status mimarisini gerçek veride dene
```

---

# 43. Kısa mimari sonuç

Bu noktada proje artık:

```text
"JSON içine elle yazılmış fake network cihazları"
```

seviyesinde değil.

Çalışan PoC:

```text
Sahte ama SNMP protokolüyle gerçekmiş gibi davranan switch
        |
        v
LibreNMS gerçek discovery yapıyor
        |
        v
LibreNMS gerçek poll yapıyor
        |
        v
LibreNMS cihazı HP ProCurve olarak sınıflandırıyor
        |
        v
LibreNMS status = UP üretiyor
```

Dolayısıyla ileride doğal dil katmanının kullanacağı veri, mümkün olduğunca gerçek LibreNMS çalışma biçimine yakın bir lab ortamından üretilebilir.

Bu, projenin resolver, device-set, status, API ve grounded answer testleri için önceki saf mock yaklaşımından daha gerçekçi bir temel sağlar.

# 44. Yaşadığımız sorunlar ve nasıl çözdük

Bu bölüm kurulum sırasında gerçekten karşılaştığımız problemleri kronolojik olarak toplar. Amaç sadece "doğru komutlar"ı bırakmak değil, aynı hatalar tekrar olduğunda nedenini hızlıca anlayabilmek.

## Sorun 1: Debian kurulumu sırasında internet var gibi görünüyordu ama paket sunucularına erişilemiyordu

### Belirti

VM IP seviyesinde dışarı çıkabiliyordu ancak domain isimleri çözülemiyordu. Bu yüzden Debian mirror ve paket işlemlerinde hata yaşandı.

Özet durum:

```text
IP bağlantısı var
DNS çözümleme yok
```

### Neden

VM'in DNS resolver ayarı doğru çalışmıyordu.

### Çözüm

`/etc/resolv.conf` içine geçici DNS sunucuları yazıldı:

```text
nameserver 1.1.1.1
nameserver 8.8.8.8
```

Bundan sonra Debian repository erişimi ve paket kurulumu devam etti.

### Öğrenilen

Bir VM internete çıkamıyor gibi görünüyorsa önce iki şeyi ayrı test etmek gerekir:

```text
1. IP connectivity
2. DNS resolution
```

İkisi aynı problem değildir.

---

## Sorun 2: Debian kullanıcısında sudo yoktu

### Belirti

Kurulumdan sonra:

```text
sudo: command not found
```

görüldü.

Ayrıca `emir` kullanıcısı sudo yetkisine sahip değildi.

### Neden

İlk Debian kurulumunda `sudo` paketi kurulmamış ve normal kullanıcı sudo grubuna eklenmemişti.

### Çözüm

Sistemi yeniden kurmak yerine Debian netinst ISO ile **Rescue Mode** açıldı.

Root filesystem:

```text
/dev/vda3
```

mount edilip:

```bash
apt install sudo openssh-server
usermod -aG sudo emir
```

uygulandı.

Sonrasında:

```bash
sudo -i
```

çalışır hale geldi.

### Öğrenilen

Linux kurulumu sonrası sudo eksikse her zaman yeniden kurulum gerekmez. Rescue Mode ile root filesystem'e girip eksik paket ve grup üyelikleri düzeltilebilir.

---

## Sorun 3: SSH kurulumu başta tam hazır değildi

### Belirti

Mac'ten VM'e rahat çalışmak için SSH gerekiyordu ancak ilk kurulumdan sonra servis hazır değildi.

### Çözüm

Rescue Mode sırasında:

```bash
apt install openssh-server
```

kuruldu.

Ardından Mac'ten:

```bash
ssh emir@192.168.64.3
```

ile bağlantı kuruldu.

### Sonuç

Kurulumun geri kalanı UTM'in sanal ekranından değil, büyük ölçüde Mac Terminal üzerinden yapıldı.

---

## Sorun 4: macOS SSH oturumunda locale uyarıları çıkıyordu

### Belirti

Paket kurulumları sırasında sürekli buna benzer uyarılar görülüyordu:

```text
LC_CTYPE=UTF-8
unsupported locale
```

### Neden

macOS SSH oturumu `LC_CTYPE=UTF-8` gönderiyordu ancak Debian tarafında uygun locale oluşturulmamıştı.

### Çözüm

```bash
sed -i 's/^# *en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen
locale-gen
update-locale LANG=en_US.UTF-8 LC_CTYPE=en_US.UTF-8

export LANG=en_US.UTF-8
export LC_CTYPE=en_US.UTF-8
```

Kontrol:

```bash
locale
```

### Sonuç

Locale uyarıları ortadan kalktı.

---

## Sorun 5: Composer sırasında LibreNMS writable klasörleri bulunamadı

### Belirti

Composer hook'ları sırasında `setfacl` işlemleri bazı path'lerde:

```text
No such file or directory
```

benzeri hata verdi.

Özellikle:

```text
/opt/librenms/rrd
/opt/librenms/logs
/opt/librenms/storage
/opt/librenms/bootstrap/cache
```

### Neden

ACL uygulanmaya çalışılan klasörlerin bazıları henüz oluşmamıştı.

### Çözüm

Önce klasörler oluşturuldu:

```bash
mkdir -p /opt/librenms/rrd
mkdir -p /opt/librenms/logs
mkdir -p /opt/librenms/storage
mkdir -p /opt/librenms/bootstrap/cache
```

Sonra ownership:

```bash
chown -R librenms:librenms /opt/librenms
```

ve ACL:

```bash
setfacl -d -m g::rwx \
/opt/librenms/rrd \
/opt/librenms/logs \
/opt/librenms/bootstrap/cache \
/opt/librenms/storage

setfacl -R -m g::rwx \
/opt/librenms/rrd \
/opt/librenms/logs \
/opt/librenms/bootstrap/cache \
/opt/librenms/storage
```

uygulandı.

### Öğrenilen

Permission hatası her zaman yanlış kullanıcı anlamına gelmez. Bazen hedef path henüz yoktur.

---

## Sorun 6: LibreNMS web installer veritabanına bağlanamadı

### Belirti

Web installer database ekranında kullanıcı bilgileri doğru gibi görünmesine rağmen bağlantı başarısız oldu.

İlk kontrol:

```bash
mysql -u root -e "SELECT User,Host FROM mysql.user;"
```

çıktısında:

```text
librenms | localhost
```

vardı.

Yani MariaDB kullanıcısı oluşmuştu.

Ancak:

```bash
mysql -u librenms -p librenms
```

şunu verdi:

```text
ERROR 1049 (42000): Unknown database 'librenms'
```

### Neden

`librenms` MariaDB kullanıcısı oluşturulmuştu fakat `librenms` adlı database gerçekte oluşmamıştı.

Bu çok önemli bir ayrımdı:

```text
MariaDB user var
Database yok
```

### Çözüm

Root olarak MariaDB'ye girildi:

```bash
mysql -u root
```

ve:

```sql
CREATE DATABASE librenms
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;

GRANT ALL PRIVILEGES ON librenms.* TO 'librenms'@'localhost';
FLUSH PRIVILEGES;
exit
```

uygulandı.

Sonra:

```bash
mysql -u librenms -p librenms
```

başarıyla:

```text
MariaDB [librenms]>
```

promptuna girdi.

### Öğrenilen

Database connection hatasında sadece kullanıcıyı değil, database'in gerçekten var olup olmadığını da ayrıca kontrol etmek gerekir.

---

## Sorun 7: MariaDB promptu ile Linux shell karıştırıldı

### Belirti

MariaDB içindeyken şu Linux shell komutu yazıldı:

```bash
mysql -u root -e "SHOW DATABASES;"
```

ve prompt:

```text
->
```

şeklinde devam etti.

### Neden

Komut MariaDB monitor içindeyken yazılmıştı. MariaDB bunu SQL statement'ın devamı olarak yorumladı.

### Çözüm

Önce mevcut statement iptal edildi:

```sql
\c
```

sonra:

```sql
exit
```

ile MariaDB'den çıkıldı.

Linux shell'e dönünce komut doğru yerde çalıştırıldı.

### Öğrenilen

Promptu takip etmek önemli:

```text
MariaDB [librenms]>   -> SQL yaz
root@librenms:#       -> Linux komutu yaz
```

---

## Sorun 8: LibreNMS kuruldu ama validate scheduler ve cron hatası verdi

### Belirti

İlk:

```bash
sudo -u librenms ./validate.php
```

sonucunda:

```text
[FAIL] Python wrapper cron entry is not present
[FAIL] Scheduler is not running
```

görüldü.

### Neden

Cron dosyası ve systemd scheduler timer gerekli yerlere yerleştirilmiş olsa da LibreNMS validator henüz scheduler'ın çalıştığına dair kendi cache işaretini görmemişti. Ayrıca cron tanımı da tekrar kontrol edilmeliydi.

### Çözüm

Cron yeniden kopyalandı:

```bash
cp /opt/librenms/dist/librenms.cron /etc/cron.d/librenms
```

Scheduler dosyaları yeniden kopyalandı:

```bash
cp /opt/librenms/dist/librenms-scheduler.service \
/opt/librenms/dist/librenms-scheduler.timer \
/etc/systemd/system/
```

Ardından:

```bash
systemctl daemon-reload
systemctl enable --now librenms-scheduler.timer
```

Kontrol:

```bash
systemctl status librenms-scheduler.timer --no-pager
```

çıktısında:

```text
Active: active (waiting)
```

görüldü.

Timer gerçekten tetiklenince tekrar:

```bash
sudo -u librenms ./validate.php
```

çalıştırıldı ve:

```text
[OK] Python poller wrapper is polling
```

geldi.

Scheduler FAIL de kayboldu.

### Öğrenilen

`active (waiting)` timer servisleri için normaldir. Timer sürekli çalışan daemon gibi `active (running)` görünmek zorunda değildir.

Ayrıca validator bazı kontrollerde servis dosyasının varlığına değil, gerçekten iş üretildiğine bakabilir.

---

## Sorun 9: validate hâlâ "You have no devices" uyarısı veriyordu

### Belirti

Kurulum sonunda:

```text
[WARN] You have no devices.
```

görülüyordu.

### Neden

Bu bir kurulum hatası değildi. LibreNMS sağlıklıydı fakat henüz izlenecek cihaz eklenmemişti.

### Çözüm

Bir test cihazı üretmeye karar verildi.

Bu noktada doğrudan DB'ye fake row yazmak yerine gerçek SNMP davranışına yakın bir simulator kuruldu.

### Öğrenilen

`WARN` ile `FAIL` aynı şey değildir.

Bu uyarı cihaz eklendiğinde doğal olarak ortadan kalkacaktır.

---

## Sorun 10: Gerçek cihaz olmadığı için LibreNMS'i nasıl test edeceğimiz net değildi

### Problem

LibreNMS kurulmuştu fakat elde gerçek HP ProCurve switch bulunmuyordu.

Sadece Excel'de gerçek cihaz modelleri vardı.

DB'ye fake device insert etmek kolaydı ancak bu durumda:

```text
SNMP test edilmez
Discovery test edilmez
Poller test edilmez
OS detection test edilmez
```

### Çözüm

SNMP simulator kullanılmasına karar verildi.

Bu sayede:

```text
sahte cihaz -> gerçek SNMP response -> LibreNMS discovery -> poller -> DB/API
```

zinciri kurulabilecekti.

### Öğrenilen

Bir monitoring sisteminin gerçekçi testi için sadece fixture data değil, protokol seviyesinde davranış simülasyonu çok daha değerlidir.

---

## Sorun 11: SNMPSim kurulunca `pysmi` modülü eksik çıktı

### Belirti

SNMPSim çalıştırılınca:

```text
ModuleNotFoundError: No module named 'pysmi'
```

hatası geldi.

### Neden

Kurulan `snmpsim` paketi runtime sırasında `pysmi` bekliyordu fakat dependency otomatik gelmemişti.

### Çözüm

Aynı Python virtual environment içine:

```bash
/opt/snmpsim-venv/bin/pip install pysmi
```

kuruldu.

### Neden system Python'a kurmadık?

SNMPSim için ayrı venv oluşturmuştuk:

```text
/opt/snmpsim-venv
```

Böylece Debian'ın sistem Python paketleri ile simulator bağımlılıkları birbirine karışmadı.

---

## Sorun 12: SNMPSim root olarak çalışmayı reddetti

### Belirti

`pysmi` düzeldikten sonra:

```text
snmpsim.error.SnmpsimError:
Must drop privileges to a non-privileged user&group
```

hatası geldi.

### Neden

SNMPSim root user olarak başlatılmıştı ve güvenlik nedeniyle privilege drop istiyordu.

### Çözüm

Mevcut `librenms` sistem kullanıcısı kullanıldı:

```bash
/opt/snmpsim-venv/bin/snmpsim-command-responder \
  --process-user=librenms \
  --process-group=librenms \
  --data-dir=/opt/snmpsim-data/j9772a \
  --agent-udpv4-endpoint=127.0.0.11:1611
```

Gerekirse directory ownership:

```bash
chown -R librenms:librenms /opt/snmpsim-data
```

ile düzeltildi.

### Öğrenilen

Simulator için root kullanmak gereksizdi çünkü UDP 161 yerine:

```text
1611
```

kullanıyorduk.

---

## Sorun 13: İlk SNMP testi timeout verdi

### Belirti

Mac'te:

```bash
snmpget -v2c -c public \
127.0.0.11:1611 \
1.3.6.1.2.1.1.5.0
```

çalıştırılınca:

```text
Timeout: No Response from 127.0.0.11:1611
```

geldi.

### İlk bakışta şüphe

Simulator çalışmıyor sanılabilirdi.

### Gerçek neden

Komut **Mac üzerinde** çalıştırılmıştı.

`127.0.0.11` her makinenin kendi loopback alanıdır.

Yani:

```text
Mac'teki 127.0.0.11 = Mac
VM'deki 127.0.0.11 = Debian VM
```

Aynı adres değillerdir.

### Çözüm

Önce VM'e SSH:

```bash
ssh emir@192.168.64.3
```

Sonra VM içinde:

```bash
snmpget -v2c -c public \
127.0.0.11:1611 \
1.3.6.1.2.1.1.5.0
```

çalıştırıldı.

Başarılı sonuç:

```text
iso.3.6.1.2.1.1.5.0 = STRING: "lab-j9772a-01"
```

### Öğrenilen

Loopback adresi VM ile host arasında paylaşılmaz.

Bu lab'da:

```text
192.168.64.3
```

VM'in Mac'ten erişilen adresidir.

```text
127.x.x.x
```

adresleri ise VM'in kendi içinde simulator instance'ları için kullanılıyor.

---

## Sorun 14: İlk test cihazının model bilgisini LibreNMS'in doğru tanıması gerekiyordu

### Problem

Sadece bir hostname döndürmek yeterli değildi.

LibreNMS'in cihazı gerçekten:

```text
HP ProCurve
```

olarak tanımasını ve model bilgisini `sysDescr` üzerinden çıkarmasını istiyorduk.

### Çözüm

SNMP record içinde uygun bilgiler verildi.

Özellikle:

```text
sysDescr
```

şöyle ayarlandı:

```text
ProCurve J9772A 2530-48G-PoEP, revision YA.16.10
```

ve `sysObjectID` HP ProCurve detection dalına uygun yapıldı:

```text
1.3.6.1.4.1.11.2.3.7.11.1
```

### Sonuç

LibreNMS cihaz ekranında:

```text
Operating System: HP ProCurve
Object ID: .1.3.6.1.4.1.11.2.3.7.11.1
Location: Test Lab
Device type: network
HPE icon
```

görüldü.

Model başlığı da:

```text
HP ProCurve J9772A 2530-48G-PoEP
YA.16.10
```

olarak çıktı.

### Öğrenilen

Network simulator testlerinde sadece cihazın cevap vermesi değil, doğru `sysDescr` ve `sysObjectID` değerleri de önemlidir.

---

## Sorun 15: LibreNMS cihazı ekledi ama "Never polled" görünüyordu

### Belirti

Cihaz başarıyla eklenmişti fakat cihaz sayfasında:

```text
Uptime: Never polled
```

görülüyordu.

### Neden

Cihaz yeni eklenmişti ve background poller henüz o cihaz için turunu tamamlamamıştı.

### Çözüm

Beklemek yerine manuel discovery:

```bash
cd /opt/librenms
sudo -u librenms ./discovery.php -h lab-j9772a-01
```

ve manuel poll:

```bash
sudo -u librenms ./poller.php -h lab-j9772a-01
```

çalıştırıldı.

### Sonuç

LibreNMS event log:

```text
Location: Test Lab
IP: 127.0.0.11
Device type: network
Icon: images/os/hpe.svg
Device status changed to Up from check.
```

gösterdi.

Bu, cihazın status değerinin gerçekten poll sonucunda üretildiğini kanıtladı.

---

# 45. Sorunlar ve çözümler hızlı tablo

| Sorun | Kök neden | Çözüm |
|---|---|---|
| Debian mirror çalışmıyor | DNS çözümleme yok | `/etc/resolv.conf` içine 1.1.1.1 ve 8.8.8.8 |
| `sudo` yok | Paket/yetki kurulmamış | Rescue Mode, `apt install sudo`, `usermod -aG sudo emir` |
| SSH eksik | openssh-server yok | Rescue Mode'da `apt install openssh-server` |
| Locale warning | macOS `LC_CTYPE` ile Debian locale uyuşmuyor | `en_US.UTF-8` generate + update-locale |
| Composer ACL path error | Writable klasörler yok | mkdir + chown + setfacl |
| LibreNMS DB bağlantı hatası | User var, database yok | `CREATE DATABASE librenms` + GRANT |
| MariaDB `->` prompt | Shell komutu SQL promptunda yazıldı | `\c`, `exit`, shell'de tekrar çalıştır |
| Python wrapper FAIL | Cron/scheduler entegrasyonu tamamlanmamış | cron kopyala, timer enable/start |
| Scheduler FAIL | Timer/cached heartbeat henüz görülmedi | `active (waiting)` doğrula, tetiklenmesini bekle |
| `You have no devices` | Henüz cihaz eklenmedi | Test SNMP cihazı oluştur |
| SNMPSim `pysmi` yok | Eksik runtime dependency | venv içinde `pip install pysmi` |
| SNMPSim root hatası | Root ile çalıştırıldı | `--process-user=librenms --process-group=librenms` |
| SNMP timeout | Test Mac loopback'te çalıştırıldı | SSH ile VM içine girip test et |
| ProCurve modeli yanlış/eksik görünebilir | `sysDescr` formatı önemli | ProCurve uyumlu sysDescr ve sysObjectID kullan |
| `Never polled` | Poller henüz tur atmadı | Manuel discovery + poller çalıştır |

---

# 46. Kurulumdan çıkan pratik dersler

Bu çalışmada birkaç genel prensip netleşti:

1. **Her hatayı bulunduğu katmanda teşhis etmek lazım.**  
   DNS problemi network problemi gibi, database yokluğu user/password problemi gibi görünebilir.

2. **Prompt'a bakmak önemli.**  
   `MariaDB>` ile Linux shell birbirine karıştırıldığında doğru komut bile yanlış yerde hata üretir.

3. **LibreNMS'in sağlıklı olması ile cihazın sağlıklı olması farklı şeylerdir.**  
   `validate.php` sistem bileşenlerini kontrol eder. Cihaz discovery/poll ise ayrı zincirdir.

4. **Mock database yerine protokol seviyesinde simülasyon daha değerlidir.**  
   SNMPSim sayesinde LibreNMS'in gerçek SNMP discovery ve polling kodu test ediliyor.

5. **Loopback adresleri hostlar arasında ortak değildir.**  
   VM içindeki `127.0.0.11`, Mac'ten doğrudan erişilemez.

6. **Timer servisinde `active (waiting)` normaldir.**  
   Bu bir daemon değil, belirli aralıklarla çalışan systemd timer'dır.

7. **Kullanıcıları ayırmak kafa karışıklığını azaltır.**  

```text
emir       -> Debian SSH kullanıcısı
librenms   -> Linux service user
librenms   -> MariaDB database user
web admin  -> LibreNMS panel kullanıcısı
```

Aynı isim bazı katmanlarda tekrar kullanılsa bile bunlar farklı authentication alanlarıdır.

8. **Şu anki test cihazı gerçekten LibreNMS tarafından kontrol edildi.**  
   En önemli kanıt:

```text
Device status changed to Up from check.
```

Bu nedenle `lab-j9772a-01 = UP` değeri elle atanmış bir fixture sonucu değildir.
