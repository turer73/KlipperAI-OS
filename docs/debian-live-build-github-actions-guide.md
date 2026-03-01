# Debian Live Build on GitHub Actions - Reference Guide

> **Purpose:** This guide documents all lessons learned while building a bootable
> Debian Bookworm ISO-hybrid image on GitHub Actions (Ubuntu 24.04 runner).
> It covers common pitfalls, version incompatibilities, and their solutions.

## Overview

Building a Debian-based live system on an Ubuntu GitHub Actions runner involves
cross-distribution tooling. The host is Ubuntu 24.04, but the target is Debian
Bookworm. This creates several compatibility issues documented below.

### Stack

| Component | Version |
|-----------|---------|
| Host OS | Ubuntu 24.04 (GitHub Actions runner) |
| Target OS | Debian Bookworm (12) |
| Build Tool | live-build (Ubuntu package) |
| Bootloader | GRUB-EFI (grub-efi-amd64) |
| Image Format | ISO-hybrid (bootable from USB and CD) |

---

## Issue #1: Unrecognized `lb config` Options

**Error:**
```
--bootloaders: unrecognized option
--updates: unrecognized option
--backports: unrecognized option
--debootstrap-options: unrecognized option
```

**Root Cause:** Ubuntu 24.04's live-build version differs from Debian's.
Many options available in Debian's version are not present in Ubuntu's.

**Solution:** Only use options that are common to both versions:
```bash
lb config \
    --mode debian \
    --system live \
    --distribution bookworm \
    --architectures amd64 \
    --binary-images iso-hybrid \
    --debian-installer false \
    --apt-recommends false \
    --security false \
    --cache true
```

**Key:** Always check `lb config --help` on the target runner to verify
which options are available.

---

## Issue #2: Ubuntu Keyring Leaking into Debian Chroot

**Error:**
```
E: Release 'bookworm' not found in Ubuntu archive
```

**Root Cause:** Without explicit mirror configuration, live-build uses the
host's Ubuntu mirrors for the Debian chroot.

**Solution:** Explicitly set ALL mirror options:
```bash
lb config \
    --parent-distribution bookworm \
    --archive-areas "main contrib non-free non-free-firmware" \
    --parent-archive-areas "main contrib non-free non-free-firmware" \
    --parent-mirror-bootstrap "http://deb.debian.org/debian" \
    --parent-mirror-chroot "http://deb.debian.org/debian" \
    --parent-mirror-binary "http://deb.debian.org/debian" \
    --mirror-bootstrap "http://deb.debian.org/debian" \
    --mirror-chroot "http://deb.debian.org/debian" \
    --mirror-binary "http://deb.debian.org/debian"
```

**Key:** Set both `--mirror-*` and `--parent-mirror-*` variants. The
`--parent-*` options control the base system, while `--mirror-*` options
control the live system.

---

## Issue #3: Debian Security Repository URL Format

**Error:**
```
404 Not Found: bookworm/updates Release
```

**Root Cause:** Old Debian used `bookworm/updates` format; Bookworm uses
`bookworm-security` format. Ubuntu's live-build may generate the wrong format.

**Solution:** Disable live-build's security handling and add repos manually:
```bash
# In lb config:
--security false

# Then manually create archive files:
mkdir -p config/archives
echo "deb http://deb.debian.org/debian-security bookworm-security main contrib non-free non-free-firmware" \
    > config/archives/security.list.chroot
echo "deb http://deb.debian.org/debian bookworm-updates main contrib non-free non-free-firmware" \
    > config/archives/updates.list.chroot
```

---

## Issue #4: `--debian-installer none` Not Supported

**Error:**
```
--debian-installer: invalid value 'none'
```

**Solution:** Use `false` instead of `none`:
```bash
--debian-installer false
```

---

## Issue #5: Contents-amd64.gz 404 Error

**Error:**
```
E: Failed to fetch .../Contents-amd64.gz  404 Not Found
```

**Root Cause:** When `--linux-packages` is not specified, live-build tries
to look up kernel package names via Contents files.

