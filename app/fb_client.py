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
        # 注意：Facebook 原始 balance 字段含义因账户资金模式而异
        # （预付费账户=预存余额；信用额度账户=待还款金额），
        # 不等同于"距花费上限还能花多少"，这里原样返回，
        # 由上层路由结合 spend_cap - amount_spent 计算出真正有用的"剩余可花费额度"。
        fields = (
            "id,name,account_status,currency,amount_spent,balance,"
            "spend_cap,funding_source_details"
        )
        return await self._get(f"{account_id}", {"fields": fields})

    async def update_spend_cap(self, account_id: str, spend_cap_cents: int):
        """spend_cap 单位为最小货币单位（如美分）。传 0 表示清除上限（不限制）。"""
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

        if breakdown_by_campaign:
            # 按广告系列拆分：必须显式要 campaign_name，否则 Facebook 只给 campaign_id
            fields += ",campaign_id,campaign_name"

        params = {
            "fields": fields,
            "date_preset": date_preset,
            "level": "campaign" if breakdown_by_campaign else level,
            "limit": 500,
        }

        if not breakdown_by_campaign:
            # 不按广告系列拆分时，默认按天拆分，否则 Facebook 会把整个 date_preset
            # 时间段汇总成唯一一行数据，图表就只有一根巨大的柱子而不是逐日走势。
            params["time_increment"] = 1

        return await self._get(f"{account_id}/insights", params)

    async def get_insights_by_level(
        self,
        account_id: str,
        level: str,                        # "campaign" | "adset" | "ad"
        date_preset: str = "last_30d",
        parent_field: str | None = None,   # "campaign.id" 或 "adset.id"
        parent_value: str | None = None,
    ) -> dict:
        """
        拉取某一层级（campaign/adset/ad）在指定周期内的汇总指标，按对象 id 建索引，
        方便与 list_campaigns/list_adsets/list_ads 的结构化数据（名称/状态/预算）拼接。
        """
        id_field = {"campaign": "campaign_id", "adset": "adset_id", "ad": "ad_id"}[level]
        fields = (
            "spend,impressions,clicks,ctr,cpc,cpm,frequency,"
            "actions,action_values,purchase_roas,"
            "video_play_actions,video_p50_watched_actions,video_p100_watched_actions,"
            f"{id_field}"
        )
        params = {
            "fields": fields,
            "date_preset": date_preset,
            "level": level,
            "limit": 500,
        }
        if parent_field and parent_value:
            params["filtering"] = f'[{{"field":"{parent_field}","operator":"EQUAL","value":"{parent_value}"}}]'

        result = await self._get(f"{account_id}/insights", params)
        by_id = {}
        for row in result.get("data", []):
            obj_id = row.get(id_field)
            if obj_id:
                by_id[obj_id] = _parse_metrics_row(row)
        return by_id

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
            "special_ad_categories": _to_json(special_ad_categories or []),
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

    # ---------- 修改（预算/名称）----------
    async def update_campaign(
        self,
        campaign_id: str,
        name: str | None = None,
        status: str | None = None,
        daily_budget_cents: int | None = None,
        lifetime_budget_cents: int | None = None,
    ):
        data = {}
        if name is not None:
            data["name"] = name
        if status is not None:
            data["status"] = status
        if daily_budget_cents is not None:
            data["daily_budget"] = daily_budget_cents
        if lifetime_budget_cents is not None:
            data["lifetime_budget"] = lifetime_budget_cents
        if not data:
            raise ValueError("没有任何要更新的字段")
        return await self._post(f"{campaign_id}", data)

    async def update_adset(
        self,
        adset_id: str,
        name: str | None = None,
        status: str | None = None,
        daily_budget_cents: int | None = None,
        lifetime_budget_cents: int | None = None,
        bid_amount_cents: int | None = None,
    ):
        data = {}
        if name is not None:
            data["name"] = name
        if status is not None:
            data["status"] = status
        if daily_budget_cents is not None:
            data["daily_budget"] = daily_budget_cents
        if lifetime_budget_cents is not None:
            data["lifetime_budget"] = lifetime_budget_cents
        if bid_amount_cents is not None:
            data["bid_amount"] = bid_amount_cents
        if not data:
            raise ValueError("没有任何要更新的字段")
        return await self._post(f"{adset_id}", data)

    async def update_ad(self, ad_id: str, name: str | None = None, status: str | None = None):
        data = {}
        if name is not None:
            data["name"] = name
        if status is not None:
            data["status"] = status
        if not data:
            raise ValueError("没有任何要更新的字段")
        return await self._post(f"{ad_id}", data)

    # ---------- 复制（用 Facebook 原生 /copies 深拷贝接口）----------
    async def copy_campaign(
        self, campaign_id: str, deep_copy: bool = True,
        status_option: str = "PAUSED", rename_suffix: str | None = None,
    ):
        data = {"deep_copy": str(deep_copy).lower(), "status_option": status_option}
        if rename_suffix:
            data["rename_options"] = _to_json({
                "rename_strategy": "ONLY_TOP_LEVEL_RESOURCE_NAMES",
                "rename_suffix": rename_suffix,
            })
        return await self._post(f"{campaign_id}/copies", data)

    async def copy_adset(
        self, adset_id: str, deep_copy: bool = True,
        status_option: str = "PAUSED", rename_suffix: str | None = None,
    ):
        data = {"deep_copy": str(deep_copy).lower(), "status_option": status_option}
        if rename_suffix:
            data["rename_options"] = _to_json({
                "rename_strategy": "ONLY_TOP_LEVEL_RESOURCE_NAMES",
                "rename_suffix": rename_suffix,
            })
        return await self._post(f"{adset_id}/copies", data)

    async def copy_ad(self, ad_id: str, status_option: str = "PAUSED"):
        data = {"status_option": status_option}
        return await self._post(f"{ad_id}/copies", data)

    async def upload_image(self, account_id: str, image_bytes: bytes, filename: str):
        # 注意：图片内容全程只在内存中经手，直接转发给 Facebook 的 /adimages 接口，
        # 本服务不会把图片写入磁盘、也不落库保存，请求结束后即从内存中释放，不占用服务器存储。
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


