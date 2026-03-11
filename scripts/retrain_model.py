#!/usr/bin/env python3
"""
KlipperOS-AI — Model Yeniden Eğitim (Gerçek Kamera Verisi)
============================================================
collect_training_frames.py ile toplanan gerçek frame'lerden
MobileNetV2 tabanlı 5-sınıf spaghetti detection modeli eğitir.

Kullanım:
    python3 retrain_model.py

Dizin yapısı:
    /opt/klipperos-ai/training_data/
        normal/         ← normal baskı frame'leri
        spaghetti/      ← spaghetti/anomali frame'leri
        stringing/      ← (opsiyonel)
        no_extrusion/   ← (opsiyonel)
        completed/      ← (opsiyonel)

Eksik sınıflar sentetik augmentation ile doldurulur.
"""

import os
import sys
import random
import numpy as np
from pathlib import Path

# Paths
TRAINING_DIR = Path("/opt/klipperos-ai/training_data")
MODEL_OUTPUT = Path("/opt/klipperos-ai/ai-monitor/models/spaghetti_detect.onnx")
MODEL_BACKUP = MODEL_OUTPUT.with_suffix(".onnx.bak")
IMG_SIZE = 224

# 5 sınıf (spaghetti_detect.py ile aynı sıra)
CLASSES = ["normal", "spaghetti", "no_extrusion", "stringing", "completed"]
MIN_SAMPLES_PER_CLASS = 30


def load_real_frames(label_dir: Path) -> list:
    """Bir sınıf dizininden tüm JPEG frame'leri yükle."""
    from PIL import Image

    frames = []
    if not label_dir.exists():
        return frames

    for f in sorted(label_dir.glob("*.jpg")):
        try:
            img = Image.open(f).convert("RGB").resize((IMG_SIZE, IMG_SIZE))
            arr = np.array(img, dtype=np.float32) / 255.0
            frames.append(arr)
        except Exception as e:
            print(f"  UYARI: {f.name} okunamadı: {e}")

    return frames


def augment_frame(frame: np.ndarray) -> np.ndarray:
    """Basit augmentation: flip, brightness, crop-resize."""
    aug = frame.astype(np.float32).copy()

    # Random horizontal flip
    if random.random() > 0.5:
        aug = np.fliplr(aug).copy()

    # Random brightness adjustment
    brightness = np.float32(random.uniform(0.7, 1.3))
    aug = np.clip(aug * brightness, 0, 1).astype(np.float32)

    # Random small rotation via crop
    if random.random() > 0.5:
        pad = random.randint(5, 20)
        h, w = aug.shape[:2]
        aug = aug[pad : h - pad, pad : w - pad]
        from PIL import Image

        img = Image.fromarray((aug * 255).astype(np.uint8))
        img = img.resize((IMG_SIZE, IMG_SIZE))
        aug = np.array(img, dtype=np.float32) / 255.0

    # Random noise
    if random.random() > 0.5:
        noise = np.random.normal(0, 0.02, aug.shape).astype(np.float32)
        aug = np.clip(aug + noise, 0, 1).astype(np.float32)

    return aug


def generate_synthetic_from_real(frames: list, target_count: int) -> list:
    """Gerçek frame'lerden augmentation ile yeni frame'ler üret."""
    if not frames:
        return []

    synthetic = []
    while len(synthetic) < target_count:
        base = random.choice(frames)
        synthetic.append(augment_frame(base))

    return synthetic


