"""Configuração da aplicação via variáveis de ambiente / App Configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    admin_api_key: str | None
    retencao_meses: int
    ambiente: str

    @property
    def usa_mssql(self) -> bool:
        return self.database_url.startswith("mssql")


def _database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    server = os.getenv("SQL_SERVER")
    database = os.getenv("SQL_DATABASE")
    if server and database:
        # Managed Identity do App Service: sem senha na connection string (RNF-04).
        driver = os.getenv("SQL_ODBC_DRIVER", "ODBC Driver 18 for SQL Server")
        client_id = os.getenv("SQL_MI_CLIENT_ID")
        url = (
            f"mssql+pyodbc://@{server}/{database}"
            f"?driver={driver.replace(' ', '+')}"
            "&Encrypt=yes&TrustServerCertificate=no"
            "&Authentication=ActiveDirectoryMsi"
        )
        if client_id:
            url = f"{url}&UID={client_id}"
        return url
    return "sqlite:///./simulacoes.db"


def get_settings() -> Settings:
    return Settings(
        database_url=_database_url(),
        admin_api_key=os.getenv("ADMIN_API_KEY"),
        retencao_meses=int(os.getenv("RETENCAO_MESES", "24")),
        ambiente=os.getenv("AMBIENTE", "dev"),
    )