# ---------- Facebook insights 里 actions/action_values/purchase_roas 都是
# [{"action_type": "...", "value": "..."}] 这种数组结构，需要按 action_type 取值 ----------

_PURCHASE_TYPES = ("omni_purchase", "offsite_conversion.fb_pixel_purchase", "purchase")
_ATC_TYPES = ("omni_add_to_cart", "offsite_conversion.fb_pixel_add_to_cart", "add_to_cart")
_CHECKOUT_TYPES = ("omni_initiated_checkout", "offsite_conversion.fb_pixel_initiate_checkout", "initiate_checkout")


def _pick(rows: list | None, *action_types: str) -> float:
    if not rows:
        return 0.0
    for row in rows:
        if row.get("action_type") in action_types:
            try:
                return float(row.get("value", 0))
            except (TypeError, ValueError):
                return 0.0
    return 0.0


def _sum_all(rows: list | None) -> float:
    if not rows:
        return 0.0
    total = 0.0
    for row in rows:
        try:
            total += float(row.get("value", 0))
        except (TypeError, ValueError):
            continue
    return total


def _parse_metrics_row(row: dict) -> dict:
    """
    把 Facebook Insights 返回的一行原始数据，解析成前端表格直接可用的字段。
    注意：这里的口径是常见/近似口径（例如购物用 omni_purchase 系列 action_type），
    实际数值可能因归因窗口设置等原因与 Ads Manager 显示略有差异，仅供参考对齐。
    """
    actions = row.get("actions") or []
    action_values = row.get("action_values") or []
    purchase_roas = row.get("purchase_roas") or []

    spend = float(row.get("spend") or 0)
    impressions = int(float(row.get("impressions") or 0))
    link_clicks = _pick(actions, "link_click")
    purchases = _pick(actions, *_PURCHASE_TYPES)
    purchase_value = _pick(action_values, *_PURCHASE_TYPES)
    roas = _pick(purchase_roas, *_PURCHASE_TYPES)
    atc = _pick(actions, *_ATC_TYPES)
    checkout = _pick(actions, *_CHECKOUT_TYPES)

    video_views = _sum_all(row.get("video_play_actions"))
    video_p50 = _sum_all(row.get("video_p50_watched_actions"))
    video_p100 = _sum_all(row.get("video_p100_watched_actions"))

    return {
        "spend": spend,
        "impressions": impressions,
        "clicks": int(float(row.get("clicks") or 0)),
        "cpm": float(row.get("cpm") or 0),
        "frequency": float(row.get("frequency") or 0),
        "purchases": purchases,
        "purchase_value": purchase_value,
        "roas": roas if roas else None,
        "cost_per_purchase": (spend / purchases) if purchases else None,
        "link_clicks": link_clicks,
        "cost_per_link_click": (spend / link_clicks) if link_clicks else None,
        "link_ctr": (link_clicks / impressions * 100) if impressions else 0,
        "atc": atc,
        "checkout_initiated": checkout,
        "video_views": video_views,
        "video_p50": video_p50,
        "video_p100": video_p100,
    }
