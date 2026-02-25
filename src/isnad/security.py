"""
isnad.security — Shared security utilities: auth, rate limiting, logging, validation.

Used by both api.py (production) and api_v1.py.
"""

import hashlib
import hmac
import json
import logging
import os
import re
import time
import uuid
from contextvars import ContextVar
from typing import Optional

from fastapi import HTTPException, Request, Response, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field, field_validator
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

# ─── Context var for request ID ────────────────────────────────────

request_id_var: ContextVar[str] = ContextVar("request_id", default="")


# ─── Structured JSON logging ──────────────────────────────────────

class RequestIdFilter(logging.Filter):
    def filter(self, record):
        record.request_id = request_id_var.get("")
        return True


def setup_structured_logging(level: str = "INFO") -> logging.Logger:
    """Configure JSON structured logging with request IDs."""
    from pythonjsonlogger.json import JsonFormatter

    logger = logging.getLogger("isnad")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = JsonFormatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s %(request_id)s",
            rename_fields={"asctime": "timestamp", "levelname": "level"},
        )
        handler.setFormatter(formatter)
        handler.addFilter(RequestIdFilter())
        logger.addHandler(handler)

    return logger


logger = setup_structured_logging()


# ─── Rate Limiter (slowapi) ───────────────────────────────────────

limiter = Limiter(key_func=get_remote_address)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """Custom 429 handler."""
    return Response(
        content='{"detail":"Rate limit exceeded. Try again later."}',
        status_code=429,
        media_type="application/json",
        headers={"Retry-After": str(exc.detail.split()[-1]) if exc.detail else "60"},
    )


# ─── API Key Auth ─────────────────────────────────────────────────

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# Admin key from env (for write endpoints when no DB)
ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY", "")


async def require_write_auth(
    request: Request,
    api_key: Optional[str] = Security(_api_key_header),
) -> str:
    """Require valid API key for write endpoints.

    Checks against:
    1. ADMIN_API_KEY env var
    2. Database api_keys table (if DB available)
    """
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")

    # Check admin key
    if ADMIN_API_KEY and api_key == ADMIN_API_KEY:
        return "admin"

    # Check DB keys if available
    db = getattr(request.app.state, "db", None)
    if db is not None:
        try:
            record = await db.validate_api_key(api_key)
            if record:
                return record.get("owner_email", "db-key")
        except Exception:
            pass

    raise HTTPException(status_code=403, detail="Invalid API key")


