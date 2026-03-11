#!/usr/bin/env python3
"""Test Bambu A1 Mini pause command via MQTT."""
import sys
import time

sys.path.insert(0, "/opt/klipperos-ai/ai-monitor")
from bambu_client import BambuMQTTClient

HOST = "192.168.1.78"
CODE = "33cff0ac"
SERIAL = "0309DA551400764"

client = BambuMQTTClient(HOST, CODE, SERIAL)
if not client.connect():
    print("MQTT baglanti BASARISIZ")
    sys.exit(1)

print("MQTT bagli")
time.sleep(2)

status = client.get_status()
if status:
    print(f"Baslangic durum: {status.gcode_state}, Progress: {status.mc_percent}%")
else:
    print("Durum alinamadi — pushall beklenecek")
    time.sleep(5)
    status = client.get_status()
    if status:
        print(f"Durum: {status.gcode_state}, Progress: {status.mc_percent}%")

# Test 1: Standard pause command
print("\n--- Test 1: Standard pause ---")
result = client.pause_print()
print(f"pause_print() sonuc: {result}")
time.sleep(5)

status = client.get_status()
if status:
    print(f"Sonra durum: {status.gcode_state}")

# Test 2: Pause with param field
print("\n--- Test 2: Pause with param ---")
cmd = {
    "print": {
        "command": "pause",
        "sequence_id": "999",
        "param": "",
    }
}
result = client.send_command(cmd)
print(f"send_command sonuc: {result}")
time.sleep(5)

status = client.get_status()
if status:
    print(f"Sonra durum: {status.gcode_state}")

# Test 3: G-code M25 (universal pause)
print("\n--- Test 3: M25 G-code pause ---")
result = client.send_gcode("M25")
print(f"M25 sonuc: {result}")
time.sleep(5)

status = client.get_status()
if status:
    print(f"Sonra durum: {status.gcode_state}")

client.disconnect()
print("\nTest tamamlandi.")
