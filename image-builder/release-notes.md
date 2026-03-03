## KlipperOS-AI Minimal ISO v4.0.0-live

Debootstrap tabanli minimal live ISO — sadece Python TUI installer icerir.
Tum Klipper ekosistemi ilk boot'ta internet uzerinden kurulur.

### Degisiklikler (v3 → v4)

- **Builder**: Ubuntu Server repack → debootstrap + squashfs (XZ)
- **Boyut**: ~3 GB → ~500 MB
- **Boot**: squashfs RAM'e kopyalanir (toram)
- **Autologin**: tty1 otomatik giris (klipper kullanicisi)
- **Locale**: tr_TR.UTF-8 + Turkish keyboard varsayilan

### Kurulum

**1. USB'ye yaz:**
```bash
# Linux / macOS
sudo dd if=klipperos-minimal-v4.0.0-live.iso of=/dev/sdX bs=4M status=progress

# Windows: Balena Etcher veya Rufus kullanin
```

**2. Ilk acilis:**
1. USB'den boot edin
2. Live sistem baslatilir (~1 dk)
3. Python TUI Installer otomatik baslar
4. Donanim algilama > Ag baglantisi > Profil secimi > Kurulum
5. Profiller: **LIGHT** (512MB RAM) | **STANDARD** (2GB+) | **FULL** (4GB+)
