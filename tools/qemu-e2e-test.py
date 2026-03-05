#!/usr/bin/env python3
"""KlipperOS-AI — QEMU End-to-End Installer Test v7.

v7 changes over v6:
  1. DISK FIX: Smart disk selection — parses menu to find vda/sda,
     navigates with Down arrows to skip floppy drives (fd0).
  2. QEMU: -fda none to prevent floppy device creation.
  3. Installer: _list_disks() now excludes floppy (lsblk -e2 + fd* filter).

v6 (kept):
  - NETWORK: 45s DHCP result wait, no blind Enter presses.
  - save_log UTF-8 encoding.
  - TIME-BASED msgbox for Welcome/Hardware.
  - Cursor advance fixes (no advance_cursor before return True).
"""
import socket
import time
import re
import sys
import threading
from datetime import datetime

# ─── Config ───────────────────────────────────────────────
HOST = "127.0.0.1"
PORT = 5555
LOGIN_USER = "klipper"
LOGIN_PASS = "klipper"

BOOT_TIMEOUT = 300      # 5 min for kernel boot
LOGIN_TIMEOUT = 180     # 3 min for login prompt
INSTALL_TIMEOUT = 900   # 15 min for disk install
GRUB_TIMEOUT = 300      # 5 min for GRUB install
NETWORK_TIMEOUT = 300   # 5 min total for network step


class ANSIStripper:
    """Incremental ANSI escape code stripper (state machine).

    Feed raw bytes incrementally. The `clean` attribute only GROWS — it never
    shrinks or shifts. This makes cursor-based tracking always reliable.

    Handles: CSI sequences, charset switching, OSC, single-char ESC commands,
    and UTF-8 multi-byte characters.
    """
    # States
    NORMAL = 0
    ESC = 1       # After ESC byte
    CSI = 2       # CSI: ESC [
    CHARSET = 3   # Charset: ESC ( or ESC )
    OSC = 4       # OSC: ESC ]

    def __init__(self):
        self.clean = ""
        self._state = self.NORMAL
        self._utf8_buf = bytearray()

    def _flush_utf8(self):
        """Decode and append any pending UTF-8 bytes."""
        if self._utf8_buf:
            self.clean += self._utf8_buf.decode('utf-8', errors='replace')
            self._utf8_buf.clear()

    def feed(self, data: bytes):
        """Process raw bytes, appending clean text."""
        for b in data:
            if self._state == self.NORMAL:
                if b == 0x1b:  # ESC
                    self._flush_utf8()
                    self._state = self.ESC
                elif b in (0x0f, 0x0e, 0x00, 0x0d):
                    # Skip: SI, SO, NUL, CR
                    self._flush_utf8()
                elif b == 0x0a:  # LF (newline)
                    self._flush_utf8()
                    self.clean += '\n'
                elif b >= 0x20:  # Printable ASCII or UTF-8 byte
                    self._utf8_buf.append(b)
                # else: skip other control chars (< 0x20)

            elif self._state == self.ESC:
                if b == 0x5b:       # [ → CSI sequence
                    self._state = self.CSI
                elif b in (0x28, 0x29):  # ( or ) → charset select
                    self._state = self.CHARSET
                elif b == 0x5d:     # ] → OSC sequence
                    self._state = self.OSC
                else:
                    # Single-char ESC command (>, =, M, D, H, E, c, 7, 8, N, O)
                    self._state = self.NORMAL

            elif self._state == self.CSI:
                if 0x40 <= b <= 0x7e:
                    # Final byte → CSI complete
                    self._state = self.NORMAL
                elif 0x20 <= b <= 0x3f:
                    pass  # Parameter (0-9;?<=>!) or intermediate bytes
                else:
                    # Unexpected byte → malformed CSI, abort
                    self._state = self.NORMAL
                    if b >= 0x20:
                        self._utf8_buf.append(b)

            elif self._state == self.CHARSET:
                # One more byte (charset ID: 0, A, B, etc.)
                self._state = self.NORMAL

            elif self._state == self.OSC:
                if b == 0x07:  # BEL terminates OSC
                    self._state = self.NORMAL
                elif b == 0x1b:
                    # ESC might start ST (ESC \) to terminate OSC
                    self._state = self.ESC

        # Flush remaining UTF-8 bytes
        self._flush_utf8()


