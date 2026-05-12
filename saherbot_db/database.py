"""SQLAlchemy engine URL built from DB_* settings (decouple / os.environ)."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

from decouple import config
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, URL
from sqlalchemy.orm import Session, sessionmaker

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def project_root() -> Path:
    return _PROJECT_ROOT


def _default_sqlite_url() -> str:
    data_dir = _PROJECT_ROOT / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return "sqlite:///" + str(data_dir / "saherbot.db").replace("\\", "/")


def _strip(s: str | None) -> str:
    return (s or "").strip()


def _env_or_config(key: str, default: str = "") -> str:
    return _strip(os.environ.get(key) or str(config(key, default=default)))


def resolve_database_url() -> str:
    """Effective SQLAlchemy URL from ``DB_TYPE`` and related ``DB_*`` variables."""
    db_type = (_env_or_config("DB_TYPE", "sqlite") or "sqlite").lower()
    if db_type in ("sqlite", "sqlite3"):
        db_path = _env_or_config("DB_DATABASE")
        if not db_path:
            return _default_sqlite_url()
        path = Path(db_path)
        if not path.is_absolute():
            path = _PROJECT_ROOT / path
        path.parent.mkdir(parents=True, exist_ok=True)
        return "sqlite:///" + str(path).replace("\\", "/")

    host = _env_or_config("DB_HOST", "127.0.0.1") or "127.0.0.1"
    port_raw = _env_or_config("DB_PORT")
    user = _env_or_config("DB_USERNAME")
    password = _env_or_config("DB_PASSWORD")
    database = _env_or_config("DB_DATABASE")
    if not database:
        raise RuntimeError("DB_DATABASE is required when DB_TYPE is not sqlite.")

    if db_type in ("postgresql", "postgres", "postgresql+psycopg2"):
        driver = "postgresql+psycopg2"
        port = int(port_raw or "5432")
        u = URL.create(
            drivername=driver,
            username=user or None,
            password=password or None,
            host=host,
            port=port,
            database=database,
        )
        return u.render_as_string(hide_password=False)

    if db_type in ("mysql", "mariadb", "mysql+pymysql"):
        port = int(port_raw or "3306")
        user_q = quote_plus(user) if user else ""
        pass_q = quote_plus(password) if password else ""
        db_q = quote_plus(database)
        host_q = host
        auth = f"{user_q}:{pass_q}@" if (user or password) else (f"{user_q}@" if user else "")
        return f"mysql+pymysql://{auth}{host_q}:{port}/{db_q}?charset=utf8mb4"

    raise RuntimeError(f"Unsupported DB_TYPE: {db_type!r} (use sqlite, postgresql, or mysql).")


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    url = resolve_database_url()
    connect_args: dict = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(url, echo=False, pool_pre_ping=True, connect_args=connect_args)


def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, autocommit=False, expire_on_commit=False)
