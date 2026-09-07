from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import calendar

from app.database import get_db
from app.models import GoogleCredential
from app.google_client import GoogleAdsClient, GoogleAdsAPIError
from app.google_resolver import get_google_client_for_customer

router = APIRouter(prefix="/api/google", tags=["google"])


def _month_range(year: int, month: int) -> tuple[str, str]:
    last_day = calendar.monthrange(year, month)[1]
    since = f"{year:04d}-{month:02d}-01"
    until = f"{year:04d}-{month:02d}-{last_day:02d}"
    return since, until


# 注：目前 Google 侧还没有像 Meta 那样做"按用户分配具体账户权限"，
# 已登录且审核通过的用户能看到所有已配置 Google 凭证下的账户。后续要做细粒度权限，
# 可以参照 app/models.py 里 UserAccess 的模式，为 Google 建一张平行的授权表。

@router.get("/accounts")
async def list_accounts(db: Session = Depends(get_db)):
    creds = db.query(GoogleCredential).filter(GoogleCredential.is_active == True).all()  # noqa: E712
    all_data = []
    errors = []
    for cred in creds:
        client = GoogleAdsClient(
            cred.developer_token, cred.client_id, cred.client_secret,
            cred.refresh_token, cred.login_customer_id,
        )
        try:
            accounts = await client.list_all_accounts()
        except GoogleAdsAPIError as e:
            errors.append({"credential": cred.label, "error": str(e)})
            continue
        for acc in accounts:
            acc["credential_id"] = cred.id
            acc["credential_label"] = cred.label
            all_data.append(acc)
    return {"data": all_data, "errors": errors}


@router.get("/accounts/{customer_id}/campaigns")
async def list_campaigns(customer_id: str, db: Session = Depends(get_db)):
    client = await get_google_client_for_customer(customer_id, db)
    try:
        return {"data": await client.list_campaigns(customer_id)}
    except GoogleAdsAPIError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/accounts/{customer_id}/daily_stats")
async def daily_stats(customer_id: str, year: int, month: int, db: Session = Depends(get_db)):
    client = await get_google_client_for_customer(customer_id, db)
    since, until = _month_range(year, month)
    try:
        rows = await client.get_daily_stats(customer_id, since, until)
    except GoogleAdsAPIError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"data": rows, "since": since, "until": until}


@router.get("/stats/daily_summary")
async def daily_summary(year: int, month: int, db: Session = Depends(get_db)):
    since, until = _month_range(year, month)
    creds = db.query(GoogleCredential).filter(GoogleCredential.is_active == True).all()  # noqa: E712

    by_date: dict[str, dict] = {}
    errors = []

    for cred in creds:
        client = GoogleAdsClient(
            cred.developer_token, cred.client_id, cred.client_secret,
            cred.refresh_token, cred.login_customer_id,
        )
        try:
            customer_ids = await client.list_accessible_customers()
        except GoogleAdsAPIError as e:
            errors.append({"credential": cred.label, "error": str(e)})
            continue

        for cid in customer_ids:
            try:
                rows = await client.get_daily_stats(cid, since, until)
            except GoogleAdsAPIError:
                continue  # 跳过没权限/不是叶子账户的情况，不算错误
            for r in rows:
                d = by_date.setdefault(r["date"], {"date": r["date"], "spend": 0.0, "revenue": 0.0, "purchases": 0.0})
                d["spend"] += r["spend"]
                d["revenue"] += r["revenue"]
                d["purchases"] += r["purchases"]

    data = sorted(by_date.values(), key=lambda x: x["date"])
    return {"data": data, "since": since, "until": until, "errors": errors}