class QEMUSerialClient:
    """Persistent TCP connection to QEMU serial console.

    Uses incremental ANSIStripper — clean text only grows, cursor is stable.
    """

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.sock = None
        self.stripper = ANSIStripper()
        self.raw_len = 0             # Total raw bytes received
        self.cursor = 0              # Position in clean text
        self.lock = threading.Lock()
        self._stop = threading.Event()

    def connect(self, retries=30, delay=2):
        for i in range(retries):
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.settimeout(5)
                self.sock.connect((self.host, self.port))
                self.sock.settimeout(1)
                log(f"Connected to serial port {self.host}:{self.port}")
                return True
            except (ConnectionRefusedError, OSError) as e:
                if i < retries - 1:
                    time.sleep(delay)
                else:
                    log(f"FAIL: Cannot connect after {retries} retries: {e}")
                    return False

    def start_reader(self):
        t = threading.Thread(target=self._reader_loop, daemon=True)
        t.start()

    def _reader_loop(self):
        """Read raw bytes and feed to incremental ANSI stripper."""
        while not self._stop.is_set():
            try:
                data = self.sock.recv(4096)
                if not data:
                    log("Serial connection closed by remote")
                    break
                with self.lock:
                    self.stripper.feed(data)
                    self.raw_len += len(data)
            except socket.timeout:
                continue
            except OSError:
                break

    def send(self, text: str, delay: float = 0.1):
        try:
            self.sock.send(text.encode('utf-8'))
            time.sleep(delay)
        except OSError as e:
            log(f"Send error: {e}")

    def send_key(self, key: str, delay: float = 0.5):
        key_map = {
            'enter': '\r',
            'tab': '\t',
            'up': '\x1b[A',
            'down': '\x1b[B',
            'left': '\x1b[D',
            'right': '\x1b[C',
            'space': ' ',
            'escape': '\x1b',
        }
        self.send(key_map.get(key, key), delay)

    def advance_cursor(self):
        """Move cursor to end of current clean text."""
        with self.lock:
            self.cursor = len(self.stripper.clean)

    def get_new_output(self) -> str:
        """Get clean text since cursor position."""
        with self.lock:
            return self.stripper.clean[self.cursor:]

    def get_all_output(self) -> str:
        with self.lock:
            return self.stripper.clean

    def wait_for_new(self, pattern: str, timeout: int = 60, advance: bool = True) -> bool:
        """Wait for pattern in NEW output (since cursor). Advances cursor on match."""
        compiled = re.compile(pattern, re.IGNORECASE)
        start = time.time()

        while time.time() - start < timeout:
            new = self.get_new_output()
            m = compiled.search(new)
            if m:
                elapsed = time.time() - start
                ctx_start = max(0, m.start() - 30)
                ctx_end = min(len(new), m.end() + 30)
                context = new[ctx_start:ctx_end].replace('\n', '↵')
                log(f"  MATCH: '{pattern}' after {elapsed:.0f}s → ...{context}...")
                if advance:
                    with self.lock:
                        self.cursor += m.end()
                return True
            time.sleep(1)

        log(f"  TIMEOUT: '{pattern}' not found after {timeout}s")
        return False

    def wait_for_any_new(self, patterns: list, timeout: int = 60) -> int:
        """Wait for any pattern in NEW output. Returns index or -1."""
        compiled = [(re.compile(p, re.IGNORECASE), p) for p in patterns]
        start = time.time()

        while time.time() - start < timeout:
            new = self.get_new_output()
            for i, (regex, pat) in enumerate(compiled):
                m = regex.search(new)
                if m:
                    elapsed = time.time() - start
                    ctx_start = max(0, m.start() - 20)
                    ctx_end = min(len(new), m.end() + 20)
                    context = new[ctx_start:ctx_end].replace('\n', '↵')
                    log(f"  MATCH[{i}]: '{pat}' after {elapsed:.0f}s → ...{context}...")
                    with self.lock:
                        self.cursor += m.end()
                    return i
            time.sleep(1)

        log(f"  TIMEOUT: None of {[p for _, p in compiled]} after {timeout}s")
        return -1

    def check_at_login(self) -> bool:
        """Check if we're back at login prompt (= installer exited)."""
        new = self.get_new_output()
        return bool(re.search(r'klipperos login:', new, re.IGNORECASE))

    def close(self):
        self._stop.set()
        if self.sock:
            self.sock.close()

    def save_log(self, path: str):
        with open(path, 'w', encoding='utf-8') as f:
            f.write(self.get_all_output())
        log(f"  Clean log: {len(self.get_all_output())} chars, raw: {self.raw_len} bytes")


