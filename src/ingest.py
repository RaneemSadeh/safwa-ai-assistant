"""
Document Ingestion Pipeline for Safwa Bank RAG System.

Reads all .docx files from Data/, extracts text with metadata
(filename, estimated page, section title), chunks it, embeds it
with a multilingual sentence-transformer, and stores everything
in a local ChromaDB collection.

Run once (or whenever documents are updated):
    python src/ingest.py
"""

import sys
import re
import json
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import (
    DATA_DIR, CHROMA_DIR, EMBEDDING_MODEL,
    COLLECTION_NAME, CHUNK_SIZE, CHUNK_OVERLAP
)

STATUS_FILE = Path(__file__).parent.parent / "ingest_status.json"
CHARS_PER_PAGE = 2000   



def split_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Smart recursive splitter optimised for Arabic text."""
    text = text.strip()
    if len(text) <= chunk_size:
        return [text] if text else []

    separators = ["\n\n", "\n", ".", "،", "؟", "!", "؛", " "]

    for sep in separators:
        if sep not in text:
            continue
        parts = text.split(sep)
        chunks, current = [], ""
        for part in parts:
            candidate = current + part + sep
            if len(candidate) <= chunk_size:
                current = candidate
            else:
                if current.strip():
                    chunks.append(current.strip())
                if chunks:
                    tail = chunks[-1]
                    carry = tail[max(0, len(tail) - overlap):]
                    current = carry + part + sep
                else:
                    current = part + sep
        if current.strip():
            chunks.append(current.strip())
        if len(chunks) > 1:
            return [c for c in chunks if len(c.strip()) >= 30]

    return [text[i: i + chunk_size] for i in range(0, len(text), chunk_size - overlap)]


def is_heading(para) -> bool:
    """Detect if a paragraph is a heading (bold, short, heading style)."""
    style_name = para.style.name.lower() if para.style else ""
    if "heading" in style_name:
        return True
    text = para.text.strip()
    if not text or len(text) > 200:
        return False
    bold_count = sum(1 for run in para.runs if run.bold)
    return bold_count > 0 and bold_count == len([r for r in para.runs if r.text.strip()])



def extract_chunks_from_docx(docx_path: Path) -> list[dict]:
    """
    Extract structured chunks from a single .docx file.
    Returns list of dicts with keys: text, source_file, page_number, section_title.
    """
    from docx import Document

    doc = Document(str(docx_path))
    filename = docx_path.name

    raw_sections: list[dict] = []
    current_heading = "مقدمة"
    current_text = ""
    char_count = 0

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue

        for run in para.runs:
            for elem in run._element:
                tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                if tag in ("br", "lastRenderedPageBreak"):
                    br_type = elem.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}type", "")
                    if br_type == "page" or tag == "lastRenderedPageBreak":
                        if current_text.strip():
                            raw_sections.append({
                                "text": current_text.strip(),
                                "heading": current_heading,
                                "char_offset": char_count,
                            })
                        current_text = ""

        if is_heading(para):
            if current_text.strip():
                raw_sections.append({
                    "text": current_text.strip(),
                    "heading": current_heading,
                    "char_offset": char_count,
                })
            current_heading = text
            current_text = text + "\n"
        else:
            current_text += text + "\n"

        char_count += len(text)

    if current_text.strip():
        raw_sections.append({
            "text": current_text.strip(),
            "heading": current_heading,
            "char_offset": char_count,
        })

    final_chunks = []
    for sec in raw_sections:
        page_est = max(1, sec["char_offset"] // CHARS_PER_PAGE + 1)
        for sub in split_text(sec["text"]):
            if len(sub.strip()) < 40:
                continue
            final_chunks.append({
                "text": sub.strip(),
                "source_file": filename,
                "page_number": page_est,
                "section_title": sec["heading"][:120],
            })

    return final_chunks



def ingest_documents(progress_callback=None) -> dict:
    """
    Full ingestion pipeline.
    Returns summary dict: {total_chunks, total_docs, error_docs}.
    """
    import chromadb
    from sentence_transformers import SentenceTransformer

    def log(msg: str):
        print(msg)
        if progress_callback:
            progress_callback(msg)

    _update_status("running", "Starting ingestion...", 0)

    log(f"Loading embedding model: {EMBEDDING_MODEL}")
    _update_status("running", f"Loading embedding model…", 5)
    model = SentenceTransformer(EMBEDDING_MODEL)

    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    try:
        client.delete_collection(COLLECTION_NAME)
        log("Cleared existing vector collection.")
    except Exception:
        pass
    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}
    )

    docx_files = sorted(DATA_DIR.glob("*.docx"))
    log(f"Found {len(docx_files)} documents in Data/")
    _update_status("running", f"Found {len(docx_files)} documents", 10)

    all_texts, all_metas, all_ids = [], [], []
    error_docs = []

    for idx, docx_path in enumerate(docx_files):
        pct = 10 + int((idx / len(docx_files)) * 50)
        _update_status("running", f"Parsing {docx_path.name}…", pct)
        log(f"  [{idx+1}/{len(docx_files)}] Processing: {docx_path.name}")
        try:
            chunks = extract_chunks_from_docx(docx_path)
            for j, chunk in enumerate(chunks):
                chunk_id = f"doc{idx:02d}_chunk{j:04d}"
                all_texts.append(chunk["text"])
                all_metas.append({
                    "source_file":   chunk["source_file"],
                    "page_number":   chunk["page_number"],
                    "section_title": chunk["section_title"],
                })
                all_ids.append(chunk_id)
            log(f"     → {len(chunks)} chunks extracted")
        except Exception as e:
            log(f"ERROR processing {docx_path.name}: {e}")
            error_docs.append(docx_path.name)

    log(f"\nTotal chunks: {len(all_texts)}")
    _update_status("running", f"Embedding {len(all_texts)} chunks…", 60)

    log("Generating embeddings…")
    batch_size = 64
    all_embeddings = []
    for i in range(0, len(all_texts), batch_size):
        batch = all_texts[i: i + batch_size]
        embs = model.encode(batch, show_progress_bar=False, normalize_embeddings=True)
        all_embeddings.extend(embs.tolist())
        done = min(i + batch_size, len(all_texts))
        pct = 60 + int((done / len(all_texts)) * 30)
        _update_status("running", f"Embedded {done}/{len(all_texts)} chunks", pct)
        log(f"  Embedded {done}/{len(all_texts)}")

    log("Storing in ChromaDB…")
    _update_status("running", "Storing in vector DB…", 90)
    store_batch = 200
    for i in range(0, len(all_texts), store_batch):
        collection.add(
            documents=all_texts[i: i + store_batch],
            embeddings=all_embeddings[i: i + store_batch],
            metadatas=all_metas[i: i + store_batch],
            ids=all_ids[i: i + store_batch],
        )

    summary = {
        "total_chunks": len(all_texts),
        "total_docs": len(docx_files),
        "error_docs": error_docs,
    }
    log(f"\n Ingestion complete! {len(all_texts)} chunks from {len(docx_files)} documents.")
    _update_status("done", "Ingestion complete!", 100, summary)
    return summary



def _update_status(state: str, message: str, progress: int, extra: dict = None):
    payload = {
        "state": state,
        "message": message,
        "progress": progress,
        "timestamp": time.time(),
    }
    if extra:
        payload.update(extra)
    try:
        STATUS_FILE.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def get_ingest_status() -> dict:
    """Read the last ingestion status from disk."""
    if not STATUS_FILE.exists():
        return {"state": "idle", "message": "Not yet ingested", "progress": 0}
    try:
        return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"state": "error", "message": "Status file unreadable", "progress": 0}


if __name__ == "__main__":
    ingest_documents()