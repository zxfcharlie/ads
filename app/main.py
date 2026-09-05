from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config import settings
from app.database import Base, engine
from app.routers import accounts, campaigns, insights

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Facebook Ads 管理面板")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------- 简单口令登录（用于内网/自用部署）----------------
class LoginIn(BaseModel):
    password: str


@app.post("/api/login")
def login(body: LoginIn):
    if body.password != settings.panel_password:
        raise HTTPException(status_code=401, detail="密码错误")
    return {"token": settings.panel_password}


def verify_token(x_panel_token: str | None = Header(default=None)):
    if x_panel_token != settings.panel_password:
        raise HTTPException(status_code=401, detail="未授权")
    return True


# 给需要保护的路由加统一依赖
app.include_router(accounts.router, dependencies=[Depends(verify_token)])
app.include_router(campaigns.router, dependencies=[Depends(verify_token)])
app.include_router(insights.router, dependencies=[Depends(verify_token)])


@app.get("/api/health")
def health():
    return {"status": "ok"}


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def index():
    return FileResponse("static/index.html")
