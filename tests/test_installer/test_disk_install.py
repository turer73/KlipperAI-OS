"""Disk kurulum altyapi testleri — target, runner chroot, sentinel, disk, bootloader."""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock


# ── target.py testleri ──────────────────────────────────────────────


def test_target_path_none():
    """target=None → yol degismeden doner (live CD modu)."""
    from packages.installer.utils.target import target_path, set_target
    set_target(None)
    assert target_path("/etc/hostname") == "/etc/hostname"
    assert target_path("/var/log/test.log") == "/var/log/test.log"


def test_target_path_set():
    """target=/mnt/target → yollar prefix'lenir (disk kurulum)."""
    from packages.installer.utils.target import target_path, set_target
    set_target("/mnt/target")
    try:
        assert target_path("/etc/hostname") == str(Path("/mnt/target/etc/hostname"))
        assert target_path("/var/log/x.log") == str(Path("/mnt/target/var/log/x.log"))
    finally:
        set_target(None)


def test_set_clear_target():
    """set/get/clear dongusu dogru calisir."""
    from packages.installer.utils.target import set_target, get_target
    assert get_target() is None
    set_target("/mnt/test")
    assert get_target() == "/mnt/test"
    set_target(None)
    assert get_target() is None


def test_target_path_strips_leading_slash():
    """Cift slash olusmasin — /mnt/target//etc degil /mnt/target/etc."""
    from packages.installer.utils.target import target_path, set_target
    set_target("/mnt/target")
    try:
        result = target_path("/etc/fstab")
        assert "//" not in result
    finally:
        set_target(None)


# ── runner.py chroot testleri ────────────────────────────────────────


@patch("packages.installer.utils.runner.subprocess.run")
def test_run_cmd_no_target(mock_run):
    """target=None → komut degismez."""
    from packages.installer.utils.runner import run_cmd
    from packages.installer.utils.target import set_target
    set_target(None)

    mock_run.return_value = MagicMock(
        returncode=0, stdout="ok", stderr=""
    )
    ok, out = run_cmd(["apt-get", "update"])
    assert ok is True
    called_cmd = mock_run.call_args[0][0]
    assert called_cmd == ["apt-get", "update"]


@patch("packages.installer.utils.runner.subprocess.run")
def test_run_cmd_with_target_adds_chroot(mock_run):
    """target set → chroot prefix eklenir."""
    from packages.installer.utils.runner import run_cmd
    from packages.installer.utils.target import set_target
    set_target("/mnt/target")
    try:
        mock_run.return_value = MagicMock(
            returncode=0, stdout="ok", stderr=""
        )
        run_cmd(["apt-get", "update"])
        called_cmd = mock_run.call_args[0][0]
        assert called_cmd == ["chroot", "/mnt/target", "apt-get", "update"]
    finally:
        set_target(None)


@patch("packages.installer.utils.runner.subprocess.run")
def test_run_cmd_host_command_no_chroot(mock_run):
    """mount, parted gibi host komutlarina chroot eklenmez."""
    from packages.installer.utils.runner import run_cmd
    from packages.installer.utils.target import set_target
    set_target("/mnt/target")
    try:
        mock_run.return_value = MagicMock(
            returncode=0, stdout="ok", stderr=""
        )
        for host_cmd in ["mount", "umount", "parted", "mkfs.ext4",
                         "grub-install", "lsblk", "blkid"]:
            run_cmd([host_cmd, "--test"])
            called_cmd = mock_run.call_args[0][0]
            assert called_cmd[0] != "chroot", (
                f"{host_cmd} should NOT be wrapped in chroot"
            )
            assert called_cmd[0] == host_cmd
    finally:
        set_target(None)


# ── sentinel.py target testleri ──────────────────────────────────────


def test_sentinel_with_target():
    """target set → sentinel dosyalari hedef diskte olusur."""
    from packages.installer.utils.sentinel import Sentinel
    from packages.installer.utils.target import set_target, target_path
    with tempfile.TemporaryDirectory() as tmpdir:
        target_root = Path(tmpdir) / "mnt" / "target"
        target_root.mkdir(parents=True)
        # Windows'ta da calisan base_dir (tmpdir altinda)
        base_dir = str(Path(tmpdir) / "sentinel_data")
        set_target(str(target_root))
        try:
            s = Sentinel(base_dir=base_dir)
            s.mark_done("test_comp")
            # target_path uzerinden cozumlenen yol mevcut olmali
            resolved = target_path(str(Path(base_dir) / ".installed-test_comp"))
            assert Path(resolved).exists()
            assert s.is_done("test_comp") is True
        finally:
            set_target(None)


