import json
from typing import Optional

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base
from .timeutil import now_iso


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    openid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    unionid: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    nickname: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    tz: Mapped[str] = mapped_column(String(64), default="Asia/Shanghai")
    day_start_hour: Mapped[int] = mapped_column(Integer, default=4)
    created_at: Mapped[str] = mapped_column(String(32), default=now_iso)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "nickname": self.nickname,
            "avatar_url": self.avatar_url,
            "tz": self.tz,
            "day_start_hour": self.day_start_hour,
        }


class DailyReview(Base):
    __tablename__ = "daily_reviews"
    __table_args__ = (
        UniqueConstraint("user_id", "review_date", name="uq_review_user_date"),
        Index("idx_reviews_user_date", "user_id", "review_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    review_date: Mapped[str] = mapped_column(String(10))
    wake_at: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    work_minutes: Mapped[int] = mapped_column(Integer, default=0)
    entertainment_minutes: Mapped[int] = mapped_column(Integer, default=0)
    mood: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String(32), default=now_iso)
    updated_at: Mapped[str] = mapped_column(String(32), default=now_iso)

    meals: Mapped[list["Meal"]] = relationship(
        back_populates="review", cascade="all, delete-orphan", lazy="selectin"
    )
    star_items: Mapped[list["StarItem"]] = relationship(
        back_populates="review", cascade="all, delete-orphan", lazy="selectin"
    )

    def to_dict(self, with_children: bool = False) -> dict:
        data = {
            "id": self.id,
            "review_date": self.review_date,
            "wake_at": self.wake_at,
            "work_minutes": self.work_minutes,
            "entertainment_minutes": self.entertainment_minutes,
            "mood": self.mood,
            "summary": self.summary,
            "updated_at": self.updated_at,
        }
        if with_children:
            data["meals"] = [m.to_dict() for m in sorted(self.meals, key=lambda x: x.id)]
            data["star_items"] = [
                s.to_dict()
                for s in sorted(self.star_items, key=lambda x: (x.sort_order, x.id))
            ]
        return data


class Meal(Base):
    __tablename__ = "meals"
    __table_args__ = (Index("idx_meals_review", "review_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    review_id: Mapped[int] = mapped_column(
        ForeignKey("daily_reviews.id", ondelete="CASCADE")
    )
    meal_type: Mapped[str] = mapped_column(String(16))
    eaten_at: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    foods_json: Mapped[str] = mapped_column(Text, default="[]")
    kcal: Mapped[float] = mapped_column(default=0.0)
    protein_g: Mapped[float] = mapped_column(default=0.0)
    fat_g: Mapped[float] = mapped_column(default=0.0)
    carb_g: Mapped[float] = mapped_column(default=0.0)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    review: Mapped[DailyReview] = relationship(back_populates="meals")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "meal_type": self.meal_type,
            "eaten_at": self.eaten_at,
            "foods": json.loads(self.foods_json or "[]"),
            "kcal": round(self.kcal or 0, 1),
            "protein_g": round(self.protein_g or 0, 1),
            "fat_g": round(self.fat_g or 0, 1),
            "carb_g": round(self.carb_g or 0, 1),
            "note": self.note,
        }


class StarItem(Base):
    __tablename__ = "star_items"
    __table_args__ = (Index("idx_star_review", "review_id", "sort_order"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    review_id: Mapped[int] = mapped_column(
        ForeignKey("daily_reviews.id", ondelete="CASCADE")
    )
    title: Mapped[str] = mapped_column(String(128))
    situation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    task: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    action: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    minutes: Mapped[int] = mapped_column(Integer, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    review: Mapped[DailyReview] = relationship(back_populates="star_items")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "situation": self.situation,
            "task": self.task,
            "action": self.action,
            "result": self.result,
            "progress": self.progress,
            "minutes": self.minutes,
            "sort_order": self.sort_order,
        }


class Countdown(Base):
    __tablename__ = "countdowns"
    __table_args__ = (Index("idx_countdown_user", "user_id", "target_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(128))
    target_at: Mapped[str] = mapped_column(String(32))
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[str] = mapped_column(String(32), default=now_iso)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "target_at": self.target_at,
            "note": self.note,
            "sort_order": self.sort_order,
            "created_at": self.created_at,
        }
