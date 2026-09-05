from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.fb_client import FBClient, FBAPIError
from app.database import get_db
from app.models import AccountNote, OperationLog, BMCredential, AccountCredentialMap
from app.resolver import get_client_for_account, _upsert_map

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


def _augment_budget_fields(acc: dict) -> dict:
    """
    Facebook 原始 balance 字段含义因账户资金模式而异（预付费=预存余额；
    信用额度=待还款金额），不等于"距花费上限还能花多少"。
    这里额外计算一个真正有意义的字段：remaining_budget = spend_cap - amount_spent。
    spend_cap 为 0 或缺失时，代表该账户没有设置花费上限。
    """
    try:
        spend_cap = int(acc.get("spend_cap") or 0)
        amount_spent = int(acc.get("amount_spent") or 0)
    except (TypeError, ValueError):
        spend_cap, amount_spent = 0, 0

    if spend_cap > 0:
        acc["has_spend_cap"] = True
        acc["remaining_budget"] = spend_cap - amount_spent
    else:
        acc["has_spend_cap"] = False
        acc["remaining_budget"] = None
    return acc


@router.get("")
async def list_accounts(db: Session = Depends(get_db)):
    """聚合所有已配置的 Business Manager 下的广告账户"""
    creds = db.query(BMCredential).filter(BMCredential.is_active == True).all()  # noqa: E712
    notes = {n.account_id: n for n in db.query(AccountNote).all()}

    all_data = []
    errors = []

    for cred in creds:
        client = FBClient(cred.access_token)
        try:
            result = await client.list_ad_accounts()
        except FBAPIError as e:
            errors.append({"credential": cred.label, "error": str(e)})
            continue

        for acc in result.get("data", []):
            acc["bm_label"] = cred.label
            acc["credential_id"] = cred.id
            note = notes.get(acc["id"])
            acc["label"] = note.label if note else ""
            acc["group"] = note.group if note else ""
            acc["note"] = note.note if note else ""
            _augment_budget_fields(acc)
            all_data.append(acc)
            _upsert_map(db, acc["id"], cred.id)

    return {"data": all_data, "errors": errors}


@router.get("/{account_id}")
async def get_account(account_id: str, db: Session = Depends(get_db)):
    client = await get_client_for_account(account_id, db)
    try:
        acc = await client.get_account(account_id)
    except FBAPIError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    return _augment_budget_fields(acc)


class SpendCapIn(BaseModel):
    spend_cap_cents: int


@router.post("/{account_id}/spend_cap")
async def set_spend_cap(account_id: str, body: SpendCapIn, db: Session = Depends(get_db)):
    client = await get_client_for_account(account_id, db)

    # 提前做一次本地校验，避免无意义地打一个必然失败的请求：
    # Facebook 不允许把花费上限设得比已花费金额还低（0 表示清除上限，不受此限制）。
    if body.spend_cap_cents != 0:
        try:
            current = await client.get_account(account_id)
            amount_spent = int(current.get("amount_spent") or 0)
        except FBAPIError:
            amount_spent = 0
        if body.spend_cap_cents < amount_spent:
            raise HTTPException(
                status_code=400,
                detail=f"新的花费上限（{body.spend_cap_cents} 分）不能低于已花费金额（{amount_spent} 分）。"
                       f"如需取消上限请填 0。",
            )

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
        # 把 Facebook 返回的具体原因原样抛给前端，而不是笼统的"失败"
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
