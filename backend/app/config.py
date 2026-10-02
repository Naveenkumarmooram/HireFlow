"""Environment configuration. Production refuses unsafe defaults."""

import os
import secrets
from typing import Literal
from urllib.parse import urlsplit

from cryptography.fernet import Fernet
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    environment: Literal["development", "test", "production"] = Field(
        default_factory=lambda: "production" if os.getenv("VERCEL") else "development"
    )
    database_url: str = "sqlite+pysqlite:///./hireflow.db"
    jwt_secret: str = Field(default_factory=lambda: secrets.token_urlsafe(48), repr=False)
    jwt_issuer: str = "hireflow-api"
    jwt_audience: str = "hireflow-web"
    access_token_minutes: int = Field(default=30, ge=5, le=120)
    auto_migrate_on_startup: bool = False
    cors_origins: str = "http://localhost:5173"
    bootstrap_org_name: str = ""
    bootstrap_admin_email: str = ""
    bootstrap_admin_password: str = Field(default="", repr=False)
    resume_encryption_key: str = Field(default="", repr=False)
    clamd_host: str = ""
    clamd_port: int = Field(default=3310, ge=1, le=65535)
    max_request_bytes: int = Field(default=4_000_000, ge=1024, le=4_000_000)
    max_resume_bytes: int = Field(default=3_500_000, ge=1024, le=3_500_000)
    login_attempt_limit: int = Field(default=10, ge=3, le=100)
    login_window_seconds: int = Field(default=900, ge=60, le=3600)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def allowed_origins(self) -> list[str]:
        return [
            origin.strip().rstrip("/") for origin in self.cors_origins.split(",") if origin.strip()
        ]

    @model_validator(mode="after")
    def validate_configuration(self):
        if os.getenv("VERCEL") and self.environment != "production":
            raise ValueError("Vercel deployments require ENVIRONMENT=production")
        if self.environment != "production" and not self.jwt_secret:
            self.jwt_secret = secrets.token_urlsafe(48)
        for origin in self.allowed_origins:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or parsed.path
                or parsed.query
                or parsed.fragment
                or parsed.username
            ):
                raise ValueError("CORS_ORIGINS must contain exact HTTP(S) origins")
        if self.resume_encryption_key:
            try:
                Fernet(self.resume_encryption_key.encode())
            except (ValueError, TypeError) as exc:
                raise ValueError("RESUME_ENCRYPTION_KEY must be a valid Fernet key") from exc
        if self.environment == "production":
            if (
                "jwt_secret" not in self.model_fields_set
                or len(self.jwt_secret) < 32
                or any(
                    marker in self.jwt_secret.lower()
                    for marker in ("change", "replace", "development")
                )
            ):
                raise ValueError(
                    "Production requires an explicit random JWT_SECRET of at least 32 characters"
                )
            url = make_url(self.database_url)
            if url.drivername != "postgresql+psycopg" or url.query.get("sslmode") not in {
                "require",
                "verify-ca",
                "verify-full",
            }:
                raise ValueError(
                    "Production DATABASE_URL must use postgresql+psycopg and sslmode=require or stronger"
                )
            if self.auto_migrate_on_startup:
                raise ValueError("Run migrations explicitly before production startup")
            if not self.allowed_origins or any(
                not origin.startswith("https://") for origin in self.allowed_origins
            ):
                raise ValueError("Production requires explicit HTTPS CORS_ORIGINS")
        return self


settings = Settings()
