from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.fb_client import FBClient, FBAPIError
from app.database import get_db
from app.models import AccountNote, OperationLog

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


@router.get("")
async def list_accounts(db: Session = Depends(get_db)):
    client = FBClient()
    try:
        result = await client.list_ad_accounts()
    except FBAPIError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))

    notes = {n.account_id: n for n in db.query(AccountNote).all()}
    data = result.get("data", [])
    for acc in data:
        note = notes.get(acc["id"])
        acc["label"] = note.label if note else ""
        acc["group"] = note.group if note else ""
        acc["note"] = note.note if note else ""
        # 金额单位由 FB 返回的是最小货币单位字符串，前端换算展示
    return {"data": data}


@router.get("/{account_id}")
async def get_account(account_id: str):
    client = FBClient()
    try:
        return await client.get_account(account_id)
    except FBAPIError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))


class SpendCapIn(BaseModel):
    spend_cap_cents: int


@router.post("/{account_id}/spend_cap")
async def set_spend_cap(account_id: str, body: SpendCapIn, db: Session = Depends(get_db)):
    client = FBClient()
    try:
        result = await client.update_spend_cap(account_id, body.spend_cap_cents)
        db.add(OperationLog(account_id=account_id, action="update_spend_cap",
                             detail=str(body.spend_cap_cents), status="success"))
        db.commit()
        return result
    except FBAPIError as e:
        db.add(OperationLog(account_id=account_id, action="update_spend_cap",
                             detail=str(e), status="failed"))
        db.commit()
        raise HTTPException(status_code=e.status_code, detail=str(e))


class NoteIn(BaseModel):
    label: str = ""
    group: str = ""
    note: str = ""


@router.post("/{account_id}/note")
def upsert_note(account_id: str, body: NoteIn, db: Session = Depends(get_db)):
    row = db.query(AccountNote).filter(AccountNote.account_id == account_id).first()
    if not row:
        row = AccountNote(account_id=account_id)
        db.add(row)
    row.label = body.label
    row.group = body.group
    row.note = body.note
    db.commit()
    return {"ok": True}
