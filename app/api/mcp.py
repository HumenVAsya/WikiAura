"""MCP (Model Context Protocol) tool manifest endpoint.

Exposes a machine-readable tool registry at /.well-known/mcp/tools
in a format compatible with Anthropic Claude tool_use and OpenAI function_call.

Agents can fetch this endpoint once to auto-discover all available WikiAura
tools without reading SKILL.md manually.
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["MCP"])


# ── Pydantic models for the manifest ──────────────────────────────────────────


class MCPPropertySchema(BaseModel):
    type: str
    description: str
    enum: List[str] | None = None
    items: Dict[str, Any] | None = None
    default: Any | None = None


class MCPInputSchema(BaseModel):
    type: str = "object"
    properties: Dict[str, MCPPropertySchema]
    required: List[str]


class MCPTool(BaseModel):
    name: str
    description: str
    input_schema: MCPInputSchema


class MCPManifest(BaseModel):
    schema_version: str = "1.0"
    service: str
    base_url: str
    tools: List[MCPTool]


# ── Tool definitions ───────────────────────────────────────────────────────────

_TOOLS: List[MCPTool] = [

    MCPTool(
        name="analyze_trends",
        description=(
            "Analyze Wikipedia pageview trends for a topic across multiple language editions. "
            "Runs the full 4-stage pipeline: Wikimedia data ingestion, gap-free standardization, "
            "quantitative metrics (MoM, YoY, Z-score anomalies, cross-language correlation), "
            "and optional AI executive synthesis. "
            "Use this as the PRIMARY tool for any market interest or trend research task. "
            "Returns a rich AnalyticsResultDTO with time series, metrics, comparison, and AI summary."
        ),
        input_schema=MCPInputSchema(
            properties={
                "topic": MCPPropertySchema(
                    type="string",
                    description=(
                        "Canonical English Wikipedia article title for the topic. "
                        "Examples: 'Coffee', 'Intermittent fasting', 'Artificial intelligence'. "
                        "Do NOT use colloquial names — use the exact Wikipedia article title."
                    ),
                ),
                "language_codes": MCPPropertySchema(
                    type="array",
                    description=(
                        "ISO 639-1 language codes to analyze, or region aliases. "
                        "Examples: ['en', 'uk', 'pl', 'de']. "
                        "Region aliases: 'europe', 'eastern_europe', 'latam', 'sea', 'mena'. "
                        "Default: ['en']. Use 2-4 targeted languages for fast results."
                    ),
                    items={"type": "string"},
                    default=["en"],
                ),
                "start_date": MCPPropertySchema(
                    type="string",
                    description=(
                        "Start date in YYYYMMDD format. "
                        "Earliest available: 20150701. "
                        "Default: 1 year before today."
                    ),
                    default=None,
                ),
                "end_date": MCPPropertySchema(
                    type="string",
                    description=(
                        "End date in YYYYMMDD format. "
                        "Default: today. "
                        "Note: the current incomplete month is marked is_partial=true."
                    ),
                    default=None,
                ),
                "granularity": MCPPropertySchema(
                    type="string",
                    description="Aggregation interval. Use 'monthly' for trend research (recommended), 'daily' for spike analysis.",
                    enum=["monthly", "daily"],
                    default="monthly",
                ),
                "source_topic": MCPPropertySchema(
                    type="string",
                    description=(
                        "Native-language article title when the topic originates in a non-English language. "
                        "Example: 'єПідтримка' for a Ukrainian government program. "
                        "Leave empty when topic is an English Wikipedia title."
                    ),
                    default=None,
                ),
                "include_ai_summary": MCPPropertySchema(
                    type="boolean",
                    description=(
                        "Whether to generate an AI executive synthesis (trend_summary, key_drivers, business_takeaway). "
                        "Set false for faster responses when you only need raw metrics."
                    ),
                    default=True,
                ),
            },
            required=["topic"],
        ),
    ),

    MCPTool(
        name="analyze_trends_nl",
        description=(
            "Parse a natural language query and run the full analytics pipeline. "
            "Use this when the user's query is in free-form text (any language). "
            "The query is parsed by Gemini to extract topic, languages, and date range. "
            "Falls back to analyze_trends internally. "
            "Prefer analyze_trends if you already have structured parameters."
        ),
        input_schema=MCPInputSchema(
            properties={
                "query": MCPPropertySchema(
                    type="string",
                    description=(
                        "Free-form natural language request in any language. "
                        "Examples: "
                        "'Show coffee trends in Europe for 2023', "
                        "'Покажи тренди єПідтримки в Україні та Польщі за рік', "
                        "'Дай аналіз інтересу до безперервного голодування у Центральній Європі'."
                    ),
                ),
                "include_ai_summary": MCPPropertySchema(
                    type="boolean",
                    description="Whether to include AI executive synthesis. Default: true.",
                    default=True,
                ),
            },
            required=["query"],
        ),
    ),

    MCPTool(
        name="generate_chart",
        description=(
            "Generate a PNG visualization from analytics results. "
            "Returns image/png bytes directly. "
            "Use AFTER analyze_trends when the user explicitly requests a chart, graph, or visual. "
            "chart_type options: "
            "'trend' = time-series with rolling average + anomaly markers + market share donut (recommended); "
            "'compare' = 3-panel bar chart (total views, MoM, YoY); "
            "'sparklines' = compact mini-chart grid, one per language."
        ),
        input_schema=MCPInputSchema(
            properties={
                "topic": MCPPropertySchema(
                    type="string",
                    description="Canonical English Wikipedia article title.",
                ),
                "language_codes": MCPPropertySchema(
                    type="array",
                    description="ISO 639-1 language codes to visualize.",
                    items={"type": "string"},
                    default=["en"],
                ),
                "start_date": MCPPropertySchema(
                    type="string",
                    description="Start date YYYYMMDD. Default: 1 year ago.",
                    default=None,
                ),
                "end_date": MCPPropertySchema(
                    type="string",
                    description="End date YYYYMMDD. Default: today.",
                    default=None,
                ),
                "granularity": MCPPropertySchema(
                    type="string",
                    enum=["monthly", "daily"],
                    description="Aggregation interval. Default: monthly.",
                    default="monthly",
                ),
                "chart_type": MCPPropertySchema(
                    type="string",
                    enum=["trend", "compare", "sparklines"],
                    description="Chart type. Default: trend.",
                    default="trend",
                ),
            },
            required=["topic"],
        ),
    ),

    MCPTool(
        name="generate_report_pdf",
        description=(
            "Generate a share-ready single-page A4 PDF report. "
            "Returns application/pdf bytes. "
            "Use when the user explicitly requests a PDF, downloadable report, or shareable document. "
            "The PDF includes: trend chart, metric badges (MoM/YoY/direction per language), "
            "AI executive summary, business takeaway, data quality section, and Wikimedia attribution."
        ),
        input_schema=MCPInputSchema(
            properties={
                "topic": MCPPropertySchema(
                    type="string",
                    description="Canonical English Wikipedia article title.",
                ),
                "language_codes": MCPPropertySchema(
                    type="array",
                    description="ISO 639-1 language codes to include in the report.",
                    items={"type": "string"},
                    default=["en"],
                ),
                "start_date": MCPPropertySchema(
                    type="string",
                    description="Start date YYYYMMDD. Default: 1 year ago.",
                    default=None,
                ),
                "end_date": MCPPropertySchema(
                    type="string",
                    description="End date YYYYMMDD. Default: today.",
                    default=None,
                ),
                "granularity": MCPPropertySchema(
                    type="string",
                    enum=["monthly", "daily"],
                    description="Aggregation interval. Default: monthly.",
                    default="monthly",
                ),
                "include_ai_summary": MCPPropertySchema(
                    type="boolean",
                    description="Include AI executive summary section. Default: true.",
                    default=True,
                ),
            },
            required=["topic"],
        ),
    ),

    MCPTool(
        name="cache_stats",
        description=(
            "Return cache statistics: hit rate, total entries, memory footprint, eviction count. "
            "Use for debugging or to check if results are served from cache."
        ),
        input_schema=MCPInputSchema(
            properties={},
            required=[],
        ),
    ),

    MCPTool(
        name="cache_invalidate",
        description=(
            "Invalidate all cached results for a specific topic. "
            "Use when you suspect stale data or want to force a fresh Wikimedia API fetch."
        ),
        input_schema=MCPInputSchema(
            properties={
                "topic": MCPPropertySchema(
                    type="string",
                    description="Topic name to invalidate (case-insensitive).",
                ),
            },
            required=["topic"],
        ),
    ),

]


# ── Endpoint ───────────────────────────────────────────────────────────────────


@router.get(
    "/.well-known/mcp/tools",
    response_model=MCPManifest,
    summary="MCP Tool Manifest",
    description=(
        "Machine-readable tool registry in Anthropic MCP / OpenAI function_call format.\n\n"
        "AI agents can fetch this endpoint once at startup to auto-discover all available "
        "WikiAura tools without reading documentation manually.\n\n"
        "Compatible with:\n"
        "- Anthropic Claude tool_use API\n"
        "- OpenAI function calling API\n"
        "- Any MCP-compatible agent framework"
    ),
    include_in_schema=True,
)
async def mcp_tools_manifest() -> MCPManifest:
    """Return the full MCP tool manifest for agent auto-discovery."""
    return MCPManifest(
        schema_version="1.0",
        service="WikiAura — Wikipedia Trend Analysis MCP Tool",
        base_url="http://localhost:8000",
        tools=_TOOLS,
    )


@router.get(
    "/.well-known/mcp/tools/{tool_name}",
    response_model=MCPTool,
    summary="Single MCP Tool Schema",
    description="Return the input schema for a single named tool.",
)
async def mcp_tool_schema(tool_name: str) -> MCPTool:
    """Return schema for a single tool by name."""
    from fastapi import HTTPException, status
    tool = next((t for t in _TOOLS if t.name == tool_name), None)
    if tool is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tool '{tool_name}' not found. Available: {[t.name for t in _TOOLS]}",
        )
    return tool
