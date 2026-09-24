"""Build and load the persistent Chroma + BM25 indexes."""

from __future__ import annotations

import json
import pickle
import logging
from pathlib import Path
from typing import Any

import chromadb
from rank_bm25 import BM25Okapi

from app.core.config import get_settings
from app.rag.chunking import chunk_corpus
from app.rag.embeddings import embed_texts
from app.rag.ingest import ingest_corpus
from app.rag.tokenize import tokenize


CHUNKS_FILE = "chunks.jsonl"
BM25_FILE = "bm25.pkl"
CHROMA_DIR = "chroma"
BUILD_MARKER = ".building"
logger = logging.getLogger(__name__)


class IndexUnavailableError(RuntimeError):
    """The index is missing, incomplete, or inconsistent."""


def _index_paths(index_dir: Path | None = None) -> dict[str, Path]:
    settings = get_settings()
    root = Path(index_dir or settings.index_dir)
    return {
        "root": root,
        "chunks": root / CHUNKS_FILE,
        "bm25": root / BM25_FILE,
        "chroma": root / CHROMA_DIR,
    }


def index_is_ready(index_dir: Path | None = None) -> bool:
    try:
        IndexStore(index_dir)
        return True
    except Exception as exc:
        logger.warning("Index validation failed (%s). Rebuild the search index.", type(exc).__name__)
        return False


