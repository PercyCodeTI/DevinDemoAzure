# PRD — Simulador de Aporte para Aposentadoria

**Versão:** 1.1 | **Data:** 2026-09-23 | **Autor:** Devin (para Percy)

> Mudança na v1.1: todas as simulações passam a ser persistidas em banco de dados.

## 1. Objetivo

Permitir que uma pessoa descubra **quanto precisa investir por mês** para atingir a renda desejada na aposentadoria, em uma aplicação web simples hospedada no Microsoft Azure.

## 2. Escopo

**Dentro do escopo (v1):**
- Simulação de aporte mensal necessário.
- Resultado com gráfico de evolução do patrimônio.
- **Persistência de todas as simulações realizadas em banco de dados.**
- Aplicação web pública, sem cadastro/login.

**Fora do escopo (v1):** login e contas de usuário, histórico por usuário na interface, impostos e inflação por faixa, integração com corretoras, app mobile nativo, recomendação de produtos financeiros.

## 3. Caso de Uso Principal

**UC-01 — Simular aporte mensal para aposentadoria**

| | |
|---|---|
| Ator | Visitante do site |
| Pré-condição | Aplicação disponível |
| Gatilho | Usuário abre a página e preenche o formulário |

**Fluxo principal:**
1. Usuário informa: idade atual, idade de aposentadoria, patrimônio já investido, renda mensal desejada na aposentadoria, expectativa de vida (ou anos de usufruto), taxa de retorno real anual estimada.
2. Usuário clica em "Simular".
3. Sistema calcula o patrimônio-alvo e o **aporte mensal necessário** e exibe em < 1s.
4. Sistema **grava a simulação no banco de dados** (parâmetros de entrada, resultado, timestamp e ID da simulação).
5. Sistema exibe gráfico da evolução do patrimônio até a aposentadoria e o ID da simulação.

**Fluxos alternativos:**
- **A1 — Dados inválidos:** campo vazio, valor negativo ou idade de aposentadoria ≤ idade atual → mensagem de erro no campo, sem chamada ao backend e sem gravação.
- **A2 — Meta já atingida:** patrimônio atual já cobre a meta → sistema informa "aporte mensal necessário: R$ 0", mostra o excedente e grava normalmente.
- **A3 — Falha na gravação:** banco indisponível → resultado é exibido normalmente ao usuário, a falha é registrada em log/telemetria e a simulação entra em fila de reprocessamento (a persistência não bloqueia a resposta).

## 4. Requisitos Funcionais

| ID | Requisito |
|---|---|
| RF-01 | Formulário com os 6 campos do UC-01 e valores padrão sugeridos (ex.: retorno real 4% a.a.). |
| RF-02 | Cálculo do patrimônio-alvo pelo modelo de anuidade: `Alvo = R × [1 − (1+r)^(−n)] / r`, onde `R` = renda mensal desejada, `r` = taxa real mensal, `n` = meses de usufruto. |
| RF-03 | Cálculo do aporte mensal: `A = (Alvo − P₀·(1+i)^m) · i / [(1+i)^m − 1]`, onde `P₀` = patrimônio atual, `i` = taxa real mensal na acumulação, `m` = meses até a aposentadoria. |
| RF-04 | Exibir: aporte mensal necessário, patrimônio-alvo, total aportado e total de rendimentos. |
| RF-05 | Gráfico de evolução anual do patrimônio (aportes vs. rendimentos). |
| RF-06 | Validação de entrada no frontend e no backend. |
| RF-07 | API REST `POST /api/simulate` recebendo os parâmetros em JSON e devolvendo o resultado + série anual. |
| RF-08 | Endpoint `GET /health` para health probe (inclui verificação de conectividade com o banco). |
| RF-09 | Persistir **toda** simulação bem-sucedida na tabela `simulacoes`, com ID (UUID), timestamp UTC, parâmetros de entrada, resultados calculados, versão da fórmula e origem (user agent / país via Front Door). |
| RF-10 | Endpoint `GET /api/simulations/{id}` para recuperar uma simulação gravada. |
| RF-11 | Endpoint administrativo `GET /api/simulations?from=&to=` (protegido por chave) para extração agregada das simulações. |
| RF-12 | Valores monetários em BRL, cálculo em termos reais (já descontada a inflação); aviso de que o resultado é uma estimativa, não recomendação de investimento. |

