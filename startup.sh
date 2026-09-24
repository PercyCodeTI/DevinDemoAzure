#!/usr/bin/env bash
# Startup do App Service (Linux): garante driver ODBC e sobe o Gunicorn/Uvicorn.
set -euo pipefail

detectar_driver() {
  if command -v odbcinst >/dev/null 2>&1; then
    for nome in "ODBC Driver 18 for SQL Server" "ODBC Driver 17 for SQL Server"; do
      if odbcinst -q -d | tr -d '[]' | grep -qx "$nome"; then
        echo "$nome"
        return 0
      fi
    done
  fi
  return 1
}

if ! driver=$(detectar_driver); then
  echo "Driver ODBC do SQL Server ausente; instalando msodbcsql18..."
  export ACCEPT_EULA=Y
  export DEBIAN_FRONTEND=noninteractive
  versao=$(. /etc/os-release && echo "$VERSION_ID")
  curl -fsSL https://packages.microsoft.com/keys/microsoft.asc \
    | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg
  curl -fsSL "https://packages.microsoft.com/config/ubuntu/${versao}/prod.list" \
    | sed 's|\[arch=|[signed-by=/usr/share/keyrings/microsoft-prod.gpg arch=|' \
    > /etc/apt/sources.list.d/mssql-release.list
  apt-get update -qq
  apt-get install -y -qq msodbcsql18 unixodbc >/dev/null
  driver=$(detectar_driver)
fi

export SQL_ODBC_DRIVER="$driver"
echo "Usando driver ODBC: $SQL_ODBC_DRIVER"

exec gunicorn app.main:app \
  --worker-class uvicorn.workers.UvicornWorker \
  --workers "${GUNICORN_WORKERS:-4}" \
  --bind 0.0.0.0:8000 \
  --timeout 120 \
  --access-logfile '-' \
  --error-logfile '-'