def save_chunks(chunks: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for chunk in chunks:
            handle.write(json.dumps(chunk, ensure_ascii=False) + "\n")


def load_chunks(index_dir: Path | None = None) -> list[dict[str, Any]]:
    path = _index_paths(index_dir)["chunks"]
    chunks: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                chunks.append(json.loads(line))
    return chunks


def _chroma_metadata(chunk: dict[str, Any]) -> dict[str, Any]:
    return {
        "doc_id": chunk["doc_id"],
        "filename": chunk["filename"],
        "title": chunk["title"],
        "short_title": chunk["short_title"],
        "year": int(chunk["year"]),
        "publisher": chunk["publisher"],
        "doc_type": chunk["doc_type"],
        "ncd_types": chunk["ncd_types"],
        "audience": chunk["audience"],
        "source_family": chunk["source_family"],
        "page": int(chunk["page"]),
        "section": chunk["section"][:300],
    }


def build_index(index_dir: Path | None = None, data_dir: Path | None = None) -> dict[str, Any]:
    settings = get_settings()
    paths = _index_paths(index_dir)
    data_dir = Path(data_dir or settings.data_dir)
    paths["root"].mkdir(parents=True, exist_ok=True)

    (paths["root"] / BUILD_MARKER).touch()
    global _STORE
    _STORE = None
    documents = ingest_corpus(data_dir)
    chunks = chunk_corpus(
        documents,
        max_chars=settings.chunk_size_chars,
        overlap=settings.chunk_overlap_chars,
    )
    if not chunks:
        raise IndexUnavailableError("Cannot build an empty search index.")
    save_chunks(chunks, paths["chunks"])

    tokenized = [tokenize(chunk["text"]) for chunk in chunks]
    bm25 = BM25Okapi(tokenized)
    with paths["bm25"].open("wb") as handle:
        pickle.dump({"bm25": bm25, "ids": [c["chunk_id"] for c in chunks]}, handle)

    embeddings = embed_texts([c["text"] for c in chunks])
    client = chromadb.PersistentClient(path=str(paths["chroma"]))
    if settings.chroma_collection in [c.name for c in client.list_collections()]:
        client.delete_collection(settings.chroma_collection)
    collection = client.get_or_create_collection(
        name=settings.chroma_collection,
        metadata={"hnsw:space": "cosine"},
    )
    batch = 128
    for start in range(0, len(chunks), batch):
        end = start + batch
        subset = chunks[start:end]
        collection.add(
            ids=[c["chunk_id"] for c in subset],
            documents=[c["text"] for c in subset],
            metadatas=[_chroma_metadata(c) for c in subset],
            embeddings=embeddings[start:end].tolist(),
        )

    IndexStore(paths["root"], allow_building=True)
    (paths["root"] / BUILD_MARKER).unlink()
    return {
        "documents": len(documents),
        "chunks": len(chunks),
        "index_dir": str(paths["root"]),
    }


class IndexStore:
    def __init__(self, index_dir: Path | None = None, *, allow_building: bool = False) -> None:
        self.paths = _index_paths(index_dir)
        self.settings = get_settings()
        if not allow_building and (self.paths["root"] / BUILD_MARKER).exists():
            raise IndexUnavailableError("Index build is incomplete. Rebuild the search index.")
        for path in (self.paths["chunks"], self.paths["bm25"], self.paths["chroma"] / "chroma.sqlite3"):
            if not path.is_file() or path.stat().st_size == 0:
                raise IndexUnavailableError("A required index file is missing or empty. Rebuild the search index.")
        self.chunks = load_chunks(self.paths["root"])
        required = {"chunk_id", "text", "doc_id", "filename", "title", "short_title", "year", "publisher", "doc_type", "ncd_types", "audience", "source_family", "page", "section"}
        if not self.chunks or any(not required <= c.keys() or not c["text"] for c in self.chunks):
            raise IndexUnavailableError("Chunk data is empty or invalid. Rebuild the search index.")
        self.chunk_by_id = {c["chunk_id"]: c for c in self.chunks}
        if len(self.chunk_by_id) != len(self.chunks):
            raise IndexUnavailableError("Duplicate chunk IDs. Rebuild the search index.")
        with self.paths["bm25"].open("rb") as handle:
            payload = pickle.load(handle)
        self.bm25: BM25Okapi = payload["bm25"]
        self.bm25_ids: list[str] = payload["ids"]
        if (not isinstance(self.bm25, BM25Okapi)
                or self.bm25_ids != [c["chunk_id"] for c in self.chunks]
                or self.bm25.corpus_size != len(self.chunks)
                or len(self.bm25.doc_freqs) != len(self.chunks)
                or len(self.bm25.doc_len) != len(self.chunks)):
            raise IndexUnavailableError("BM25 and chunk data disagree. Rebuild the search index.")
        self.client = chromadb.PersistentClient(path=str(self.paths["chroma"]))
        self.collection = self.client.get_collection(self.settings.chroma_collection)
        if set(self.collection.get(include=[])["ids"]) != set(self.chunk_by_id):
            raise IndexUnavailableError("Vector and chunk data disagree. Rebuild the search index.")

    def facets(self) -> dict[str, Any]:
        ncd: set[str] = set()
        docs = {}
        years: set[int] = set()
        doc_types: set[str] = set()
        families: set[str] = set()
        for chunk in self.chunks:
            for label in chunk["ncd_types"].split(","):
                if label.strip():
                    ncd.add(label.strip())
            docs[chunk["doc_id"]] = {
                "doc_id": chunk["doc_id"],
                "title": chunk["title"],
                "short_title": chunk["short_title"],
                "year": chunk["year"],
            }
            years.add(int(chunk["year"]))
            doc_types.add(chunk["doc_type"])
            families.add(chunk["source_family"])
        return {
            "ncd_types": sorted(ncd),
            "documents": sorted(docs.values(), key=lambda d: d["short_title"]),
            "years": sorted(years),
            "doc_types": sorted(doc_types),
            "source_families": sorted(families),
        }


_STORE: IndexStore | None = None


def get_store() -> IndexStore:
    global _STORE
    if (_index_paths()["root"] / BUILD_MARKER).exists():
        _STORE = None
        raise IndexUnavailableError("Index build is incomplete. Rebuild the search index.")
    if _STORE is None:
        try:
            _STORE = IndexStore()
        except Exception as exc:
            raise IndexUnavailableError("Search index is unavailable or incomplete. Rebuild it before retrying.") from exc
    return _STORE


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Validate all index components without rebuilding.")
    args = parser.parse_args()
    if args.check:
        raise SystemExit(0 if index_is_ready() else 1)
    summary = build_index()
    print(f"Indexed {summary['chunks']} chunks from {summary['documents']} documents -> {summary['index_dir']}")
