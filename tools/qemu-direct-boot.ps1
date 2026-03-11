$iso = "C:\linux_ai\klipperos-v4.0.0-netinstall.iso"
$disk = "C:\linux_ai\test-disk.qcow2"
$kernel = "C:\linux_ai\qemu-boot\vmlinuz"
$initrd = "C:\linux_ai\qemu-boot\initrd.img"
$qemu = "C:\Users\sevdi\scoop\apps\qemu\current\qemu-system-x86_64.exe"

# Fresh test disk
if (Test-Path $disk) { Remove-Item $disk -Force }
& "C:\Users\sevdi\scoop\apps\qemu\current\qemu-img.exe" create -f qcow2 $disk 20G

Start-Process -FilePath $qemu -ArgumentList @(
    "-m", "2G",
    "-smp", "2",
    "-cpu", "max",
    "-cdrom", $iso,
    "-kernel", $kernel,
    "-initrd", $initrd,
    "-append", "boot=live components toram console=ttyS0,115200 locales=tr_TR.UTF-8 keyboard-layouts=tr",
    "-drive", "file=$disk,if=virtio,format=qcow2",
    "-nic", "user,model=virtio-net-pci",
    "-serial", "tcp::5555,server,nowait",
    "-display", "sdl"
) -WindowStyle Normal

Write-Host "QEMU started with direct kernel boot"