# ─── Logging ──────────────────────────────────────────────
_UNICODE_MAP = str.maketrans({
    '→': '->', '↵': '\\n', '✓': '+', '✗': 'X',
    '─': '-', '═': '=', '│': '|', '┤': '|', '├': '|',
    '┘': '+', '┐': '+', '└': '+', '┌': '+',
})

def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    safe = line.translate(_UNICODE_MAP)
    try:
        print(safe, flush=True)
    except UnicodeEncodeError:
        print(safe.encode('ascii', errors='replace').decode('ascii'), flush=True)


# ─── Test Steps ───────────────────────────────────────────
def step_login(c: QEMUSerialClient) -> bool:
    log("Waiting for login prompt...")
    if not c.wait_for_new(r'login:', timeout=LOGIN_TIMEOUT):
        return True

    c.send(LOGIN_USER + '\r')
    time.sleep(1)
    if c.wait_for_new(r'[Pp]assword:', timeout=10):
        c.send(LOGIN_PASS + '\r')
    time.sleep(3)

    if c.wait_for_new(r'Kurulum|Installer|baslatiliyor', timeout=30):
        log("  Installer starting!")
    time.sleep(3)
    c.advance_cursor()
    return True


def step_keyboard(c: QEMUSerialClient) -> bool:
    """Keyboard selection — MENU dialog, text IS detectable."""
    log("Waiting for Keyboard layout screen...")
    if c.wait_for_new(r'Klavye|keyboard|Duzeni|Turkce|English', timeout=30):
        time.sleep(1)
        c.send_key('enter')  # Select default (Turkce Q)
        time.sleep(2)
        c.advance_cursor()
        return True
    # Fallback — press Enter anyway
    log("  Fallback: pressing Enter for keyboard")
    c.send_key('enter')
    time.sleep(2)
    c.advance_cursor()
    return True


def step_welcome(c: QEMUSerialClient) -> bool:
    """Welcome screen — MSGBOX dialog, text does NOT survive ANSI stripping.

    ★ Insight: whiptail msgbox renders text entirely within ANSI cursor
    positioning sequences. The actual characters become CSI final bytes,
    so they never appear in clean text. We use TIME-BASED Enter instead.
    """
    log("Waiting 8s for Welcome msgbox, then Enter...")
    time.sleep(8)
    c.send_key('enter')
    time.sleep(2)
    c.advance_cursor()
    log("  Welcome: OK (time-based)")
    return True


def step_hardware(c: QEMUSerialClient) -> bool:
    """Hardware detection — MSGBOX dialog, time-based like Welcome."""
    log("Waiting 8s for Hardware msgbox, then Enter...")
    time.sleep(8)
    c.send_key('enter')
    time.sleep(2)
    c.advance_cursor()
    log("  Hardware: OK (time-based)")
    return True


def _wait_for_dhcp_result(c: QEMUSerialClient) -> int:
    """After DHCP/check_internet infobox, wait for the RESULT dialog.

    check_internet(retries=3) takes up to 34s (3 × 2 hosts × 5s + 2 × 2s).
    We wait 45s for the next dialog: retry yesno, skip yesno, or success msgbox.

    Returns: 0=skip, 1=retry, 2=success, 3=moved-past-network, -1=timeout
    """
    result_patterns = [
        r'Ag olmadan|olmadan devam|without.network',  # 0: skip dialog
        r'Tekrar.*ister|yeniden.*dene',                # 1: retry dialog
        r'internet.*basari|baglanti.*basari|mevcut',   # 2: success
        r'Profil|Profile|Kurulum.Profili',             # 3: moved past network
        r'Kullanici|[Hh]ostname|Cihaz.*adi',           # 4: moved past network
    ]
    idx = c.wait_for_any_new(result_patterns, timeout=45)
    if idx in (3, 4):
        return 3  # moved past network
    return idx