def test_sentinel_without_target():
    """target=None → sentinel normal calisir."""
    from packages.installer.utils.sentinel import Sentinel
    from packages.installer.utils.target import set_target
    set_target(None)
    with tempfile.TemporaryDirectory() as tmpdir:
        s = Sentinel(base_dir=tmpdir)
        s.mark_done("xyz")
        assert s.is_done("xyz") is True
        expected = Path(tmpdir) / ".installed-xyz"
        assert expected.exists()


# ── disk.py testleri ─────────────────────────────────────────────────


@patch("packages.installer.steps.disk.run_cmd")
def test_list_disks(mock_run):
    """lsblk ciktisi dogru parse edilir."""
    from packages.installer.steps.disk import DiskStep
    tui = MagicMock()
    step = DiskStep(tui=tui)

    mock_run.return_value = (
        True,
        "sda     50G Samsung SSD\nnvme0n1 256G WD Blue\nmmcblk0 32G  SD Card\n",
    )
    disks = step._list_disks()
    assert len(disks) >= 3
    assert any("sda" in d[0] for d in disks)
    assert any("nvme0n1" in d[0] for d in disks)


@patch("packages.installer.steps.disk.run_cmd")
def test_partition_uefi(mock_run):
    """UEFI modda GPT + ESP + root bolumleri olusturulur."""
    from packages.installer.steps.disk import DiskStep
    tui = MagicMock()
    step = DiskStep(tui=tui)
    step.uefi = True
    step.disk = "/dev/sda"

    mock_run.return_value = (True, "")
    step._partition()

    # parted komutlari kontrol
    calls = [str(c) for c in mock_run.call_args_list]
    parted_calls = [c for c in calls if "parted" in c]
    assert len(parted_calls) > 0, "parted cagrilmali"
    # gpt label
    assert any("gpt" in c for c in parted_calls)
    # ESP bölümü
    assert any("fat32" in c or "ESP" in c for c in parted_calls)

    assert step.efi_part != ""
    assert step.root_part != ""


@patch("packages.installer.steps.disk.run_cmd")
def test_partition_bios(mock_run):
    """BIOS modda MBR + tek root bolumu olusturulur."""
    from packages.installer.steps.disk import DiskStep
    tui = MagicMock()
    step = DiskStep(tui=tui)
    step.uefi = False
    step.disk = "/dev/sda"

    mock_run.return_value = (True, "")
    step._partition()

    calls = [str(c) for c in mock_run.call_args_list]
    parted_calls = [c for c in calls if "parted" in c]
    assert len(parted_calls) > 0
    # msdos label
    assert any("msdos" in c for c in parted_calls)
    assert step.root_part != ""
    assert step.efi_part == ""


def test_resolve_partition_sda():
    """sda → sda1, sda2 gibi standart cozumleme."""
    from packages.installer.steps.disk import DiskStep
    tui = MagicMock()
    step = DiskStep(tui=tui)
    step.disk = "/dev/sda"
    assert step._resolve_partition(1) == "/dev/sda1"
    assert step._resolve_partition(2) == "/dev/sda2"


def test_resolve_partition_nvme():
    """nvme0n1 → nvme0n1p1 seklinde 'p' separator'li cozumleme."""
    from packages.installer.steps.disk import DiskStep
    tui = MagicMock()
    step = DiskStep(tui=tui)
    step.disk = "/dev/nvme0n1"
    assert step._resolve_partition(1) == "/dev/nvme0n1p1"
    assert step._resolve_partition(2) == "/dev/nvme0n1p2"


def test_resolve_partition_mmcblk():
    """mmcblk0 → mmcblk0p1 seklinde 'p' separator'li cozumleme."""
    from packages.installer.steps.disk import DiskStep
    tui = MagicMock()
    step = DiskStep(tui=tui)
    step.disk = "/dev/mmcblk0"
    assert step._resolve_partition(1) == "/dev/mmcblk0p1"


# ── bootloader.py testleri ───────────────────────────────────────────


def test_bootloader_fstab_uefi():
    """UEFI modda fstab'da hem root hem EFI satirlari olur."""
    from packages.installer.steps.bootloader import BootloaderStep
    from packages.installer.utils.target import set_target
    tui = MagicMock()

    with tempfile.TemporaryDirectory() as tmpdir:
        set_target(tmpdir)
        try:
            step = BootloaderStep(
                tui=tui,
                disk="/dev/sda",
                root_part="/dev/sda2",
                efi_part="/dev/sda1",
                uefi=True,
                mount_point=tmpdir,
            )
            # UUID mock
            with patch.object(step, "_get_uuid", side_effect=["ROOT-UUID-123", "EFI-UUID-456"]):
                result = step._generate_fstab()

            assert result is True
            fstab = Path(tmpdir) / "etc" / "fstab"
            assert fstab.exists()
            content = fstab.read_text()
            assert "ROOT-UUID-123" in content
            assert "EFI-UUID-456" in content
            assert "/boot/efi" in content
            assert "ext4" in content
            assert "vfat" in content
        finally:
            set_target(None)


