from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config import settings
from app.database import Base, engine
from app.auth import create_access_token, decode_access_token
from app.routers import accounts, campaigns, insights, credentials, targeting

Base.metadata.create_all(bind=engine)

app = FastAPI(title="广告管理平台（Meta 已接入，Google/TikTok 等渠道待接入）")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------- 账号密码登录（JWT）----------------
class LoginIn(BaseModel):
    username: str
    password: str


@app.post("/api/login")
def login(body: LoginIn):
    if body.username != settings.admin_username or body.password != settings.admin_password:
        raise HTTPException(status_code=401, detail="账号或密码错误")
    token = create_access_token(body.username)
    return {"token": token, "username": body.username}


def verify_token(authorization: str | None = Header(default=None)):
    """请求头需要： Authorization: Bearer <token>"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未授权")
    token = authorization.split(" ", 1)[1]
    username = decode_access_token(token)
    if not username:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    return username


# 给需要保护的路由加统一依赖
app.include_router(accounts.router, dependencies=[Depends(verify_token)])
app.include_router(campaigns.router, dependencies=[Depends(verify_token)])
app.include_router(insights.router, dependencies=[Depends(verify_token)])
app.include_router(credentials.router, dependencies=[Depends(verify_token)])
app.include_router(targeting.router, dependencies=[Depends(verify_token)])


@app.get("/api/health")
def health():
    return {"status": "ok"}


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def index():
    return FileResponse("static/index.html")