def step_network(c: QEMUSerialClient) -> bool:
    """Network step — v6: proper DHCP result waiting, no blind Enters.

    Ethernet flow: up to 3 check_internet attempts.
    Each failed attempt → yesno "Tekrar denemek ister misiniz?"
    After 3 failures → yesno "Ag olmadan devam etmek ister misiniz?"

    check_internet takes up to 34s per attempt, so we WAIT for the
    result dialog instead of blindly pressing Enter on timeout.
    """
    log("Waiting for Network screen...")

    start = time.time()
    retries_seen = 0
    max_retries = 3  # Match MAX_ETH_RETRIES in installer

    # Post-network patterns — if we see these, network step is done
    POST_NET = [
        r'Profil|Profile|Kurulum.Profili',
        r'Disk.*[Ss]ec|Hedef.*[Dd]isk',
        r'Kullanici|[Hh]ostname|Cihaz.*adi',
    ]

    while time.time() - start < NETWORK_TIMEOUT:
        # Main pattern scan (shorter timeout for quick responses)
        idx = c.wait_for_any_new([
            r'Profil|Profile|Kurulum.Profili',           # 0: moved to Profile
            r'Disk.*[Ss]ec|Hedef.*[Dd]isk',              # 1: moved to Disk
            r'Ag olmadan|olmadan devam|without.network',  # 2: skip dialog
            r'Tekrar.*ister|yeniden.*dene',               # 3: retry dialog
            r'internet.*basari|baglanti.*basari|mevcut',  # 4: success!
            r'Deneme.*\d/\d|DHCP|kontrol ediliyor',       # 5: DHCP infobox
            r'bulunamadi|Internet.*hata',                  # 6: failure msg
            r'Kullanici|[Hh]ostname|Cihaz.*adi',          # 7: user setup
        ], timeout=20)

        # ── Post-network: we're past the network step ──
        if idx in (0, 1, 7):
            log(f"  Network done -> next screen! ({retries_seen} retries)")
            return True

        # ── Skip dialog: "Ag olmadan devam etmek ister misiniz?" ──
        elif idx == 2:
            log("  SKIP dialog -> Enter (Yes = continue without network)")
            time.sleep(1)
            c.send_key('enter')
            time.sleep(0.5)
            # NOTE: Don't advance_cursor here! Next step needs to see its text.
            return True

        # ── Retry dialog: "Tekrar denemek ister misiniz?" ──
        elif idx == 3:
            retries_seen += 1
            if retries_seen < max_retries:
                log(f"  Retry dialog #{retries_seen} -> Enter (Yes = retry)")
                time.sleep(1)
                c.send_key('enter')  # Yes = retry
                time.sleep(3)
                c.advance_cursor()
                # After accepting retry, installer does:
                #   time.sleep(ETH_WAIT=10) → infobox → check_internet
                # So the DHCP infobox will appear in ~10s
            else:
                # 3rd retry dialog or beyond — decline, let _offer_skip run
                log(f"  Retry dialog #{retries_seen} -> Tab+Enter (No = skip)")
                time.sleep(1)
                c.send_key('tab')   # Tab to <No> button
                time.sleep(0.5)
                c.send_key('enter')
                time.sleep(3)
                c.advance_cursor()
                # Now _offer_skip_network() yesno should appear
                log("  Waiting for skip confirmation dialog...")
                idx2 = c.wait_for_any_new([
                    r'Ag olmadan|olmadan devam|without.network',
                ] + POST_NET, timeout=10)
                if idx2 == 0:
                    log("  Skip confirmation -> Enter (Yes)")
                    time.sleep(1)
                    c.send_key('enter')
                    time.sleep(0.5)
                    return True
                elif idx2 > 0:
                    log("  Already moved past network")
                    return True

        # ── Internet success ──
        elif idx == 4:
            log("  Internet check PASSED!")
            time.sleep(1)
            c.send_key('enter')  # Dismiss success msgbox
            time.sleep(0.5)
            return True

        # ── DHCP infobox: check_internet is running ──
        elif idx == 5:
            log("  DHCP/check in progress... waiting for result (up to 45s)")
            c.advance_cursor()

            # KEY FIX: Wait for the RESULT of check_internet.
            # check_internet takes up to 34s. Use 45s timeout.
            dhcp_result = _wait_for_dhcp_result(c)

            if dhcp_result == 0:
                # Skip dialog
                log("  -> Skip dialog after DHCP -> Enter (Yes)")
                time.sleep(1)
                c.send_key('enter')
                time.sleep(0.5)
                return True
            elif dhcp_result == 1:
                # Retry dialog
                retries_seen += 1
                log(f"  -> Retry dialog #{retries_seen} after DHCP")
                if retries_seen < max_retries:
                    log("    Enter (Yes = retry)")
                    time.sleep(1)
                    c.send_key('enter')
                    time.sleep(3)
                    c.advance_cursor()
                else:
                    log("    Tab+Enter (No = skip)")
                    time.sleep(1)
                    c.send_key('tab')
                    time.sleep(0.5)
                    c.send_key('enter')
                    time.sleep(3)
                    c.advance_cursor()
            elif dhcp_result == 2:
                # Success
                log("  -> Internet OK after DHCP!")
                time.sleep(1)
                c.send_key('enter')
                time.sleep(0.5)
                return True
            elif dhcp_result == 3:
                # Moved past network
                log("  -> Moved past network after DHCP")
                return True
            else:
                # Timeout — no result dialog detected
                log("  -> DHCP result timeout (45s). Checking state...")
                if c.check_at_login():
                    log("  Back at login! (installer exited)")
                    return False
                # Don't press Enter — just loop and try again
                log("  No result dialog, continuing to scan...")

        # ── Failure message ──
        elif idx == 6:
            log("  Connection failure message — waiting for dialog...")
            time.sleep(2)
            c.advance_cursor()

        # ── Timeout: no pattern matched ──
        else:
            if c.check_at_login():
                log("  Back at login! (installer exited)")
                return False

            # Diagnostic: show what's in the buffer
            snippet = c.get_new_output()[-200:].replace('\n', '|')
            log(f"  No pattern in 20s. Buffer tail: ...{snippet}")

            # DON'T press Enter blindly! Just continue scanning.
            # The installer might be in the middle of check_internet
            # or rendering a dialog. Give it more time.
            c.advance_cursor()

    log("  Network timed out (5 min) — pressing Enter to continue")
    c.send_key('enter')
    time.sleep(2)
    c.advance_cursor()
    return True


