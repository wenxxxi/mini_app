from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..models import DailyReview, User
from ..services import check_date
from ..timeutil import parse_dt

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/summary")
def summary(
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
        .order_by(DailyReview.review_date.asc())
    ).all()

    wakes: list[int] = []
    kcal_total = 0.0
    series = []
    for row in rows:
        day_kcal = round(sum(m.kcal or 0 for m in row.meals), 1)
        kcal_total += day_kcal
        if row.wake_at:
            try:
                dt = parse_dt(row.wake_at)
                wakes.append(dt.hour * 60 + dt.minute)
            except ValueError:
                pass
        series.append(
            {
                "date": row.review_date,
                "work_minutes": row.work_minutes,
                "entertainment_minutes": row.entertainment_minutes,
                "kcal": day_kcal,
            }
        )

    days = len(rows)
    avg_wake = round(sum(wakes) / len(wakes)) if wakes else None
    return {
        "days": days,
        "work_minutes": sum(r.work_minutes for r in rows),
        "entertainment_minutes": sum(r.entertainment_minutes for r in rows),
        "avg_wake_minutes": avg_wake,
        "avg_wake_text": (
            f"{avg_wake // 60:02d}:{avg_wake % 60:02d}" if avg_wake is not None else None
        ),
        "kcal_total": round(kcal_total, 1),
        "avg_kcal": round(kcal_total / days, 1) if days else 0,
        "series": series,
    }
