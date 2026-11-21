from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.routing import APIRoute
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
from backend.app.api.routes.certification import router as certification_router
from backend.app.api.routes.dashboard import router as dashboard_router
from backend.app.api.routes.entra import router as entra_router
from backend.app.api.routes.entra_automation import router as entra_automation_router
from backend.app.api.routes.iam_operations import router as iam_operations_router
from backend.app.api.routes.unified_entra_directory import router as unified_entra_directory_router
from backend.app.api.routes.enterprise_governance import router as enterprise_governance_router
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
    description="Read-only IAM and SecOps monitoring for Microsoft Entra ID.",
    version="1.4.1",
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


# Only local sign-in and read-only directory collection accept POST in this app.
monitoring_posts = {"/auth/login", "/entra/sync"}
monitoring_routes = APIRouter()
for source in (
    auth_router, departments_router, employees_router, groups_router, permissions_router,
    memberships_router, governance_router, entra_router, entra_automation_router,
    unified_entra_directory_router, enterprise_governance_router, iam_operations_router,
    certification_router, dashboard_router,
):
    monitoring_routes.routes.extend(
        route for route in source.routes
        if isinstance(route, APIRoute)
        and (route.methods == {"GET"} or (route.methods == {"POST"} and route.path in monitoring_posts))
    )
app.include_router(monitoring_routes)


@app.get("/", tags=["General"])
def root():
    return {
        "application": "IdentityOps",
        "message": "IdentityOps API is running",
        "version": "1.4.1",
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
