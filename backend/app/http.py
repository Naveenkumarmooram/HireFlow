"""Request limits, security headers and redacted request diagnostics."""

import json
import logging
import time
from uuid import uuid4

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.datastructures import MutableHeaders
from starlette.middleware.cors import CORSMiddleware

from app.config import settings

logger = logging.getLogger("hireflow.http")


class RequestSafetyMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request_id = uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        started = time.monotonic()
        status = 500

        async def safe_send(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = MutableHeaders(scope=message)
                headers["X-Request-ID"] = request_id
                headers["X-Content-Type-Options"] = "nosniff"
                headers["X-Frame-Options"] = "DENY"
                headers["Referrer-Policy"] = "no-referrer"
                headers["Cache-Control"] = "no-store"
                if settings.environment == "production":
                    headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
            await send(message)

        # Buffer only up to the hard limit; enforce for chunked requests too.
        chunks = []
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body = message.get("body", b"")
            size += len(body)
            if size > settings.max_request_bytes:
                response = JSONResponse(
                    {"detail": "Request body exceeds the upload limit"}, status_code=413
                )
                return await response(scope, receive, safe_send)
            chunks.append(body)
            if not message.get("more_body", False):
                break
        consumed = False

        async def replay():
            nonlocal consumed
            if not consumed:
                consumed = True
                return {
                    "type": "http.request",
                    "body": b"".join(chunks),
                    "more_body": False,
                }
            return await receive()

        try:
            await self.app(scope, replay, safe_send)
        finally:
            # Never log URL tokens, query strings, credentials, bodies or SQL.
            route = scope.get("route")
            logger.info(
                json.dumps(
                    {
                        "request_id": request_id,
                        "method": scope["method"],
                        "route": getattr(route, "path", "unmatched"),
                        "status": status,
                        "duration_ms": round((time.monotonic() - started) * 1000),
                    }
                )
            )


def install_http_controls(app):
    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return JSONResponse(
            status_code=422,
            content={
                "detail": [
                    {
                        "loc": list(issue["loc"]),
                        "msg": issue["msg"],
                        "type": issue["type"],
                    }
                    for issue in exc.errors()
                ],
                "request_id": request.state.request_id,
            },
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error(request, _exc):
        return JSONResponse(
            status_code=409,
            content={
                "detail": "The operation conflicts with an existing record.",
                "request_id": request.state.request_id,
            },
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request, exc):
        logger.error(
            "database_error request_id=%s type=%s",
            request.state.request_id,
            type(exc).__name__,
        )
        return JSONResponse(
            status_code=503,
            content={
                "detail": "Service temporarily unavailable.",
                "request_id": request.state.request_id,
            },
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request, exc):
        logger.error(
            "request_error request_id=%s type=%s",
            getattr(request.state, "request_id", ""),
            type(exc).__name__,
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "The request could not be completed."},
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )

    app.add_middleware(RequestSafetyMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["X-Request-ID", "Retry-After"],
    )
