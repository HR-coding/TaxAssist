from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.orchestrator.gateway import router as gateway_router
from app.mcps.services.db_initializer import initialize_database


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    yield


app = FastAPI(title="Tax Agent API", version="1.0.0", lifespan=lifespan)
app.include_router(gateway_router)


@app.get("/")
def root():
    return {"message": "Tax Agent Router Active and Secure"}
