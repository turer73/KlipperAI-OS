#!/usr/bin/env python3
"""Quick serial debug: login, cancel installer, check /run/live for squashfs."""
import socket
import time
import re
import sys

# Fix Windows encoding
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

HOST, PORT = "127.0.0.1", 5555
ANSI_RE = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]|\x1b\([AB012]|\x0f|\x0e')

def clean(data: bytes) -> str:
    text = data.decode("utf-8", errors="replace")
    return ANSI_RE.sub('', text)

def send(sock, text, delay=1.0):
    sock.sendall((text + '\r').encode())
    time.sleep(delay)

def send_ctrl_c(sock, delay=1.0):
    sock.sendall(b'\x03')  # Ctrl+C
    time.sleep(delay)

def recv_all(sock, timeout=3.0):
    sock.settimeout(timeout)
    chunks = []
    try:
        while True:
            data = sock.recv(4096)
            if not data:
                break
            chunks.append(data)
    except socket.timeout:
        pass
    return clean(b''.join(chunks))

def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((HOST, PORT))
    print(f"Connected to {HOST}:{PORT}")

    # Clear buffer
    recv_all(sock, 1.0)

    # Send Enter to get login prompt
    send(sock, '', 2.0)
    out = recv_all(sock, 3.0)
    print(f"[Initial]: ...{out[-100:]}")

    # Login
    send(sock, 'klipper', 1.0)
    out = recv_all(sock, 2.0)
    print(f"[After user]: ...{out[-100:]}")

    send(sock, 'klipper', 5.0)
    out = recv_all(sock, 5.0)
    print(f"[After pass]: ...{out[-200:]}")

    # Cancel installer with Ctrl+C multiple times
    print("\n--- Cancelling installer with Ctrl+C ---")
    for i in range(5):
        send_ctrl_c(sock, 1.0)
    time.sleep(2)
    out = recv_all(sock, 3.0)
    print(f"[After Ctrl+C]: ...{out[-200:]}")

    # Try to get a shell prompt
    send(sock, '', 1.0)
    out = recv_all(sock, 2.0)
    print(f"[Shell check]: ...{out[-200:]}")

    # If still in installer, try more aggressive escape
    if 'Kurulum' in out or 'Installer' in out or '$' not in out:
        print("--- Still in installer, trying Ctrl+C again ---")
        for i in range(10):
            send_ctrl_c(sock, 0.5)
        time.sleep(3)
        out = recv_all(sock, 3.0)
        print(f"[After more Ctrl+C]: ...{out[-200:]}")

    # Now run diagnostic commands
    commands = [
        "echo '=== SQUASHFS DEBUG ==='",
        "ls -la /run/live/ 2>&1",
        "ls -la /run/live/medium/ 2>&1",
        "ls -la /run/live/medium/live/ 2>&1",
        "ls -la /run/live/rootfs/ 2>&1",
        "find /run/live -maxdepth 3 -name '*.squashfs' 2>&1",
        "find / -maxdepth 5 -name 'filesystem.squashfs' 2>/dev/null",
        "mount | grep -E 'live|squash|cdrom|sr0|overlay'",
        "cat /proc/mounts | grep -E 'live|squash|sr0|cdrom|overlay'",
        "ls -la /cdrom/ 2>&1",
        "ls -la /lib/live/ 2>&1",
        "ls -la /lib/live/mount/ 2>&1",
        "ls -la /lib/live/mount/medium/ 2>&1",
        "ls -la /lib/live/mount/medium/live/ 2>&1",
        "findmnt -t squashfs 2>&1",
        "findmnt /run/live/medium 2>&1",
        "blkid 2>&1",
        "lsblk 2>&1",
    ]

    for cmd in commands:
        print(f"\n{'='*60}")
        print(f"CMD: {cmd}")
        print('='*60)
        send(sock, cmd, 2.0)
        out = recv_all(sock, 5.0)
        # Print output, skip echoed command
        for line in out.strip().split('\n'):
            stripped = line.strip()
            if stripped and not stripped.startswith(cmd[:15]):
                print(stripped)

    sock.close()
    print("\n\nDone!")

if __name__ == "__main__":
    main()
