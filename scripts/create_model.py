#!/usr/bin/env python3
"""
KlipperOS-AI — Spaghetti Detection Model Creator
==================================================
MobileNetV2 pretrained backbone + 5-sinif classifier head.

1. Bambu kameradan canli "normal" frame'ler yakalar
2. Sentetik anomali frame'leri uretir (spaghetti, stringing, no_extrusion)
3. Fine-tune eder
4. ONNX export eder

Kullanim:
    cd /opt/klipperos-ai
    ai-venv/bin/python3 scripts/create_model.py
"""

import logging
import os
import ssl
import socket
import struct
import json
import time
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset
from PIL import Image, ImageFilter, ImageDraw

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("model-creator")

# ─── Config ──────────────────────────────────────
BAMBU_HOST = "192.168.1.78"
BAMBU_ACCESS_CODE = "33cff0ac"
NUM_NORMAL_FRAMES = 40          # Kameradan yakalanacak normal frame sayisi
SYNTHETIC_PER_CLASS = 30        # Her anomali sinifi icin sentetik frame
IMG_SIZE = 224
NUM_CLASSES = 5
CLASS_LABELS = ["normal", "spaghetti", "no_extrusion", "stringing", "completed"]
EPOCHS = 15
BATCH_SIZE = 8
LR = 0.001
MODEL_DIR = Path("/opt/klipperos-ai/ai-monitor/models")
MODEL_PATH = MODEL_DIR / "spaghetti_detect.onnx"


# ─── 1. Kameradan Frame Yakalama ────────────────
def capture_frames_from_bambu(host, access_code, num_frames=40, timeout=60):
    """Bambu Lab kamerasından JPEG frame'ler yakala."""
    log.info("Bambu kameraya baglaniyor: %s ...", host)

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    sock = socket.create_connection((host, 6000), timeout=10)
    tls_sock = ctx.wrap_socket(sock, server_hostname=host)

    # Auth paketi
    auth_data = json.dumps({"username": "bblp", "access_code": access_code}).encode()
    header = struct.pack("<IHH", 0x40, 0x3000, 0) + struct.pack("<I", len(auth_data))
    tls_sock.sendall(header + auth_data)
    log.info("Auth gonderildi, frame bekleniyor...")

    frames = []
    buf = b""
    start = time.time()

    while len(frames) < num_frames and (time.time() - start) < timeout:
        chunk = tls_sock.recv(65536)
        if not chunk:
            break
        buf += chunk

        # JPEG frame'leri ayikla (SOI=0xFFD8, EOI=0xFFD9)
        while True:
            soi = buf.find(b'\xff\xd8')
            if soi < 0:
                break
            eoi = buf.find(b'\xff\xd9', soi + 2)
            if eoi < 0:
                break
            jpeg_data = buf[soi:eoi + 2]
            buf = buf[eoi + 2:]

            try:
                img = Image.open(__import__('io').BytesIO(jpeg_data)).convert("RGB")
                img = img.resize((IMG_SIZE, IMG_SIZE), Image.BILINEAR)
                frames.append(img)
                if len(frames) % 10 == 0:
                    log.info("  %d/%d frame yakalandi", len(frames), num_frames)
            except Exception:
                continue

        # Frame'ler arasi kisa bekleme (farkli acilarda frame almak icin)
        if len(frames) < num_frames:
            time.sleep(0.3)

    tls_sock.close()
    log.info("Toplam %d frame yakalandi", len(frames))
    return frames


# ─── 2. Sentetik Anomali Uretimi ────────────────
def make_spaghetti(img: Image.Image) -> Image.Image:
    """Spaghetti/fail efekti — rastgele ipliksi yapilar + gurultu."""
    out = img.copy()
    draw = ImageDraw.Draw(out)
    arr = np.array(out)

    # Rastgele spaghetti iplikleri ciz
    w, h = out.size
    for _ in range(np.random.randint(15, 40)):
        x1, y1 = np.random.randint(0, w), np.random.randint(0, h)
        x2, y2 = x1 + np.random.randint(-80, 80), y1 + np.random.randint(-80, 80)
        color = tuple(np.random.randint(150, 255, 3).tolist())
        width = np.random.randint(1, 3)
        draw.line([(x1, y1), (x2, y2)], fill=color, width=width)

    # Blob gurultu ekle
    noise = np.random.randint(-40, 40, arr.shape, dtype=np.int16)
    arr = np.clip(np.array(out).astype(np.int16) + noise, 0, 255).astype(np.uint8)

    return Image.fromarray(arr)


