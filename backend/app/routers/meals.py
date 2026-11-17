from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..models import DailyReview, Meal, User
from ..schemas import MealIn
from ..services import apply_meal, check_date, get_or_create_review, touch

router = APIRouter(prefix="/api", tags=["meals"])


def _get_meal(db: Session, user: User, meal_id: int) -> Meal:
    meal = db.scalar(
        select(Meal)
        .join(DailyReview)
        .where(Meal.id == meal_id, DailyReview.user_id == user.id)
    )
    if meal is None:
        raise HTTPException(status_code=404, detail="餐食记录不存在")
    return meal


@router.post("/reviews/{date}/meals")
def create_meal(
    date: str,
    payload: MealIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    check_date(date)
    review = get_or_create_review(db, user, date)
    meal = Meal(review_id=review.id)
    apply_meal(meal, payload)
    touch(review)
    db.add(meal)
    db.commit()
    db.refresh(meal)
    return meal.to_dict()


@router.put("/meals/{meal_id}")
def update_meal(
    meal_id: int,
    payload: MealIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    meal = _get_meal(db, user, meal_id)
    apply_meal(meal, payload)
    touch(meal.review)
    db.commit()
    db.refresh(meal)
    return meal.to_dict()


@router.delete("/meals/{meal_id}")
def delete_meal(
    meal_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    meal = _get_meal(db, user, meal_id)
    touch(meal.review)
    db.delete(meal)
    db.commit()
    return Response(status_code=204)
