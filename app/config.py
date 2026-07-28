import os
from datetime import timedelta
from urllib.parse import quote_plus

from dotenv import load_dotenv

load_dotenv()


def _normalize_mysql_url(url: str) -> str:
    if url.startswith("mysql://"):
        return url.replace("mysql://", "mysql+pymysql://", 1)
    return url


def _build_database_uri() -> str:
    """Support Railway DATABASE_URL / MYSQL_URL and MYSQL* service variables."""
    url = os.getenv("DATABASE_URL") or os.getenv("MYSQL_URL")
    if url:
        return _normalize_mysql_url(url)

    mysql_host = os.getenv("MYSQLHOST") or os.getenv("DB_HOST")
    mysql_port = os.getenv("MYSQLPORT") or os.getenv("DB_PORT", "3306")
    mysql_user = os.getenv("MYSQLUSER") or os.getenv("DB_USER", "root")
    mysql_password = os.getenv("MYSQLPASSWORD") or os.getenv("DB_PASSWORD", "")
    mysql_database = os.getenv("MYSQLDATABASE") or os.getenv("DB_NAME", "hirehub")

    if mysql_host:
        password = quote_plus(mysql_password)
        return (
            f"mysql+pymysql://{mysql_user}:{password}@"
            f"{mysql_host}:{mysql_port}/{mysql_database}"
        )

    return (
        f"mysql+pymysql://{os.getenv('DB_USER', 'root')}:"
        f"{quote_plus(os.getenv('DB_PASSWORD', ''))}@"
        f"{os.getenv('DB_HOST', '127.0.0.1')}/"
        f"{os.getenv('DB_NAME', 'hirehub')}"
    )


class Config:
    SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-key")
    SQLALCHEMY_DATABASE_URI = _build_database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-key")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(
        minutes=int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES_MINUTES", "1440"))
    )
    DEBUG = os.getenv("FLASK_DEBUG", "0") == "1"
