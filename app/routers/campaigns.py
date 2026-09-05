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


# ==================== 聚合视图：结构信息 + 指标数据拼在一起 ====================
# 供「广告管理」页面使用：先列出对象结构（名称/状态/预算），
# 再拉一次该层级的 insights 按 id 关联上花费/购物/ROAS/视频等指标。

def _budget_fields(obj: dict) -> dict:
    daily = obj.get("daily_budget")
    lifetime = obj.get("lifetime_budget")
    has_own_budget = bool(daily) or bool(lifetime)
    return {
        "has_own_budget": has_own_budget,
        "budget_cents": int(daily or lifetime or 0),
        "budget_type": "daily" if daily else ("lifetime" if lifetime else None),
    }


@router.get("/accounts/{account_id}/campaigns/overview")
async def campaigns_overview(account_id: str, date_preset: str = "last_30d", db: Session = Depends(get_db)):
    client = await get_client_for_account(account_id, db)
    try:
        campaigns_res = await client.list_campaigns(account_id)
        metrics_map = await client.get_insights_by_level(account_id, "campaign", date_preset)
    except FBAPIError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))

    rows = []
    for c in campaigns_res.get("data", []):
        rows.append({**c, **metrics_map.get(c["id"], {}), **_budget_fields(c)})
    return {"data": rows}


@router.get("/accounts/{account_id}/adsets/overview")
async def adsets_overview(
    account_id: str, campaign_id: str, date_preset: str = "last_30d", db: Session = Depends(get_db)
):
    client = await get_client_for_account(account_id, db)
    try:
        adsets_res = await client.list_adsets(account_id, campaign_id)
        metrics_map = await client.get_insights_by_level(
            account_id, "adset", date_preset, "campaign.id", campaign_id
        )
    except FBAPIError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))

    rows = []
    for s in adsets_res.get("data", []):
        rows.append({**s, **metrics_map.get(s["id"], {}), **_budget_fields(s)})
    return {"data": rows}


@router.get("/accounts/{account_id}/ads/overview")
async def ads_overview(
    account_id: str, adset_id: str, date_preset: str = "last_30d", db: Session = Depends(get_db)
):
    client = await get_client_for_account(account_id, db)
    try:
        ads_res = await client.list_ads(account_id, adset_id)
        metrics_map = await client.get_insights_by_level(account_id, "ad", date_preset, "adset.id", adset_id)
    except FBAPIError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))

    rows = []
    for ad in ads_res.get("data", []):
        rows.append({**ad, **metrics_map.get(ad["id"], {})})
    return {"data": rows}


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
    """图片全程只经过内存，直接转发给 Facebook，本服务不写入磁盘、不落库保存"""
    client = await get_client_for_account(account_id, db)
    content = await file.read()
    await file.close()
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


# ==================== 修改预算/名称 & 复制（对齐 Ads Manager 常用操作）====================

class CampaignUpdateIn(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    daily_budget_cents: Optional[int] = None
    lifetime_budget_cents: Optional[int] = None


@router.patch("/accounts/{account_id}/campaigns/{campaign_id}")
async def update_campaign(account_id: str, campaign_id: str, body: CampaignUpdateIn, db: Session = Depends(get_db)):
    client = await get_client_for_account(account_id, db)
    try:
        result = await client.update_campaign(
            campaign_id, body.name, body.status, body.daily_budget_cents, body.lifetime_budget_cents
        )
        _log(db, account_id, "update_campaign", f"{campaign_id}:{body.model_dump(exclude_none=True)}")
        return result
    except FBAPIError as e:
        _log(db, account_id, "update_campaign", str(e), "failed")
        raise HTTPException(status_code=e.status_code, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class CopyIn(BaseModel):
    deep_copy: bool = True          # 是否把子对象（AdSet 下的 Ad）也一并复制
    status_option: str = "PAUSED"   # PAUSED / ACTIVE / INHERITED_FROM_SOURCE
    rename_suffix: Optional[str] = " - 副本"


@router.post("/accounts/{account_id}/campaigns/{campaign_id}/duplicate")
async def duplicate_campaign(account_id: str, campaign_id: str, body: CopyIn, db: Session = Depends(get_db)):
    client = await get_client_for_account(account_id, db)
    try:
        result = await client.copy_campaign(campaign_id, body.deep_copy, body.status_option, body.rename_suffix)
        _log(db, account_id, "duplicate_campaign", f"{campaign_id}->{result}")
        return result
    except FBAPIError as e:
        _log(db, account_id, "duplicate_campaign", str(e), "failed")
        raise HTTPException(status_code=e.status_code, detail=str(e))


class AdSetUpdateIn(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    daily_budget_cents: Optional[int] = None
    lifetime_budget_cents: Optional[int] = None
    bid_amount_cents: Optional[int] = None


@router.patch("/accounts/{account_id}/adsets/{adset_id}")
async def update_adset_endpoint(account_id: str, adset_id: str, body: AdSetUpdateIn, db: Session = Depends(get_db)):
    client = await get_client_for_account(account_id, db)
    try:
        result = await client.update_adset(
            adset_id, body.name, body.status, body.daily_budget_cents,
            body.lifetime_budget_cents, body.bid_amount_cents,
        )
        _log(db, account_id, "update_adset", f"{adset_id}:{body.model_dump(exclude_none=True)}")
        return result
    except FBAPIError as e:
        _log(db, account_id, "update_adset", str(e), "failed")
        raise HTTPException(status_code=e.status_code, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/accounts/{account_id}/adsets/{adset_id}/duplicate")
async def duplicate_adset(account_id: str, adset_id: str, body: CopyIn, db: Session = Depends(get_db)):
    client = await get_client_for_account(account_id, db)
    try:
        result = await client.copy_adset(adset_id, body.deep_copy, body.status_option, body.rename_suffix)
        _log(db, account_id, "duplicate_adset", f"{adset_id}->{result}")
        return result
    except FBAPIError as e:
        _log(db, account_id, "duplicate_adset", str(e), "failed")
        raise HTTPException(status_code=e.status_code, detail=str(e))


class AdUpdateIn(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None


@router.patch("/accounts/{account_id}/ads/{ad_id}")
async def update_ad_endpoint(account_id: str, ad_id: str, body: AdUpdateIn, db: Session = Depends(get_db)):
    client = await get_client_for_account(account_id, db)
    try:
        result = await client.update_ad(ad_id, body.name, body.status)
        _log(db, account_id, "update_ad", f"{ad_id}:{body.model_dump(exclude_none=True)}")
        return result
    except FBAPIError as e:
        _log(db, account_id, "update_ad", str(e), "failed")
        raise HTTPException(status_code=e.status_code, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/accounts/{account_id}/ads/{ad_id}/duplicate")
async def duplicate_ad(account_id: str, ad_id: str, body: CopyIn, db: Session = Depends(get_db)):
    client = await get_client_for_account(account_id, db)
    try:
        result = await client.copy_ad(ad_id, body.status_option)
        _log(db, account_id, "duplicate_ad", f"{ad_id}->{result}")
        return result
    except FBAPIError as e:
        _log(db, account_id, "duplicate_ad", str(e), "failed")
        raise HTTPException(status_code=e.status_code, detail=str(e))