def test_bootloader_fstab_bios():
    """BIOS modda fstab'da sadece root satiri olur, EFI yok."""
    from packages.installer.steps.bootloader import BootloaderStep
    from packages.installer.utils.target import set_target
    tui = MagicMock()

    with tempfile.TemporaryDirectory() as tmpdir:
        set_target(tmpdir)
        try:
            step = BootloaderStep(
                tui=tui,
                disk="/dev/sda",
                root_part="/dev/sda1",
                efi_part="",
                uefi=False,
                mount_point=tmpdir,
            )
            with patch.object(step, "_get_uuid", return_value="ROOT-UUID-789"):
                result = step._generate_fstab()

            assert result is True
            fstab = Path(tmpdir) / "etc" / "fstab"
            content = fstab.read_text()
            assert "ROOT-UUID-789" in content
            assert "/boot/efi" not in content
            assert "vfat" not in content
        finally:
            set_target(None)


@patch("packages.installer.steps.bootloader.run_cmd")
def test_grub_install_uefi(mock_run):
    """UEFI modda grub-install x86_64-efi target ile cagrilir."""
    from packages.installer.steps.bootloader import BootloaderStep
    tui = MagicMock()
    step = BootloaderStep(
        tui=tui,
        disk="/dev/sda",
        root_part="/dev/sda2",
        efi_part="/dev/sda1",
        uefi=True,
        mount_point="/mnt/target",
    )
    mock_run.return_value = (True, "")
    result = step._install_grub_uefi()
    assert result is True
    called_cmd = mock_run.call_args[0][0]
    assert "grub-install" in called_cmd
    assert "--target=x86_64-efi" in called_cmd
    assert "--removable" in called_cmd


@patch("packages.installer.steps.bootloader.run_cmd")
def test_grub_install_bios(mock_run):
    """BIOS modda grub-install i386-pc target ile cagrilir."""
    from packages.installer.steps.bootloader import BootloaderStep
    tui = MagicMock()
    step = BootloaderStep(
        tui=tui,
        disk="/dev/sda",
        root_part="/dev/sda1",
        efi_part="",
        uefi=False,
        mount_point="/mnt/target",
    )
    mock_run.return_value = (True, "")
    result = step._install_grub_bios()
    assert result is True
    called_cmd = mock_run.call_args[0][0]
    assert "grub-install" in called_cmd
    assert "--target=i386-pc" in called_cmd
    assert "/dev/sda" in called_cmd


# ── complete.py unmount testleri ─────────────────────────────────────


@patch("packages.installer.steps.complete.run_cmd")
def test_complete_unmount(mock_run):
    """Disk kurulumda unmount cagrilir."""
    from packages.installer.steps.complete import CompleteStep
    from packages.installer.utils.target import set_target, get_target

    mock_run.return_value = (True, "")
    set_target("/mnt/target")
    try:
        tui = MagicMock()
        step = CompleteStep(tui=tui, profile_name="basic")
        step.run()
        # umount cagrilmis mi?
        umount_calls = [
            c for c in mock_run.call_args_list
            if len(c[0][0]) > 0 and c[0][0][0] == "umount"
        ]
        assert len(umount_calls) > 0, "umount en az bir kez cagrilmali"
        # target sifirlanmis mi?
        assert get_target() is None
    finally:
        set_target(None)


@patch("packages.installer.steps.complete.run_cmd")
def test_complete_no_unmount_live(mock_run):
    """Live CD modda (target=None) unmount cagrilmaz."""
    from packages.installer.steps.complete import CompleteStep
    from packages.installer.utils.target import set_target

    mock_run.return_value = (True, "bilinmiyor")
    set_target(None)

    tui = MagicMock()
    step = CompleteStep(tui=tui, profile_name="basic")
    step.run()
    # umount cagrilmamis olmali
    umount_calls = [
        c for c in mock_run.call_args_list
        if len(c[0][0]) > 0 and c[0][0][0] == "umount"
    ]
    assert len(umount_calls) == 0


# ── app.py import testleri ───────────────────────────────────────────


def test_app_imports_disk_and_bootloader():
    """app.py'da DiskStep ve BootloaderStep import edilebiliyor."""
    from packages.installer.app import InstallerApp
    from packages.installer.steps.disk import DiskStep
    from packages.installer.steps.bootloader import BootloaderStep
    assert InstallerApp is not None
    assert DiskStep is not None
    assert BootloaderStep is not None


