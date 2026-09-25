"""Executa um script T-SQL no Azure SQL usando token do Entra ID (az CLI).

Uso: python3 infra/executar_sql.py <servidor_fqdn> <banco> <arquivo.sql>
"""

from __future__ import annotations

import struct
import subprocess
import sys

import pyodbc

TOKEN_SCOPE = "https://database.windows.net/.default"
SQL_COPT_SS_ACCESS_TOKEN = 1256


def obter_token() -> bytes:
    saida = subprocess.run(
        ["az", "account", "get-access-token", "--resource", "https://database.windows.net/", "--query", "accessToken", "-o", "tsv"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    bytes_token = saida.encode("utf-16-le")
    return struct.pack("<i", len(bytes_token)) + bytes_token


def driver_disponivel() -> str:
    for nome in ("ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server"):
        if nome in pyodbc.drivers():
            return nome
    raise RuntimeError(f"Nenhum driver ODBC do SQL Server encontrado: {pyodbc.drivers()}")


def main() -> int:
    servidor, banco, arquivo = sys.argv[1], sys.argv[2], sys.argv[3]
    with open(arquivo, encoding="utf-8") as f:
        script = f.read()

    conn_str = (
        f"Driver={{{driver_disponivel()}}};Server=tcp:{servidor},1433;"
        f"Database={banco};Encrypt=yes;TrustServerCertificate=no;Connection Timeout=60;"
    )
    with pyodbc.connect(conn_str, attrs_before={SQL_COPT_SS_ACCESS_TOKEN: obter_token()}) as conn:
        conn.autocommit = True
        cursor = conn.cursor()
        for lote in script.split("\nGO\n"):
            if lote.strip():
                cursor.execute(lote)
    print("Script executado com sucesso.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
