from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.rag import (
    MinioConfig,
    MinioObjectStore,
    QdrantStoreConfig,
    RagDocumentProcessor,
    RagDocumentRepository,
    RagDocumentStore,
    build_embedding_provider,
    build_rag_service,
    build_sparse_embedding_provider,
    sha256_file,
)
from app.rag.service import SYSTEM_DESIGN_DOCUMENT

DEFAULT_FILE = ROOT / "develop_documents/pss/人身安全联锁系统.doc"
DEFAULT_DOCUMENT_ID = "pss_personnel_safety_interlock_system"
DEFAULT_DOCUMENT_UID = "ragdoc_pss_personnel_safety_interlock"
PARSER_VERSION = "pss-doc-v1"
CHUNKER_VERSION = "rag-service-default-v1"


def main() -> None:
    args = _parse_args()
    file_path = args.file.resolve()
    if not file_path.exists():
        raise FileNotFoundError(file_path)

    init_db()

    text = extract_doc_text(file_path)
    sections = build_sections(text)
    if not sections:
        raise ValueError("No usable text sections were extracted from the document.")

    service = build_rag_service()
    service.initialize(recreate=False)
    processor = RagDocumentProcessor()
    rag_documents = processor.process_system_design_document(
        document_id=args.document_id,
        sections=sections,
        source=str(file_path.relative_to(ROOT)),
        metadata={
            "domain": "pss",
            "subsystem": "pss",
            "source_file": str(file_path.relative_to(ROOT)),
            "title": args.title,
            "parser_version": PARSER_VERSION,
        },
    )
    chunks = service.index_documents(rag_documents)

    dense_embeddings = build_embedding_provider()
    sparse_embeddings = build_sparse_embedding_provider()
    qdrant_config = QdrantStoreConfig.from_env()

    with SessionLocal() as db:
        repository = RagDocumentRepository(db)
        record = repository.get(args.document_uid)
        checksum = sha256_file(file_path)
        if record is None:
            document_store = RagDocumentStore(
                repository=repository,
                object_store=MinioObjectStore(MinioConfig.from_env()),
            )
            record = document_store.save_original_file(
                file_path,
                doc_type=SYSTEM_DESIGN_DOCUMENT,
                title=args.title,
                source_type="local_document",
                document_uid=args.document_uid,
                metadata={
                    "domain": "pss",
                    "subsystem": "pss",
                    "document_id": args.document_id,
                    "parser_version": PARSER_VERSION,
                },
            )
        elif record.checksum_sha256 != checksum:
            raise ValueError(
                "A RAG document with the requested document_uid already exists "
                "but its checksum is different. Use another --document-uid."
            )

        record = repository.mark_indexed(
            record.document_uid,
            qdrant_collection=qdrant_config.collection_name,
            chunk_count=len(chunks),
            embedding_model=dense_embeddings.model,
            embedding_dimension=dense_embeddings.dimension,
            sparse_model=sparse_embeddings.model,
            parser_version=PARSER_VERSION,
            chunker_version=CHUNKER_VERSION,
        )

    verification = service.search(
        args.verify_query,
        limit=5,
        include_system_design=True,
        metadata_filter={"subsystem": "pss"},
    )
    output = {
        "document_uid": record.document_uid,
        "document_id": args.document_id,
        "title": record.title,
        "status": record.status,
        "minio_uri": record.source_uri,
        "qdrant_collection": record.qdrant_collection,
        "section_count": len(sections),
        "chunk_count": len(chunks),
        "verification_hits": [
            {
                "document_id": item.document_id,
                "score": item.score,
                "section_title": item.metadata.get("section_title"),
                "text_preview": item.text[:160],
            }
            for item in verification
        ],
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


def extract_doc_text(file_path: Path) -> str:
    if file_path.suffix.lower() != ".doc":
        return file_path.read_text(encoding="utf-8")

    external_text = _extract_with_external_tool(file_path)
    if _looks_like_pss_text(external_text):
        return normalize_text(external_text)

    raw = file_path.read_bytes()
    decoded = raw.decode("utf-16le", errors="ignore")
    return normalize_text(decoded)


def build_sections(text: str) -> list[dict[str, Any]]:
    pss_text = _slice_pss_section(text)
    headings = [
        "4.3.1人身安全联锁系统",
        "4.3.1.1系统总体设计",
        "4.3.1.2基本结构",
        "4.3.1.3系统主要设备",
        "4.3.1.4系统状态及运行流程",
        "4.3.1.5系统联锁逻辑",
        "4.3.1.6 相关系统信号接口",
    ]

    matches: list[tuple[int, str]] = []
    for heading in headings:
        index = pss_text.find(heading)
        if index >= 0:
            matches.append((index, heading))
    matches.sort(key=lambda item: item[0])

    if not matches:
        return [
            {
                "section_id": "pss_document",
                "title": "PSS document",
                "text": pss_text,
            }
        ]

    sections: list[dict[str, Any]] = []
    for index, (start, heading) in enumerate(matches):
        end = matches[index + 1][0] if index + 1 < len(matches) else len(pss_text)
        body = pss_text[start:end].strip()
        if len(body) < 20:
            continue
        section_id = re.sub(r"[^0-9a-zA-Z]+", "_", heading).strip("_").lower()
        sections.append(
            {
                "section_id": section_id,
                "title": heading,
                "text": body,
            }
        )
    return sections


def normalize_text(text: str) -> str:
    visible = "".join(
        char if (char.isprintable() or char in "\n\r\t") else " "
        for char in text
    )
    visible = re.sub(r"HYPERLINK\s+\\l\s+_Toc\d+", " ", visible)
    visible = re.sub(r"PAGEREF\s+_Toc\d+\s+\\h", " ", visible)
    visible = re.sub(r"REF\s+_Ref\d+\s+\\h", " ", visible)
    visible = re.sub(r"PAGE\s+\\\*\s+MERGEFORMAT\s+\S+", " ", visible)
    visible = re.sub(r"\s+", " ", visible)
    return visible.strip()


def _slice_pss_section(text: str) -> str:
    start_candidates = [
        text.find("4.3.1人身安全联锁系统 4.3.1.1系统总体设计"),
        text.find("4.3.1.1系统总体设计"),
        text.find("STCF-BTP加速器人身安全联锁系统"),
    ]
    start = next((item for item in start_candidates if item >= 0), 0)
    if start > 0 and text[start:].startswith("4.3.1.1"):
        previous = text.rfind("4.3.1人身安全联锁系统", 0, start)
        if previous >= 0:
            start = previous

    end_candidates = [
        text.find("4.3.2辐射监测系统", start + 1),
        text.find("超级陶粲装置关键技术攻关项目", start + 1),
        text.find("核工业二七", start + 1),
    ]
    end = next((item for item in end_candidates if item > start), len(text))
    return text[start:end].strip()


def _extract_with_external_tool(file_path: Path) -> str:
    commands = [
        ["antiword", str(file_path)],
        ["catdoc", str(file_path)],
        ["wvText", str(file_path), "-"],
        ["pandoc", "-t", "plain", str(file_path)],
    ]
    for command in commands:
        if shutil.which(command[0]) is None:
            continue
        try:
            completed = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=60,
            )
        except (subprocess.SubprocessError, OSError):
            continue
        if completed.stdout.strip():
            return completed.stdout
    return ""


def _looks_like_pss_text(text: str) -> bool:
    return bool(text) and "人身安全联锁系统" in text and "PLC" in text


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest the PSS personnel safety interlock document into RAG.",
    )
    parser.add_argument("--file", type=Path, default=DEFAULT_FILE)
    parser.add_argument("--document-id", default=DEFAULT_DOCUMENT_ID)
    parser.add_argument("--document-uid", default=DEFAULT_DOCUMENT_UID)
    parser.add_argument("--title", default="人身安全联锁系统")
    parser.add_argument(
        "--verify-query",
        default="PSS 人身安全联锁 系统状态 急停按钮 PLC 门禁",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
