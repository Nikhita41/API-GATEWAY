from contextlib import asynccontextmanager
from app.security.waf import WAFMiddleware
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


from fastapi.openapi.utils import get_openapi

app = FastAPI(
    title="API Gateway",
    version="1.0.0",
    lifespan=lifespan,
)

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title="API Gateway",
        version="1.0.0",
        routes=app.routes,
    )
    
    if "components" not in openapi_schema:
        openapi_schema["components"] = {}
        
    if "securitySchemes" not in openapi_schema["components"]:
        openapi_schema["components"]["securitySchemes"] = {}
        
    # Remove the auto-generated HTTPBearer scheme if it exists
    if "HTTPBearer" in openapi_schema["components"]["securitySchemes"]:
        del openapi_schema["components"]["securitySchemes"]["HTTPBearer"]
        
    # Add our custom bearerAuth scheme
    openapi_schema["components"]["securitySchemes"]["bearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
    }
    
    # Replace references to HTTPBearer with bearerAuth in all endpoints
    for path in openapi_schema.get("paths", {}).values():
        for operation in path.values():
            if "security" in operation:
                for sec in operation["security"]:
                    if "HTTPBearer" in sec:
                        sec["bearerAuth"] = sec.pop("HTTPBearer")
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

app.add_exception_handler(
    HTTPException,
    http_exception_handler,
)

app.add_exception_handler(
    Exception,
    unhandled_exception_handler,
)

app.add_middleware(
    WAFMiddleware
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