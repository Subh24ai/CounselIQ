"""Regulatory monitor service: ingestion, embedding, and impact matching.

Matching is always scoped to a single organisation — clause embeddings are
compared only against documents owned by the caller's org, never across the
tenant boundary.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Clause, Document, RegulatoryUpdate
from app.schemas.regulatory import AffectedDocumentMatch, RegulatoryUpdateCreate
from app.services.embeddings import embedding_service

# Calibrated for all-MiniLM-L6-v2 on cross-domain text (a regulatory summary vs
# a contract clause). Empirically these pairs score ~0.27-0.45 even when clearly
# related, so the near-duplicate-style 0.55 default returns nothing. 0.35
# surfaces the genuinely relevant clauses while filtering the weakest matches;
# tune per deployment as more data accrues.
DEFAULT_SIMILARITY_THRESHOLD = 0.35


async def create_regulatory_update(
    db: AsyncSession, data: RegulatoryUpdateCreate
) -> RegulatoryUpdate:
    """Persist a regulatory update and embed its title+summary for matching.

    Embedding is generated inline (local model, fast) — no Celery hand-off.
    """
    embedding = await embedding_service.generate_embedding(
        f"{data.title}\n{data.summary}"
    )
    record = RegulatoryUpdate(
        source=data.source,
        title=data.title,
        summary=data.summary,
        full_text=data.full_text,
        url=data.url,
        published_date=data.published_date,
        embedding=embedding,
        is_processed=False,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


async def _get_update(
    db: AsyncSession, regulatory_update_id: UUID
) -> RegulatoryUpdate:
    update = await db.get(RegulatoryUpdate, regulatory_update_id)
    if update is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Regulatory update not found",
        )
    return update


async def find_affected_documents(
    db: AsyncSession,
    regulatory_update_id: UUID,
    organisation_id: UUID,
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    limit: int = 20,
) -> list[AffectedDocumentMatch]:
    """Return the org's documents whose clauses best match an update.

    Uses pgvector cosine distance. ``DISTINCT ON (document_id)`` keeps only the
    single best-matching clause per document; results are then filtered by the
    similarity threshold and returned strongest-first.
    """
    update = await _get_update(db, regulatory_update_id)
    if update.embedding is None:
        # Nothing to compare against — should not happen for created updates.
        return []

    distance = Clause.embedding.cosine_distance(update.embedding)
    stmt = (
        select(
            Clause.document_id.label("document_id"),
            Clause.id.label("clause_id"),
            Clause.content.label("content"),
            Document.name.label("document_name"),
            distance.label("distance"),
        )
        .join(Document, Clause.document_id == Document.id)
        .where(
            Document.organisation_id == organisation_id,
            Clause.embedding.is_not(None),
        )
        # DISTINCT ON requires the distinct column to lead the ORDER BY; within
        # each document the lowest distance (closest clause) wins.
        .distinct(Clause.document_id)
        .order_by(Clause.document_id, distance)
    )
    rows = (await db.execute(stmt)).all()

    matches: list[AffectedDocumentMatch] = []
    for row in rows:
        similarity = 1.0 - float(row.distance)
        if similarity < similarity_threshold:
            continue
        excerpt = (row.content or "")[:200]
        matches.append(
            AffectedDocumentMatch(
                document_id=row.document_id,
                document_name=row.document_name,
                similarity_score=round(similarity, 4),
                matched_clause_id=row.clause_id,
                matched_clause_excerpt=excerpt or None,
            )
        )

    matches.sort(key=lambda m: m.similarity_score, reverse=True)
    return matches[:limit]


async def mark_processed(
    db: AsyncSession, regulatory_update_id: UUID
) -> RegulatoryUpdate:
    """Flag an update as reviewed/handled by the organisation."""
    update = await _get_update(db, regulatory_update_id)
    update.is_processed = True
    await db.commit()
    await db.refresh(update)
    return update


async def backfill_clause_embeddings(
    db: AsyncSession,
    organisation_id: UUID | None = None,
    batch_size: int = 50,
) -> int:
    """Embed clauses that have no vector yet. Returns the number embedded.

    One-time/periodic maintenance: clauses created before embedding-on-analysis
    existed (and any that slipped through) get backfilled here. Optionally
    scoped to one organisation; with no scope it processes all orgs.
    """
    stmt = select(Clause).where(Clause.embedding.is_(None))
    if organisation_id is not None:
        stmt = stmt.join(Document, Clause.document_id == Document.id).where(
            Document.organisation_id == organisation_id
        )
    clauses = list((await db.execute(stmt)).scalars().all())

    updated = 0
    for start in range(0, len(clauses), batch_size):
        batch = clauses[start : start + batch_size]
        vectors = await embedding_service.generate_embeddings_batch(
            [clause.content or "" for clause in batch]
        )
        for clause, vector in zip(batch, vectors, strict=True):
            clause.embedding = vector
        await db.commit()
        updated += len(batch)

    return updated
