#!/usr/bin/env python3
"""Patch spaghetti_detect.py on server:
1. Lower no_extrusion threshold from 0.75 to 0.65
2. Add anomaly detection: if normal < 50% consistently, trigger pause
"""
import paramiko
import time

SERVER = "192.168.1.129"
USER = "klipperos"
PASS = "tur0452"
TARGET = "/opt/klipperos-ai/ai-monitor/spaghetti_detect.py"

# Patch 1: Lower no_extrusion threshold
OLD_THRESHOLDS = '''THRESHOLDS = {
    "spaghetti": 0.70,     # %70 guven -> duraklat
    "no_extrusion": 0.75,  # %75 guven -> duraklat
    "stringing": 0.80,     # %80 guven -> uyar
    "completed": 0.85,     # %85 guven -> tamamlandi bildir
}'''

NEW_THRESHOLDS = '''THRESHOLDS = {
    "spaghetti": 0.65,     # %65 guven -> duraklat (dusuruldu)
    "no_extrusion": 0.60,  # %60 guven -> duraklat (dusuruldu)
    "stringing": 0.75,     # %75 guven -> uyar (dusuruldu)
    "completed": 0.85,     # %85 guven -> tamamlandi bildir
}

# Anomali tespiti: normal sinif guveni bu esik altindaysa
# ve baska sinif kendi esigini gecmemisse -> anomali
NORMAL_LOW_THRESHOLD = 0.40   # Normal <%40 = siniflama belirsiz -> anomali'''

# Patch 2: Add anomaly detection to _process_scores
OLD_PROCESS_RETURN = '''        return {
            "class": predicted_class,
            "confidence": confidence,
            "action": action,
            "scores": class_scores,
        }'''

NEW_PROCESS_RETURN = '''        # Anomali tespiti: normal skoru cok dusukse VE hicbir sinif
        # kendi esigini gecmemisse -> bilinmeyen anomali -> pause
        if action == "none" and class_scores.get("normal", 1.0) < NORMAL_LOW_THRESHOLD:
            # En yuksek anomali sinifini bul (normal haricinde)
            anomaly_classes = {k: v for k, v in class_scores.items() if k != "normal"}
            if anomaly_classes:
                top_anomaly = max(anomaly_classes, key=anomaly_classes.get)
                top_score = anomaly_classes[top_anomaly]
                if top_score > 0.30:  # En az %30 bir anomali sinifi varsa
                    action = "pause"
                    predicted_class = top_anomaly
                    confidence = top_score
                    logger.warning(
                        "Anomali tespit: normal=%.1f%% < %d%%, en yuksek: %s=%.1f%%",
                        class_scores.get("normal", 0) * 100,
                        NORMAL_LOW_THRESHOLD * 100,
                        top_anomaly,
                        top_score * 100,
                    )

        return {
            "class": predicted_class,
            "confidence": confidence,
            "action": action,
            "scores": class_scores,
        }'''

def apply_patch():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(SERVER, username=USER, password=PASS)

    # Read current file
    sftp = ssh.open_sftp()
    with sftp.file(TARGET, 'r') as f:
        content = f.read().decode('utf-8')

    # Apply patches
    patched = content

    # Patch 1: Thresholds
    if OLD_THRESHOLDS in patched:
        patched = patched.replace(OLD_THRESHOLDS, NEW_THRESHOLDS)
        print("Patch 1: Thresholds updated")
    else:
        print("Patch 1: SKIP (already patched or not found)")

    # Patch 2: Anomaly detection
    if OLD_PROCESS_RETURN in patched:
        patched = patched.replace(OLD_PROCESS_RETURN, NEW_PROCESS_RETURN)
        print("Patch 2: Anomaly detection added")
    else:
        print("Patch 2: SKIP (already patched or not found)")

    # Write back
    if patched != content:
        with sftp.file(TARGET, 'w') as f:
            f.write(patched)
        print(f"\nPatched: {TARGET}")
    else:
        print("\nNo changes needed")

    sftp.close()

    # Restart service
    print("\nRestarting monitor service...")
    ssh.exec_command(f'echo {PASS} | sudo -S systemctl restart kos-bambu-monitor 2>&1')
    time.sleep(8)

    stdin, stdout, stderr = ssh.exec_command('systemctl is-active kos-bambu-monitor')
    state = stdout.read().decode().strip()
    print(f"Service: {state}")

    ssh.close()

if __name__ == "__main__":
    apply_patch()
