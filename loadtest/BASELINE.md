# Baseline de carga — ambiente dev

Execução: `baseline-1790292901` (Azure Load Testing `alt-simapos`, rgdevin/centralus)
Alvo: `https://app-simapos-dev-ewkqhfwp3sejs.azurewebsites.net` (App Service B1, 1 instância; Azure SQL Serverless GP)
Perfil: 0→100 VUs em 2 min, 100 VUs sustentados, rampa 100→300 (interrompida em ~244 VUs)
Duração efetiva: ~15 min (execução cancelada antes do ramp-down final)
Mix: 90% `POST /api/simulate` + 10% `GET /`

## Resultados

| Métrica | PRD | Medido |
| --- | --- | --- |
| p95 sustentação (POST) | < 300 ms | 2599 ms |
| p95 pico (POST) | < 800 ms | 4237 ms |
| Erros | < 1% | 0,003% (2 em 72.734) |
| CPU do App Service | < 80% | ~44% (CpuTime 133 s / 300 s em 1 vCPU) |
| Simulações persistidas | 100% | 57.895 de 65.482 POSTs 200 (88,4%) |

## Interpretação

- Latência: o SKU B1 (1 vCPU) satura muito antes de 100 VUs; a CPU do plano não chega a 80% porque a
  fila de requisições do Gunicorn é o gargalo, não o processamento. O alvo de p95 do PRD pressupõe o
  SKU de produção (P1v3 com autoscale 1→5).
- Persistência: ~11,6% das simulações não chegaram ao banco. A fila do `GravadorAssincrono` é limitada
  a 10.000 itens e drenada por uma única thread; acima de ~70 req/s ela enche e os registros excedentes
  são descartados (log `fila_gravacao_cheia`). Para atender ao requisito de 100% é necessário mais de
  uma thread gravadora e/ou inserção em lote.

## Limpeza

Os 58.203 registros gerados pelo teste foram removidos via `DELETE /api/admin/simulations?from=&to=`.
