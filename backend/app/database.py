from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


engine_options = {"pool_pre_ping": True, "hide_parameters": True}
if settings.database_url.startswith("postgresql"):
    engine_options.update({"pool_size": 1, "max_overflow": 0, "pool_recycle": 300})
    engine_options["connect_args"] = {"prepare_threshold": None, "connect_timeout": 10}

engine = create_engine(settings.database_url, **engine_options)
if engine.dialect.name == "sqlite":

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
