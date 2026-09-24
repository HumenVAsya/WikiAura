from fastapi import APIRouter, status
from pydantic import BaseModel

from app.schemas.requests import AnalyzeRequest

router = APIRouter(prefix="", tags=["Analysis"])


class AnalyzeResponse(BaseModel):
    """Placeholder response schema for analysis endpoint."""

    status: str
    message: str
    topic: str
    lang: str
    months: int


@router.post(
    "/analyze",
    response_model=AnalyzeResponse,
    status_code=status.HTTP_200_OK,
    summary="Trigger Wikipedia data retrieval, trend calculation, and report generation",
    description="Stateless endpoint that accepts an analysis request payload and kicks off the processing pipeline.",
)
async def analyze_topic(payload: AnalyzeRequest) -> AnalyzeResponse:
    """Handle Wikipedia trend analysis and PDF report generation request.

    Note: Core pipeline logic (Wikipedia API fetching, pandas YoY/MoM analytics,
    and Playwright PDF rendering) will be wired into services in subsequent phases.
    """
    return AnalyzeResponse(
        status="success",
        message=f"Analysis pipeline initialized for topic '{payload.topic}'.",
        topic=payload.topic,
        lang=payload.lang,
        months=payload.months,
    )
