from fastapi import APIRouter, HTTPException, Query
from app.fb_client import FBClient, FBAPIError

router = APIRouter(prefix="/api/accounts", tags=["insights"])


@router.get("/{account_id}/insights")
async def get_insights(
    account_id: str,
    date_preset: str = Query("last_30d"),
    by_campaign: bool = Query(False),
):
    client = FBClient()
    try:
        return await client.get_insights(account_id, date_preset, breakdown_by_campaign=by_campaign)
    except FBAPIError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
