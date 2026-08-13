from fastapi import FastAPI

from app.routes.auth import router as auth_router
from app.routes.admin import router as admin_router
from app.routing.router import router as proxy_router

app = FastAPI(
    title="API Gateway",
    version="1.0.0",
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