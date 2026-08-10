from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from .db import engine, Base
from . import models
from .router import router
from .support_system.router import router as support_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

from app.xlsx_import.router import router as xlsx_import_router
from app.xlsx_import.control import init_control_tables


Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_control_tables()
    yield


app = FastAPI(lifespan=lifespan)

app.include_router(router)
app.include_router(support_router, prefix="/api")
app.include_router(xlsx_import_router)


@app.get("/")
def read_root():
    return {"status": "Backend is running"}