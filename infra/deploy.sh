#!/usr/bin/env bash
# Provisiona a infraestrutura e publica a aplicação em um ambiente.
#
#   AMBIENTE=dev ADMIN_API_KEY=... ./infra/deploy.sh
#
# Requer: az CLI autenticado com permissão de contribuidor no resource group.
set -euo pipefail

AMBIENTE="${AMBIENTE:-dev}"
RESOURCE_GROUP="${RESOURCE_GROUP:-rgdevin}"
LOCATION="${LOCATION:-centralus}"
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

: "${ADMIN_API_KEY:?defina ADMIN_API_KEY}"

export SQL_ADMIN_OBJECT_ID="${SQL_ADMIN_OBJECT_ID:-$(az ad signed-in-user show --query id -o tsv 2>/dev/null || az ad sp show --id "$(az account show --query user.name -o tsv)" --query id -o tsv)}"
export SQL_ADMIN_LOGIN="${SQL_ADMIN_LOGIN:-deployer-${AMBIENTE}}"
export ADMIN_API_KEY

az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none

echo "==> Provisionando infraestrutura (${AMBIENTE})"
az deployment group create \
  --resource-group "$RESOURCE_GROUP" \
  --name "simapos-${AMBIENTE}-$(date +%s)" \
  --parameters "${RAIZ}/infra/${AMBIENTE}.bicepparam" \
  --output none

WEBAPP=$(az deployment group list --resource-group "$RESOURCE_GROUP" \
  --query "sort_by([?contains(name, 'simapos-${AMBIENTE}')], &properties.timestamp)[-1].properties.outputs.webAppName.value" -o tsv)
SQL_FQDN=$(az deployment group list --resource-group "$RESOURCE_GROUP" \
  --query "sort_by([?contains(name, 'simapos-${AMBIENTE}')], &properties.timestamp)[-1].properties.outputs.sqlServerFqdn.value" -o tsv)

echo "==> Concedendo acesso da Managed Identity ao banco"
SQL_SCRIPT=$(mktemp)
sed "s/{{APP_NAME}}/${WEBAPP}/g" "${RAIZ}/infra/conceder-acesso-mi.sql" > "$SQL_SCRIPT"
python3 "${RAIZ}/infra/executar_sql.py" "$SQL_FQDN" sqldb-simulacoes "$SQL_SCRIPT"
rm -f "$SQL_SCRIPT"

echo "==> Publicando aplicação"
PACOTE=$(mktemp -u).zip
(cd "$RAIZ" && zip -qr "$PACOTE" app requirements.txt startup.sh -x '*__pycache__*')
az webapp deploy --resource-group "$RESOURCE_GROUP" --name "$WEBAPP" \
  --src-path "$PACOTE" --type zip --async false --output none
rm -f "$PACOTE"

URL="https://$(az webapp show -g "$RESOURCE_GROUP" -n "$WEBAPP" --query defaultHostName -o tsv)"
echo "==> Ambiente ${AMBIENTE} publicado: ${URL}"
