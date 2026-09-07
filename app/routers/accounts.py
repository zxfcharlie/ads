from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
import calendar

from app.fb_client import FBClient, FBAPIError
from app.database import get_db
from app.models import AccountNote, OperationLog, BMCredential, AccountCredentialMap, User, UserAccess
from app.resolver import get_client_for_account, _upsert_map
from app.deps import get_current_user

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
async def list_accounts(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """聚合展示广告账户：管理员看所有已配置 BM 下的账户；普通用户只看被授权的部分"""
    creds = db.query(BMCredential).filter(BMCredential.is_active == True).all()  # noqa: E712
    notes = {n.account_id: n for n in db.query(AccountNote).all()}

    grants_by_cred: dict[int, set[str] | None] = {}
    if not user.is_admin:
        grants = db.query(UserAccess).filter(UserAccess.user_id == user.id).all()
        for g in grants:
            if g.credential_id not in grants_by_cred:
                grants_by_cred[g.credential_id] = set()
            bucket = grants_by_cred[g.credential_id]
            if g.account_id is None:
                grants_by_cred[g.credential_id] = None  # None 表示整个 BM 都放行
            elif bucket is not None:
                bucket.add(g.account_id)

    all_data = []
    errors = []

    for cred in creds:
        if not user.is_admin and cred.id not in grants_by_cred:
            continue  # 普通用户完全没被授权这个 BM，跳过

        client = FBClient(cred.access_token)
        try:
            result = await client.list_ad_accounts()
        except FBAPIError as e:
            errors.append({"credential": cred.label, "error": str(e)})
            continue

        allowed_accounts = None if user.is_admin else grants_by_cred.get(cred.id)

        for acc in result.get("data", []):
            if allowed_accounts is not None and acc["id"] not in allowed_accounts:
                continue  # 普通用户只被授权了这个 BM 下的部分账户

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
async def get_account(account_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    client = await get_client_for_account(account_id, db, user)
    try:
        acc = await client.get_account(account_id)
    except FBAPIError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    return _augment_budget_fields(acc)


class SpendCapIn(BaseModel):
    spend_cap_cents: int


@router.post("/{account_id}/spend_cap")
async def set_spend_cap(
    account_id: str, body: SpendCapIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    client = await get_client_for_account(account_id, db, user)

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


# ==================== 数据统计：按月看每天的花费 / 销售额 ====================


def _month_range(year: int, month: int) -> tuple[str, str]:
    last_day = calendar.monthrange(year, month)[1]
    since = f"{year:04d}-{month:02d}-01"
    until = f"{year:04d}-{month:02d}-{last_day:02d}"
    return since, until


@router.get("/{account_id}/daily_stats")
async def daily_stats(
    account_id: str,
    year: int,
    month: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """某个账户在指定月份，逐日的花费/销售额，用于「数据统计」页面"""
    client = await get_client_for_account(account_id, db, user)
    since, until = _month_range(year, month)
    try:
        rows = await client.get_daily_stats(account_id, since, until)
    except FBAPIError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    return {"data": rows, "since": since, "until": until}


@router.get("/stats/daily_summary")
async def daily_summary(
    year: int,
    month: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    把当前用户能看到的所有账户，按天汇总花费/销售额（跨账户求和）。
    用于「数据统计」页面选"全部账户汇总"时展示。
    """
    since, until = _month_range(year, month)

    creds = db.query(BMCredential).filter(BMCredential.is_active == True).all()  # noqa: E712
    grants_by_cred: dict[int, set[str] | None] = {}
    if not user.is_admin:
        grants = db.query(UserAccess).filter(UserAccess.user_id == user.id).all()
        for g in grants:
            if g.credential_id not in grants_by_cred:
                grants_by_cred[g.credential_id] = set()
            bucket = grants_by_cred[g.credential_id]
            if g.account_id is None:
                grants_by_cred[g.credential_id] = None
            elif bucket is not None:
                bucket.add(g.account_id)

    by_date: dict[str, dict] = {}
    errors = []

    for cred in creds:
        if not user.is_admin and cred.id not in grants_by_cred:
            continue

        client = FBClient(cred.access_token)
        try:
            accounts_res = await client.list_ad_accounts()
        except FBAPIError as e:
            errors.append({"credential": cred.label, "error": str(e)})
            continue

        allowed_accounts = None if user.is_admin else grants_by_cred.get(cred.id)

        for acc in accounts_res.get("data", []):
            if allowed_accounts is not None and acc["id"] not in allowed_accounts:
                continue
            try:
                rows = await client.get_daily_stats(acc["id"], since, until)
            except FBAPIError as e:
                errors.append({"credential": cred.label, "account": acc.get("name", acc["id"]), "error": str(e)})
                continue
            for r in rows:
                d = by_date.setdefault(r["date"], {"date": r["date"], "spend": 0.0, "revenue": 0.0, "purchases": 0.0})
                d["spend"] += r["spend"]
                d["revenue"] += r["revenue"]
                d["purchases"] += r["purchases"]

    data = sorted(by_date.values(), key=lambda x: x["date"])
    return {"data": data, "since": since, "until": until, "errors": errors}