def make_stringing(img: Image.Image) -> Image.Image:
    """Stringing efekti — ince iplikler + hafif blur."""
    out = img.copy()
    draw = ImageDraw.Draw(out)
    w, h = out.size

    # Ince uzun cizgiler (stringing)
    for _ in range(np.random.randint(8, 25)):
        x1 = np.random.randint(0, w)
        y1 = np.random.randint(0, h)
        length = np.random.randint(30, 120)
        angle = np.random.uniform(-0.5, 0.5)  # Neredeyse dikey
        x2 = int(x1 + length * np.sin(angle))
        y2 = int(y1 - length * np.cos(angle))
        color = tuple(np.random.randint(180, 255, 3).tolist())
        draw.line([(x1, y1), (x2, y2)], fill=color, width=1)

    # Hafif blur
    out = out.filter(ImageFilter.GaussianBlur(radius=0.5))
    return out


def make_no_extrusion(img: Image.Image) -> Image.Image:
    """No-extrusion efekti — parcali katmanlar, eksik kisimlar."""
    arr = np.array(img)
    h, w, c = arr.shape

    # Rastgele yatay bantlari karart (eksik ekstruzyon)
    for _ in range(np.random.randint(5, 15)):
        y_start = np.random.randint(0, h - 20)
        band_h = np.random.randint(3, 15)
        x_start = np.random.randint(0, w // 2)
        x_end = np.random.randint(x_start + 20, w)
        arr[y_start:y_start + band_h, x_start:x_end] = (
            arr[y_start:y_start + band_h, x_start:x_end] * 0.3
        ).astype(np.uint8)

    # Genel kontrast dusur
    arr = (arr * np.random.uniform(0.5, 0.8)).astype(np.uint8)

    return Image.fromarray(arr)


def make_completed(img: Image.Image) -> Image.Image:
    """Completed/bos tabla — uniform renk, az doku."""
    arr = np.array(img)
    h, w, c = arr.shape

    # Buyuk bir alanini uniform yap (bos tabla efekti)
    base_color = np.array([50, 45, 40], dtype=np.uint8)  # Koyu yatak rengi
    mask = np.random.random((h, w)) > 0.3
    for ch in range(3):
        arr[mask, ch] = np.clip(
            base_color[ch] + np.random.randint(-15, 15, mask.sum()),
            0, 255
        ).astype(np.uint8)

    # Hafif blur
    return Image.fromarray(arr).filter(ImageFilter.GaussianBlur(radius=1.5))


def generate_synthetic_data(normal_frames, per_class=30):
    """Normal frame'lerden sentetik anomali frame'leri uret."""
    log.info("Sentetik veri uretiliyor (%d/sinif)...", per_class)

    all_images = []
    all_labels = []

    # CLASS 0: Normal — orijinal frame'ler + hafif augmentation
    for img in normal_frames:
        all_images.append(img)
        all_labels.append(0)
        # Hafif augmentation (flip, brightness)
        if np.random.random() > 0.5:
            all_images.append(img.transpose(Image.FLIP_LEFT_RIGHT))
            all_labels.append(0)

    generators = {
        1: make_spaghetti,      # spaghetti
        2: make_no_extrusion,   # no_extrusion
        3: make_stringing,      # stringing
        4: make_completed,      # completed
    }

    for class_idx, gen_func in generators.items():
        for i in range(per_class):
            base = normal_frames[i % len(normal_frames)]
            synthetic = gen_func(base)
            all_images.append(synthetic)
            all_labels.append(class_idx)

    log.info("Toplam %d egitim ornegi (sinif dagilimi: %s)",
             len(all_images),
             {CLASS_LABELS[i]: all_labels.count(i) for i in range(NUM_CLASSES)})

    return all_images, all_labels


def images_to_tensors(images, labels):
    """PIL Image listesini PyTorch tensor'lere donustur."""
    X = []
    for img in images:
        arr = np.array(img.resize((IMG_SIZE, IMG_SIZE)), dtype=np.float32) / 255.0
        X.append(arr)

    X = np.stack(X)                      # (N, 224, 224, 3) — NHWC
    X_tensor = torch.from_numpy(X)       # float32
    y_tensor = torch.tensor(labels, dtype=torch.long)

    return X_tensor, y_tensor


# ─── 3. Model Tanimi ─────────────────────────────
class SpaghettiModel(nn.Module):
    """MobileNetV2 backbone + 5-sinif classifier.

    Input: (N, 224, 224, 3) — NHWC (TFLite/detector uyumlu)
    Output: (N, 5) — softmax probabilities
    """
    def __init__(self, num_classes=5):
        super().__init__()
        from torchvision.models import mobilenet_v2, MobileNet_V2_Weights

        base = mobilenet_v2(weights=MobileNet_V2_Weights.IMAGENET1K_V1)
        self.features = base.features     # Pretrained feature extractor
        self.pool = nn.AdaptiveAvgPool2d(1)
        self.classifier = nn.Sequential(
            nn.Dropout(0.3),
            nn.Linear(1280, num_classes),
        )

    def forward(self, x):
        # x: (N, H, W, C) NHWC — detector'un gonderdigi format
        x = x.permute(0, 3, 1, 2)  # -> (N, C, H, W) PyTorch NCHW

        # ImageNet normalization
        mean = torch.tensor([0.485, 0.456, 0.406], device=x.device).view(1, 3, 1, 1)
        std = torch.tensor([0.229, 0.224, 0.225], device=x.device).view(1, 3, 1, 1)
        x = (x - mean) / std

        x = self.features(x)
        x = self.pool(x)
        x = torch.flatten(x, 1)
        x = self.classifier(x)
        x = torch.softmax(x, dim=1)
        return x


# ─── 4. Egitim ──────────────────────────────────
def train_model(X_tensor, y_tensor, epochs=15, lr=0.001, batch_size=8):
    """MobileNetV2 fine-tune."""
    log.info("Model olusturuluyor (MobileNetV2 + 5-sinif head)...")
    model = SpaghettiModel(NUM_CLASSES)
    model.train()

    # Backbone'u dondur (sadece classifier head egit — hizli + stabil)
    for param in model.features.parameters():
        param.requires_grad = False

    dataset = TensorDataset(X_tensor, y_tensor)
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=True)

    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.classifier.parameters(), lr=lr)

    log.info("Egitim basliyor (%d epoch, %d ornek)...", epochs, len(dataset))

    for epoch in range(epochs):
        total_loss = 0
        correct = 0
        total = 0

        for X_batch, y_batch in loader:
            optimizer.zero_grad()

            # Forward — softmax output'tan log alip NLLLoss yerine
            # dogrudan logits kullanmak daha stabil olur
            # Ama modelimiz softmax donduruyor, bu yuzden log + NLL kullanalim
            outputs = model(X_batch)
            loss = criterion(torch.log(outputs + 1e-8), y_batch)

            loss.backward()
            optimizer.step()

            total_loss += loss.item()
            predicted = outputs.argmax(dim=1)
            correct += (predicted == y_batch).sum().item()
            total += y_batch.size(0)

        acc = 100 * correct / total
        avg_loss = total_loss / len(loader)
        if (epoch + 1) % 3 == 0 or epoch == 0:
            log.info("  Epoch %2d/%d — loss: %.4f, acc: %.1f%%",
                     epoch + 1, epochs, avg_loss, acc)

    # Son epoch sonuclari
    log.info("Egitim tamamlandi! Son dogruluk: %.1f%%", acc)

    # Backbone'u tekrar ac (ONNX export icin tum model gerekli)
    for param in model.features.parameters():
        param.requires_grad = True

    return model


