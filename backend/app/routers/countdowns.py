from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..models import Countdown, User
from ..schemas import CountdownIn
from ..timeutil import now_iso

router = APIRouter(prefix="/api/countdowns", tags=["countdowns"])


@router.get("")
def list_countdowns(
    include_past: bool = Query(default=False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = select(Countdown).where(Countdown.user_id == user.id)
    if not include_past:
        stmt = stmt.where(Countdown.target_at >= now_iso())
    rows = db.scalars(stmt.order_by(Countdown.target_at.asc(), Countdown.id.asc())).all()
    return [row.to_dict() for row in rows]


@router.post("")
def create_countdown(
    payload: CountdownIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = Countdown(user_id=user.id, **payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item.to_dict()


@router.put("/{item_id}")
def update_countdown(
    item_id: int,
    payload: CountdownIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = db.get(Countdown, item_id)
    if item is None or item.user_id != user.id:
        raise HTTPException(status_code=404, detail="倒计时不存在")
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return item.to_dict()


@router.delete("/{item_id}")
def delete_countdown(
    item_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = db.get(Countdown, item_id)
    if item is None or item.user_id != user.id:
        raise HTTPException(status_code=404, detail="倒计时不存在")
    db.delete(item)
    db.commit()
    return Response(status_code=204)
