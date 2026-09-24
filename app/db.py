"""Camada de banco de dados: tabela `simulacoes` e utilitários de acesso."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    create_engine,
    delete,
    func,
    select,
    text,
)
from sqlalchemy.engine import Engine

from app.config import Settings

metadata = MetaData()

simulacoes = Table(
    "simulacoes",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("criado_em", DateTime, nullable=False),
    Column("idade_atual", Integer, nullable=False),
    Column("idade_aposentadoria", Integer, nullable=False),
    Column("anos_usufruto", Integer, nullable=False),
    Column("patrimonio_atual", Numeric(18, 2), nullable=False),
    Column("renda_desejada", Numeric(18, 2), nullable=False),
    Column("taxa_retorno_real", Numeric(6, 4), nullable=False),
    Column("aporte_mensal", Numeric(18, 2), nullable=False),
    Column("patrimonio_alvo", Numeric(18, 2), nullable=False),
    Column("total_aportado", Numeric(18, 2), nullable=False),
    Column("total_rendimentos", Numeric(18, 2), nullable=False),
    Column("versao_formula", String(10), nullable=False),
    Column("origem_pais", String(50)),
    Column("origem_dispositivo", String(50)),
    Index("ix_simulacoes_criado_em", "criado_em"),
)


def criar_engine(settings: Settings) -> Engine:
    kwargs: dict[str, object] = {"pool_pre_ping": True, "future": True}
    if settings.usa_mssql:
        kwargs.update(pool_size=10, max_overflow=20, pool_recycle=1800)
    else:
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(settings.database_url, **kwargs)


def criar_schema(engine: Engine) -> None:
    metadata.create_all(engine)


def verificar_conexao(engine: Engine) -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001 - health check não deve propagar erro
        return False


def inserir(engine: Engine, registro: dict) -> None:
    with engine.begin() as conn:
        conn.execute(simulacoes.insert().values(**registro))


def buscar(engine: Engine, simulacao_id: str) -> dict | None:
    with engine.connect() as conn:
        row = conn.execute(
            select(simulacoes).where(simulacoes.c.id == simulacao_id)
        ).mappings().first()
    return dict(row) if row else None


def listar(
    engine: Engine,
    inicio: datetime | None,
    fim: datetime | None,
    limite: int = 1000,
) -> list[dict]:
    stmt = select(simulacoes)
    if inicio is not None:
        stmt = stmt.where(simulacoes.c.criado_em >= inicio)
    if fim is not None:
        stmt = stmt.where(simulacoes.c.criado_em <= fim)
    stmt = stmt.order_by(simulacoes.c.criado_em.desc()).limit(limite)
    with engine.connect() as conn:
        return [dict(row) for row in conn.execute(stmt).mappings()]


def contar(engine: Engine, inicio: datetime | None, fim: datetime | None) -> int:
    stmt = select(func.count()).select_from(simulacoes)
    if inicio is not None:
        stmt = stmt.where(simulacoes.c.criado_em >= inicio)
    if fim is not None:
        stmt = stmt.where(simulacoes.c.criado_em <= fim)
    with engine.connect() as conn:
        return int(conn.execute(stmt).scalar_one())


def remover_intervalo(engine: Engine, inicio: datetime, fim: datetime) -> int:
    """Remove simulações criadas em um intervalo (limpeza pós-teste de carga)."""
    with engine.begin() as conn:
        result = conn.execute(
            delete(simulacoes).where(
                simulacoes.c.criado_em >= inicio, simulacoes.c.criado_em <= fim
            )
        )
    return result.rowcount or 0


def expurgar(engine: Engine, retencao_meses: int) -> int:
    """Expurgo automático das simulações fora da janela de retenção (RNF-09)."""
    limite = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
        days=retencao_meses * 30
    )
    with engine.begin() as conn:
        result = conn.execute(delete(simulacoes).where(simulacoes.c.criado_em < limite))
    return result.rowcount or 0
