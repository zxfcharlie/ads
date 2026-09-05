from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.fb_client import FBAPIError
from app.database import get_db
from app.models import OperationLog
from app.resolver import get_client_for_account

router = APIRouter(prefix="/api", tags=["campaigns"])


def _log(db: Session, account_id: str, action: str, detail: str, status: str = "success"):
    db.add(OperationLog(account_id=account_id, action=action, detail=detail, status=status))
    db.commit()


# ---------------- Campaign ----------------
@router.get("/accounts/{account_id}/campaigns")
async def list_campaigns(account_id: str, db: Session = Depends(get_db)):
    client = await get_client_for_account(account_id, db)
    try:
        return await client.list_campaigns(account_id)
    except FBAPIError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))


class CampaignIn(BaseModel):
    name: str
    objective: str  # 如 OUTCOME_TRAFFIC / OUTCOME_LEADS / OUTCOME_SALES / OUTCOME_ENGAGEMENT
    status: str = "PAUSED"
    special_ad_categories: list[str] = []


@router.post("/accounts/{account_id}/campaigns")
async def create_campaign(account_id: str, body: CampaignIn, db: Session = Depends(get_db)):
    client = await get_client_for_account(account_id, db)
    try:
        result = await client.create_campaign(
            account_id, body.name, body.objective, body.status, body.special_ad_categories
        )
        _log(db, account_id, "create_campaign", f"{body.name}/{result.get('id')}")
        return result
    except FBAPIError as e:
        _log(db, account_id, "create_campaign", str(e), "failed")
        raise HTTPException(status_code=e.status_code, detail=str(e))


# ---------------- AdSet ----------------
@router.get("/accounts/{account_id}/adsets")
async def list_adsets(account_id: str, campaign_id: Optional[str] = None, db: Session = Depends(get_db)):
    client = await get_client_for_account(account_id, db)
    try:
        return await client.list_adsets(account_id, campaign_id)
    except FBAPIError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))


class AdSetIn(BaseModel):
    name: str
    campaign_id: str
    daily_budget_cents: int
    billing_event: str = "IMPRESSIONS"
    optimization_goal: str = "LINK_CLICKS"
    status: str = "PAUSED"
    bid_amount_cents: Optional[int] = None
    # 简化的定向参数
    countries: list[str] = ["US"]
    age_min: int = 18
    age_max: int = 65
    genders: Optional[list[int]] = None  # 1=男 2=女，留空为不限


@router.post("/accounts/{account_id}/adsets")
async def create_adset(account_id: str, body: AdSetIn, db: Session = Depends(get_db)):
    client = await get_client_for_account(account_id, db)
    targeting = {
        "geo_locations": {"countries": body.countries},
        "age_min": body.age_min,
        "age_max": body.age_max,
    }
    if body.genders:
        targeting["genders"] = body.genders
    try:
        result = await client.create_adset(
            account_id,
            body.name,
            body.campaign_id,
            body.daily_budget_cents,
            body.billing_event,
            body.optimization_goal,
            targeting,
            body.status,
            body.bid_amount_cents,
        )
        _log(db, account_id, "create_adset", f"{body.name}/{result.get('id')}")
        return result
    except FBAPIError as e:
        _log(db, account_id, "create_adset", str(e), "failed")
        raise HTTPException(status_code=e.status_code, detail=str(e))


# ---------------- Ad Creative & Ad ----------------
class CreativeIn(BaseModel):
    name: str
    page_id: str
    message: str
    link: str
    image_hash: Optional[str] = None
    headline: Optional[str] = None
    description: Optional[str] = None
    call_to_action_type: str = "LEARN_MORE"


@router.post("/accounts/{account_id}/creatives")
async def create_creative(account_id: str, body: CreativeIn, db: Session = Depends(get_db)):
    client = await get_client_for_account(account_id, db)
    try:
        result = await client.create_ad_creative(
            account_id, body.name, body.page_id, body.message, body.link,
            body.image_hash, body.headline, body.description, body.call_to_action_type,
        )
        _log(db, account_id, "create_creative", f"{body.name}/{result.get('id')}")
        return result
    except FBAPIError as e:
        _log(db, account_id, "create_creative", str(e), "failed")
        raise HTTPException(status_code=e.status_code, detail=str(e))


@router.post("/accounts/{account_id}/images")
async def upload_image(account_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    client = await get_client_for_account(account_id, db)
    content = await file.read()
    try:
        return await client.upload_image(account_id, content, file.filename)
    except FBAPIError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))


@router.get("/accounts/{account_id}/ads")
async def list_ads(account_id: str, adset_id: Optional[str] = None, db: Session = Depends(get_db)):
    client = await get_client_for_account(account_id, db)
    try:
        return await client.list_ads(account_id, adset_id)
    except FBAPIError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))


class AdIn(BaseModel):
    name: str
    adset_id: str
    creative_id: str
    status: str = "PAUSED"


@router.post("/accounts/{account_id}/ads")
async def create_ad(account_id: str, body: AdIn, db: Session = Depends(get_db)):
    client = await get_client_for_account(account_id, db)
    try:
        result = await client.create_ad(
            account_id, body.name, body.adset_id, body.creative_id, body.status
        )
        _log(db, account_id, "create_ad", f"{body.name}/{result.get('id')}")
        return result
    except FBAPIError as e:
        _log(db, account_id, "create_ad", str(e), "failed")
        raise HTTPException(status_code=e.status_code, detail=str(e))


class StatusIn(BaseModel):
    status: str  # ACTIVE / PAUSED / ARCHIVED / DELETED


@router.post("/accounts/{account_id}/objects/{object_id}/status")
async def update_status(account_id: str, object_id: str, body: StatusIn, db: Session = Depends(get_db)):
    """account_id 用于定位应使用哪个 BM 的 token，object_id 可以是 campaign/adset/ad 的 ID"""
    client = await get_client_for_account(account_id, db)
    try:
        result = await client.update_status(object_id, body.status)
        _log(db, account_id, "update_status", f"{object_id}->{body.status}")
        return result
    except FBAPIError as e:
        _log(db, account_id, "update_status", str(e), "failed")
        raise HTTPException(status_code=e.status_code, detail=str(e))
