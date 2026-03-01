#!/bin/bash
# =============================================================================
# KlipperAI-OS — First Boot Wizard
# =============================================================================
# Ilk boot'ta calisir. Donanim algilar, profil onerir, ag ayarlarini yapar,
# istege bagli diske kurar, profil installer'i calistirir.
# =============================================================================

set -euo pipefail

export TERM=linux
export NEWT_COLORS='
root=,blue
window=,black
border=white,black
textbox=white,black
button=black,cyan
actbutton=black,cyan
compactbutton=white,black
title=cyan,black
roottext=cyan,blue
emptyscale=,black
fullscale=,cyan
entry=white,black
checkbox=white,black
actcheckbox=black,cyan
listbox=white,black
actlistbox=black,cyan
actsellistbox=black,cyan
'

VERSION="2.1.0"
BACKTITLE="KlipperAI-OS v${VERSION} Kurulum Sihirbazi"
LOG_FILE="/var/log/klipperai-wizard.log"
KLIPPER_HOME="/home/klipper"
INSTALL_DIR="/opt/klipperos-ai"
DEFERRED_LIST="${INSTALL_DIR}/config/package-lists/klipperos-deferred.list"

log() { echo "[$(date '+%H:%M:%S')] $*" >> "$LOG_FILE"; }

# ===================================================================
# Adim 1: Hosgeldin
# ===================================================================
step_welcome() {
    whiptail --backtitle "$BACKTITLE" \
        --title "KlipperAI-OS'e Hosgeldiniz!" \
        --msgbox "\
  _  _  _ _                      _    ___
 | |/ /| (_)_ __  _ __   ___ _ _/_\  |_ _|
 | ' / | | | '_ \| '_ \ / _ \ '_/ _ \ | |
 | . \ | | | |_) | |_) |  __/ |/ ___ \| |
 |_|\_\|_|_| .__/| .__/ \___|_/_/   \_\___|
            |_|   |_|     OS v${VERSION}

  AI-Powered 3D Printer Operating System

  Bu sihirbaz sisteminizi yapilandiracak:
  1. Donanim algilama
  2. Kurulum profili secimi
  3. Ag ayarlari
  4. Diske kurulum (istege bagli)
  5. Sistem paketleri kurulumu
  6. Yazilim kurulumu

  Devam etmek icin OK'a basin." \
        20 60
    log "Wizard basladi"
}

