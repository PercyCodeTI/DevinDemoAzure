"""Chatbot de recomendações financeiras sobre o Azure AI Foundry (modelo GPT)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from openai import AzureOpenAI

from app.schemas import ChatMensagem, ContextoSimulacao

API_VERSION = "2024-10-21"

INSTRUCOES = """Você é um assistente de educação financeira do Simulador de Aporte para
Aposentadoria. Responda em português do Brasil, em no máximo 180 palavras, com tom direto e
didático.

Regras:
- Baseie as recomendações nos números da simulação do usuário, citando-os quando ajudar.
- Dê sugestões práticas e gerais (taxa de poupança, prazo, diversificação, reserva de
  emergência, previdência, revisão periódica), nunca recomendação de ativo específico,
  corretora, criptoativo ou promessa de retorno.
- Se o aporte necessário parecer inviável frente a rendas típicas, aponte alternativas:
  adiar a aposentadoria, reduzir a renda desejada, aumentar a taxa real assumida com mais
  risco (explicando o trade-off) ou aumentar o patrimônio inicial.
- Se perguntarem algo fora de finanças pessoais/aposentadoria, recuse brevemente.
- Encerre sempre lembrando que é conteúdo educacional e não recomendação de investimento.
"""


class ChatIndisponivelError(RuntimeError):
    """O chatbot não está configurado (sem endpoint do Foundry)."""


@dataclass(frozen=True)
class ChatConfig:
    endpoint: str
    deployment: str

    @property
    def habilitado(self) -> bool:
        return bool(self.endpoint and self.deployment)


def get_chat_config() -> ChatConfig:
    return ChatConfig(
        endpoint=os.getenv("AZURE_AI_ENDPOINT", ""),
        deployment=os.getenv("AZURE_AI_DEPLOYMENT", "gpt-4o-mini"),
    )


@lru_cache(maxsize=1)
def _cliente(endpoint: str) -> AzureOpenAI:
    """Cliente autenticado por Managed Identity (sem chave de API)."""
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider

    credential = DefaultAzureCredential(
        managed_identity_client_id=os.getenv("SQL_MI_CLIENT_ID") or None
    )
    token_provider = get_bearer_token_provider(
        credential, "https://cognitiveservices.azure.com/.default"
    )
    return AzureOpenAI(
        azure_endpoint=endpoint,
        azure_ad_token_provider=token_provider,
        api_version=API_VERSION,
    )


def _brl(valor: float) -> str:
    inteiro, centavos = f"{valor:,.2f}".split(".")
    return f"R$ {inteiro.replace(',', '.')},{centavos}"


def _resumo_simulacao(ctx: ContextoSimulacao) -> str:
    anos = ctx.idade_aposentadoria - ctx.idade_atual
    linhas = [
        f"Idade atual: {ctx.idade_atual} anos (faltam {anos} anos para a aposentadoria)",
        f"Idade de aposentadoria: {ctx.idade_aposentadoria} anos",
        f"Anos de usufruto planejados: {ctx.anos_usufruto}",
        f"Patrimônio atual: {_brl(ctx.patrimonio_atual)}",
        f"Renda mensal desejada na aposentadoria: {_brl(ctx.renda_desejada)}",
        f"Taxa de retorno real anual assumida: {ctx.taxa_retorno_real:.2%}",
        f"Patrimônio-alvo calculado: {_brl(ctx.patrimonio_alvo)}",
        f"Aporte mensal necessário: {_brl(ctx.aporte_mensal)}",
        f"Total a aportar: {_brl(ctx.total_aportado)}",
        f"Rendimentos projetados: {_brl(ctx.total_rendimentos)}",
    ]
    if ctx.meta_ja_atingida:
        linhas.append(
            f"A meta já está atingida com o patrimônio atual (excedente de {_brl(ctx.excedente)})"
        )
    return "\n".join(linhas)


def responder(
    pergunta: str,
    contexto: ContextoSimulacao,
    historico: list[ChatMensagem],
    config: ChatConfig,
) -> str:
    """Gera a resposta do modelo GPT para a pergunta do usuário."""
    if not config.habilitado:
        raise ChatIndisponivelError("AZURE_AI_ENDPOINT não configurado")

    mensagens: list[dict[str, str]] = [
        {"role": "system", "content": INSTRUCOES},
        {
            "role": "system",
            "content": "Dados da simulação do usuário:\n" + _resumo_simulacao(contexto),
        },
    ]
    # Só as últimas trocas entram no prompt: contexto suficiente e custo previsível.
    for m in historico[-6:]:
        mensagens.append({"role": m.papel, "content": m.conteudo})
    mensagens.append({"role": "user", "content": pergunta})

    resposta = _cliente(config.endpoint).chat.completions.create(
        model=config.deployment,
        messages=mensagens,
        temperature=0.3,
        max_tokens=500,
    )
    return (resposta.choices[0].message.content or "").strip()
