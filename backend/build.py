from pathlib import Path

from alembic import command
from alembic.config import Config

from app.config import settings


def main() -> None:
    config = Config(str(Path(__file__).resolve().parent / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).resolve().parent / "migrations"))
    config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
    command.upgrade(config, "head")


if __name__ == "__main__":
    main()
