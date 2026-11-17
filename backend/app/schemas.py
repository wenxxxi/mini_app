from typing import Literal, Optional

from pydantic import BaseModel, Field

MealType = Literal["breakfast", "lunch", "dinner", "snack"]


class LoginIn(BaseModel):
    code: str = Field(min_length=1, max_length=256)


class UserPatch(BaseModel):
    nickname: Optional[str] = Field(default=None, max_length=64)
    avatar_url: Optional[str] = Field(default=None, max_length=512)
    day_start_hour: Optional[int] = Field(default=None, ge=0, le=12)


class FoodItem(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    amount: float = Field(default=0, ge=0)
    unit: str = Field(default="g", max_length=16)
    kcal: float = Field(default=0, ge=0)
    protein: float = Field(default=0, ge=0)
    fat: float = Field(default=0, ge=0)
    carb: float = Field(default=0, ge=0)


class MealIn(BaseModel):
    meal_type: MealType
    eaten_at: Optional[str] = Field(default=None, max_length=32)
    foods: list[FoodItem] = Field(default_factory=list, max_length=50)
    note: Optional[str] = Field(default=None, max_length=1000)


class ReviewUpdate(BaseModel):
    wake_at: Optional[str] = Field(default=None, max_length=32)
    work_minutes: Optional[int] = Field(default=None, ge=0, le=1440)
    entertainment_minutes: Optional[int] = Field(default=None, ge=0, le=1440)
    mood: Optional[int] = Field(default=None, ge=1, le=5)
    summary: Optional[str] = Field(default=None, max_length=2000)


class StarIn(BaseModel):
    title: str = Field(min_length=1, max_length=128)
    situation: Optional[str] = Field(default=None, max_length=2000)
    task: Optional[str] = Field(default=None, max_length=2000)
    action: Optional[str] = Field(default=None, max_length=2000)
    result: Optional[str] = Field(default=None, max_length=2000)
    progress: int = Field(default=0, ge=0, le=100)
    minutes: int = Field(default=0, ge=0, le=1440)
    sort_order: int = Field(default=0, ge=0)


class ProgressPatch(BaseModel):
    progress: int = Field(ge=0, le=100)


class CountdownIn(BaseModel):
    title: str = Field(min_length=1, max_length=128)
    target_at: str = Field(min_length=10, max_length=32)
    note: Optional[str] = Field(default=None, max_length=1000)
    sort_order: int = Field(default=0, ge=0)