def make_synthetic_spaghetti(normal_frames: list, count: int) -> list:
    """Normal frame'lere spaghetti benzeri çizgiler ekle."""
    from PIL import Image, ImageDraw

    frames = []
    for _ in range(count):
        if normal_frames:
            base = random.choice(normal_frames).copy()
        else:
            base = np.random.uniform(0.1, 0.3, (IMG_SIZE, IMG_SIZE, 3)).astype(
                np.float32
            )

        img = Image.fromarray((base * 255).astype(np.uint8))
        draw = ImageDraw.Draw(img)

        # Rastgele ince çizgiler (spaghetti)
        for _ in range(random.randint(8, 25)):
            x1, y1 = random.randint(30, 194), random.randint(30, 194)
            x2, y2 = x1 + random.randint(-60, 60), y1 + random.randint(-60, 60)
            color = (
                random.randint(150, 255),
                random.randint(100, 200),
                random.randint(50, 150),
            )
            draw.line([(x1, y1), (x2, y2)], fill=color, width=random.randint(1, 3))

        arr = np.array(img, dtype=np.float32) / 255.0
        frames.append(augment_frame(arr))

    return frames


def make_synthetic_no_extrusion(normal_frames: list, count: int) -> list:
    """Normal frame'lere koyu bantlar ekle (ekstrüzyon eksikliği)."""
    frames = []
    for _ in range(count):
        if normal_frames:
            base = random.choice(normal_frames).copy()
        else:
            base = np.random.uniform(0.2, 0.5, (IMG_SIZE, IMG_SIZE, 3)).astype(
                np.float32
            )

        # Koyu bant ekle
        for _ in range(random.randint(2, 5)):
            y = random.randint(20, IMG_SIZE - 30)
            h = random.randint(5, 15)
            base[y : y + h, :, :] *= random.uniform(0.2, 0.5)

        frames.append(augment_frame(np.clip(base, 0, 1)))

    return frames


def make_synthetic_completed(normal_frames: list, count: int) -> list:
    """Boş yatak (baskı tamamlandı) frame'leri üret."""
    frames = []
    for _ in range(count):
        # Düz renkli boş yatak
        color = np.array(
            [
                random.uniform(0.15, 0.35),
                random.uniform(0.15, 0.35),
                random.uniform(0.15, 0.35),
            ]
        )
        base = np.ones((IMG_SIZE, IMG_SIZE, 3), dtype=np.float32) * color

        # Hafif texture
        noise = np.random.normal(0, 0.03, base.shape).astype(np.float32)
        base = np.clip(base + noise, 0, 1)

        frames.append(augment_frame(base))

    return frames


