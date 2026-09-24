from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    """Payload schema for requesting Wikipedia trend analysis and PDF report generation."""

    topic: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Wikipedia article title or search keyword to fetch and analyze.",
        examples=["Artificial intelligence"],
    )
    lang: str = Field(
        default="en",
        pattern=r"^[a-z]{2,3}$",
        description="Wikipedia language edition code (e.g., 'en', 'de', 'fr', 'uk').",
        examples=["en"],
    )
    months: int = Field(
        default=12,
        ge=1,
        le=60,
        description="Number of past months to retrieve for MoM (Month-over-Month) and YoY (Year-over-Year) trends.",
        examples=[12],
    )
