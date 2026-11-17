from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..models import DailyReview, StarItem, User
from ..schemas import ProgressPatch, StarIn
from ..services import check_date, get_or_create_review, touch

router = APIRouter(prefix="/api", tags=["star"])


def _get_item(db: Session, user: User, item_id: int) -> StarItem:
    item = db.scalar(
        select(StarItem)
        .join(DailyReview)
        .where(StarItem.id == item_id, DailyReview.user_id == user.id)
    )
    if item is None:
        raise HTTPException(status_code=404, detail="工作记录不存在")
    return item


def _validate(payload: StarIn) -> None:
    if not (payload.situation or "").strip() and not (payload.result or "").strip():
        raise HTTPException(status_code=422, detail="情境与结果至少填写一项")


@router.post("/reviews/{date}/star")
def create_star(
    date: str,
    payload: StarIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    check_date(date)
    _validate(payload)
    review = get_or_create_review(db, user, date)
    item = StarItem(review_id=review.id, **payload.model_dump())
    touch(review)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item.to_dict()


@router.put("/star/{item_id}")
def update_star(
    item_id: int,
    payload: StarIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _validate(payload)
    item = _get_item(db, user, item_id)
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    touch(item.review)
    db.commit()
    db.refresh(item)
    return item.to_dict()


@router.patch("/star/{item_id}/progress")
def update_progress(
    item_id: int,
    payload: ProgressPatch,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = _get_item(db, user, item_id)
    item.progress = payload.progress
    touch(item.review)
    db.commit()
    db.refresh(item)
    return item.to_dict()


@router.delete("/star/{item_id}")
def delete_star(
    item_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = _get_item(db, user, item_id)
    touch(item.review)
    db.delete(item)
    db.commit()
    return Response(status_code=204)
