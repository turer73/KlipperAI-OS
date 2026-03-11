#!/usr/bin/env python3
"""
RAG sistemi entegrasyon testi.
Indexleme yapildiktan sonra calistirilir.

Kullanim:
    python3 scripts/test_rag.py
"""

import logging
import os
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("rag-test")

# ai-chat'i path'e ekle
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, os.path.join(PROJECT_DIR, "ai-chat"))

from knowledge_base import KnowledgeBase
import rag_config


def test_availability():
    """RAG bagimlilikları mevcut mu?"""
    kb = KnowledgeBase(config=rag_config)
    assert kb.available, "RAG bagimliliklari eksik!"
    logger.info("[OK] RAG bagimliliklari mevcut")
    return kb


def test_search(kb):
    """Arama testleri — cesitli sorgular."""
    test_cases = [
        # (sorgu, beklenen_subcategory_icerir)
        ("stepper_x motor ayarlari", "stepper_config"),
        ("TMC2209 UART", "tmc_driver"),
        ("PID kalibrasyonu", "pid_tuning"),
        ("nozzle sicakligi cok dalgalaniyor", "pid_tuning"),
        ("Moonraker REST API", "rest_api"),
        ("bed mesh nasil alinir", "bed_mesh"),
        ("ilk katman yapismama sorunu", "first_layer"),
        ("pressure advance nedir", "pressure_advance"),
        ("Mainsail webcam ayarlari", "mainsail_config"),
        ("KlipperScreen kurulumu", "klipperscreen"),
        ("thermal runaway hatasi", "common_errors"),
        ("filament kurutma", "filament_settings"),
        ("input shaper ADXL345", "input_shaper"),
        ("CAN bus hata", "common_errors"),
    ]

    passed = 0
    failed = 0

    for query, expected_sub in test_cases:
        t0 = time.time()
        results = kb.search(query, top_k=3)
        elapsed_ms = (time.time() - t0) * 1000

        if not results:
            logger.error("  [FAIL] '%s' -> SONUC YOK!", query)
            failed += 1
            continue

        best = results[0]
        sub = best["subcategory"]
        score = best["score"]

        if expected_sub in sub:
            logger.info("  [OK] '%s' -> [%.3f, %.0fms] %s (%s)",
                       query, score, elapsed_ms, best["title"], sub)
            passed += 1
        else:
            logger.warning("  [?]  '%s' -> [%.3f] %s (%s) — beklenen: %s",
                          query, score, best["title"], sub, expected_sub)
            # Yanlis subcategory ama sonuc var — partial pass
            passed += 0.5
            failed += 0.5

    logger.info("\nArama testi: %d/%d basarili", int(passed), len(test_cases))
    return passed, failed


def test_context(kb):
    """build_context ciktisi testi."""
    query = "extruder PID nasil ayarlanir"
    context = kb.build_context(query, max_entries=3)

    assert len(context) > 0, "Context bos!"
    assert len(context) < rag_config.CONTEXT_MAX_CHARS + 500, "Context cok uzun!"

    logger.info("[OK] build_context: %d karakter", len(context))
    logger.info("--- Context onizleme (ilk 300 char) ---")
    logger.info(context[:300])
    logger.info("---")


def test_latency(kb):
    """Arama latency benchmarki."""
    queries = [
        "stepper motor",
        "sicaklik sorunu",
        "Moonraker API",
        "bed mesh kalibrasyon",
        "pressure advance",
    ]

    times = []
    for query in queries:
        t0 = time.time()
        kb.search(query, top_k=5)
        elapsed = (time.time() - t0) * 1000
        times.append(elapsed)

    avg = sum(times) / len(times)
    logger.info("[OK] Arama latency: ortalama %.1fms (min: %.1f, max: %.1f)",
               avg, min(times), max(times))


def test_stats(kb):
    """KB istatistikleri."""
    stats = kb.get_stats()
    logger.info("[OK] KB stats: %s", stats)
    assert stats["available"] is True
    assert stats["entry_count"] > 0


def main():
    logger.info("=" * 50)
    logger.info("RAG Entegrasyon Testi")
    logger.info("=" * 50)

    # 1. Kullanilabilirlik
    kb = test_availability()

    # 2. Arama testi
    logger.info("\n--- Arama Testleri ---")
    passed, failed = test_search(kb)

    # 3. Context olusturma
    logger.info("\n--- Context Testi ---")
    test_context(kb)

    # 4. Latency
    logger.info("\n--- Latency Testi ---")
    test_latency(kb)

    # 5. Stats
    logger.info("\n--- Stats Testi ---")
    test_stats(kb)

    # Ozet
    logger.info("\n" + "=" * 50)
    if failed == 0:
        logger.info("TUM TESTLER BASARILI!")
    else:
        logger.warning("Bazi testler basarisiz: %.0f hata", failed)
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
