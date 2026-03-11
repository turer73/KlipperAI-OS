#!/usr/bin/env python3
"""AI Chat streaming test."""
import requests, json, time

start = time.time()
first_token_time = None

resp = requests.post(
    "http://127.0.0.1:8085/api/chat",
    json={"messages": [{"role": "user", "content": "Hello"}]},
    stream=True,
    timeout=300,
)

full = ""
for line in resp.iter_lines():
    if not line:
        continue
    line = line.decode("utf-8")
    if not line.startswith("data: "):
        continue
    data = line[6:]
    if data == "[DONE]":
        break
    try:
        parsed = json.loads(data)
        token = parsed.get("token", "")
        if token:
            if first_token_time is None:
                first_token_time = time.time() - start
            full += token
    except Exception:
        pass

total = time.time() - start
print(f"First token: {first_token_time:.1f}s" if first_token_time else "No tokens")
print(f"Total time: {total:.1f}s")
print(f"Response: {full[:300]}")
print(f"Words: ~{len(full.split())}")
