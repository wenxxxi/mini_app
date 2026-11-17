from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..models import User
from ..schemas import UserPatch

router = APIRouter(prefix="/api/me", tags=["me"])


@router.get("")
def read_me(user: User = Depends(get_current_user)):
    return user.to_dict()


@router.patch("")
def update_me(
    payload: UserPatch,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        if value is not None:
            setattr(user, key, value)
    db.commit()
    db.refresh(user)
    return user.to_dict()
