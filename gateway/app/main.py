from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi import FastAPI, HTTPException

from app.core.errors import (
    http_exception_handler,
    unhandled_exception_handler,
)

from app.routes.auth import router as auth_router
from app.routes.admin import router as admin_router
from app.logging.middleware import RequestLoggingMiddleware
from app.security.middleware import SecurityHeadersMiddleware
from app.routing.router import (
    router as proxy_router,
    start_health_monitor,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await start_health_monitor()

    yield


app = FastAPI(
    title="API Gateway",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_exception_handler(
    HTTPException,
    http_exception_handler,
)

app.add_exception_handler(
    Exception,
    unhandled_exception_handler,
)

app.add_middleware(
    SecurityHeadersMiddleware
)

app.add_middleware(
    RequestLoggingMiddleware
)

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(proxy_router)


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "api-gateway",
    }