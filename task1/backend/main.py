import os
import time
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import asyncpg

logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","message":"%(message)s"}',
)
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://dodo:dodopass@postgres:5432/dodo_db"
)
APP_VERSION = os.getenv("APP_VERSION", "1.0.0")
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")

db_pool: Optional[asyncpg.Pool] = None


async def create_pool(retries: int = 10, delay: int = 3) -> asyncpg.Pool:
    """Create DB connection pool with retry logic."""
    for attempt in range(1, retries + 1):
        try:
            pool = await asyncpg.create_pool(
                DATABASE_URL,
                min_size=2,
                max_size=10,
                command_timeout=30,
            )
            logger.info("Database pool created successfully")
            return pool
        except Exception as e:
            logger.warning(f"DB connection attempt {attempt}/{retries} failed: {e}")
            if attempt == retries:
                raise
            time.sleep(delay)


async def get_db() -> asyncpg.Connection:
    """Dependency: yield a DB connection from the pool."""
    async with db_pool.acquire() as conn:
        yield conn


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    global db_pool
    logger.info("Starting application...")
    db_pool = await create_pool()

    # Create tables
    async with db_pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id        SERIAL PRIMARY KEY,
                name      VARCHAR(255) NOT NULL,
                description TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
    logger.info("Database tables ready")

    yield

    logger.info("Shutting down application...")
    if db_pool:
        await db_pool.close()


app = FastAPI(
    title="Dodo Payments API",
    description="K8s Demo microservice backend",
    version=APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ItemCreate(BaseModel):
    name: str
    description: Optional[str] = None


class ItemResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    created_at: str

    @classmethod
    def from_record(cls, record):
        return cls(
            id=record["id"],
            name=record["name"],
            description=record["description"],
            created_at=record["created_at"].isoformat(),
        )


@app.get("/health")
async def health_check():
    """Kubernetes liveness + readiness probe endpoint."""
    db_status = "disconnected"
    try:
        async with db_pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        db_status = "connected"
    except Exception as e:
        logger.error(f"DB health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "database": db_status, "version": APP_VERSION},
        )

    return {"status": "healthy", "database": db_status, "version": APP_VERSION}


@app.get("/ready")
async def readiness():
    """Separate readiness probe — ensures DB is reachable before serving traffic."""
    try:
        async with db_pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return {"status": "ready"}
    except Exception:
        raise HTTPException(status_code=503, detail="Database not ready")


@app.get("/metrics-info")
async def metrics_info():
    """Expose basic app metrics for Prometheus scraping (custom)."""
    async with db_pool.acquire() as conn:
        count = await conn.fetchval("SELECT COUNT(*) FROM items")
    return {
        "total_items": count,
        "db_pool_size": db_pool.get_size(),
        "db_pool_free": db_pool.get_idle_size(),
    }


@app.get("/items", response_model=list[ItemResponse])
async def list_items(conn=Depends(get_db)):
    """Get all items."""
    logger.info("Fetching all items")
    rows = await conn.fetch("SELECT * FROM items ORDER BY created_at DESC")
    return [ItemResponse.from_record(r) for r in rows]


@app.get("/items/{item_id}", response_model=ItemResponse)
async def get_item(item_id: int, conn=Depends(get_db)):
    """Get a single item by ID."""
    row = await conn.fetchrow("SELECT * FROM items WHERE id = $1", item_id)
    if not row:
        raise HTTPException(status_code=404, detail="Item not found")
    return ItemResponse.from_record(row)


@app.post("/items", response_model=ItemResponse, status_code=201)
async def create_item(item: ItemCreate, conn=Depends(get_db)):
    """Create a new item."""
    logger.info(f"Creating item: {item.name}")
    row = await conn.fetchrow(
        "INSERT INTO items (name, description) VALUES ($1, $2) RETURNING *",
        item.name, item.description,
    )
    return ItemResponse.from_record(row)


@app.delete("/items/{item_id}", status_code=204)
async def delete_item(item_id: int, conn=Depends(get_db)):
    """Delete an item."""
    result = await conn.execute("DELETE FROM items WHERE id = $1", item_id)
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Item not found")
    logger.info(f"Deleted item: {item_id}")