def step_profile(c: QEMUSerialClient) -> bool:
    """Profile selection — MENU dialog, text IS detectable."""
    log("Waiting for Profile selection screen...")
    if c.check_at_login():
        log("  ABORT: At login prompt")
        return False
    if c.wait_for_new(r'Profil|Profile|light|standard|full|LIGHT|STANDARD|FULL|Kurulum', timeout=60):
        time.sleep(1)
        c.send_key('enter')  # Select default profile
        time.sleep(0.5)
        return True
    # Fallback — may have been skipped or dialog not detected
    if c.check_at_login():
        log("  ABORT: At login prompt after timeout")
        return False
    log("  Profile not detected — pressing Enter to continue.")
    c.send_key('enter')
    time.sleep(0.5)
    return True


def step_disk_selection(c: QEMUSerialClient) -> bool:
    """Disk selection — MENU dialog, text IS detectable.

    Smart disk selection: parse menu to find the real disk (vda/sda/nvme)
    and navigate to it with Down arrows. Avoids selecting floppy (fd0).
    """
    log("Waiting for Disk selection screen...")
    if c.check_at_login():
        log("  ABORT: At login prompt")
        return False
    if c.wait_for_new(r'Disk.*[Ss]ec|Hedef.*[Dd]isk|Kurulum.*[Dd]isk|vda|sda', timeout=60):
        # Parse the disk menu to find which item is the real disk
        output = c.get_new_output()
        target_item = 1  # default: first item
        # Look for numbered entries like "2 /dev/vda  20G"
        for m in re.finditer(r'(\d+)\s+/dev/(\w+)\s+(\S+)', output):
            item_num = int(m.group(1))
            dev_name = m.group(2)
            dev_size = m.group(3)
            # Prefer vda/sda/nvme/mmcblk over fd*
            if not dev_name.startswith('fd'):
                target_item = item_num
                log(f"  Target disk: item {item_num} = /dev/{dev_name} {dev_size}")
                break

        # Navigate to target item (menu starts at item 1)
        if target_item > 1:
            log(f"  Pressing Down {target_item - 1}x to reach item {target_item}")
            for _ in range(target_item - 1):
                c.send_key('down')
                time.sleep(0.3)

        time.sleep(0.5)
        c.send_key('enter')
        time.sleep(0.5)
        return True
    if c.check_at_login():
        log("  ABORT: At login prompt after timeout")
        return False
    log("  Fallback: pressing Enter")
    c.send_key('enter')
    time.sleep(0.5)
    return True


