from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from planagent.db import get_session
from planagent.domain.api import DebateVoteCreate, DebateVoteRead
from planagent.domain.models import DebateSessionRecord, DebateVote

router = APIRouter(tags=["Debate Votes"])


@router.post("/debate/votes", response_model=DebateVoteRead, status_code=201)
async def create_debate_vote(
    payload: DebateVoteCreate,
    session: AsyncSession = Depends(get_session),
) -> DebateVoteRead:
    debate = await session.get(DebateSessionRecord, payload.debate_session_id)
    if debate is None:
        raise HTTPException(
            status_code=404,
            detail=f"Debate {payload.debate_session_id} was not found.",
        )

    vote = DebateVote(
        debate_session_id=payload.debate_session_id,
        round_number=payload.round_number,
        role=payload.role,
        vote=payload.vote,
        comment=payload.comment.strip() if payload.comment else None,
    )
    session.add(vote)
    await session.commit()
    await session.refresh(vote)
    return DebateVoteRead.model_validate(vote)


@router.get("/debate/votes", response_model=list[DebateVoteRead])
async def list_debate_votes(
    debate_session_id: str = Query(min_length=1),
    session: AsyncSession = Depends(get_session),
) -> list[DebateVoteRead]:
    votes = (
        await session.scalars(
            select(DebateVote)
            .where(DebateVote.debate_session_id == debate_session_id)
            .order_by(
                DebateVote.round_number.asc(),
                DebateVote.role.asc(),
                DebateVote.created_at.desc(),
            )
        )
    ).all()
    return [DebateVoteRead.model_validate(vote) for vote in votes]