# ===================================================================
# Adim 2: Donanim Algilama
# ===================================================================
step_detect_hardware() {
    log "Donanim algilaniyor..."

    # RAM
    TOTAL_RAM_MB=$(( $(grep MemTotal /proc/meminfo | awk '{print $2}') / 1024 ))

    # CPU
    CPU_CORES=$(nproc 2>/dev/null || echo 1)
    CPU_MODEL=$(grep -m1 "model name" /proc/cpuinfo 2>/dev/null | cut -d: -f2 | xargs || echo "Bilinmiyor")

    # Disk
    ROOT_DISK_MB=$(df -BM / | awk 'NR==2{print $2}' | tr -d 'M')

    # Ag
    HAS_WIFI="Hayir"
    [ -d /sys/class/net/wlan0/wireless ] 2>/dev/null && HAS_WIFI="Evet"
    for iface in /sys/class/net/*/wireless; do
        [ -d "$iface" ] && HAS_WIFI="Evet" && break
    done

    HAS_ETHERNET="Hayir"
    for iface in /sys/class/net/eth* /sys/class/net/en*; do
        [ -e "$iface" ] && HAS_ETHERNET="Evet" && break
    done

    # Profil onerisi
    RECOMMENDED_PROFILE="LIGHT"
    if [ "$TOTAL_RAM_MB" -ge 4096 ] && [ "$CPU_CORES" -ge 4 ]; then
        RECOMMENDED_PROFILE="FULL"
    elif [ "$TOTAL_RAM_MB" -ge 1536 ]; then
        RECOMMENDED_PROFILE="STANDARD"
    fi

    # RAM < 1.5GB ise sadece LIGHT
    FORCE_LIGHT=false
    if [ "$TOTAL_RAM_MB" -lt 1536 ]; then
        FORCE_LIGHT=true
    fi

    log "RAM=${TOTAL_RAM_MB}MB CPU=${CPU_CORES} Disk=${ROOT_DISK_MB}MB Oneri=${RECOMMENDED_PROFILE}"

    whiptail --backtitle "$BACKTITLE" \
        --title "Donanim Algilama Sonuclari" \
        --msgbox "\
  CPU:       ${CPU_MODEL}
  Cekirdek:  ${CPU_CORES}
  RAM:       ${TOTAL_RAM_MB} MB
  Disk:      ${ROOT_DISK_MB} MB
  WiFi:      ${HAS_WIFI}
  Ethernet:  ${HAS_ETHERNET}

  Onerilen Profil: ${RECOMMENDED_PROFILE}" \
        16 60
}

# ===================================================================
# Adim 3: Profil Secimi
# ===================================================================
step_select_profile() {
    if [ "$FORCE_LIGHT" = true ]; then
        SELECTED_PROFILE="LIGHT"
        whiptail --backtitle "$BACKTITLE" \
            --title "Profil Secimi" \
            --msgbox "\
  RAM: ${TOTAL_RAM_MB} MB (< 1.5 GB)

  Yetersiz RAM nedeniyle sadece LIGHT profil
  kurulabilir.

  LIGHT: Klipper + Moonraker + Mainsail" \
            12 55
        log "Profil: LIGHT (zorunlu — dusuk RAM)"
        return
    fi

    local default_item="2"
    case "$RECOMMENDED_PROFILE" in
        LIGHT)    default_item="1" ;;
        STANDARD) default_item="2" ;;
        FULL)     default_item="3" ;;
    esac

    SELECTED_PROFILE=$(whiptail --backtitle "$BACKTITLE" \
        --title "Kurulum Profili Secin" \
        --default-item "$default_item" \
        --menu "\
  Donanim: ${TOTAL_RAM_MB}MB RAM, ${CPU_CORES} cekirdek
  Onerilen: ${RECOMMENDED_PROFILE}\n" \
        18 65 3 \
        "1" "LIGHT    — Klipper + Moonraker + Mainsail (512MB+)" \
        "2" "STANDARD — + KlipperScreen + Kamera + AI (2GB+)" \
        "3" "FULL     — + Multi-printer + Timelapse (4GB+)" \
        3>&1 1>&2 2>&3) || SELECTED_PROFILE="$default_item"

    case "$SELECTED_PROFILE" in
        1) SELECTED_PROFILE="LIGHT" ;;
        2) SELECTED_PROFILE="STANDARD" ;;
        3) SELECTED_PROFILE="FULL" ;;
    esac

    log "Profil: ${SELECTED_PROFILE}"
}

# ===================================================================
# Adim 4: Ag Ayarlari
# ===================================================================
step_network() {
    # Ethernet varsa ve bagliysa atla
    if ip route get 1.1.1.1 &>/dev/null; then
        whiptail --backtitle "$BACKTITLE" \
            --title "Ag Baglantisi" \
            --msgbox "Internet baglantisi mevcut. Devam ediliyor." \
            8 50
        log "Ag: zaten bagli"
        return
    fi

    # WiFi varsa SSID sor
    if [ "$HAS_WIFI" = "Evet" ]; then
        # nmcli ile tarama
        local wifi_list
        wifi_list=$(nmcli -t -f SSID,SIGNAL dev wifi list 2>/dev/null | head -10 | sort -t: -k2 -rn)

        if [ -z "$wifi_list" ]; then
            whiptail --backtitle "$BACKTITLE" \
                --title "WiFi" \
                --msgbox "WiFi agi bulunamadi. Ethernet kablo baglayin veya WiFi'yi sonra yapilandirin." \
                8 60
            return
        fi

        # Menu icin SSID listesi
        local menu_items=()
        local idx=1
        while IFS=: read -r ssid signal; do
            [ -z "$ssid" ] && continue
            menu_items+=("$idx" "${ssid} (${signal}%)")
            idx=$((idx + 1))
        done <<< "$wifi_list"

        local choice
        choice=$(whiptail --backtitle "$BACKTITLE" \
            --title "WiFi Agi Secin" \
            --menu "Baglanilacak agi secin:" \
            18 60 8 \
            "${menu_items[@]}" \
            3>&1 1>&2 2>&3) || return

        # Secilen SSID
        local selected_ssid
        selected_ssid=$(echo "$wifi_list" | sed -n "${choice}p" | cut -d: -f1)

        # Sifre
        local wifi_pass
        wifi_pass=$(whiptail --backtitle "$BACKTITLE" \
            --title "WiFi Sifresi" \
            --passwordbox "${selected_ssid} icin sifre:" \
            10 50 \
            3>&1 1>&2 2>&3) || return

        # Baglan
        log "WiFi baglaniyor: ${selected_ssid}"
        if nmcli dev wifi connect "$selected_ssid" password "$wifi_pass" 2>/dev/null; then
            whiptail --backtitle "$BACKTITLE" \
                --title "WiFi" \
                --msgbox "Baglanti basarili: ${selected_ssid}" \
                8 50
            log "WiFi baglandi: ${selected_ssid}"
        else
            whiptail --backtitle "$BACKTITLE" \
                --title "WiFi Hatasi" \
                --msgbox "Baglanti basarisiz. Sifre yanlis olabilir.\nKurulum sonrasi tekrar deneyebilirsiniz." \
                10 55
            log "WiFi basarisiz: ${selected_ssid}"
        fi
    else
        whiptail --backtitle "$BACKTITLE" \
            --title "Ag Baglantisi" \
            --msgbox "WiFi algilanamiyor. Ethernet kablo baglayin.\nKurulum icin internet gerekli." \
            8 55
    fi
}

# ===================================================================
# Adim 5: Kullanici Ayarlari
# ===================================================================
step_user_settings() {
    # Hostname
    local new_hostname
    new_hostname=$(whiptail --backtitle "$BACKTITLE" \
        --title "Hostname" \
        --inputbox "Cihaz adi (hostname):" \
        10 50 "klipperos" \
        3>&1 1>&2 2>&3) || new_hostname="klipperos"

    if [ -n "$new_hostname" ] && [ "$new_hostname" != "klipperos" ]; then
        echo "$new_hostname" > /etc/hostname
        sed -i "s/klipperos/${new_hostname}/g" /etc/hosts 2>/dev/null || true
        hostnamectl set-hostname "$new_hostname" 2>/dev/null || true
        log "Hostname: ${new_hostname}"
    fi

    # klipper kullanici sifresi
    local user_pass
    user_pass=$(whiptail --backtitle "$BACKTITLE" \
        --title "Kullanici Sifresi" \
        --passwordbox "'klipper' kullanicisi icin yeni sifre\n(bos birakirsaniz varsayilan: klipper):" \
        10 55 \
        3>&1 1>&2 2>&3) || user_pass=""

    if [ -n "$user_pass" ]; then
        echo "klipper:${user_pass}" | chpasswd
        log "klipper sifresi degistirildi"
    fi
}

# ===================================================================
# Adim 6: Diske Kurulum (Istege Bagli)
# ===================================================================
step_disk_install() {
    local do_install
    do_install=$(whiptail --backtitle "$BACKTITLE" \
        --title "Diske Kurulum" \
        --menu "Kurulum tipi secin:" \
        14 60 3 \
        "1" "Diske kur (kalici kurulum)" \
        "2" "Live olarak devam et (RAM'de calis)" \
        3>&1 1>&2 2>&3) || do_install="2"

    if [ "$do_install" = "2" ]; then
        log "Live mod secildi"
        return
    fi

    # Disk listesi
    local disks
    disks=$(lsblk -dpno NAME,SIZE,TYPE | grep "disk" | grep -v "loop\|sr\|ram")

    if [ -z "$disks" ]; then
        whiptail --backtitle "$BACKTITLE" \
            --title "Hata" \
            --msgbox "Kurulum icin uygun disk bulunamadi." \
            8 50
        return
    fi

    local disk_items=()
    while read -r name size _type; do
        disk_items+=("$name" "${size}")
    done <<< "$disks"

    local target_disk
    target_disk=$(whiptail --backtitle "$BACKTITLE" \
        --title "Hedef Disk Secin" \
        --menu "UYARI: Secilen diskteki TUM VERILER SILINECEK!" \
        16 60 5 \
        "${disk_items[@]}" \
        3>&1 1>&2 2>&3) || return

    # Onay
    if ! whiptail --backtitle "$BACKTITLE" \
        --title "ONAY" \
        --yesno "UYARI!\n\n${target_disk} diskteki TUM VERILER SILINECEK.\n\nDevam etmek istiyor musunuz?" \
        12 55; then
        log "Disk kurulumu iptal edildi"
        return
    fi

    log "Diske kurulum basliyor: ${target_disk}"

    # Partitioning
    {
        echo "10"; echo "# Disk bolumlendiriliyor..."
        parted -s "$target_disk" mklabel gpt
        parted -s "$target_disk" mkpart ESP fat32 1MiB 512MiB
        parted -s "$target_disk" set 1 esp on
        parted -s "$target_disk" mkpart primary ext4 512MiB 100%

        echo "20"; echo "# Dosya sistemleri olusturuluyor..."
        mkfs.fat -F 32 "${target_disk}1" 2>/dev/null || mkfs.fat -F 32 "${target_disk}p1"
        mkfs.ext4 -F "${target_disk}2" 2>/dev/null || mkfs.ext4 -F "${target_disk}p2"

        echo "30"; echo "# Dosyalar kopyalaniyor..."
        local mount_root="/mnt/klipperai"
        mkdir -p "${mount_root}"
        mount "${target_disk}2" "${mount_root}" 2>/dev/null || mount "${target_disk}p2" "${mount_root}"
        mkdir -p "${mount_root}/boot/efi"
        mount "${target_disk}1" "${mount_root}/boot/efi" 2>/dev/null || mount "${target_disk}p1" "${mount_root}/boot/efi"

        echo "40"; echo "# Sistem kopyalaniyor (rsync)..."
        rsync -aAXv --exclude={"/dev/*","/proc/*","/sys/*","/tmp/*","/run/*","/mnt/*","/media/*","/lost+found"} \
            / "${mount_root}/" >> "$LOG_FILE" 2>&1

        echo "70"; echo "# Bootloader kuruluyor..."
        # fstab olustur
        local root_uuid
        root_uuid=$(blkid -s UUID -o value "${target_disk}2" 2>/dev/null || blkid -s UUID -o value "${target_disk}p2")
        local efi_uuid
        efi_uuid=$(blkid -s UUID -o value "${target_disk}1" 2>/dev/null || blkid -s UUID -o value "${target_disk}p1")

        cat > "${mount_root}/etc/fstab" << FSTAB
UUID=${root_uuid}  /          ext4  defaults,noatime  0  1
UUID=${efi_uuid}   /boot/efi  vfat  defaults          0  2
tmpfs              /tmp       tmpfs defaults,noatime,size=64M 0 0
FSTAB

        echo "80"; echo "# GRUB kuruluyor..."
        mount --bind /dev "${mount_root}/dev"
        mount --bind /proc "${mount_root}/proc"
        mount --bind /sys "${mount_root}/sys"
        chroot "${mount_root}" grub-install --target=x86_64-efi --efi-directory=/boot/efi --bootloader-id=KlipperAI-OS 2>>"$LOG_FILE" || true
        chroot "${mount_root}" grub-install "$target_disk" 2>>"$LOG_FILE" || true
        chroot "${mount_root}" update-grub 2>>"$LOG_FILE"

        echo "95"; echo "# Temizleniyor..."
        umount -R "${mount_root}" 2>/dev/null || true

        echo "100"; echo "# Tamamlandi!"
    } | whiptail --backtitle "$BACKTITLE" \
        --title "Diske Kurulum" \
        --gauge "Hazirlaniyor..." \
        8 60 0

    log "Disk kurulumu tamamlandi: ${target_disk}"
}

# ===================================================================
# Adim 7: Ertelenmis Paket Kurulumu
# ===================================================================
step_install_deferred_packages() {
    # Internet kontrolu
    if ! ping -c 1 -W 3 1.1.1.1 &>/dev/null; then
        whiptail --backtitle "$BACKTITLE" \
            --title "Internet Baglantisi Yok" \
            --msgbox "Sistem paketleri icin internet gerekli.\nEthernet baglayip tekrar deneyin.\n\nSistem yeniden baslatildiginda wizard tekrar calisacak." \
            10 55
        log "Paket kurulumu iptal — internet yok"
        touch /opt/klipperos-ai/.first-boot
        return 1
    fi

    # Ertelenmis paket listesi var mi?
    if [ ! -f "$DEFERRED_LIST" ]; then
        log "Ertelenmis paket listesi bulunamadi: ${DEFERRED_LIST}"
        log "Tum paketler zaten ISO'da — atlaniyor."
        return 0
    fi

    # Paket listesini oku (yorum ve bos satirlari filtrele)
    local packages
    packages=$(grep -v '^#' "$DEFERRED_LIST" | grep -v '^$' | tr '\n' ' ')
    local pkg_count
    pkg_count=$(echo "$packages" | wc -w)

    if [ "$pkg_count" -eq 0 ]; then
        log "Ertelenmis paket listesi bos — atlaniyor."
        return 0
    fi

    whiptail --backtitle "$BACKTITLE" \
        --title "Sistem Paketleri Kuruluyor" \
        --msgbox "\
  ${pkg_count} adet sistem paketi indiriliyor ve kuruluyor.

  Bu islem internet hiziniza bagli olarak
  10-30 dakika surebilir.

  Paketler: Build tools, X11, GTK, ARM compiler,
  firmware araclari, web server vb.

  Lutfen bekleyin ve sistemi kapatmayin." \
        14 55

    log "Ertelenmis paket kurulumu basliyor (${pkg_count} paket)..."

    # APT guncelle
    apt-get update >> "$LOG_FILE" 2>&1

    # Paketleri kur (gauge ile ilerleme)
    {
        local installed=0
        local percent=0

        # Toplu kurulum (tek apt-get — daha hizli ve guvenilir)
        echo "5"; echo "# apt-get update tamamlandi..."
        echo "10"; echo "# ${pkg_count} paket kuruluyor..."

        if DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
            $packages >> "$LOG_FILE" 2>&1; then
            echo "95"; echo "# Paketler basariyla kuruldu!"
            log "Ertelenmis paketler basariyla kuruldu"
        else
            echo "95"; echo "# UYARI: Bazi paketler kurulamadi!"
            log "HATA: Bazi ertelenmis paketler kurulamadi"
        fi

        echo "100"; echo "# Tamamlandi!"
    } | whiptail --backtitle "$BACKTITLE" \
        --title "Paket Kurulumu" \
        --gauge "Sistem paketleri kuruluyor..." \
        8 60 0

    # Sentinel: ertelenmis paketler kuruldu
    touch /opt/klipperos-ai/.deferred-packages-installed
    log "Ertelenmis paket kurulumu tamamlandi"
}

# ===================================================================
# Adim 8: Profil Kurulumu
# ===================================================================
step_install_profile() {
    # Internet kontrolu
    if ! ping -c 1 -W 3 1.1.1.1 &>/dev/null; then
        whiptail --backtitle "$BACKTITLE" \
            --title "Internet Baglantisi Yok" \
            --msgbox "Kurulum icin internet gerekli.\nEthernet baglayip tekrar deneyin.\n\nSistem yeniden baslatildiginda wizard tekrar calisacak." \
            10 55
        log "Kurulum iptal — internet yok"
        # Sentinel dosyasini silme (wizard tekrar calissin)
        touch /opt/klipperos-ai/.first-boot
        return 1
    fi

    whiptail --backtitle "$BACKTITLE" \
        --title "Kurulum Basliyor" \
        --msgbox "\
  Profil: ${SELECTED_PROFILE}

  Simdi yazilim kuruluyor. Bu islem internet
  hiziniza bagli olarak 10-30 dakika surebilir.

  Lutfen bekleyin ve sistemi kapatmayin." \
        12 55

    log "Profil kurulumu basliyor: ${SELECTED_PROFILE}"

    # Profil installer'i calistir
    local installer=""
    case "$SELECTED_PROFILE" in
        LIGHT)    installer="${INSTALL_DIR}/scripts/install-light.sh" ;;
        STANDARD) installer="${INSTALL_DIR}/scripts/install-standard.sh" ;;
        FULL)     installer="${INSTALL_DIR}/scripts/install-full.sh" ;;
    esac

    if [ -x "$installer" ]; then
        bash "$installer" 2>&1 | tee -a "$LOG_FILE"
    else
        log "HATA: Installer bulunamadi: ${installer}"
        whiptail --backtitle "$BACKTITLE" \
            --title "Hata" \
            --msgbox "Installer bulunamadi: ${installer}" \
            8 55
        return 1
    fi

    log "Profil kurulumu tamamlandi: ${SELECTED_PROFILE}"
}

# ===================================================================
# Adim 9: Tamamlandi
# ===================================================================
step_complete() {
    local ip_addr
    ip_addr=$(ip route get 1.1.1.1 2>/dev/null | grep -oP 'src \K\S+' || echo "bilinmiyor")

    whiptail --backtitle "$BACKTITLE" \
        --title "Kurulum Tamamlandi!" \
        --msgbox "\
  KlipperAI-OS basariyla kuruldu!

  Profil:     ${SELECTED_PROFILE}
  IP Adresi:  ${ip_addr}
  Web UI:     http://klipperos.local
  SSH:        ssh klipper@${ip_addr}

  Sonraki adimlar:
  1. printer.cfg'yi yaziciya gore duzenleyin
  2. MCU firmware flash: kos_mcu flash
  3. Web arayuzunden yaziciyi test edin

  Sistem simdi yeniden baslatilacak." \
        18 55

    log "Wizard tamamlandi. Reboot."
}

# ===================================================================
# Ana
# ===================================================================
main() {
    log "=== KlipperAI-OS First Boot Wizard v${VERSION} ==="

    step_welcome
    step_detect_hardware
    step_select_profile
    step_network
    step_user_settings
    step_disk_install
    step_install_deferred_packages || {
        log "Ertelenmis paket kurulumu basarisiz. Wizard sonlandirildi."
        exit 1
    }
    step_install_profile || {
        log "Profil kurulumu basarisiz. Wizard sonlandirildi."
        exit 1
    }
    step_complete

    # Reboot
    sleep 2
    reboot
}

main "$@"