# ─── 5. ONNX Export ─────────────────────────────
def export_onnx(model, output_path):
    """Model'i ONNX formatina export et."""
    model.eval()

    dummy = torch.randn(1, IMG_SIZE, IMG_SIZE, 3)  # NHWC input

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # PyTorch 2.10+ dynamo exporter yerine legacy exporter kullan
    torch.onnx.export(
        model,
        dummy,
        str(output_path),
        input_names=["input"],
        output_names=["output"],
        dynamic_axes={
            "input": {0: "batch"},
            "output": {0: "batch"},
        },
        opset_version=13,
        dynamo=False,  # Legacy ONNX exporter (onnxscript gerektirmez)
    )

    # Dogrulama
    import onnxruntime as ort
    sess = ort.InferenceSession(str(output_path), providers=["CPUExecutionProvider"])
    inp = sess.get_inputs()[0]
    out = sess.get_outputs()[0]
    log.info("ONNX model kaydedildi: %s", output_path)
    log.info("  Input:  %s %s", inp.name, inp.shape)
    log.info("  Output: %s %s", out.name, out.shape)

    # Test inference
    test_input = np.random.rand(1, IMG_SIZE, IMG_SIZE, 3).astype(np.float32)
    result = sess.run(None, {inp.name: test_input})[0]
    log.info("  Test output: %s (sum=%.3f)",
             {CLASS_LABELS[i]: f"{result[0][i]:.3f}" for i in range(NUM_CLASSES)},
             result[0].sum())

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    log.info("  Dosya boyutu: %.1f MB", size_mb)


