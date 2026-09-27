from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app.api.analyze import router as analyze_router
from app.api.cache import router as cache_router
from app.api.charts import router as charts_router
from app.api.report import router as report_router

app = FastAPI(
    title="WikiAura - Wikipedia Trend Analysis MCP Tool",
    description="Stateless FastAPI microservice and MCP tool to analyze Wikipedia pageview trends across languages to evaluate B2C market interest.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analyze_router)
app.include_router(charts_router)
app.include_router(report_router)
app.include_router(cache_router)


@app.get("/", include_in_schema=False)
async def root_redirect():
    """Redirect root path to interactive API documentation."""
    return RedirectResponse(url="/docs")


@app.get(
    "/healthz",
    tags=["Health"],
    summary="Service Health Check",
    description="Stateless liveness and readiness probe.",
)
async def health_check() -> dict[str, str]:
    """Return health status of the microservice."""
    return {"status": "healthy", "service": "WikiAura"}