**Solution:** Set `--linux-packages none` and include the kernel package
explicitly in your package list:
```bash
# In lb config:
--linux-packages none

# In package list (klipperos.list.chroot):
linux-image-amd64
```

---

## Issue #6: Syslinux/Isolinux `/root/isolinux/` Not Found

**Error:**
```
cp: cannot stat '/root/isolinux/isolinux.bin': No such file or directory
```

**Root Cause:** This was the most complex issue. Multiple layers:

1. **live-build's `binary_syslinux`** stage looks for isolinux files
2. On Ubuntu runner, the files are at different paths than expected
3. The script looks inside the **chroot**, not on the host filesystem
4. Even after copying files to both host and chroot locations, the error persisted
5. The live-build scripts themselves are at different paths on Ubuntu vs Debian

**Solution:** Completely disable syslinux and use GRUB-EFI only.

### Critical Detail: Variable Name Difference

Ubuntu 24.04's live-build uses `LB_BOOTLOADER` (SINGULAR):
```
# In config/binary:
LB_BOOTLOADER="syslinux"   ← Ubuntu 24.04 live-build
```

Debian's newer live-build uses `LB_BOOTLOADERS` (PLURAL):
```
# In config/binary:
LB_BOOTLOADERS="grub-efi,syslinux"   ← Debian's version
```

### Implementation:
```bash
# After lb config, override the bootloader setting:
if [ -f "${BUILD_DIR}/config/binary" ]; then
    # Delete ALL bootloader variable lines (both singular and plural)
    sed -i '/LB_BOOTLOADER/d' "${BUILD_DIR}/config/binary"
    # Add correct value with SINGULAR variable name (Ubuntu's format)
    echo 'LB_BOOTLOADER="grub-efi"' >> "${BUILD_DIR}/config/binary"
fi
```

### What NOT to Do:
- Don't try to copy isolinux files to `/root/isolinux/` (host or chroot)
- Don't try to find the `binary_syslinux` script to patch it
- Don't install syslinux/isolinux packages in the chroot package list
- Don't use `--bootloaders` flag (not supported on Ubuntu's live-build)

---

## Issue #7: `isohybrid: not found` After ISO Creation

**Error:**
```
binary.sh: 5: isohybrid: not found
```

**Root Cause:** `isohybrid` command comes from `syslinux-utils` package.
When syslinux packages were removed from runner dependencies, this
utility was also removed.

**Solution:** Install `syslinux-utils` (NOT `syslinux`) on the runner:
```yaml
- name: Install build dependencies
  run: |
    sudo apt-get install -y \
      live-build \
      debootstrap \
      debian-archive-keyring \
      squashfs-tools \
      xorriso \
      grub-efi-amd64-bin \
      grub-pc-bin \
      mtools \
      dosfstools \
      syslinux-utils    # For isohybrid command only
```

**Key:** `syslinux-utils` provides the `isohybrid` utility without
installing the full syslinux bootloader.

---

## Runner Dependencies

### Required Packages on Ubuntu 24.04 Runner

```bash
sudo apt-get install -y \
    live-build            # Core build tool
    debootstrap           # Bootstrap Debian system
    debian-archive-keyring # GPG keys for Debian repos
    squashfs-tools        # Create squashfs filesystem
    xorriso               # Create ISO image
    grub-efi-amd64-bin    # GRUB EFI bootloader binaries
    grub-pc-bin           # GRUB PC/BIOS bootloader binaries
    mtools                # FAT filesystem tools
    dosfstools            # DOS filesystem tools
    syslinux-utils        # isohybrid utility
```

### NOT Required (Remove These)

```
syslinux          # Bootloader (not used, causes isolinux issues)
syslinux-common   # Syslinux common files (not needed)
isolinux          # ISO boot sector (not needed with GRUB-EFI)
```

---

## Package List Guidelines

### In the chroot package list (`*.list.chroot`):

```
# Bootloader - GRUB only, NO syslinux
grub-efi-amd64
grub-pc-bin

# Kernel - explicit because --linux-packages none
linux-image-amd64
live-boot
systemd-sysv
```