def train_model(data: dict):
    """MobileNetV2 transfer learning ile model eğit."""
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader, TensorDataset
    from torchvision.models import mobilenet_v2, MobileNet_V2_Weights

    print("\n=== Model Eğitimi ===")

    # Veriyi hazırla
    all_frames = []
    all_labels = []
    for cls_idx, cls_name in enumerate(CLASSES):
        frames = data[cls_name]
        all_frames.extend(frames)
        all_labels.extend([cls_idx] * len(frames))
        print(f"  {cls_name}: {len(frames)} frame")

    # Shuffle
    combined = list(zip(all_frames, all_labels))
    random.shuffle(combined)
    all_frames, all_labels = zip(*combined)

    # Numpy → Tensor (NHWC → NCHW for training)
    X = np.stack(all_frames).astype(np.float32)  # (N, 224, 224, 3) float32 garantisi
    y = np.array(all_labels, dtype=np.int64)

    X_tensor = torch.from_numpy(X).permute(0, 3, 1, 2).float()  # (N, 3, 224, 224)
    y_tensor = torch.from_numpy(y)

    dataset = TensorDataset(X_tensor, y_tensor)
    loader = DataLoader(dataset, batch_size=16, shuffle=True, drop_last=False)

    print(f"  Toplam: {len(X)} frame, {len(CLASSES)} sınıf")

    # Model
    class SpaghettiModel(nn.Module):
        def __init__(self):
            super().__init__()
            backbone = mobilenet_v2(weights=MobileNet_V2_Weights.DEFAULT)
            self.features = backbone.features
            self.pool = nn.AdaptiveAvgPool2d(1)
            self.classifier = nn.Sequential(
                nn.Dropout(0.3), nn.Linear(1280, 5), nn.Softmax(dim=1)
            )
            # ImageNet normalizasyon
            self.register_buffer(
                "mean", torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1)
            )
            self.register_buffer(
                "std", torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1)
            )

        def forward(self, x):
            # Input: NHWC (batch, 224, 224, 3)
            if x.dim() == 4 and x.shape[-1] == 3:
                x = x.permute(0, 3, 1, 2)
            x = (x - self.mean) / self.std
            x = self.features(x)
            x = self.pool(x).flatten(1)
            return self.classifier(x)

    model = SpaghettiModel()
    model.train()

    # Backbone'u dondur, sadece classifier eğit (ilk 10 epoch)
    for p in model.features.parameters():
        p.requires_grad = False

    optimizer = torch.optim.Adam(model.classifier.parameters(), lr=1e-3)
    criterion = nn.CrossEntropyLoss()

    # Phase 1: Classifier eğit (10 epoch)
    print("\n  Phase 1: Classifier eğitimi (10 epoch)...")
    for epoch in range(10):
        total_loss, correct, total = 0, 0, 0
        for xb, yb in loader:
            # NCHW → model forward (içinde NHWC→NCHW + normalize yapar)
            # Ama training'de direkt NCHW veriyoruz, features'a manual besle
            xb_norm = (xb - model.mean) / model.std
            feat = model.features(xb_norm)
            feat = model.pool(feat).flatten(1)
            pred = model.classifier(feat)

            loss = criterion(torch.log(pred + 1e-8), yb)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            total_loss += loss.item()
            correct += (pred.argmax(1) == yb).sum().item()
            total += len(yb)

        if (epoch + 1) % 2 == 0:
            acc = correct / total * 100
            print(f"    Epoch {epoch+1:2d}: loss={total_loss:.4f}, acc={acc:.1f}%")

    # Phase 2: Fine-tune son katmanlar (5 epoch, düşük lr)
    print("\n  Phase 2: Fine-tuning (5 epoch)...")
    # Son 4 features katmanını aç
    for i, layer in enumerate(model.features):
        if i >= 14:  # Son 4 inverted residual block
            for p in layer.parameters():
                p.requires_grad = True

    optimizer = torch.optim.Adam(
        filter(lambda p: p.requires_grad, model.parameters()), lr=1e-4
    )

    for epoch in range(5):
        total_loss, correct, total = 0, 0, 0
        for xb, yb in loader:
            xb_norm = (xb - model.mean) / model.std
            feat = model.features(xb_norm)
            feat = model.pool(feat).flatten(1)
            pred = model.classifier(feat)

            loss = criterion(torch.log(pred + 1e-8), yb)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            total_loss += loss.item()
            correct += (pred.argmax(1) == yb).sum().item()
            total += len(yb)

        acc = correct / total * 100
        print(f"    Epoch {epoch+1:2d}: loss={total_loss:.4f}, acc={acc:.1f}%")

    # ONNX export
    model.eval()
    print("\n=== ONNX Export ===")

    # Backup eski model
    if MODEL_OUTPUT.exists():
        import shutil

        shutil.copy2(MODEL_OUTPUT, MODEL_BACKUP)
        print(f"  Eski model yedeklendi: {MODEL_BACKUP}")

    # NHWC dummy input (model forward'da NCHW'ye çevirir)
    dummy = torch.randn(1, IMG_SIZE, IMG_SIZE, 3)
    MODEL_OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    torch.onnx.export(
        model,
        dummy,
        str(MODEL_OUTPUT),
        input_names=["input"],
        output_names=["output"],
        dynamic_axes={"input": {0: "batch"}, "output": {0: "batch"}},
        opset_version=13,
        dynamo=False,
    )

    size_mb = MODEL_OUTPUT.stat().st_size / (1024 * 1024)
    print(f"  Model kaydedildi: {MODEL_OUTPUT} ({size_mb:.1f} MB)")

    # Hızlı doğrulama
    import onnxruntime as ort

    sess = ort.InferenceSession(str(MODEL_OUTPUT))
    test_input = np.random.rand(1, IMG_SIZE, IMG_SIZE, 3).astype(np.float32)
    out = sess.run(None, {"input": test_input})[0]
    print(f"  ONNX doğrulama: output shape={out.shape}, sum={out.sum():.3f}")
    print(f"  Sınıf dağılımı: {dict(zip(CLASSES, [f'{v:.1%}' for v in out[0]]))}")

    return True


