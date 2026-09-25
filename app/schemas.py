"""Schemas de entrada e saída da API (RF-06: validação no backend)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class SimulacaoRequest(BaseModel):
    idade_atual: int = Field(ge=18, le=100, description="Idade atual em anos")
    idade_aposentadoria: int = Field(ge=19, le=110)
    patrimonio_atual: float = Field(ge=0, le=1_000_000_000)
    renda_desejada: float = Field(gt=0, le=10_000_000)
    anos_usufruto: int = Field(ge=1, le=60)
    taxa_retorno_real: float = Field(ge=0, le=0.5, description="Taxa real anual, ex.: 0.04")

    @model_validator(mode="after")
    def validar_idades(self) -> "SimulacaoRequest":
        if self.idade_aposentadoria <= self.idade_atual:
            raise ValueError("idade_aposentadoria deve ser maior que idade_atual")
        return self


class PontoEvolucaoOut(BaseModel):
    ano: int
    idade: int
    patrimonio: float
    total_aportado: float
    total_rendimentos: float


class SimulacaoResponse(BaseModel):
    id: str
    criado_em: datetime
    aporte_mensal: float
    patrimonio_alvo: float
    total_aportado: float
    total_rendimentos: float
    excedente: float
    meta_ja_atingida: bool
    versao_formula: str
    moeda: str = "BRL"
    aviso: str = (
        "Estimativa em termos reais (taxa já descontada a inflação). "
        "Não constitui recomendação de investimento."
    )
    evolucao: list[PontoEvolucaoOut]


class SimulacaoRegistro(BaseModel):
    id: str
    criado_em: datetime
    idade_atual: int
    idade_aposentadoria: int
    anos_usufruto: int
    patrimonio_atual: float
    renda_desejada: float
    taxa_retorno_real: float
    aporte_mensal: float
    patrimonio_alvo: float
    total_aportado: float
    total_rendimentos: float
    versao_formula: str
    origem_pais: str | None = None
    origem_dispositivo: str | None = None


class ContextoSimulacao(BaseModel):
    """Números da simulação enviados como contexto para o chatbot."""

    idade_atual: int = Field(ge=18, le=100)
    idade_aposentadoria: int = Field(ge=19, le=110)
    anos_usufruto: int = Field(ge=1, le=60)
    patrimonio_atual: float = Field(ge=0)
    renda_desejada: float = Field(gt=0)
    taxa_retorno_real: float = Field(ge=0, le=0.5)
    aporte_mensal: float = Field(ge=0)
    patrimonio_alvo: float = Field(ge=0)
    total_aportado: float = Field(ge=0)
    total_rendimentos: float = Field(ge=0)
    excedente: float = 0.0
    meta_ja_atingida: bool = False


class ChatMensagem(BaseModel):
    papel: Literal["user", "assistant"]
    conteudo: str = Field(min_length=1, max_length=2000)


class ChatRequest(BaseModel):
    pergunta: str = Field(min_length=3, max_length=500)
    contexto: ContextoSimulacao
    historico: list[ChatMensagem] = Field(default_factory=list, max_length=20)


class ChatResponse(BaseModel):
    resposta: str
    modelo: str
    aviso: str = "Conteúdo educacional. Não constitui recomendação de investimento."


class HealthResponse(BaseModel):
    status: str
    banco: str
    ambiente: str
    fila_pendente: int
