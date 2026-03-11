"""
RAG (Retrieval Augmented Generation) yapilandirma sabitleri.
Env var ile override edilebilir.
"""

import os

# ChromaDB
CHROMA_PERSIST_DIR = os.environ.get(
    "RAG_CHROMA_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "chroma_db")
)
CHROMA_COLLECTION = os.environ.get("RAG_CHROMA_COLLECTION", "klipper_kb")

# JSONL kaynak dosya
KB_JSONL_PATH = os.environ.get(
    "RAG_KB_JSONL",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "klipper_kb.jsonl")
)

# Embedding model
EMBEDDING_MODEL = os.environ.get("RAG_EMBEDDING_MODEL", "all-MiniLM-L6-v2")

# Arama parametreleri
SEARCH_TOP_K = int(os.environ.get("RAG_SEARCH_TOP_K", "5"))
CONTEXT_MAX_ENTRIES = int(os.environ.get("RAG_CONTEXT_MAX_ENTRIES", "2"))
CONTEXT_MAX_CHARS = int(os.environ.get("RAG_CONTEXT_MAX_CHARS", "700"))

# Minimum relevance score (0-1, dusuk = daha genis eslesme)
MIN_RELEVANCE_SCORE = float(os.environ.get("RAG_MIN_SCORE", "0.3"))
