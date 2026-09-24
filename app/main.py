from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.analyze import router as analyze_router

app = FastAPI(
    title="Wikipedia Trend Analysis Microservice",
    description="Stateless microservice to fetch Wikipedia data, calculate YoY/MoM trends, and generate PDF reports.",
    version="0.1.0",
)

# CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register route modules
app.include_router(analyze_router)


@app.get("/", include_in_schema=False)
async def root_redirect():
    """Redirect root path to interactive API documentation."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/docs")



@app.get(
    "/healthz",
    tags=["Health"],
    summary="Service Health Check",
    description="Stateless liveness and readiness probe.",
)
async def health_check() -> dict[str, str]:
    """Return health status of the microservice."""
    return {"status": "healthy", "service": "wikipedia-skill"}
