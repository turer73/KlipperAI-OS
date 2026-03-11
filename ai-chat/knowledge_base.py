"""
KlipperOS-AI Knowledge Base - RAG Engine
ChromaDB + sentence-transformers ile semantik arama.
Graceful degradation: Bagimliliklar yoksa RAG atlanir.
"""

import json
import logging
import os
import time

logger = logging.getLogger("klipperos-ai.rag")

# Lazy import - bagimliliklar yoksa None kalir
_chromadb = None
_SentenceTransformer = None
_RAG_AVAILABLE = None


def _check_deps():
    """Bagimliliklari kontrol et (bir kez)."""
    global _chromadb, _SentenceTransformer, _RAG_AVAILABLE
    if _RAG_AVAILABLE is not None:
        return _RAG_AVAILABLE

    try:
        import chromadb as _cdb
        from sentence_transformers import SentenceTransformer as _ST
        _chromadb = _cdb
        _SentenceTransformer = _ST
        _RAG_AVAILABLE = True
        logger.info("RAG bagimliliklari mevcut (chromadb + sentence-transformers)")
    except ImportError as e:
        _RAG_AVAILABLE = False
        logger.warning(f"RAG bagimliliklari eksik, RAG devre disi: {e}")

    return _RAG_AVAILABLE


class KnowledgeBase:
    """
    Klipper bilgi bankasi - ChromaDB backend ile semantik arama.

    Kullanim:
        kb = KnowledgeBase()
        if kb.available:
            results = kb.search("TMC2209 UART baglantisi")
            context = kb.build_context("extruder PID ayari")
    """

    def __init__(self, config=None):
        """
        Args:
            config: rag_config modulu veya dict. None ise default config kullanilir.
        """
        if config is None:
            import rag_config as config
        self._config = config

        self._collection = None
        self._embedder = None
        self._initialized = False
        self._entry_count = 0

    @property
    def available(self):
        """RAG kullanilabilir mi?"""
        return _check_deps()

    def _ensure_init(self):
        """Lazy initialization - ilk kullanımda yükle."""
        if self._initialized:
            return True

        if not self.available:
            return False

        try:
            t0 = time.time()

            # ChromaDB client
            persist_dir = self._config.CHROMA_PERSIST_DIR
            if os.path.exists(persist_dir):
                client = _chromadb.PersistentClient(path=persist_dir)
            else:
                logger.warning(f"ChromaDB dizini yok: {persist_dir}. Once indexleme gerekli.")
                return False

            # Collection
            collection_name = self._config.CHROMA_COLLECTION
            try:
                self._collection = client.get_collection(name=collection_name)
                self._entry_count = self._collection.count()
            except Exception:
                logger.warning(f"ChromaDB collection '{collection_name}' bulunamadi. Once indexleme gerekli.")
                return False

            # Embedding model (en agir kisim, ~2-3 saniye)
            model_name = self._config.EMBEDDING_MODEL
            logger.info(f"Embedding model yukleniyor: {model_name}")
            self._embedder = _SentenceTransformer(model_name)

            elapsed = time.time() - t0
            logger.info(f"RAG hazir: {self._entry_count} giris, {elapsed:.1f}s init")
            self._initialized = True
            return True

        except Exception as e:
            logger.error(f"RAG init hatasi: {e}")
            return False

    @staticmethod
    def _rerank_by_keywords(query, results):
        """Keyword eslesmesine gore sonuclari yeniden sirala.

        ChromaDB'nin semantik skoru bazen yaniltici olabilir
        (ornegin 'nozul sicakligi' sorgusu icin 'kurutma sicakligi'
        sonucu yuksek skor alabilir). Sorgu kelimelerinin baslik ve
        icerik icinde eslesmesini kontrol ederek daha isabetli siralama yapariz.
        """
        # Sorguyu kelimelere ayir, kisa kelimeleri at
        query_lower = query.lower()
        keywords = [w for w in query_lower.split() if len(w) >= 3]
        if not keywords:
            return results

        # Stop words (Turkce)
        stop = {"bir", "icin", "ile", "kac", "nas", "olmali", "olan",
                "gibi", "daha", "kadar", "cok", "var", "yok", "bana"}

        keywords = [w for w in keywords if w not in stop]
        if not keywords:
            return results

        for r in results:
            title_lower = r["title"].lower()
            content_lower = r["content"][:300].lower()  # ilk 300 char yeterli

            # Baslikta eslesen keyword sayisi (agirlik: 0.15 / keyword)
            title_hits = sum(1 for kw in keywords if kw in title_lower)
            # Icerikte eslesen keyword sayisi (agirlik: 0.05 / keyword)
            content_hits = sum(1 for kw in keywords if kw in content_lower)

            bonus = title_hits * 0.15 + content_hits * 0.05
            r["score"] = round(r["score"] + bonus, 3)

        # Yeniden sirala (yuksek skor once)
        results.sort(key=lambda x: x["score"], reverse=True)
        return results

    def search(self, query, top_k=None, category=None):
        """
        Semantik arama + keyword re-ranking yapar.

        Args:
            query: Kullanici sorusu (Turkce/Ingilizce)
            top_k: Dondurulecek max sonuc (default: config'den)
            category: Kategori filtresi (ornegin "klipper_core")

        Returns:
            list[dict]: Her biri {id, title, content, category, subcategory, score, difficulty}
        """
        if not self._ensure_init():
            return []

        if top_k is None:
            top_k = self._config.SEARCH_TOP_K

        try:
            # Query embedding
            query_embedding = self._embedder.encode(query).tolist()

            # ChromaDB arama
            where_filter = None
            if category:
                where_filter = {"category": category}

            results = self._collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=where_filter,
                include=["documents", "metadatas", "distances"]
            )

            # Sonuclari isle
            output = []
            if results and results["ids"] and results["ids"][0]:
                for i, doc_id in enumerate(results["ids"][0]):
                    # ChromaDB cosine distance → similarity score (1 - distance)
                    distance = results["distances"][0][i] if results["distances"] else 0
                    score = 1.0 - distance

                    # Minimum skor filtresi
                    if score < self._config.MIN_RELEVANCE_SCORE:
                        continue

                    metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                    content = results["documents"][0][i] if results["documents"] else ""

                    output.append({
                        "id": doc_id,
                        "title": metadata.get("title", ""),
                        "content": content,
                        "category": metadata.get("category", ""),
                        "subcategory": metadata.get("subcategory", ""),
                        "difficulty": metadata.get("difficulty", ""),
                        "score": round(score, 3),
                    })

            # Keyword re-ranking: sorgu kelimelerinin baslik+icerik ile
            # eslesmesini semantik skora bonus olarak ekle
            if output:
                output = self._rerank_by_keywords(query, output)

            return output

        except Exception as e:
            logger.error(f"RAG arama hatasi: {e}")
            return []

    def build_context(self, query, max_entries=None, max_chars=None):
        """
        Kullanici sorusu icin RAG context metni olusturur.
        System prompt'a enjekte edilecek format.

        Args:
            query: Kullanici sorusu
            max_entries: Max giris sayisi (default: config'den)
            max_chars: Max toplam karakter (default: config'den)

        Returns:
            str: Formatli context metni, veya "" (sonuc yoksa)
        """
        if max_entries is None:
            max_entries = self._config.CONTEXT_MAX_ENTRIES
        if max_chars is None:
            max_chars = self._config.CONTEXT_MAX_CHARS

        results = self.search(query, top_k=max_entries + 2)  # biraz fazla ara, sonra kes
        if not results:
            return ""

        # En iyi sonuclari sec
        results = results[:max_entries]

        # Kompakt context formatla — token tasarrufu icin minimal overhead
        parts = []
        total_chars = 0
        for idx, r in enumerate(results, 1):
            entry_text = f"[{idx}] {r['title']}: {r['content']}"
            if total_chars + len(entry_text) > max_chars:
                # Karakter limitine ulasildi — icerigi kirp ama dahil et
                remaining = max_chars - total_chars - len(f"[{idx}] {r['title']}: ")
                if remaining > 50:
                    entry_text = f"[{idx}] {r['title']}: {r['content'][:remaining]}..."
                    parts.append(entry_text)
                break
            parts.append(entry_text)
            total_chars += len(entry_text)

        if not parts:
            return ""

        return "\n".join(parts)

    def load_from_jsonl(self, jsonl_path=None):
        """
        JSONL dosyasindan ChromaDB'ye toplu import.
        Indexleme scripti tarafindan kullanilir.

        Args:
            jsonl_path: JSONL dosya yolu (default: config'den)

        Returns:
            int: Eklenen giris sayisi
        """
        if not self.available:
            raise RuntimeError("RAG bagimliliklari eksik (chromadb, sentence-transformers)")

        if jsonl_path is None:
            jsonl_path = self._config.KB_JSONL_PATH

        # Embedding model yukle
        model_name = self._config.EMBEDDING_MODEL
        logger.info(f"Embedding model yukleniyor: {model_name}")
        embedder = _SentenceTransformer(model_name)

        # JSONL oku
        entries = []
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))

        logger.info(f"{len(entries)} giris okundu: {jsonl_path}")

        # ChromaDB client + collection olustur
        persist_dir = self._config.CHROMA_PERSIST_DIR
        os.makedirs(persist_dir, exist_ok=True)
        client = _chromadb.PersistentClient(path=persist_dir)

        # Eski collection varsa sil, yeniden olustur
        collection_name = self._config.CHROMA_COLLECTION
        try:
            client.delete_collection(name=collection_name)
            logger.info(f"Eski collection silindi: {collection_name}")
        except Exception:
            pass

        collection = client.create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}
        )

        # Batch embedding + insert
        batch_size = 50
        total_added = 0

        for i in range(0, len(entries), batch_size):
            batch = entries[i:i + batch_size]

            # Embedding icin icerik: title + keywords + content
            texts = []
            for e in batch:
                kw_str = ", ".join(e.get("keywords", []))
                embed_text = f"{e['title']}. {kw_str}. {e['content']}"
                texts.append(embed_text)

            # Batch embedding
            embeddings = embedder.encode(texts).tolist()

            # ChromaDB'ye ekle
            ids = [e["id"] for e in batch]
            documents = [e["content"] for e in batch]
            metadatas = [{
                "title": e["title"],
                "category": e["category"],
                "subcategory": e["subcategory"],
                "difficulty": e.get("difficulty", "beginner"),
                "source": e.get("source", ""),
                "keywords": ", ".join(e.get("keywords", [])),
            } for e in batch]

            collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas,
            )

            total_added += len(batch)
            logger.info(f"  {total_added}/{len(entries)} indexlendi")

        logger.info(f"Indexleme tamamlandi: {total_added} giris")
        return total_added

    @property
    def entry_count(self):
        """Indexlenmis giris sayisi."""
        if self._ensure_init():
            return self._entry_count
        return 0

    def get_stats(self):
        """RAG durumu ozeti."""
        return {
            "available": self.available,
            "initialized": self._initialized,
            "entry_count": self._entry_count,
            "model": self._config.EMBEDDING_MODEL if self.available else None,
        }
