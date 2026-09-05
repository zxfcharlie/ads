from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, engine, SessionLocal, get_db
from app.auth import create_access_token, hash_password, verify_password
from app.models import User
from app.deps import get_current_user, require_admin
from app.routers import accounts, campaigns, insights, credentials, targeting, users

Base.metadata.create_all(bind=engine)


def _ensure_admin_user():
    """把 .env 里的 ADMIN_USERNAME/ADMIN_PASSWORD 同步成一个 is_admin=True 的账号，
    每次启动都会校验一次，方便你改了 .env 密码后重启就生效。"""
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.username == settings.admin_username).first()
        if not admin:
            db.add(User(
                username=settings.admin_username,
                password_hash=hash_password(settings.admin_password),
                is_admin=True,
                is_approved=True,
            ))
            db.commit()
        elif not verify_password(settings.admin_password, admin.password_hash):
            admin.password_hash = hash_password(settings.admin_password)
            admin.is_admin = True
            admin.is_approved = True
            db.commit()
    finally:
        db.close()


_ensure_admin_user()

app = FastAPI(title="广告管理平台（Meta 已接入，Google/TikTok 等渠道待接入）")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------- 注册 / 登录（账号密码 + 审核制）----------------
class RegisterIn(BaseModel):
    username: str
    password: str


@app.post("/api/register")
def register(body: RegisterIn, db: Session = Depends(get_db)):
    username = body.username.strip()
    if not username or not body.password:
        raise HTTPException(status_code=400, detail="请填写用户名和密码")
    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="密码至少 6 位")
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        raise HTTPException(status_code=400, detail="用户名已被占用")
    user = User(username=username, password_hash=hash_password(body.password), is_admin=False, is_approved=False)
    db.add(user)
    db.commit()
    return {"message": "注册成功，请等待管理员审核通过后再登录"}


class LoginIn(BaseModel):
    username: str
    password: str


@app.post("/api/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == body.username).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="账号或密码错误")
    if not user.is_approved:
        raise HTTPException(status_code=403, detail="账号正在等待管理员审核，请稍后再试")
    token = create_access_token(user.username)
    return {"token": token, "username": user.username, "is_admin": user.is_admin}


# 普通功能路由：登录且审核通过即可访问，具体账户可见范围由各接口内部按授权过滤
app.include_router(accounts.router, dependencies=[Depends(get_current_user)])
app.include_router(campaigns.router, dependencies=[Depends(get_current_user)])
app.include_router(insights.router, dependencies=[Depends(get_current_user)])
app.include_router(targeting.router, dependencies=[Depends(get_current_user)])

# 管理员专属路由：BM 令牌管理、用户审核与权限分配
app.include_router(credentials.router, dependencies=[Depends(require_admin)])
app.include_router(users.router, dependencies=[Depends(require_admin)])


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/me")
def me(user: User = Depends(get_current_user)):
    return {"username": user.username, "is_admin": user.is_admin}


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def index():
    return FileResponse("static/index.html")
