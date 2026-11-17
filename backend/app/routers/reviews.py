from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..models import DailyReview, User
from ..schemas import ReviewUpdate
from ..services import (
    check_date,
    empty_review,
    get_or_create_review,
    get_review,
    touch,
)
router = APIRouter(prefix="/api/reviews", tags=["reviews"])


@router.get("")
def list_reviews(
    from_: str = Query(alias="from"),
    to: str = Query(),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    check_date(from_)
    check_date(to)
    rows = db.scalars(
        select(DailyReview)
        .where(
            DailyReview.user_id == user.id,
            DailyReview.review_date >= from_,
            DailyReview.review_date <= to,
        )
        .order_by(DailyReview.review_date.desc())
    ).all()
    result = []
    for row in rows:
        item = row.to_dict()
        item["kcal"] = round(sum(m.kcal or 0 for m in row.meals), 1)
        item["star_count"] = len(row.star_items)
        item["star_minutes"] = sum(s.minutes or 0 for s in row.star_items)
        result.append(item)
    return result


@router.get("/{date}")
def read_review(
    date: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    check_date(date)
    review = get_review(db, user, date)
    if review is None:
        return empty_review(date)
    return review.to_dict(with_children=True)


@router.put("/{date}")
def upsert_review(
    date: str,
    payload: ReviewUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    check_date(date)
    review = get_or_create_review(db, user, date)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(review, key, value)
    touch(review)
    db.commit()
    db.refresh(review)
    return review.to_dict(with_children=True)


@router.delete("/{date}")
def delete_review(
    date: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    check_date(date)
    review = get_review(db, user, date)
    if review is not None:
        db.delete(review)
        db.commit()
    return Response(status_code=204)
