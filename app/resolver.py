"""
多 Business Manager 场景下，campaigns/insights/accounts 等接口操作某个
account_id 时，需要知道该账户属于哪个 BM 凭证（access_token）。

策略：
1. 先查本地缓存表 AccountCredentialMap（由账户列表接口维护）。
2. 命中则直接用该凭证。
3. 未命中（比如缓存还没建立），遍历所有启用中的 BM 凭证尝试访问该账户，
   一旦成功就写入缓存，后续直接命中。
"""
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.models import BMCredential, AccountCredentialMap
from app.fb_client import FBClient, FBAPIError


async def get_client_for_account(account_id: str, db: Session) -> FBClient:
    mapping = db.query(AccountCredentialMap).filter(
        AccountCredentialMap.account_id == account_id
    ).first()

    if mapping:
        cred = db.query(BMCredential).filter(
            BMCredential.id == mapping.credential_id, BMCredential.is_active == True  # noqa: E712
        ).first()
        if cred:
            return FBClient(cred.access_token)

    # 缓存未命中，逐个尝试
    creds = db.query(BMCredential).filter(BMCredential.is_active == True).all()  # noqa: E712
    if not creds:
        raise HTTPException(status_code=400, detail="尚未配置任何 Business Manager 凭证，请先到「BM账号管理」添加")

    for cred in creds:
        client = FBClient(cred.access_token)
        try:
            await client.get_account(account_id)
        except FBAPIError:
            continue
        else:
            _upsert_map(db, account_id, cred.id)
            return client

    raise HTTPException(status_code=404, detail=f"在已配置的所有 BM 凭证中都找不到账户 {account_id}，请检查该账户是否已授权给对应系统用户")


def _upsert_map(db: Session, account_id: str, credential_id: int):
    row = db.query(AccountCredentialMap).filter(
        AccountCredentialMap.account_id == account_id
    ).first()
    if not row:
        row = AccountCredentialMap(account_id=account_id)
        db.add(row)
    row.credential_id = credential_id
    db.commit()
