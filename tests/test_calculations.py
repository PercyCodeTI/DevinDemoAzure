import pytest

from app import calculations


def test_taxa_mensal_equivalente():
    i = calculations.taxa_mensal(0.04)
    assert pytest.approx((1 + i) ** 12 - 1, rel=1e-12) == 0.04


def test_patrimonio_alvo_anuidade():
    alvo = calculations.patrimonio_alvo(8000, 0.04, 25)
    r = calculations.taxa_mensal(0.04)
    esperado = 8000 * (1 - (1 + r) ** (-300)) / r
    assert alvo == pytest.approx(esperado)


def test_patrimonio_alvo_taxa_zero():
    assert calculations.patrimonio_alvo(1000, 0.0, 10) == pytest.approx(120000)


def test_aporte_atinge_o_alvo():
    resultado = calculations.simular(
        idade_atual=35,
        idade_aposentadoria=65,
        patrimonio_atual=50000,
        renda_desejada=8000,
        anos_usufruto=25,
        taxa_retorno_real=0.04,
    )
    patrimonio_final = resultado.evolucao[-1].patrimonio
    assert patrimonio_final == pytest.approx(resultado.patrimonio_alvo, rel=1e-6)
    assert resultado.aporte_mensal > 0
    assert not resultado.meta_ja_atingida


def test_meta_ja_atingida_gera_aporte_zero_e_excedente():
    resultado = calculations.simular(
        idade_atual=50,
        idade_aposentadoria=65,
        patrimonio_atual=5_000_000,
        renda_desejada=3000,
        anos_usufruto=20,
        taxa_retorno_real=0.04,
    )
    assert resultado.aporte_mensal == 0.0
    assert resultado.meta_ja_atingida
    assert resultado.excedente > 0


def test_evolucao_tem_um_ponto_por_ano():
    resultado = calculations.simular(
        idade_atual=40,
        idade_aposentadoria=60,
        patrimonio_atual=0,
        renda_desejada=5000,
        anos_usufruto=20,
        taxa_retorno_real=0.05,
    )
    assert len(resultado.evolucao) == 21
    assert resultado.evolucao[0].idade == 40
    assert resultado.evolucao[-1].idade == 60
    assert resultado.evolucao[-1].total_rendimentos > 0


def test_totais_coerentes():
    resultado = calculations.simular(
        idade_atual=30,
        idade_aposentadoria=60,
        patrimonio_atual=10000,
        renda_desejada=6000,
        anos_usufruto=30,
        taxa_retorno_real=0.04,
    )
    final = resultado.evolucao[-1]
    assert final.total_aportado == pytest.approx(
        resultado.total_aportado + 10000, rel=1e-6
    )
    assert resultado.total_rendimentos == pytest.approx(
        final.patrimonio - final.total_aportado, rel=1e-6
    )


def test_taxa_zero_nao_divide_por_zero():
    resultado = calculations.simular(
        idade_atual=30,
        idade_aposentadoria=60,
        patrimonio_atual=0,
        renda_desejada=1000,
        anos_usufruto=10,
        taxa_retorno_real=0.0,
    )
    assert resultado.patrimonio_alvo == pytest.approx(120000)
    assert resultado.aporte_mensal == pytest.approx(120000 / 360, abs=0.01)
