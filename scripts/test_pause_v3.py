#!/usr/bin/env python3
"""Test A1 Mini pause — after LAN Only mode enabled."""
import json
import sys
import time

sys.path.insert(0, "/opt/klipperos-ai/ai-monitor")
from bambu_client import BambuMQTTClient

HOST = "192.168.1.78"
CODE = "33cff0ac"
SERIAL = "0309DA551400764"
TOPIC = f"device/{SERIAL}/request"

client = BambuMQTTClient(HOST, CODE, SERIAL)
if not client.connect():
    print("MQTT baglanti BASARISIZ")
    sys.exit(1)

print("MQTT bagli")
time.sleep(3)

status = client.get_status()
if status:
    print(f"Durum: {status.gcode_state}, Progress: {status.mc_percent}%")

# Test: M600 filament change (forces pause)
print("\n--- Test: M600 filament change pause ---")
cmd = {
    "print": {
        "command": "gcode_line",
        "sequence_id": "0",
        "param": "M600\n",
    }
}
info = client._client.publish(TOPIC, json.dumps(cmd), qos=1)
info.wait_for_publish(timeout=5)
print(f"Published: rc={info.rc}, is_published={info.is_published()}")
time.sleep(5)
status = client.get_status()
if status:
    print(f"Durum: {status.gcode_state}")

# Test: Bambu-specific stop
print("\n--- Test: print stop ---")
cmd = {
    "print": {
        "command": "stop",
        "sequence_id": "0",
        "param": "",
    }
}
# Only send if still RUNNING
if status and status.gcode_state == "RUNNING":
    info = client._client.publish(TOPIC, json.dumps(cmd), qos=1)
    info.wait_for_publish(timeout=5)
    print(f"Published: rc={info.rc}, is_published={info.is_published()}")
    time.sleep(5)
    status = client.get_status()
    if status:
        print(f"Durum: {status.gcode_state}")
else:
    print(f"Zaten durdu: {status.gcode_state if status else 'N/A'}")

client.disconnect()
print("\nTest tamamlandi.")
