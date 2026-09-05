"""
轻量 Facebook Marketing (Graph) API 客户端。
不依赖官方重量级 SDK，用 httpx 直接调用 REST 接口，方便按需扩展。
"""
import httpx
from app.config import settings, GRAPH_BASE


class FBAPIError(Exception):
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self.payload = payload
        message = payload.get("error", {}).get("message", str(payload))
        super().__init__(f"FB API Error [{status_code}]: {message}")


class FBClient:
    def __init__(self, access_token: str | None = None):
        self.token = access_token or settings.fb_access_token

    def _params(self, extra: dict | None = None) -> dict:
        p = {"access_token": self.token}
        if extra:
            p.update(extra)
        return p

    async def _get(self, path: str, params: dict | None = None) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(f"{GRAPH_BASE}/{path}", params=self._params(params))
        if r.status_code >= 400:
            raise FBAPIError(r.status_code, r.json())
        return r.json()

    async def _post(self, path: str, data: dict | None = None) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(f"{GRAPH_BASE}/{path}", data=self._params(data))
        if r.status_code >= 400:
            raise FBAPIError(r.status_code, r.json())
        return r.json()

    async def _delete(self, path: str) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.delete(f"{GRAPH_BASE}/{path}", params=self._params())
        if r.status_code >= 400:
            raise FBAPIError(r.status_code, r.json())
        return r.json()

    # ---------- 账户 ----------
    async def list_ad_accounts(self):
        fields = (
            "id,name,account_id,account_status,currency,timezone_name,"
            "amount_spent,balance,spend_cap,funding_source_details"
        )
        return await self._get("me/adaccounts", {"fields": fields, "limit": 200})

    async def get_account(self, account_id: str):
        fields = (
            "id,name,account_status,currency,amount_spent,balance,"
            "spend_cap,funding_source_details"
        )
        return await self._get(f"{account_id}", {"fields": fields})

    async def update_spend_cap(self, account_id: str, spend_cap_cents: int):
        """spend_cap 单位为最小货币单位（如美分）"""
        return await self._post(f"{account_id}", {"spend_cap": spend_cap_cents})

    # ---------- 数据洞察 ----------
    async def get_insights(
        self,
        account_id: str,
        date_preset: str = "last_30d",
        level: str = "account",
        breakdown_by_campaign: bool = False,
    ):
        fields = (
            "spend,impressions,clicks,ctr,cpc,cpm,reach,frequency,"
            "actions,account_currency,date_start,date_stop"
        )
        params = {
            "fields": fields,
            "date_preset": date_preset,
            "level": "campaign" if breakdown_by_campaign else level,
            "limit": 500,
        }
        return await self._get(f"{account_id}/insights", params)

    # ---------- 广告系列 / 广告组 / 广告 ----------
    async def list_campaigns(self, account_id: str):
        fields = "id,name,status,objective,daily_budget,lifetime_budget,created_time"
        return await self._get(f"{account_id}/campaigns", {"fields": fields, "limit": 200})

    async def create_campaign(
        self,
        account_id: str,
        name: str,
        objective: str,
        status: str = "PAUSED",
        special_ad_categories: list[str] | None = None,
    ):
        data = {
            "name": name,
            "objective": objective,
            "status": status,
            "special_ad_categories": special_ad_categories or [],
        }
        return await self._post(f"{account_id}/campaigns", data)

    async def list_adsets(self, account_id: str, campaign_id: str | None = None):
        fields = (
            "id,name,status,daily_budget,lifetime_budget,billing_event,"
            "optimization_goal,targeting,campaign_id"
        )
        params = {"fields": fields, "limit": 200}
        if campaign_id:
            params["filtering"] = f'[{{"field":"campaign.id","operator":"EQUAL","value":"{campaign_id}"}}]'
        return await self._get(f"{account_id}/adsets", params)

    async def create_adset(
        self,
        account_id: str,
        name: str,
        campaign_id: str,
        daily_budget_cents: int,
        billing_event: str,
        optimization_goal: str,
        targeting: dict,
        status: str = "PAUSED",
        bid_amount_cents: int | None = None,
    ):
        data = {
            "name": name,
            "campaign_id": campaign_id,
            "daily_budget": daily_budget_cents,
            "billing_event": billing_event,
            "optimization_goal": optimization_goal,
            "targeting": _to_json(targeting),
            "status": status,
        }
        if bid_amount_cents:
            data["bid_amount"] = bid_amount_cents
        return await self._post(f"{account_id}/adsets", data)

    async def create_ad_creative(
        self,
        account_id: str,
        name: str,
        page_id: str,
        message: str,
        link: str,
        image_hash: str | None = None,
        headline: str | None = None,
        description: str | None = None,
        call_to_action_type: str = "LEARN_MORE",
    ):
        link_data = {
            "message": message,
            "link": link,
            "call_to_action": {"type": call_to_action_type, "value": {"link": link}},
        }
        if headline:
            link_data["name"] = headline
        if description:
            link_data["description"] = description
        if image_hash:
            link_data["image_hash"] = image_hash

        object_story_spec = {"page_id": page_id, "link_data": link_data}
        data = {
            "name": name,
            "object_story_spec": _to_json(object_story_spec),
        }
        return await self._post(f"{account_id}/adcreatives", data)

    async def list_ads(self, account_id: str, adset_id: str | None = None):
        fields = "id,name,status,adset_id,creative,effective_status"
        params = {"fields": fields, "limit": 200}
        if adset_id:
            params["filtering"] = f'[{{"field":"adset.id","operator":"EQUAL","value":"{adset_id}"}}]'
        return await self._get(f"{account_id}/ads", params)

    async def create_ad(
        self,
        account_id: str,
        name: str,
        adset_id: str,
        creative_id: str,
        status: str = "PAUSED",
    ):
        data = {
            "name": name,
            "adset_id": adset_id,
            "creative": _to_json({"creative_id": creative_id}),
            "status": status,
        }
        return await self._post(f"{account_id}/ads", data)

    async def update_status(self, object_id: str, status: str):
        """通用：暂停/启用 campaign / adset / ad"""
        return await self._post(f"{object_id}", {"status": status})

    async def upload_image(self, account_id: str, image_bytes: bytes, filename: str):
        async with httpx.AsyncClient(timeout=60) as client:
            files = {"filename": (filename, image_bytes)}
            r = await client.post(
                f"{GRAPH_BASE}/{account_id}/adimages",
                data={"access_token": self.token},
                files=files,
            )
        if r.status_code >= 400:
            raise FBAPIError(r.status_code, r.json())
        return r.json()


def _to_json(obj) -> str:
    import json
    return json.dumps(obj)
