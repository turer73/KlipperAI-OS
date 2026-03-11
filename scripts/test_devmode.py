#!/usr/bin/env python3
"""Test Developer Mode — two-way MQTT communication."""
import sys
import time

sys.path.insert(0, "/opt/klipperos-ai/ai-monitor")
from bambu_client import BambuMQTTClient

HOST = "192.168.1.78"
CODE = "33cff0ac"
SERIAL = "0309DA551400764"

client = BambuMQTTClient(HOST, CODE, SERIAL)
if not client.connect():
    print("MQTT BAGLANTI BASARISIZ")
    sys.exit(1)

print("MQTT bagli OK")
time.sleep(3)

# Test 1: Durum al
status = client.get_status()
if status:
    print(f"Durum: {status.gcode_state}, Progress: {status.mc_percent}%")
    print(f"Nozzle: {status.nozzle_temper}C, Bed: {status.bed_temper}C")
else:
    print("Durum alinamadi")

# Test 2: pushall komutu gonder
print("\n=== Test: pushall ===")
cmd = {"pushing": {"sequence_id": "0", "command": "pushall"}}
result = client.send_command(cmd)
print(f"pushall sonuc: {result}")
time.sleep(3)

# Test 3: Gcode M115 (firmware info - zararsiz)
print("\n=== Test: M115 (firmware bilgisi) ===")
result = client.send_gcode("M115")
print(f"M115 sonuc: {result}")
time.sleep(2)

# Test 4: Gcode M104 S0 (nozzle sogutma - zararsiz)
print("\n=== Test: M104 S0 (nozzle sogut) ===")
result = client.send_gcode("M104 S0")
print(f"M104 S0 sonuc: {result}")
time.sleep(2)

# Test 5: Eger yazdiriyorsa PAUSE test
status = client.get_status()
if status:
    print(f"\nGuncel durum: {status.gcode_state}")
    if status.gcode_state == "RUNNING":
        print("\n=== PAUSE TEST ===")
        result = client.pause_print()
        print(f"pause_print() sonuc: {result}")
        time.sleep(8)
        status = client.get_status()
        if status:
            print(f"Pause sonrasi: {status.gcode_state}")
            if status.gcode_state == "PAUSE":
                print("*** PAUSE BASARILI! ***")
                # Resume
                print("\n=== RESUME TEST ===")
                result = client.resume_print()
                print(f"resume_print() sonuc: {result}")
                time.sleep(8)
                status = client.get_status()
                if status:
                    print(f"Resume sonrasi: {status.gcode_state}")
            else:
                print(f"PAUSE CALISMADI - hala {status.gcode_state}")
    else:
        print(f"Yazici RUNNING degil ({status.gcode_state}) - pause test atlanacak")
        print("Bir baski baslatin ve bu testi tekrar calistirin")

client.disconnect()
print("\nDeveloper Mode test TAMAMLANDI")