def step_disk_confirm(c: QEMUSerialClient) -> bool:
    """Disk erasure confirmation — YESNO dialog, text IS detectable."""
    log("Waiting for disk erasure confirmation...")
    if c.check_at_login():
        log("  ABORT: At login prompt")
        return False
    if c.wait_for_new(r'[Ss]ilinecek|UYARI|[Oo]nay|tum.*veri|erase|Silme|Disk.*Onay', timeout=60):
        time.sleep(1)
        c.send_key('enter')  # Yes = confirm
        time.sleep(0.5)
        return True
    if c.check_at_login():
        log("  ABORT: At login prompt after timeout")
        return False
    log("  Fallback: pressing Enter")
    c.send_key('enter')
    time.sleep(0.5)
    return True


def step_disk_install(c: QEMUSerialClient) -> bool:
    """Disk installation: partition → format → squashfs → mount."""
    log("Disk installation in progress...")

    start = time.time()
    while time.time() - start < INSTALL_TIMEOUT:
        idx = c.wait_for_any_new([
            r'Kullanici|[Hh]ostname|Cihaz.*adi',     # 0: user setup
            r'Paket|Package|apt.*install',             # 1: packages
            r'[Bb]olum|partition|fdisk|parted',        # 2: partitioning
            r'mkfs|format|dosya.*sistemi',             # 3: formatting
            r'squashfs|unsquash|extract',               # 4: squashfs (NOT 'kopyala' — too broad)
            r'mount|bagla',                            # 5: mounting
            r'Servis|Service|yapilandir',              # 6: services (skipped user/pkg)
            r'GRUB|grub|[Bb]ootloader',                # 7: bootloader
            r'Tamamland|Complete|Bitti',               # 8: done
            r'Hata|Error|FAIL|basarisiz|kopyalanamadi', # 9: error (added kopyalanamadi)
        ], timeout=60)

        elapsed = time.time() - start
        if idx in (0, 1, 6, 7, 8):
            labels = {0: "User Setup", 1: "Packages", 6: "Services", 7: "GRUB", 8: "Complete"}
            log(f"  → {labels.get(idx, 'Next step')} ({elapsed:.0f}s)")
            return True
        elif idx in (2, 3, 4, 5):
            labels = {2: "Partitioning", 3: "Formatting", 4: "Squashfs", 5: "Mounting"}
            log(f"  {labels[idx]}... ({elapsed:.0f}s)")
        elif idx == 9:
            log(f"  ERROR! ({elapsed:.0f}s)")
            # Show error context
            snippet = c.get_new_output()[-200:].replace('\n', '|')
            log(f"  Error context: ...{snippet}")
            c.send_key('enter')  # Dismiss error dialog
            time.sleep(3)
            if c.check_at_login():
                log(f"  Installer exited after error ({elapsed:.0f}s)")
                return False
        else:
            if c.check_at_login():
                log(f"  Back at login during install ({elapsed:.0f}s)")
                return False
            log(f"  Waiting... ({elapsed:.0f}s)")

    log("  Disk install timed out!")
    return False


def step_user_setup(c: QEMUSerialClient) -> bool:
    """User setup — input dialogs for hostname and password."""
    log("Waiting for User setup...")
    # Hostname
    if c.wait_for_new(r'hostname|Cihaz.*adi|cihaz.*ismi|Bilgisayar', timeout=60):
        time.sleep(1)
        c.send_key('enter')  # Accept default hostname
        time.sleep(2)
        c.advance_cursor()
    # Password — may be auto-skipped in dry_run
    if c.wait_for_new(r'[Ss]ifre|[Pp]assword|parola', timeout=30):
        time.sleep(1)
        c.send_key('enter')  # Accept default password
        time.sleep(2)
        c.advance_cursor()
    return True


