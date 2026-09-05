from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.orm import Session

from app.fb_client import FBAPIError
from app.database import get_db
from app.resolver import get_client_for_account

router = APIRouter(prefix="/api/accounts", tags=["insights"])


@router.get("/{account_id}/insights")
async def get_insights(
    account_id: str,
    date_preset: str = Query("last_30d"),
    by_campaign: bool = Query(False),
    db: Session = Depends(get_db),
):
    client = await get_client_for_account(account_id, db)
    try:
        return await client.get_insights(account_id, date_preset, breakdown_by_campaign=by_campaign)
    except FBAPIError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
