from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.models import BMCredential, AccountCredentialMap
from app.fb_client import FBClient, FBAPIError

router = APIRouter(prefix="/api/credentials", tags=["credentials"])


def _mask(token: str) -> str:
    if not token or len(token) < 10:
        return "****"
    return token[:6] + "..." + token[-4:]


@router.get("")
def list_credentials(db: Session = Depends(get_db)):
    rows = db.query(BMCredential).order_by(BMCredential.created_at.desc()).all()
    return [
        {
            "id": r.id,
            "label": r.label,
            "bm_id": r.bm_id,
            "is_active": r.is_active,
            "token_preview": _mask(r.access_token),
            "created_at": r.created_at,
        }
        for r in rows
    ]


class CredentialIn(BaseModel):
    label: str
    bm_id: str = ""
    access_token: str


@router.post("")
async def create_credential(body: CredentialIn, db: Session = Depends(get_db)):
    # 先用这个 token 试探性调用一次，确认有效再存
    client = FBClient(body.access_token)
    try:
        await client.list_ad_accounts()
    except FBAPIError as e:
        raise HTTPException(status_code=400, detail=f"令牌校验失败，未保存：{e}")

    row = BMCredential(label=body.label, bm_id=body.bm_id, access_token=body.access_token)
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "label": row.label}


class CredentialUpdateIn(BaseModel):
    label: str | None = None
    bm_id: str | None = None
    access_token: str | None = None
    is_active: bool | None = None


@router.patch("/{credential_id}")
def update_credential(credential_id: int, body: CredentialUpdateIn, db: Session = Depends(get_db)):
    row = db.query(BMCredential).filter(BMCredential.id == credential_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="未找到该凭证")
    if body.label is not None:
        row.label = body.label
    if body.bm_id is not None:
        row.bm_id = body.bm_id
    if body.access_token is not None:
        row.access_token = body.access_token
    if body.is_active is not None:
        row.is_active = body.is_active
    db.commit()
    return {"ok": True}


@router.delete("/{credential_id}")
def delete_credential(credential_id: int, db: Session = Depends(get_db)):
    row = db.query(BMCredential).filter(BMCredential.id == credential_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="未找到该凭证")
    db.delete(row)
    db.query(AccountCredentialMap).filter(
        AccountCredentialMap.credential_id == credential_id
    ).delete()
    db.commit()
    return {"ok": True}
