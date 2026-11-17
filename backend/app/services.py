import json
import re

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import DailyReview, User
from .schemas import MealIn
from .timeutil import now_iso

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def check_date(value: str) -> str:
    if not DATE_RE.match(value):
        raise HTTPException(status_code=422, detail="日期格式应为 YYYY-MM-DD")
    return value


def get_review(db: Session, user: User, date: str) -> DailyReview | None:
    return db.scalar(
        select(DailyReview).where(
            DailyReview.user_id == user.id,
            DailyReview.review_date == date,
        )
    )


def get_or_create_review(db: Session, user: User, date: str) -> DailyReview:
    review = get_review(db, user, date)
    if review is None:
        review = DailyReview(user_id=user.id, review_date=date)
        db.add(review)
        db.commit()
        db.refresh(review)
    return review


def require_review(db: Session, user: User, date: str) -> DailyReview:
    review = get_review(db, user, date)
    if review is None:
        raise HTTPException(status_code=404, detail="当日复盘不存在")
    return review


def apply_meal(meal, payload: MealIn) -> None:
    """以 foods 明细为准重新计算营养合计，不信任客户端合计值。"""
    meal.meal_type = payload.meal_type
    meal.eaten_at = payload.eaten_at
    meal.note = payload.note
    meal.foods_json = json.dumps(
        [f.model_dump() for f in payload.foods], ensure_ascii=False
    )
    meal.kcal = round(sum(f.kcal for f in payload.foods), 1)
    meal.protein_g = round(sum(f.protein for f in payload.foods), 1)
    meal.fat_g = round(sum(f.fat for f in payload.foods), 1)
    meal.carb_g = round(sum(f.carb for f in payload.foods), 1)


def touch(review: DailyReview) -> None:
    review.updated_at = now_iso()


def empty_review(date: str) -> dict:
    return {
        "id": None,
        "review_date": date,
        "wake_at": None,
        "work_minutes": 0,
        "entertainment_minutes": 0,
        "mood": None,
        "summary": None,
        "updated_at": None,
        "meals": [],
        "star_items": [],
    }
