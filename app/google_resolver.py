"""
和 Meta 的 resolver.py 是同一个思路：一个 Google 凭证（GoogleCredential）
可能管理多个 customer_id，操作某个具体账户时需要知道该用哪个凭证。

Google 这边账户数量一般不大（不像 Meta 常见几十上百个广告账户），暂时不做
本地缓存表，每次直接遍历已启用的凭证逐个尝试，找到能访问这个 customer_id 的那个。
"""
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.models import GoogleCredential
from app.google_client import GoogleAdsClient, GoogleAdsAPIError


async def get_google_client_for_customer(customer_id: str, db: Session) -> GoogleAdsClient:
    customer_id = customer_id.replace("-", "")
    creds = db.query(GoogleCredential).filter(GoogleCredential.is_active == True).all()  # noqa: E712
    if not creds:
        raise HTTPException(status_code=400, detail="尚未配置任何 Google Ads 凭证，请先到「凭证管理」添加")

    for cred in creds:
        client = GoogleAdsClient(
            cred.developer_token, cred.client_id, cred.client_secret,
            cred.refresh_token, cred.login_customer_id,
        )
        try:
            accessible = await client.list_accessible_customers()
        except GoogleAdsAPIError:
            continue
        if customer_id in accessible:
            return client

    raise HTTPException(status_code=404, detail=f"在已配置的所有 Google Ads 凭证中都找不到账户 {customer_id}")
