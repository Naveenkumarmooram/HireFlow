from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://hireflow:hireflow_dev_only@localhost:5432/hireflow"
    jwt_secret: str = "local-development-secret-change-before-deploy"
    access_token_minutes: int = 60
    auto_migrate_on_startup: bool = True
    cors_origins: str = "http://localhost:5173"
    bootstrap_org_name: str = "Amiro Tech Solutions"
    bootstrap_admin_email: str = "admin@hireflow.dev"
    bootstrap_admin_password: str = "change-this-before-use"
    resume_encryption_key: str = ""
    clamd_host: str = ""
    clamd_port: int = 3310

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()