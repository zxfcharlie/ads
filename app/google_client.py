"""
轻量 Google Ads API 客户端，用 httpx 直接调用 REST 接口（searchStream + GAQL），
不依赖官方 google-ads Python SDK（那个包依赖 gRPC + protobuf，体积和复杂度都大很多）。

Google Ads API 的鉴权模型跟 Meta 不一样，不是一个长效令牌就够，而是：
- developer_token：在 Google Ads 后台申请的开发者令牌
- client_id / client_secret：Google Cloud 项目里的 OAuth2 客户端凭证
- refresh_token：用上面这对 client_id/secret 走一次 OAuth2 授权流程换来的长效刷新令牌
  （官方文档：https://developers.google.com/google-ads/api/docs/oauth/overview）
- login_customer_id（可选）：如果 refresh_token 对应的账号是通过一个 MCC 经理账户
  管理具体客户账户，需要指定这个 MCC 的 ID

access_token 是短效的（约1小时），每次请求前都用 refresh_token 换一个新的，不做缓存
（Google 这步很快，多换几次也无所谓，换来实现简单、不用管过期时间）。
"""
import httpx

API_VERSION = "v17"
BASE_URL = f"https://googleads.googleapis.com/{API_VERSION}"
OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"


class GoogleAdsAPIError(Exception):
    def __init__(self, status_code: int, payload: dict | str):
        self.status_code = status_code
        self.payload = payload
        message = str(payload)
        if isinstance(payload, dict):
            err = payload.get("error", {})
            message = err.get("message", str(payload))
            details = err.get("details", [])
            for d in details:
                errors = d.get("errors", [])
                for e in errors:
                    msg = e.get("message")
                    if msg:
                        message += f" | {msg}"
        super().__init__(f"Google Ads API Error [{status_code}]: {message}")


class GoogleAdsClient:
    def __init__(
        self,
        developer_token: str,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        login_customer_id: str = "",
    ):
        self.developer_token = developer_token
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.login_customer_id = (login_customer_id or "").replace("-", "")

    async def _get_access_token(self) -> str:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                OAUTH_TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": self.refresh_token,
                    "grant_type": "refresh_token",
                },
            )
        if r.status_code >= 400:
            raise GoogleAdsAPIError(r.status_code, r.json())
        return r.json()["access_token"]

    async def _headers(self, customer_id: str | None = None) -> dict:
        access_token = await self._get_access_token()
        headers = {
            "Authorization": f"Bearer {access_token}",
            "developer-token": self.developer_token,
            "Content-Type": "application/json",
        }
        login_id = self.login_customer_id or customer_id
        if login_id:
            headers["login-customer-id"] = login_id.replace("-", "")
        return headers

    async def _search(self, customer_id: str, query: str) -> list[dict]:
        """GAQL 查询，走 searchStream，自动把分块结果拼成一个列表返回"""
        customer_id = customer_id.replace("-", "")
        headers = await self._headers(customer_id)
        url = f"{BASE_URL}/customers/{customer_id}/googleAds:searchStream"
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(url, headers=headers, json={"query": query})
        if r.status_code >= 400:
            try:
                payload = r.json()
            except Exception:
                payload = r.text
            raise GoogleAdsAPIError(r.status_code, payload)

        results = []
        for chunk in r.json():
            results.extend(chunk.get("results", []))
        return results

    # ---------- 账户 ----------
    async def list_accessible_customers(self) -> list[str]:
        """返回当前 refresh_token 能访问的所有 customer id（不带横线的纯数字字符串）"""
        headers = await self._headers()
        url = f"{BASE_URL}/customers:listAccessibleCustomers"
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(url, headers=headers)
        if r.status_code >= 400:
            raise GoogleAdsAPIError(r.status_code, r.json())
        resource_names = r.json().get("resourceNames", [])
        return [rn.split("/")[-1] for rn in resource_names]

    async def get_customer_info(self, customer_id: str) -> dict:
        query = "SELECT customer.id, customer.descriptive_name, customer.currency_code, customer.status FROM customer LIMIT 1"
        rows = await self._search(customer_id, query)
        if not rows:
            return {}
        c = rows[0].get("customer", {})
        return {
            "id": customer_id,
            "name": c.get("descriptiveName", customer_id),
            "currency": c.get("currencyCode", ""),
            "status": c.get("status", ""),
        }

    async def list_all_accounts(self) -> list[dict]:
        """列出这个凭证下所有能访问的客户账户及基本信息（名称/货币/状态）"""
        customer_ids = await self.list_accessible_customers()
        accounts = []
        for cid in customer_ids:
            try:
                info = await self.get_customer_info(cid)
                if info:
                    accounts.append(info)
            except GoogleAdsAPIError:
                # 有些是 MCC 经理账户本身，或者没权限的，跳过
                continue
        return accounts

    # ---------- 广告系列（只读概览）----------
    async def list_campaigns(self, customer_id: str) -> list[dict]:
        query = """
            SELECT campaign.id, campaign.name, campaign.status,
                   campaign_budget.amount_micros
            FROM campaign
            ORDER BY campaign.id
        """
        rows = await self._search(customer_id, query)
        result = []
        for row in rows:
            c = row.get("campaign", {})
            b = row.get("campaignBudget", {})
            result.append({
                "id": c.get("id"),
                "name": c.get("name"),
                "status": c.get("status"),
                "budget_micros": int(b.get("amountMicros", 0) or 0),
            })
        return result

    # ---------- 数据统计：按天花费/转化价值 ----------
    async def get_daily_stats(self, customer_id: str, since: str, until: str) -> list[dict]:
        """since/until 格式 YYYY-MM-DD"""
        query = f"""
            SELECT segments.date, metrics.cost_micros, metrics.conversions,
                   metrics.conversions_value
            FROM customer
            WHERE segments.date BETWEEN '{since}' AND '{until}'
            ORDER BY segments.date
        """
        rows = await self._search(customer_id, query)
        result = []
        for row in rows:
            seg = row.get("segments", {})
            m = row.get("metrics", {})
            spend = int(m.get("costMicros", 0) or 0) / 1_000_000
            revenue = float(m.get("conversionsValue", 0) or 0)
            result.append({
                "date": seg.get("date"),
                "spend": spend,
                "revenue": revenue,
                "purchases": float(m.get("conversions", 0) or 0),
                "roas": (revenue / spend) if spend else None,
            })
        return result