# ─── Request ID + Logging Middleware ──────────────────────────────

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Inject request ID, log requests, add security headers."""

    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
        request_id_var.set(rid)

        t0 = time.time()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("Unhandled error", extra={"path": request.url.path})
            raise

        elapsed_ms = round((time.time() - t0) * 1000, 1)
        logger.info(
            "request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": elapsed_ms,
                "client": request.client.host if request.client else "",
            },
        )

        # Security headers
        response.headers["X-Request-ID"] = rid
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"

        return response


# ─── CORS configuration ──────────────────────────────────────────

def configure_cors(app, allowed_origins: Optional[list[str]] = None):
    """Add CORS middleware with configurable origins."""
    origins = allowed_origins
    if not origins:
        env_origins = os.environ.get("ALLOWED_ORIGINS", "")
        if env_origins:
            origins = [o.strip() for o in env_origins.split(",") if o.strip()]
        else:
            origins = ["*"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )


# ─── Input validation models (strict) ─────────────────────────────

class StrictAttestRequest(BaseModel):
    """Attestation request with strict validation."""
    subject_id: str = Field(..., min_length=1, max_length=200)
    witness_id: str = Field(..., min_length=1, max_length=200)
    task: str = Field(..., min_length=1, max_length=1000)
    evidence: str = Field("", max_length=2000)

    @field_validator("subject_id", "witness_id")
    @classmethod
    def no_null_bytes(cls, v: str) -> str:
        if "\x00" in v:
            raise ValueError("Null bytes not allowed")
        return v.strip()

    @field_validator("task")
    @classmethod
    def task_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Task cannot be empty/whitespace")
        return v


class StrictIdentityRequest(BaseModel):
    """Identity creation — optional name with validation."""
    name: Optional[str] = Field(None, max_length=100)


# ─── Health check with DB ─────────────────────────────────────────

async def health_check_with_db(db=None) -> dict:
    """Enhanced health check including DB connectivity."""
    result = {
        "status": "ok",
        "version": "0.3.0",
        "timestamp": time.time(),
    }

    if db is not None:
        try:
            async with db._pool.acquire() as conn:
                row = await conn.fetchrow("SELECT 1 as ok")
                result["database"] = "connected" if row else "error"
        except Exception as e:
            result["database"] = f"error: {type(e).__name__}"
            result["status"] = "degraded"
    else:
        result["database"] = "not_configured"

    return result


# ─── XSS / SQL Injection detection ────────────────────────────────

_XSS_PATTERN = re.compile(r'<script|javascript:|on\w+\s*=|<iframe|<object|<embed', re.IGNORECASE)
_SQL_INJECTION_PATTERN = re.compile(
    r"(\b(union|select|insert|update|delete|drop|alter|exec|execute)\b.*\b(from|into|table|where)\b)|"
    r"(--|;)\s*(drop|alter|delete|update|select|insert)",
    re.IGNORECASE,
)


def check_xss(value: str) -> bool:
    return bool(_XSS_PATTERN.search(value))


def check_sql_injection(value: str) -> bool:
    return bool(_SQL_INJECTION_PATTERN.search(value))


def sanitize_input(value: str, field_name: str = "input") -> str:
    """Validate a user-supplied string. Raises HTTPException if suspicious."""
    if check_xss(value):
        raise HTTPException(status_code=400, detail=f"Invalid characters in {field_name}")
    if check_sql_injection(value):
        raise HTTPException(status_code=400, detail=f"Invalid characters in {field_name}")
    return value


# ─── Timing-safe API key comparison ──────────────────────────────

def timing_safe_validate_key(provided: str, stored_hash: str) -> bool:
    """Compare API key hash in constant time."""
    provided_hash = hashlib.sha256(provided.encode()).hexdigest()
    return hmac.compare_digest(provided_hash, stored_hash)


# ─── Request body size limiter ───────────────────────────────────

class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_size: int = 1_048_576):
        super().__init__(app)
        self.max_size = max_size

    async def dispatch(self, request: Request, call_next):
        cl = request.headers.get("content-length")
        if cl and int(cl) > self.max_size:
            return JSONResponse(status_code=413, content={"detail": "Request body too large"})
        return await call_next(request)


# ─── Global exception handler (never leak internals) ─────────────

async def generic_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception on %s: %s", request.url.path, type(exc).__name__)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# ─── Admin auth dependency ───────────────────────────────────────

_admin_key_header = APIKeyHeader(name="X-Admin-Key", auto_error=False)


async def require_admin_key(request: Request, key: str = Security(_admin_key_header)):
    admin_key = os.environ.get("ADMIN_API_KEY", "")
    if not admin_key:
        raise HTTPException(status_code=503, detail="Admin access not configured")
    if not key:
        log_auth_failure(request.client.host if request.client else "unknown",
                         "missing admin key", request.url.path)
        raise HTTPException(status_code=401, detail="Missing admin key")
    if not hmac.compare_digest(key, admin_key):
        log_auth_failure(request.client.host if request.client else "unknown",
                         "invalid admin key", request.url.path)
        raise HTTPException(status_code=403, detail="Invalid admin key")
    return True


def log_auth_failure(ip: str, reason: str, endpoint: str = ""):
    logger.warning("Auth failure: %s from %s on %s", reason, ip, endpoint,
                    extra={"event": "auth_failure", "ip": ip, "reason": reason, "endpoint": endpoint})


# ─── Apply all security to a FastAPI app ──────────────────────────

def apply_security(app):
    """One-call setup: CORS, rate limiting, logging middleware, error handlers."""
    from slowapi.errors import RateLimitExceeded

    configure_cors(app)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    app.add_middleware(RequestLoggingMiddleware)
