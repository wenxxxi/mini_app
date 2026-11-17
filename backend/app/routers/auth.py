import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import DEV_LOGIN, WX_APPID, WX_SECRET
from ..db import get_db
from ..models import User
from ..schemas import LoginIn
from ..security import create_token

router = APIRouter(prefix="/api/auth", tags=["auth"])

WX_CODE2SESSION = "https://api.weixin.qq.com/sns/jscode2session"


async def resolve_openid(code: str) -> str:
    if DEV_LOGIN and code.startswith("dev:"):
        return f"dev-{code[4:] or 'local'}"
    if not WX_APPID or not WX_SECRET:
        raise HTTPException(status_code=500, detail="服务端未配置小程序 AppID/Secret")
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            WX_CODE2SESSION,
            params={
                "appid": WX_APPID,
                "secret": WX_SECRET,
                "js_code": code,
                "grant_type": "authorization_code",
            },
        )
    data = resp.json()
    openid = data.get("openid")
    if not openid:
        raise HTTPException(
            status_code=401,
            detail=f"微信登录失败：{data.get('errmsg', '未知错误')}",
        )
    return openid


@router.post("/login")
async def login(payload: LoginIn, db: Session = Depends(get_db)):
    openid = await resolve_openid(payload.code)
    user = db.scalar(select(User).where(User.openid == openid))
    if user is None:
        user = User(openid=openid)
        db.add(user)
        db.commit()
        db.refresh(user)
    return {"token": create_token(user.id), "user": user.to_dict()}
