import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from database import engine, Base, SessionLocal
from crypto.server_key_holder import server_key_holder
from services.demo_service import seed_accounts
from routers import api, dashboard

logging.basicConfig(
    format="%(asctime)s [%(threadName)s] %(levelname)-5s %(name)s - %(message)s",
    level=logging.INFO,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)

    server_key_holder.init()

    db = SessionLocal()
    try:
        seed_accounts(db)
    finally:
        db.close()

    yield


app = FastAPI(
    title="UPI Offline Mesh",
    description="Backend for offline UPI payments via Bluetooth mesh",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(api.router)
app.include_router(dashboard.router)
