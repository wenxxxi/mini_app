from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from . import models  # noqa: F401  确保建表前模型已注册
from .db import Base, engine
from .routers import auth, countdowns, files, meals, me, reviews, star, stats

APP_VERSION = "0.1.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Review MiniApp API", version=APP_VERSION, lifespan=lifespan)

app.include_router(auth.router)
app.include_router(me.router)
app.include_router(reviews.router)
app.include_router(meals.router)
app.include_router(star.router)
app.include_router(countdowns.router)
app.include_router(stats.router)
app.include_router(files.router)


@app.get("/")
def root_redirect():
    return RedirectResponse("/files/ui")


@app.get("/healthz")
def healthz():
    return {"ok": True, "version": APP_VERSION}