# ─── 6. Ana Akis ────────────────────────────────
def run_cmd(cmd):
    """Shell komutu calistir ve sonucu dondur."""
    import subprocess
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def main():
    log.info("=" * 60)
    log.info("KlipperOS-AI Spaghetti Detection Model Creator")
    log.info("=" * 60)

    # 0. Monitor'u gecici durdur (kamera baglantisini serbest birak)
    log.info("\n[0/5] Monitor servisi gecici olarak durduruluyor...")
    code, out, err = run_cmd("sudo systemctl stop kos-bambu-monitor")
    if code == 0:
        log.info("  Monitor durduruldu")
    else:
        log.warning("  Monitor durdurulamadi (kod: %d): %s", code, err)
    time.sleep(2)  # Kamera baglantisinin kapanmasini bekle

    # 1. Kameradan normal frame'ler yakala
    log.info("\n[1/5] Kameradan normal frame yakalama")
    try:
        normal_frames = capture_frames_from_bambu(
            BAMBU_HOST, BAMBU_ACCESS_CODE, NUM_NORMAL_FRAMES
        )
    except Exception as exc:
        log.error("Kamera baglantisi basarisiz: %s", exc)
        log.info("Kaydedilmis snapshot'tan frame kullaniliyor...")
        normal_frames = []
        # Kaydedilmis snapshot'u oku
        snap_path = "/var/lib/klipperos-ai/snapshots/bambu-3e4daa5d.jpg"
        if os.path.exists(snap_path):
            img = Image.open(snap_path).convert("RGB").resize((IMG_SIZE, IMG_SIZE))
            # Ayni frame'den augmentation ile cesitli frame'ler uret
            normal_frames.append(img)
            for _ in range(NUM_NORMAL_FRAMES - 1):
                aug = img.copy()
                # Rastgele brightness/contrast degisimi
                arr = np.array(aug, dtype=np.float32)
                arr = arr * np.random.uniform(0.85, 1.15) + np.random.uniform(-10, 10)
                arr = np.clip(arr, 0, 255).astype(np.uint8)
                # Rastgele flip
                pil = Image.fromarray(arr)
                if np.random.random() > 0.5:
                    pil = pil.transpose(Image.FLIP_LEFT_RIGHT)
                normal_frames.append(pil)
            log.info("  Snapshot'tan %d augmented frame uretildi", len(normal_frames))
        else:
            # Son care: sentetik
            for _ in range(NUM_NORMAL_FRAMES):
                arr = np.random.randint(30, 80, (IMG_SIZE, IMG_SIZE, 3), dtype=np.uint8)
                normal_frames.append(Image.fromarray(arr))

    if len(normal_frames) < 5:
        log.error("Yeterli frame yakalanamadi (%d)", len(normal_frames))
        run_cmd("sudo systemctl start kos-bambu-monitor")
        return

    # 2. Sentetik anomali verisi uret
    log.info("\n[2/5] Sentetik anomali verisi uretimi")
    images, labels = generate_synthetic_data(normal_frames, SYNTHETIC_PER_CLASS)

    # 3. Tensor'lere donustur + egit
    log.info("\n[3/5] Model egitimi")
    X_tensor, y_tensor = images_to_tensors(images, labels)
    log.info("Veri tensoru: X=%s, y=%s", X_tensor.shape, y_tensor.shape)

    model = train_model(X_tensor, y_tensor, EPOCHS, LR, BATCH_SIZE)

    # 4. ONNX export
    log.info("\n[4/5] ONNX export")
    export_onnx(model, MODEL_PATH)

    # 5. Monitor'u yeniden baslat
    log.info("\n[5/5] Monitor servisi yeniden baslatiliyor...")
    code, out, err = run_cmd("sudo systemctl start kos-bambu-monitor")
    if code == 0:
        log.info("  Monitor baslatildi")
    else:
        log.warning("  Monitor baslatilma hatasi (kod: %d): %s", code, err)

    log.info("\n" + "=" * 60)
    log.info("MODEL HAZIR!")
    log.info("Konum: %s", MODEL_PATH)
    log.info("Siniflar: %s", CLASS_LABELS)
    log.info("Monitor servisi: aktif")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
