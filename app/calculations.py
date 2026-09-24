"""Cálculo financeiro do simulador de aposentadoria (RF-02 a RF-05).

Todos os valores são reais (já descontada a inflação).
"""

from __future__ import annotations

from dataclasses import dataclass, field

VERSAO_FORMULA = "1.0.0"


@dataclass(frozen=True)
class PontoEvolucao:
    ano: int
    idade: int
    patrimonio: float
    total_aportado: float
    total_rendimentos: float


@dataclass(frozen=True)
class ResultadoSimulacao:
    aporte_mensal: float
    patrimonio_alvo: float
    total_aportado: float
    total_rendimentos: float
    excedente: float
    meta_ja_atingida: bool
    versao_formula: str = VERSAO_FORMULA
    evolucao: list[PontoEvolucao] = field(default_factory=list)


def taxa_mensal(taxa_anual: float) -> float:
    """Converte taxa real anual efetiva em taxa real mensal equivalente."""
    return (1.0 + taxa_anual) ** (1.0 / 12.0) - 1.0


def patrimonio_alvo(renda_mensal: float, taxa_anual: float, anos_usufruto: int) -> float:
    """Valor presente de uma anuidade: Alvo = R x [1 - (1+r)^-n] / r."""
    r = taxa_mensal(taxa_anual)
    n = anos_usufruto * 12
    if r == 0:
        return renda_mensal * n
    return renda_mensal * (1.0 - (1.0 + r) ** (-n)) / r


def aporte_mensal(alvo: float, patrimonio_atual: float, taxa_anual: float, meses: int) -> float:
    """A = (Alvo - P0*(1+i)^m) * i / [(1+i)^m - 1], limitado a zero."""
    i = taxa_mensal(taxa_anual)
    futuro_patrimonio_atual = patrimonio_atual * (1.0 + i) ** meses
    faltante = alvo - futuro_patrimonio_atual
    if faltante <= 0:
        return 0.0
    if i == 0:
        return faltante / meses
    return faltante * i / ((1.0 + i) ** meses - 1.0)


def _evolucao(
    patrimonio_atual: float,
    aporte: float,
    taxa_anual: float,
    idade_atual: int,
    meses: int,
) -> list[PontoEvolucao]:
    i = taxa_mensal(taxa_anual)
    patrimonio = patrimonio_atual
    aportado = patrimonio_atual
    pontos = [
        PontoEvolucao(
            ano=0,
            idade=idade_atual,
            patrimonio=round(patrimonio, 2),
            total_aportado=round(aportado, 2),
            total_rendimentos=0.0,
        )
    ]
    for mes in range(1, meses + 1):
        patrimonio = patrimonio * (1.0 + i) + aporte
        aportado += aporte
        if mes % 12 == 0 or mes == meses:
            pontos.append(
                PontoEvolucao(
                    ano=(mes + 11) // 12,
                    idade=idade_atual + (mes + 11) // 12,
                    patrimonio=round(patrimonio, 2),
                    total_aportado=round(aportado, 2),
                    total_rendimentos=round(patrimonio - aportado, 2),
                )
            )
    return pontos


def simular(
    *,
    idade_atual: int,
    idade_aposentadoria: int,
    patrimonio_atual: float,
    renda_desejada: float,
    anos_usufruto: int,
    taxa_retorno_real: float,
) -> ResultadoSimulacao:
    meses_acumulacao = (idade_aposentadoria - idade_atual) * 12
    alvo = patrimonio_alvo(renda_desejada, taxa_retorno_real, anos_usufruto)
    aporte = aporte_mensal(alvo, patrimonio_atual, taxa_retorno_real, meses_acumulacao)

    pontos = _evolucao(
        patrimonio_atual, aporte, taxa_retorno_real, idade_atual, meses_acumulacao
    )
    final = pontos[-1]
    i = taxa_mensal(taxa_retorno_real)
    futuro_patrimonio_atual = patrimonio_atual * (1.0 + i) ** meses_acumulacao
    excedente = max(futuro_patrimonio_atual - alvo, 0.0)

    return ResultadoSimulacao(
        aporte_mensal=round(aporte, 2),
        patrimonio_alvo=round(alvo, 2),
        total_aportado=round(aporte * meses_acumulacao, 2),
        total_rendimentos=round(final.patrimonio - final.total_aportado, 2),
        excedente=round(excedente, 2),
        meta_ja_atingida=aporte == 0.0,
        evolucao=pontos,
    )
