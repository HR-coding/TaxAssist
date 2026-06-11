import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.orchestrator.gateway import router as gateway_router
from app.orchestrator.feedback_api import router as feedback_router
from app.orchestrator.auth_api import router as auth_router
from app.orchestrator.app_api import router as app_router
from app.orchestrator.google_oauth_api import router as google_oauth_router
from app.core.db_initializer import initialize_database
from app.core.control_db import init_control_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_control_db()      # create control-plane tables (users, profiles, runs, …)
    initialize_database()  # create MongoDB indexes
    yield


app = FastAPI(title="Tax Agent API", version="1.0.0", lifespan=lifespan)

# CORS for the React frontend (set FRONTEND_ORIGINS to your deployed origins).
_origins = os.getenv(
    "FRONTEND_ORIGINS", "http://localhost:5173,http://localhost:3000"
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(gateway_router)
app.include_router(feedback_router)
app.include_router(auth_router)
app.include_router(app_router)
app.include_router(google_oauth_router)


@app.get("/healthz")
def healthz():
    return {"ok": True}


# ── Serve the built React frontend (single-container deploy) ──────────────────
# When app/static exists (production image), serve the SPA: real files if present,
# else index.html so client-side routing works. API routes above take precedence.
_STATIC_DIR = os.getenv("STATIC_DIR", os.path.join(os.path.dirname(__file__), "static"))
if os.path.isdir(_STATIC_DIR):
    from fastapi.responses import FileResponse

    @app.get("/")
    def _index():
        return FileResponse(os.path.join(_STATIC_DIR, "index.html"))

    @app.get("/{full_path:path}")
    def _spa(full_path: str):
        candidate = os.path.join(_STATIC_DIR, full_path)
        if full_path and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(os.path.join(_STATIC_DIR, "index.html"))
else:
    @app.get("/")
    def root():
        return {"message": "Tax Agent Router Active and Secure"}