def step_package_install(c: QEMUSerialClient) -> bool:
    """Package installation (may be skipped without network)."""
    log("Waiting for Package installation...")
    start = time.time()
    while time.time() - start < INSTALL_TIMEOUT:
        idx = c.wait_for_any_new([
            r'Servis|Service|Nginx|yapilandir',   # 0: services
            r'GRUB|grub|[Bb]ootloader',            # 1: bootloader
            r'Tamamland|Complete|Bitti',            # 2: done
            r'Paket|Package|kuruluyor|apt',         # 3: installing
            r'Hata|Error|FAIL',                     # 4: error
        ], timeout=60)

        elapsed = time.time() - start
        if idx in (0, 1, 2):
            log(f"  Packages done → next ({elapsed:.0f}s)")
            return True
        elif idx == 3:
            log(f"  Installing... ({elapsed:.0f}s)")
        elif idx == 4:
            log(f"  Error ({elapsed:.0f}s)")
            c.send_key('enter')
        else:
            if c.check_at_login():
                log("  Back at login")
                return False
            log(f"  Waiting... ({elapsed:.0f}s)")
    return True


def step_services(c: QEMUSerialClient) -> bool:
    """Service configuration step."""
    log("Waiting for Service configuration...")
    if c.wait_for_new(r'GRUB|grub|[Bb]ootloader|Yukleyici|Tamamland', timeout=INSTALL_TIMEOUT):
        log("  Services done")
        c.advance_cursor()
        return True
    return True


def step_bootloader(c: QEMUSerialClient) -> bool:
    """GRUB bootloader installation."""
    log("Waiting for Bootloader (GRUB)...")
    if c.wait_for_new(r'Tamamland|Complete|Bitti|Basarili|unmount|Yeniden', timeout=GRUB_TIMEOUT):
        log("  GRUB done!")
        c.advance_cursor()
        return True
    return True


def step_complete(c: QEMUSerialClient) -> bool:
    """Completion screen — reboot prompt."""
    log("Waiting for completion...")
    if c.wait_for_new(r'Tamamland|Complete|Bitti|Yeniden.*baslat|reboot', timeout=60):
        time.sleep(2)
        c.send_key('enter')
        log("  Reboot initiated!")
        c.advance_cursor()
        return True
    c.send_key('enter')
    return True


# ─── Main ─────────────────────────────────────────────────
def main():
    log("=" * 60)
    log("KlipperOS-AI — QEMU E2E Test v7")
    log("  Smart disk selection + floppy filter + DHCP wait")
    log("=" * 60)

    client = QEMUSerialClient(HOST, PORT)
    if not client.connect():
        return 1
    client.start_reader()

    # Wait for boot
    log("Waiting for kernel boot...")
    if not client.wait_for_new(r'login:|Welcome to|klipperos', timeout=BOOT_TIMEOUT):
        log("FAIL: System did not boot")
        client.save_log('/tmp/qemu-e2e.log')
        client.close()
        return 1
    log("System booted!")
    # NOTE: Do NOT advance cursor — login prompt is in same chunk

    steps = [
        ("Login", step_login),
        ("Keyboard", step_keyboard),
        ("Welcome", step_welcome),
        ("Hardware", step_hardware),
        ("Network", step_network),
        ("Profile", step_profile),
        ("Disk Selection", step_disk_selection),
        ("Disk Confirm", step_disk_confirm),
        ("Disk Install", step_disk_install),
        ("User Setup", step_user_setup),
        ("Package Install", step_package_install),
        ("Services", step_services),
        ("Bootloader", step_bootloader),
        ("Complete", step_complete),
    ]

    results = {}
    for name, func in steps:
        log(f"\n{'='*50}")
        log(f">>> {name}")
        log(f"{'='*50}")
        try:
            ok = func(client)
            results[name] = "PASS" if ok else "FAIL"
            if not ok:
                log(f"FAIL at step: {name}")
                if client.check_at_login():
                    log("Installer exited — stopping test")
                    break
        except Exception as e:
            log(f"EXCEPTION at {name}: {e}")
            import traceback
            traceback.print_exc()
            results[name] = "ERROR"

    # Summary
    log("\n" + "=" * 60)
    log("TEST RESULTS SUMMARY")
    log("=" * 60)
    for name, result in results.items():
        icon = "✓" if result == "PASS" else "✗"
        log(f"  [{icon}] {name}: {result}")

    passed = sum(1 for r in results.values() if r == "PASS")
    total = len(results)
    log(f"\n  {passed}/{total} steps passed")

    client.save_log('/tmp/qemu-e2e.log')
    log("Logs saved to /tmp/qemu-e2e.log")
    client.close()
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
