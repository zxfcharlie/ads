from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.database import get_db
from app.models import User, UserAccess, BMCredential

router = APIRouter(prefix="/api/admin", tags=["admin-users"])


# ---------------- 用户列表 / 审核 ----------------
@router.get("/users")
def list_users(db: Session = Depends(get_db)):
    rows = db.query(User).order_by(User.created_at.desc()).all()
    return [
        {
            "id": u.id,
            "username": u.username,
            "is_admin": u.is_admin,
            "is_approved": u.is_approved,
            "created_at": u.created_at,
        }
        for u in rows
    ]


@router.post("/users/{user_id}/approve")
def approve_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    user.is_approved = True
    db.commit()
    return {"ok": True}


@router.post("/users/{user_id}/revoke")
def revoke_user(user_id: int, db: Session = Depends(get_db)):
    """撤销审核通过状态（重新变回待审核，暂时无法登录）"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.is_admin:
        raise HTTPException(status_code=400, detail="不能撤销管理员账号")
    user.is_approved = False
    db.commit()
    return {"ok": True}


@router.delete("/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db)):
    """删除用户（用于拒绝注册申请，或彻底移除某个账号）"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.is_admin:
        raise HTTPException(status_code=400, detail="不能删除管理员账号")
    db.delete(user)
    db.query(UserAccess).filter(UserAccess.user_id == user_id).delete()
    db.commit()
    return {"ok": True}


# ---------------- 账户访问权限分配 ----------------
@router.get("/users/{user_id}/access")
def list_access(user_id: int, db: Session = Depends(get_db)):
    grants = db.query(UserAccess).filter(UserAccess.user_id == user_id).all()
    cred_map = {c.id: c.label for c in db.query(BMCredential).all()}
    return [
        {
            "id": g.id,
            "credential_id": g.credential_id,
            "bm_label": cred_map.get(g.credential_id, "（该BM已被删除）"),
            "account_id": g.account_id,  # None = 整个 BM
        }
        for g in grants
    ]


class AccessGrantIn(BaseModel):
    credential_id: int
    account_id: Optional[str] = None  # 留空 = 整个 BM 下所有账户


@router.post("/users/{user_id}/access")
def grant_access(user_id: int, body: AccessGrantIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    cred = db.query(BMCredential).filter(BMCredential.id == body.credential_id).first()
    if not cred:
        raise HTTPException(status_code=404, detail="BM 凭证不存在")

    # 避免重复授权同一条
    existing = db.query(UserAccess).filter(
        UserAccess.user_id == user_id,
        UserAccess.credential_id == body.credential_id,
        UserAccess.account_id == body.account_id,
    ).first()
    if existing:
        return {"ok": True, "id": existing.id}

    row = UserAccess(user_id=user_id, credential_id=body.credential_id, account_id=body.account_id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"ok": True, "id": row.id}


@router.delete("/access/{access_id}")
def revoke_access(access_id: int, db: Session = Depends(get_db)):
    row = db.query(UserAccess).filter(UserAccess.id == access_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="授权记录不存在")
    db.delete(row)
    db.commit()
    return {"ok": True}
