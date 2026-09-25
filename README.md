# Simulador de Aporte para Aposentadoria

Aplicação web que calcula **quanto investir por mês** para atingir a renda desejada na
aposentadoria, com persistência de todas as simulações. Implementa o
[PRD v1.1](docs/prd-simulador-aposentadoria.md).

## Estrutura

```
app/                API FastAPI + SPA estática (app/static)
  calculations.py   Fórmulas de anuidade e aporte (RF-02, RF-03, RF-05)
  persistence.py    Gravação assíncrona com fila de reprocessamento (A3, RNF-01)
  db.py             Tabela `simulacoes`, consultas e expurgo de retenção (RF-09, RNF-09)
infra/              Bicep (App Service, Azure SQL, Front Door, App Insights, alertas)
loadtest/           Plano JMeter + config do Azure Load Testing
.github/workflows/  CI (lint/testes/bicep) e Deploy (dev → load test → prod com swap)
```

## API

| Método | Rota | Descrição |
|---|---|---|
| `POST` | `/api/simulate` | Calcula o aporte e devolve a série anual; grava a simulação |
| `GET` | `/api/simulations/{id}` | Recupera uma simulação gravada |
| `GET` | `/api/simulations?from=&to=` | Extração agregada (header `X-API-Key`) |
| `POST` | `/api/admin/purge` | Expurgo da retenção de 24 meses (header `X-API-Key`) |
| `GET` | `/health` | Health probe, inclui conectividade com o banco |

## Rodar localmente

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload      # http://localhost:8000
pytest -q && ruff check app tests
```

Sem `DATABASE_URL`/`SQL_SERVER` definidos, a aplicação usa SQLite local.

## Deploy na Azure

```bash
AMBIENTE=dev ADMIN_API_KEY='<chave>' ./infra/deploy.sh
```

O script provisiona o Bicep no resource group `rgdevin` (`centralus`), concede acesso da
Managed Identity do App Service ao banco e publica o pacote da aplicação.

| | dev | prod |
|---|---|---|
| Plano | B1, 1 instância | P1v3, autoscale 1–5 (CPU > 70%) |
| Front Door + WAF | desabilitado | habilitado |
| Azure SQL Serverless | auto-pause 60 min | auto-pause desabilitado |
| Slot de staging | não | sim (deploy com swap) |

A conexão com o Azure SQL usa **Managed Identity** (sem senha na aplicação); autenticação
somente Entra ID no servidor SQL e PITR de 7 dias.

## Teste de carga

```bash
az load test create --load-test-resource <recurso> -g rgdevin \
  --test-id simulador-aposentadoria --load-test-config-file loadtest/config.yaml
```

Perfil: ramp-up 0→100 VUs (2 min), sustentação 100 VUs (10 min), pico 300 VUs (3 min).
Critérios: p95 < 300 ms na sustentação (< 800 ms no pico), erro < 1%, CPU < 80% e 100%
das simulações bem-sucedidas persistidas — verificável comparando o número de amostras
com `GET /api/simulations?from=...`.

## Observabilidade

Application Insights (Live Metrics, requisições, exceções, dependências) e availability
test de `/health` de 3 regiões a cada 5 min; logs no Log Analytics com retenção de 30 dias.
Alertas de latência, 5xx, disponibilidade, CPU, falha de gravação, vCore e espaço do banco
notificam o e-mail configurado em `emailAlertas`.
