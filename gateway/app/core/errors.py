from fastapi import Request
from fastapi.responses import JSONResponse


def get_request_id(request: Request) -> str:
    return getattr(
        request.state,
        "request_id",
        request.headers.get("X-Correlation-ID", ""),
    )


async def http_exception_handler(
    request: Request,
    exc,
):
    request_id = get_request_id(request)

    response = JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "request_id": request_id,
        },
    )

    if request_id:
        response.headers["X-Correlation-ID"] = request_id

    return response


async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
):
    request_id = get_request_id(request)

    response = JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "request_id": request_id,
        },
    )

    if request_id:
        response.headers["X-Correlation-ID"] = request_id

    return response