## 5. Requisitos Não Funcionais

| ID | Requisito |
|---|---|
| RNF-01 | Latência do `POST /api/simulate`: p95 < 300 ms sob 100 requisições/s (gravação assíncrona não pode elevar a latência percebida). |
| RNF-02 | Disponibilidade mensal ≥ 99,5%. |
| RNF-03 | Suportar 200 usuários simultâneos com autoscale. |
| RNF-04 | HTTPS obrigatório; sem coleta de dados pessoais identificáveis. |
| RNF-05 | Aplicação stateless; todo estado fica no banco de dados gerenciado. |
| RNF-06 | Deploy automatizado por pipeline (CI/CD) com ambientes `dev` e `prod`. |
| RNF-07 | Banco com backup automático (PITR de 7 dias) e criptografia em repouso e em trânsito. |
| RNF-08 | Sem dados pessoais identificáveis gravados: apenas parâmetros financeiros anônimos, sem nome, e-mail, CPF ou IP completo. |
| RNF-09 | Retenção das simulações: 24 meses, com expurgo automático. |

## 6. Arquitetura e Infraestrutura (Azure)

```
Usuário → Azure Front Door (WAF/CDN/TLS)
            → Azure App Service (Linux, Plano P1v3, autoscale 1–5 instâncias)
                 ├── Frontend (SPA estática)
                 └── API REST (stateless)
                        → Azure SQL Database (Serverless, General Purpose) — tabela `simulacoes`
            → Application Insights + Log Analytics Workspace
Deploy: GitHub Actions → App Service (slot de staging → swap para produção)
IaC: Bicep no repositório
```

| Componente | Serviço Azure | Função |
|---|---|---|
| Hospedagem | App Service (Linux) | Frontend + API |
| Banco de dados | Azure SQL Database (Serverless, auto-pause desabilitado em prod) | Persistência das simulações |
| Escala | Autoscale rules do App Service Plan | 1–5 instâncias, gatilho CPU > 70% |
| Borda | Front Door + WAF | TLS, cache estático, proteção |
| Segredos/config | App Configuration + Key Vault | Parâmetros e chaves |
| Observabilidade | Application Insights + Log Analytics | Métricas, logs, traces |
| Alertas | Azure Monitor Alerts | Notificação por e-mail/Teams |
| Provisionamento | Bicep + GitHub Actions | IaC e CI/CD |

Acesso ao banco via **Managed Identity** do App Service (sem senha na aplicação), com firewall restrito a serviços Azure/Private Endpoint.

**Modelo de dados — tabela `simulacoes`:**

| Coluna | Tipo | Descrição |
|---|---|---|
| `id` | UNIQUEIDENTIFIER (PK) | ID da simulação |
| `criado_em` | DATETIME2 (UTC) | Momento da simulação |
| `idade_atual`, `idade_aposentadoria`, `anos_usufruto` | INT | Entradas |
| `patrimonio_atual`, `renda_desejada` | DECIMAL(18,2) | Entradas |
| `taxa_retorno_real` | DECIMAL(6,4) | Entrada |
| `aporte_mensal`, `patrimonio_alvo`, `total_aportado`, `total_rendimentos` | DECIMAL(18,2) | Resultados |
| `versao_formula` | VARCHAR(10) | Versão do cálculo |
| `origem_pais`, `origem_dispositivo` | VARCHAR(50) | Contexto anônimo |

Índice em `criado_em` para consultas por período.

Ambientes: `dev` (1 instância, plano B1) e `prod` (autoscale). Região primária: `centralus` (resource group `rgdevin`).

## 7. Procedimento de Teste de Carga

**Ferramenta:** Azure Load Testing (motor Apache JMeter/Locust gerenciado), executado contra o ambiente `dev` ou o slot de staging — nunca contra produção com tráfego real.

**Cenário:** 90% das requisições em `POST /api/simulate` com payloads variados (idades e valores aleatórios dentro das faixas válidas — cada uma gera uma gravação no banco) e 10% em `GET /` (página inicial).

**Perfil de execução:**

| Fase | Carga | Duração |
|---|---|---|
| Ramp-up | 0 → 100 usuários virtuais | 2 min |
| Sustentação | 100 usuários virtuais | 10 min |
| Pico | 100 → 300 usuários virtuais | 3 min |
| Ramp-down | 300 → 0 | 1 min |

