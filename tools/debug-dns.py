#!/usr/bin/env python3
"""Debug DNS resolution inside the QEMU guest.
Connect to serial, send Ctrl+C to break installer, then check DNS config."""
import socket
import time
import re
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

HOST, PORT = "127.0.0.1", 5555
ANSI_RE = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]|\x1b\([AB012]|\x0f|\x0e')

def clean(data: bytes) -> str:
    return ANSI_RE.sub('', data.decode("utf-8", errors="replace"))

def send(sock, text, delay=1.0):
    sock.sendall((text + '\r').encode())
    time.sleep(delay)

def send_ctrl_c(sock, delay=0.5):
    sock.sendall(b'\x03')
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

    # Break out of installer
    print("\n--- Sending Ctrl+C to break installer ---")
    for _ in range(10):
        send_ctrl_c(sock, 0.3)
    time.sleep(2)
    recv_all(sock, 2.0)

    # Try to get shell
    send(sock, '', 1.0)
    out = recv_all(sock, 2.0)
    print(f"[After break]: ...{out[-200:]}")

    # If no shell prompt, try logging in
    if '$' not in out and '#' not in out:
        print("No shell prompt, trying new login...")
        # Try sending newlines to get login prompt
        for _ in range(3):
            send(sock, '', 1.0)
        out = recv_all(sock, 2.0)
        if 'login:' in out:
            send(sock, 'klipper', 1.0)
            recv_all(sock, 1.0)
            send(sock, 'klipper', 3.0)
            out = recv_all(sock, 3.0)
            print(f"[Login]: ...{out[-200:]}")
        # Cancel installer
        for _ in range(10):
            send_ctrl_c(sock, 0.3)
        time.sleep(2)
        out = recv_all(sock, 2.0)

    # Now run diagnostic commands
    commands = [
        "echo '=== RESOLV.CONF IN CHROOT ==='",
        "cat /mnt/target/etc/resolv.conf 2>&1",
        "ls -la /mnt/target/etc/resolv.conf 2>&1",
        "file /mnt/target/etc/resolv.conf 2>&1",
        "echo '=== HOST RESOLV.CONF ==='",
        "cat /etc/resolv.conf 2>&1",
        "ls -la /etc/resolv.conf 2>&1",
        "echo '=== UPSTREAM RESOLV ==='",
        "cat /run/systemd/resolve/resolv.conf 2>&1",
        "echo '=== NSSWITCH.CONF IN CHROOT ==='",
        "grep hosts /mnt/target/etc/nsswitch.conf 2>&1",
        "echo '=== HOST NSSWITCH ==='",
        "grep hosts /etc/nsswitch.conf 2>&1",
        "echo '=== DNS TEST FROM HOST ==='",
        "host archive.ubuntu.com 2>&1 || nslookup archive.ubuntu.com 2>&1 || echo 'no DNS tools'",
        "echo '=== DNS TEST FROM CHROOT ==='",
        "chroot /mnt/target host archive.ubuntu.com 2>&1 || chroot /mnt/target nslookup archive.ubuntu.com 2>&1 || echo 'no DNS in chroot'",
        "echo '=== PING TEST ==='",
        "ping -c 1 -W 2 8.8.8.8 2>&1",
        "echo '=== APT TEST IN CHROOT ==='",
        "chroot /mnt/target apt-get update -o Debug::Acquire::http=true 2>&1 | head -20",
    ]

    for cmd in commands:
        print(f"\n{'='*60}")
        print(f"CMD: {cmd}")
        print('='*60)
        send(sock, cmd, 2.0)
        out = recv_all(sock, 8.0)
        for line in out.strip().split('\n'):
            stripped = line.strip()
            if stripped and not stripped.startswith(cmd[:20]):
                print(stripped)

    sock.close()
    print("\n\nDone!")

if __name__ == "__main__":
    main()
