from __future__ import annotations

import uuid
from typing import Any

from app.rag.schemas import RagDocument


class RagDocumentProcessor:
    def process_human_diagnosis_case(
        self,
        *,
        case_id: str,
        text: str,
        source: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> list[RagDocument]:
        return [
            RagDocument(
                document_id=case_id,
                text=text,
                source=source,
                metadata={
                    **(metadata or {}),
                    "doc_type": "human_diagnosis_case",
                    "case_id": case_id,
                    "chunk_strategy": "case",
                },
            )
        ]

    def process_system_design_document(
        self,
        *,
        document_id: str,
        sections: list[dict[str, Any]],
        source: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> list[RagDocument]:
        documents: list[RagDocument] = []
        for index, section in enumerate(sections):
            text = str(section.get("text") or "").strip()
            if not text:
                continue
            section_id = str(section.get("section_id") or f"section_{index}")
            documents.append(
                RagDocument(
                    document_id=f"{document_id}:{section_id}",
                    text=text,
                    source=source,
                    metadata={
                        **(metadata or {}),
                        "doc_type": "system_design_document",
                        "parent_document_id": document_id,
                        "section_id": section_id,
                        "section_title": section.get("title"),
                        "page_start": section.get("page_start"),
                        "page_end": section.get("page_end"),
                        "chunk_strategy": "section",
                    },
                )
            )
        return documents

    def process_agent_case_summary(
        self,
        *,
        case_uid: str,
        user_query: str | None,
        final_answer: str,
        evidence_summary: str | None = None,
        candidate_causes: list[dict[str, Any]] | None = None,
        tools_used: list[str] | None = None,
        skills_used: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> list[RagDocument]:
        text_parts = [
            f"用户问题: {user_query or ''}",
            f"诊断结论: {final_answer}",
        ]
        if evidence_summary:
            text_parts.append(f"证据摘要: {evidence_summary}")
        if candidate_causes:
            text_parts.append(f"候选原因: {candidate_causes}")

        return [
            RagDocument(
                document_id=f"agent_case:{case_uid}:{_short_uuid(final_answer)}",
                text="\n".join(text_parts),
                source="agent_case_summary",
                metadata={
                    **(metadata or {}),
                    "doc_type": "agent_case_summary",
                    "case_uid": case_uid,
                    "candidate_causes": candidate_causes or [],
                    "tools_used": tools_used or [],
                    "skills_used": skills_used or [],
                    "chunk_strategy": "summary_card",
                },
            )
        ]


def _short_uuid(value: str) -> str:
    return uuid.uuid5(uuid.NAMESPACE_URL, value).hex[:12]
