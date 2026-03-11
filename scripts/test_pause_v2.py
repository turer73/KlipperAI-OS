#!/usr/bin/env python3
"""Test Bambu A1 Mini pause — advanced command formats + QoS."""
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

# ========================================
# Test 4: QoS 1 ile pause
# ========================================
print("\n--- Test 4: QoS 1 pause ---")
cmd = {"print": {"command": "pause", "sequence_id": "0", "param": ""}}
info = client._client.publish(TOPIC, json.dumps(cmd), qos=1)
info.wait_for_publish(timeout=5)
print(f"Published: rc={info.rc}, is_published={info.is_published()}")
time.sleep(5)
status = client.get_status()
if status:
    print(f"Durum: {status.gcode_state}")

# ========================================
# Test 5: M400 + M25 gcode combo
# ========================================
print("\n--- Test 5: M400+M25 gcode ---")
cmd = {
    "print": {
        "command": "gcode_line",
        "sequence_id": "0",
        "param": "M400\nM25\n",
    }
}
info = client._client.publish(TOPIC, json.dumps(cmd), qos=1)
info.wait_for_publish(timeout=5)
print(f"Published: rc={info.rc}, is_published={info.is_published()}")
time.sleep(5)
status = client.get_status()
if status:
    print(f"Durum: {status.gcode_state}")

# ========================================
# Test 6: project_file stop
# ========================================
print("\n--- Test 6: project stop ---")
cmd = {
    "print": {
        "command": "project_file",
        "sequence_id": "0",
        "param": "Metadata/plate_1.gcode",
        "subtask_name": "",
        "url": "",
        "bed_type": "auto",
        "timelapse": False,
        "bed_leveling": True,
        "flow_cali": False,
        "vibration_cali": False,
        "layer_inspect": False,
        "use_ams": False,
    }
}
# Don't send this - it would restart the print
print("(skip - would restart print)")

# ========================================
# Test 7: Direct gcode M0 (emergency stop)
# ========================================
print("\n--- Test 7: M0 emergency stop gcode ---")
cmd = {
    "print": {
        "command": "gcode_line",
        "sequence_id": "0",
        "param": "M0\n",
    }
}
info = client._client.publish(TOPIC, json.dumps(cmd), qos=1)
info.wait_for_publish(timeout=5)
print(f"Published: rc={info.rc}, is_published={info.is_published()}")
time.sleep(5)
status = client.get_status()
if status:
    print(f"Durum: {status.gcode_state}")

# ========================================
# Test 8: print_speed to 0 (workaround pause)
# ========================================
print("\n--- Test 8: speed to 1% ---")
cmd = {
    "print": {
        "command": "print_speed",
        "sequence_id": "0",
        "param": "1",
    }
}
info = client._client.publish(TOPIC, json.dumps(cmd), qos=1)
info.wait_for_publish(timeout=5)
print(f"Published: rc={info.rc}, is_published={info.is_published()}")
time.sleep(5)
status = client.get_status()
if status:
    print(f"Durum: {status.gcode_state}")

# Reset speed
print("\n--- Reset speed to normal (4=standard) ---")
cmd = {
    "print": {
        "command": "print_speed",
        "sequence_id": "0",
        "param": "2",
    }
}
client._client.publish(TOPIC, json.dumps(cmd), qos=1)

client.disconnect()
print("\nTest tamamlandi.")
