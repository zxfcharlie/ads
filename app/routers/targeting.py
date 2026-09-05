from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.fb_client import FBAPIError
from app.database import get_db
from app.resolver import get_client_for_account
from app.deps import get_current_user
from app.models import User

router = APIRouter(prefix="/api/accounts", tags=["targeting"])


@router.get("/{account_id}/pixels")
async def list_pixels(account_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    client = await get_client_for_account(account_id, db, user)
    try:
        return await client.list_pixels(account_id)
    except FBAPIError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))


@router.get("/{account_id}/pages")
async def list_pages(account_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """account_id 只用来定位该用哪个 BM 的令牌，主页本身不属于某个广告账户"""
    client = await get_client_for_account(account_id, db, user)
    try:
        return await client.list_pages()
    except FBAPIError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))


@router.get("/{account_id}/interests")
async def search_interests(
    account_id: str, q: str = Query(..., min_length=1), db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    client = await get_client_for_account(account_id, db, user)
    try:
        return await client.search_interests(q)
    except FBAPIError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