def main():
    print("=" * 60)
    print("  KlipperOS-AI Model Yeniden Eğitim")
    print("=" * 60)

    # Gerçek frame'leri yükle
    print("\n=== Gerçek Frame Yükleme ===")
    real_data = {}
    for cls in CLASSES:
        cls_dir = TRAINING_DIR / cls
        frames = load_real_frames(cls_dir)
        real_data[cls] = frames
        if frames:
            print(f"  {cls}: {len(frames)} gerçek frame yüklendi")
        else:
            print(f"  {cls}: gerçek frame yok (sentetik üretilecek)")

    # Normal frame zorunlu
    if len(real_data["normal"]) < 10:
        print("\n  HATA: En az 10 'normal' frame gerekli!")
        print("  Önce collect_training_frames.py ile normal frame toplayin.")
        sys.exit(1)

    normal_frames = real_data["normal"]

    # Eksik sınıfları doldur
    print("\n=== Veri Hazırlama ===")
    training_data = {}

    for cls in CLASSES:
        real_count = len(real_data[cls])

        if real_count >= MIN_SAMPLES_PER_CLASS:
            # Yeterli gerçek veri var — augmentation ile zenginleştir
            augmented = generate_synthetic_from_real(
                real_data[cls], MIN_SAMPLES_PER_CLASS
            )
            training_data[cls] = real_data[cls] + augmented
            print(
                f"  {cls}: {real_count} gerçek + {len(augmented)} augmented = {len(training_data[cls])}"
            )

        elif real_count > 0:
            # Az gerçek veri — augmentation ile çoğalt
            needed = MIN_SAMPLES_PER_CLASS - real_count
            augmented = generate_synthetic_from_real(real_data[cls], needed)
            training_data[cls] = real_data[cls] + augmented
            print(
                f"  {cls}: {real_count} gerçek + {len(augmented)} augmented = {len(training_data[cls])}"
            )

        else:
            # Gerçek veri yok — tamamen sentetik
            if cls == "spaghetti":
                training_data[cls] = make_synthetic_spaghetti(
                    normal_frames, MIN_SAMPLES_PER_CLASS
                )
            elif cls == "no_extrusion":
                training_data[cls] = make_synthetic_no_extrusion(
                    normal_frames, MIN_SAMPLES_PER_CLASS
                )
            elif cls == "completed":
                training_data[cls] = make_synthetic_completed(
                    normal_frames, MIN_SAMPLES_PER_CLASS
                )
            elif cls == "stringing":
                # Stringing = normal + ince çizgiler (spaghetti'ye benzer ama daha hafif)
                training_data[cls] = make_synthetic_spaghetti(
                    normal_frames, MIN_SAMPLES_PER_CLASS
                )
            else:
                training_data[cls] = generate_synthetic_from_real(
                    normal_frames, MIN_SAMPLES_PER_CLASS
                )
            print(f"  {cls}: {len(training_data[cls])} sentetik")

    # Eğit
    success = train_model(training_data)

    if success:
        print("\n✓ Model başarıyla eğitildi ve kaydedildi!")
        print("  Servisi restart edin: sudo systemctl restart kos-bambu-monitor")
    else:
        print("\n✗ Model eğitimi başarısız!")
        sys.exit(1)


if __name__ == "__main__":
    main()
