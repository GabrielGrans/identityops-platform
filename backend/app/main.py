from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from backend.app.core.database import engine
from backend.app.models import (
    Base,
    Department,
    Employee,
    Group,
    Permission,
)

from backend.app.api.routes.auth import router as auth_router
from backend.app.api.routes.governance import router as governance_router
from backend.app.api.routes.departments import (
    router as departments_router,
)
from backend.app.api.routes.employees import (
    router as employees_router,
)
from backend.app.api.routes.groups import (
    router as groups_router,
)
from backend.app.api.routes.permissions import (
    router as permissions_router,
)
from backend.app.api.routes.memberships import (
    router as memberships_router,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)

    yield

    engine.dispose()


app = FastAPI(
    title="IdentityOps API",
    description=(
        "Enterprise Identity and Access Management Platform"
    ),
    version="0.7.0",
    lifespan=lifespan,
)


# Frontend development origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth_router)
app.include_router(departments_router)
app.include_router(employees_router)
app.include_router(groups_router)
app.include_router(permissions_router)
app.include_router(memberships_router)
app.include_router(governance_router)


@app.get("/", tags=["General"])
def root():
    return {
        "application": "IdentityOps",
        "message": "IdentityOps API is running",
        "version": "0.7.0",
    }


@app.get("/health", tags=["Health"])
def health_check():
    return {
        "status": "healthy",
        "application": "IdentityOps",
    }


@app.get("/health/database", tags=["Health"])
def database_health_check():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        return {
            "status": "healthy",
            "database": "connected",
        }

    except SQLAlchemyError:
        return {
            "status": "unhealthy",
            "database": "disconnected",
        }