**Passos:**
1. Provisionar/atualizar o ambiente alvo pela pipeline e confirmar `GET /health` = 200.
2. Criar o recurso de Azure Load Testing no `rgdevin` e subir o script de teste + arquivo de parâmetros.
3. Vincular a App Service e o Application Insights como *app components* para correlacionar métricas de servidor.
4. Executar o teste e acompanhar em tempo real (RPS, latência, erros, CPU/memória).
5. Comparar contra os critérios de aprovação abaixo.
6. Verificar no banco que o número de linhas gravadas em `simulacoes` corresponde ao número de requisições bem-sucedidas (tolerância de 0%).
7. Limpar os dados de teste do banco do ambiente de teste ao final da execução.
8. Registrar o resultado como baseline e rodar o teste a cada release na pipeline (falha da pipeline se os critérios não forem atendidos).

**Critérios de aprovação:**
- p95 de latência < 300 ms na fase de sustentação; < 800 ms no pico.
- Taxa de erro < 1%.
- CPU média das instâncias < 80%.
- Uso de DTU/vCore do Azure SQL < 80% e sem erros de conexão/timeout.
- 100% das simulações bem-sucedidas persistidas no banco.
- Autoscale adiciona instâncias durante o pico e retorna ao mínimo após o ramp-down.

## 8. Monitoramento em Tempo Real

**Aplicação (Application Insights):**
- Live Metrics Stream para acompanhamento em tempo real (RPS, latência, falhas, CPU/memória por instância).
- Telemetria de requisições, exceções e dependências habilitada por padrão.
- Availability test (ping em `GET /health` a cada 5 min, de 3 regiões).

**Infraestrutura (Azure Monitor):**
- Métricas de plataforma do App Service Plan e do Front Door (CPU, memória, fila HTTP, códigos 5xx, tráfego).
- Métricas do Azure SQL: uso de vCore/DTU, sessões ativas, deadlocks, latência e falhas de conexão, espaço utilizado.
- Logs centralizados no Log Analytics Workspace, com retenção de 30 dias.

**Dashboard:** painel único no Azure Portal (compartilhado com o time) com RPS, latência p50/p95, taxa de erro, CPU/memória, instâncias ativas, disponibilidade, uso do banco e simulações gravadas por minuto.

**Alertas (Azure Monitor Alerts → e-mail/Teams):**

| Alerta | Condição | Severidade |
|---|---|---|
| Latência alta | p95 de `/api/simulate` > 1 s por 5 min | Sev 2 |
| Erros de servidor | taxa de 5xx > 1% por 5 min | Sev 1 |
| Indisponibilidade | availability test falhando em 2 regiões | Sev 1 |
| CPU alta | CPU média > 85% por 10 min | Sev 3 |
| Falha de gravação | erros de escrita no banco > 0 em 5 min | Sev 1 |
| Banco sobrecarregado | uso de vCore/DTU > 85% por 10 min | Sev 2 |
| Espaço do banco | > 80% da capacidade alocada | Sev 3 |
| Escala no limite | instâncias no máximo por 15 min | Sev 3 |

## 9. Métricas de Sucesso

- ≥ 80% das simulações iniciadas são concluídas com resultado exibido.
- 100% das simulações concluídas gravadas no banco de dados.
- p95 de latência da API < 300 ms em produção.
- Disponibilidade mensal ≥ 99,5%.
- Zero incidentes Sev 1 não detectados por alerta (todo incidente detectado antes de reporte de usuário).

## 10. Premissas e Riscos

- Cálculo em **termos reais**: a taxa informada já desconta a inflação; não há projeção tributária.
- As simulações são gravadas de forma **anônima**; nenhum dado pessoal identificável é coletado, o que mantém o escopo de LGPD mínimo. Se no futuro houver identificação do usuário, é necessária revisão de LGPD (base legal, consentimento e direito de exclusão).
- Risco: crescimento do volume de gravações em picos pode gargalar o banco — mitigado por gravação assíncrona, autoscale do Azure SQL Serverless e alerta de uso de vCore.
- Custo do plano P1v3 + Front Door + Azure SQL deve ser validado contra o orçamento da subscription antes do go-live.
- Front Door pode ser dispensado na v1 se o custo for restritivo (perde-se WAF e cache de borda).
