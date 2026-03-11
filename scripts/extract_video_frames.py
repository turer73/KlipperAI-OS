#!/usr/bin/env python3
"""Extract labeled training frames from failed/normal print videos.

Analyzes videos from a local folder, extracts every Nth frame,
resizes to 224x224, and saves as JPEG organized by label.
Then uploads to the training server via SFTP.
"""
import cv2
import os
import sys
import numpy as np
from pathlib import Path

# === VIDEO LABEL MAP ===
# Based on visual analysis of sample frames
VIDEO_LABELS = {
    "video_2025-10-23_22-55-13.avi": "normal",       # flat dark knife shape, clean
    "video_2025-10-25_14-08-39.avi": "spaghetti",     # massive spaghetti mess
    "video_2025-10-26_16-13-37.avi": "normal",        # tall cylindrical print, clean
    "video_2025-11-19_01-56-56.avi": "spaghetti",     # deformed with strands
    "video_2025-11-19_03-37-11.avi": "spaghetti",     # two deformed + strands
    "video_2025-11-23_19-59-46.avi": "normal",        # white box, clean
    "video_2025-11-24_00-05-46.avi": "normal",        # large white box, clean
    "video_2025-12-13_21-05-26.avi": "stringing",     # small piece with strands
    "video_2025-12-23_13-17-13.avi": "normal",        # large arch, mostly clean
    "video_2026-01-11_07-24-20.avi": "stringing",     # large print with stringing
}

# Config
VIDEO_DIR = r"C:\Users\sevdi\Desktop\Yeni klasör"
OUTPUT_DIR = r"C:\linux_ai\KlipperOS-AI\extracted_frames"
FRAME_INTERVAL = 12     # Every 12th frame (= 2 per second at 24fps)
TARGET_SIZE = (224, 224) # Model input size
JPEG_QUALITY = 92

def extract_frames():
    """Extract and label frames from all videos."""
    stats = {}

    for label in set(VIDEO_LABELS.values()):
        os.makedirs(os.path.join(OUTPUT_DIR, label), exist_ok=True)
        stats[label] = 0

    for filename, label in sorted(VIDEO_LABELS.items()):
        video_path = os.path.join(VIDEO_DIR, filename)
        if not os.path.exists(video_path):
            print(f"  SKIP {filename} (not found)")
            continue

        cap = cv2.VideoCapture(video_path)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)

        frame_idx = 0
        saved = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % FRAME_INTERVAL == 0:
                # Resize to model input size
                resized = cv2.resize(frame, TARGET_SIZE, interpolation=cv2.INTER_AREA)

                # Save with unique name: label_videodate_frameNNN.jpg
                video_date = filename.replace("video_", "").replace(".avi", "")
                out_name = f"{label}_{video_date}_f{frame_idx:04d}.jpg"
                out_path = os.path.join(OUTPUT_DIR, label, out_name)
                cv2.imwrite(out_path, resized, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
                saved += 1

            frame_idx += 1

        cap.release()
        stats[label] += saved
        print(f"  {filename} -> {label}: {saved} frames (from {total} total)")

    print(f"\n{'='*50}")
    print("EXTRACTION SUMMARY")
    print(f"{'='*50}")
    total_extracted = 0
    for label, count in sorted(stats.items()):
        print(f"  {label:15s}: {count:4d} frames")
        total_extracted += count
    print(f"  {'TOTAL':15s}: {total_extracted:4d} frames")
    print(f"\nOutput: {OUTPUT_DIR}")
    return stats

def upload_to_server():
    """Upload extracted frames to training server via SFTP."""
    import paramiko

    SERVER = "192.168.1.129"
    USER = "klipperos"
    PASS = "tur0452"
    REMOTE_BASE = "/opt/klipperos-ai/training_data"

    print(f"\n{'='*50}")
    print("UPLOADING TO SERVER")
    print(f"{'='*50}")

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(SERVER, username=USER, password=PASS)
    sftp = ssh.open_sftp()

    uploaded = 0
    for label in os.listdir(OUTPUT_DIR):
        label_dir = os.path.join(OUTPUT_DIR, label)
        if not os.path.isdir(label_dir):
            continue

        remote_dir = f"{REMOTE_BASE}/{label}"
        # Ensure remote dir exists
        try:
            sftp.stat(remote_dir)
        except FileNotFoundError:
            ssh.exec_command(f"mkdir -p {remote_dir}")
            import time; time.sleep(1)

        files = sorted(os.listdir(label_dir))
        print(f"  {label}: uploading {len(files)} files...")

        for fname in files:
            local_path = os.path.join(label_dir, fname)
            remote_path = f"{remote_dir}/{fname}"
            sftp.put(local_path, remote_path)
            uploaded += 1

        print(f"  {label}: {len(files)} uploaded OK")

    sftp.close()
    ssh.close()
    print(f"\nTotal uploaded: {uploaded} frames to {SERVER}:{REMOTE_BASE}")

if __name__ == "__main__":
    print("="*50)
    print("VIDEO FRAME EXTRACTOR")
    print("="*50)

    stats = extract_frames()

    if "--upload" in sys.argv:
        upload_to_server()
    else:
        print("\nRun with --upload to upload frames to server")