### Do NOT include in chroot:
```
syslinux          # Causes build conflicts
syslinux-common   # Not needed
isolinux          # Not needed
```

---

## Complete `lb config` Template

```bash
lb config \
    --mode debian \
    --system live \
    --distribution bookworm \
    --parent-distribution bookworm \
    --archive-areas "main contrib non-free non-free-firmware" \
    --parent-archive-areas "main contrib non-free non-free-firmware" \
    --parent-mirror-bootstrap "http://deb.debian.org/debian" \
    --parent-mirror-chroot "http://deb.debian.org/debian" \
    --parent-mirror-binary "http://deb.debian.org/debian" \
    --mirror-bootstrap "http://deb.debian.org/debian" \
    --mirror-chroot "http://deb.debian.org/debian" \
    --mirror-binary "http://deb.debian.org/debian" \
    --architectures amd64 \
    --binary-images iso-hybrid \
    --linux-packages none \
    --debian-installer false \
    --memtest none \
    --apt-recommends false \
    --security false \
    --cache true

# After lb config: override bootloader
sed -i '/LB_BOOTLOADER/d' config/binary
echo 'LB_BOOTLOADER="grub-efi"' >> config/binary

# Add security/updates repos manually
mkdir -p config/archives
echo "deb http://deb.debian.org/debian-security bookworm-security main" \
    > config/archives/security.list.chroot
echo "deb http://deb.debian.org/debian bookworm-updates main" \
    > config/archives/updates.list.chroot
```

---

## GitHub Actions Workflow Tips

### Timeout
```yaml
timeout-minutes: 180   # Large package lists (X11, GTK, cross-compilers) need 90-120 min
```

**Warning:** With a large package list (X11, GTK3, gcc-arm-none-eabi, nginx,
Python, etc.), the build easily exceeds 90 minutes. Set at least 180 minutes.

### Runner
```yaml
runs-on: ubuntu-24.04  # Use specific version, not ubuntu-latest
```

### Version Determination
```yaml
- name: Determine version
  run: |
    if [[ "${{ github.ref }}" == refs/tags/v* ]]; then
      VERSION="${{ github.ref_name }}"
      VERSION="${VERSION#v}"    # Strip 'v' prefix
    fi
```

### Artifact Upload (Always)
```yaml
- uses: actions/upload-artifact@v4
  with:
    compression-level: 0       # ISO is already compressed
    retention-days: 14
```

### GitHub Release (On Tag Push)
```yaml
- if: startsWith(github.ref, 'refs/tags/v')
  uses: softprops/action-gh-release@v2
  with:
    generate_release_notes: true
```

---

## Debugging Tips

1. **Add `cat config/binary`** after `lb config` to see actual configuration
2. **Check live-build version:** `lb --version`
3. **Find live-build scripts:** `find /usr -name "binary_syslinux" 2>/dev/null`
4. **Log everything:** `lb build 2>&1 | tee build.log`
5. **Check variable names:** Ubuntu vs Debian may use different variable names
   (e.g., `LB_BOOTLOADER` vs `LB_BOOTLOADERS`)

---

## Timeline of Fixes (For Reference)

| # | Error | Fix | Time Impact |
|---|-------|-----|-------------|
| 1 | Unrecognized lb config options | Remove unsupported flags | Build starts |
| 2 | Ubuntu keyring in Debian chroot | Explicit mirror config | Debootstrap works |
| 3 | Wrong security repo URL | Manual repo files | Packages install |
| 4 | `--debian-installer none` | Use `false` | Config passes |
| 5 | Contents-amd64.gz 404 | `--linux-packages none` + explicit kernel | Package resolution works |
| 6 | `/root/isolinux/` not found | Disable syslinux, GRUB-EFI only | Binary stage passes |
| 7 | `LB_BOOTLOADERS` wrong name | Use `LB_BOOTLOADER` (singular) | Syslinux truly disabled |
| 8 | `isohybrid: not found` | Install `syslinux-utils` | ISO-hybrid created |
| 9 | Build timeout (90 min) | Increase to 180 min | Build completes |

---

*Last updated: 2026-03-01*
*Project: KlipperAI-OS v2.1.0*
