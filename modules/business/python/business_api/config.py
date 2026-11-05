from dataclasses import dataclass


@dataclass(frozen=True)
class DbConfig:
    host: str
    port: int
    user: str
    password: str
    database: str
    schema: str = "public"
    driver: str = "pg8000"
    connect_timeout_s: float = 5.0
