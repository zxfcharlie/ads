from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.models import GoogleCredential
from app.google_client import GoogleAdsClient, GoogleAdsAPIError

router = APIRouter(prefix="/api/google/credentials", tags=["google-credentials"])


def _mask(s: str) -> str:
    if not s or len(s) < 8:
        return "****"
    return s[:4] + "..." + s[-4:]


@router.get("")
def list_credentials(db: Session = Depends(get_db)):
    rows = db.query(GoogleCredential).order_by(GoogleCredential.created_at.desc()).all()
    return [
        {
            "id": r.id,
            "label": r.label,
            "login_customer_id": r.login_customer_id,
            "is_active": r.is_active,
            "developer_token_preview": _mask(r.developer_token),
            "refresh_token_preview": _mask(r.refresh_token),
            "created_at": r.created_at,
        }
        for r in rows
    ]


class GoogleCredentialIn(BaseModel):
    label: str = ""
    developer_token: str
    client_id: str
    client_secret: str
    refresh_token: str
    login_customer_id: str = ""


@router.post("")
async def create_credential(body: GoogleCredentialIn, db: Session = Depends(get_db)):
    # 先试探性拉一次可访问账户列表，确认这套 OAuth2 凭证真的有效再存
    client = GoogleAdsClient(
        body.developer_token, body.client_id, body.client_secret,
        body.refresh_token, body.login_customer_id,
    )
    try:
        customer_ids = await client.list_accessible_customers()
    except GoogleAdsAPIError as e:
        raise HTTPException(status_code=400, detail=f"凭证校验失败，未保存：{e}")

    label = body.label.strip()
    if not label:
        if customer_ids:
            try:
                info = await client.get_customer_info(customer_ids[0])
                label = info.get("name") or f"Google账户-{customer_ids[0]}"
            except GoogleAdsAPIError:
                label = f"Google凭证-{body.refresh_token[-4:]}"
        else:
            label = f"Google凭证-{body.refresh_token[-4:]}"

    row = GoogleCredential(
        label=label,
        developer_token=body.developer_token,
        client_id=body.client_id,
        client_secret=body.client_secret,
        refresh_token=body.refresh_token,
        login_customer_id=body.login_customer_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "label": row.label, "accessible_customers": customer_ids}


class GoogleCredentialUpdateIn(BaseModel):
    label: str | None = None
    developer_token: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    refresh_token: str | None = None
    login_customer_id: str | None = None
    is_active: bool | None = None


@router.patch("/{credential_id}")
def update_credential(credential_id: int, body: GoogleCredentialUpdateIn, db: Session = Depends(get_db)):
    row = db.query(GoogleCredential).filter(GoogleCredential.id == credential_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="未找到该凭证")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(row, field, value)
    db.commit()
    return {"ok": True}


@router.delete("/{credential_id}")
def delete_credential(credential_id: int, db: Session = Depends(get_db)):
    row = db.query(GoogleCredential).filter(GoogleCredential.id == credential_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="未找到该凭证")
    db.delete(row)
    db.commit()
    return {"ok": True}
