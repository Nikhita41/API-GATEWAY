from fastapi import FastAPI

from app.routes.auth import router as auth_router

print("Loaded router:", auth_router)

app = FastAPI(
    title="API Gateway",
    version="1.0.0",
)

app.include_router(auth_router)

print(app.routes)


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "api-gateway",
    }