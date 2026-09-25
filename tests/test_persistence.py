from datetime import datetime, timedelta, timezone

from app import db
from app.config import Settings
from app.persistence import GravadorAssincrono


def _registro(idx: int = 0, criado_em: datetime | None = None) -> dict:
    return {
        "id": f"00000000-0000-0000-0000-{idx:012d}",
        "criado_em": criado_em or datetime.now(timezone.utc).replace(tzinfo=None),
        "idade_atual": 35,
        "idade_aposentadoria": 65,
        "anos_usufruto": 25,
        "patrimonio_atual": 50000,
        "renda_desejada": 8000,
        "taxa_retorno_real": 0.04,
        "aporte_mensal": 1000,
        "patrimonio_alvo": 1_500_000,
        "total_aportado": 360_000,
        "total_rendimentos": 1_090_000,
        "versao_formula": "1.0.0",
        "origem_pais": "BR",
        "origem_dispositivo": "desktop",
    }


def _engine(tmp_path):
    engine = db.criar_engine(
        Settings(
            database_url=f"sqlite:///{tmp_path/'p.db'}",
            admin_api_key=None,
            retencao_meses=24,
            ambiente="test",
        )
    )
    db.criar_schema(engine)
    return engine


def test_gravacao_assincrona_persiste(tmp_path):
    engine = _engine(tmp_path)
    gravador = GravadorAssincrono(engine, db.inserir)
    gravador.iniciar()
    try:
        for i in range(20):
            assert gravador.enfileirar(_registro(i))
        gravador.drenar()
    finally:
        gravador.parar()
    assert gravador.gravadas == 20
    assert len(db.listar(engine, None, None)) == 20


def test_falha_de_gravacao_nao_derruba_e_reprocessa(tmp_path):
    engine = _engine(tmp_path)
    tentativas = {"n": 0}

    def inserir_instavel(eng, registro):
        tentativas["n"] += 1
        if tentativas["n"] == 1:
            raise RuntimeError("banco indisponível")
        db.inserir(eng, registro)

    gravador = GravadorAssincrono(engine, inserir_instavel, intervalo_retry_s=0.05)
    gravador.iniciar()
    try:
        gravador.enfileirar(_registro(1))
        deadline = 5.0
        import time

        inicio = time.monotonic()
        while gravador.gravadas == 0 and time.monotonic() - inicio < deadline:
            time.sleep(0.05)
    finally:
        gravador.parar()

    assert gravador.gravadas == 1
    assert len(db.listar(engine, None, None)) == 1


def test_expurgo_remove_fora_da_retencao(tmp_path):
    engine = _engine(tmp_path)
    antigo = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=800)
    db.inserir(engine, _registro(1, antigo))
    db.inserir(engine, _registro(2))

    assert db.expurgar(engine, 24) == 1
    assert len(db.listar(engine, None, None)) == 1