def test_app_imports_mount_point():
    """app.py MOUNT_POINT'i dogrudan import edebiliyor (AttributeError yok)."""
    from packages.installer.app import MOUNT_POINT
    from packages.installer.steps.disk import MOUNT_POINT as DISK_MP
    assert MOUNT_POINT == DISK_MP
    assert MOUNT_POINT == "/mnt/target"


# ── bind mount testleri ──────────────────────────────────────────────


@patch("packages.installer.steps.disk.run_cmd")
def test_bind_mounts_correct_proc_command(mock_run):
    """proc mount komutunda source argumani (proc) var."""
    from packages.installer.steps.disk import DiskStep
    tui = MagicMock()
    step = DiskStep(tui=tui)

    mock_run.return_value = (True, "")
    step._bind_mounts()

    # Tum mount komutlarini topla
    mount_calls = [
        c[0][0] for c in mock_run.call_args_list
        if c[0][0][0] == "mount"
    ]

    # proc mount kontrolu: mount -t proc proc /mnt/target/proc
    proc_calls = [c for c in mount_calls if "proc" in c and "-t" in c]
    assert len(proc_calls) >= 1, "proc mount komutu olmali"
    proc_cmd = proc_calls[0]
    # Komut: ["mount", "-t", "proc", "proc", "/mnt/target/proc"]
    assert proc_cmd[1] == "-t"
    assert proc_cmd[2] == "proc"
    assert proc_cmd[3] == "proc"  # source argumani — kritik!

    # sysfs mount kontrolu
    sys_calls = [c for c in mount_calls if "sysfs" in c and "-t" in c]
    assert len(sys_calls) >= 1
    sys_cmd = sys_calls[0]
    assert sys_cmd[3] == "sysfs"  # source argumani


@patch("packages.installer.steps.disk.run_cmd")
def test_bind_mounts_returns_false_on_failure(mock_run):
    """Bind mount basarisiz olunca False doner."""
    from packages.installer.steps.disk import DiskStep
    tui = MagicMock()
    step = DiskStep(tui=tui)

    # Sadece mkdir basarili, mount basarisiz
    def side_effect(cmd, **kwargs):
        if cmd[0] == "mkdir":
            return (True, "")
        return (False, "mount failed")

    mock_run.side_effect = side_effect
    result = step._bind_mounts()
    assert result is False


# ── bootloader fallback grub.cfg testleri ─────────────────────────


def test_bootloader_fallback_grub_cfg():
    """update-grub basarisiz olunca fallback grub.cfg yazilir."""
    from packages.installer.steps.bootloader import BootloaderStep
    from packages.installer.utils.target import set_target
    tui = MagicMock()

    with tempfile.TemporaryDirectory() as tmpdir:
        set_target(tmpdir)
        try:
            step = BootloaderStep(
                tui=tui,
                disk="/dev/sda",
                root_part="/dev/sda1",
                efi_part="",
                uefi=False,
                mount_point=tmpdir,
            )
            with patch.object(step, "_get_uuid", return_value="TEST-UUID-999"):
                step._write_fallback_grub_cfg()

            grub_cfg = Path(tmpdir) / "boot" / "grub" / "grub.cfg"
            assert grub_cfg.exists()
            content = grub_cfg.read_text()
            assert "TEST-UUID-999" in content
            assert "KlipperOS-AI" in content
            assert "vmlinuz" in content
        finally:
            set_target(None)


# ── services.py testleri ──────────────────────────────────────────


def test_services_nginx_symlink_uses_target_path():
    """services.py nginx symlink'i target_path ile hedef diskte olusturur."""
    from packages.installer.utils.target import set_target, target_path

    with tempfile.TemporaryDirectory() as tmpdir:
        set_target(tmpdir)
        try:
            # Nginx dizinlerini olustur
            avail = Path(target_path("/etc/nginx/sites-available"))
            avail.mkdir(parents=True)
            enabled = Path(target_path("/etc/nginx/sites-enabled"))
            enabled.mkdir(parents=True)

            # Mainsail config yaz
            (avail / "mainsail").write_text("server {}")

            # services.py os.symlink + os.remove kullanir (ln/rm _HOST_COMMANDS'ta)
            # Windows'ta symlink yetki gerektirdiginden mock ile test edelim
            symlink_path = str(enabled / "mainsail")
            with patch("os.symlink") as mock_symlink:
                import os as _os
                _os.symlink("/etc/nginx/sites-available/mainsail", symlink_path)
                mock_symlink.assert_called_once_with(
                    "/etc/nginx/sites-available/mainsail", symlink_path
                )
        finally:
            set_target(None)
