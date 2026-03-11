#!/usr/bin/env python3
"""
JSONL bilgi bankasini ChromaDB'ye indexler.
Bu script i7 uzerinde bir kez calistirilir.

Kullanim:
    python3 scripts/index_knowledge_base.py

Cikti:
    ai-chat/data/chroma_db/ dizini olusur
"""

import logging
import os
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("kb-indexer")

# Proje kok dizini
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
AI_CHAT_DIR = os.path.join(PROJECT_DIR, "ai-chat")

# ai-chat'i Python path'e ekle
sys.path.insert(0, AI_CHAT_DIR)

from knowledge_base import KnowledgeBase
import rag_config


def main():
    jsonl_path = rag_config.KB_JSONL_PATH

    if not os.path.exists(jsonl_path):
        logger.error("JSONL dosyasi bulunamadi: %s", jsonl_path)
        logger.info("Once training/generate_knowledge_base.py calistirin.")
        sys.exit(1)

    logger.info("Indexleme basliyor...")
    logger.info("  JSONL: %s", jsonl_path)
    logger.info("  ChromaDB: %s", rag_config.CHROMA_PERSIST_DIR)
    logger.info("  Model: %s", rag_config.EMBEDDING_MODEL)

    t0 = time.time()
    kb = KnowledgeBase(config=rag_config)
    count = kb.load_from_jsonl(jsonl_path)
    elapsed = time.time() - t0

    logger.info("Tamamlandi: %d giris indexlendi, %.1f saniye", count, elapsed)

    # Dogrulama: basit bir arama testi
    logger.info("\nDogrulama aramas\u0131...")
    test_queries = [
        "stepper_x nasil yapilandirilir",
        "TMC2209 UART baglantisi",
        "PID kalibrasyonu nasil yapilir",
        "Mainsail dashboard",
    ]

    for query in test_queries:
        results = kb.search(query, top_k=3)
        if results:
            best = results[0]
            logger.info("  Q: '%s' -> [%.3f] %s", query, best["score"], best["title"])
        else:
            logger.warning("  Q: '%s' -> SONUC YOK!", query)

    logger.info("\nIndexleme ve dogrulama tamamlandi.")


if __name__ == "__main__":
    main()
