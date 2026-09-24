"""API do Simulador de Aporte para Aposentadoria."""

from __future__ import annotations

import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app import calculations, db
from app.config import get_settings
from app.persistence import GravadorAssincrono
from app.schemas import (
    HealthResponse,
    SimulacaoRegistro,
    SimulacaoRequest,
    SimulacaoResponse,
)

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("simulador")

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    engine = db.criar_engine(settings)
    try:
        db.criar_schema(engine)
    except Exception:  # noqa: BLE001 - app sobe mesmo com banco indisponível (A3)
        logger.exception("falha_criar_schema")
    gravador = GravadorAssincrono(engine, db.inserir)
    gravador.iniciar()
    app.state.settings = settings
    app.state.engine = engine
    app.state.gravador = gravador
    try:
        yield
    finally:
        gravador.parar()
        engine.dispose()


app = FastAPI(
    title="Simulador de Aporte para Aposentadoria",
    version="1.1.0",
    lifespan=lifespan,
)


def _configurar_telemetria() -> None:
    """Application Insights (opcional, ativado pela connection string no App Service)."""
    if not os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING"):
        return
    try:
        from azure.monitor.opentelemetry import configure_azure_monitor

        configure_azure_monitor()
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
    except Exception:  # noqa: BLE001 - telemetria nunca derruba a aplicação
        logger.exception("falha_configurar_telemetria")


_configurar_telemetria()


def get_engine(request: Request):
    return request.app.state.engine


def get_gravador(request: Request) -> GravadorAssincrono:
    return request.app.state.gravador


def _dispositivo(user_agent: str | None) -> str:
    ua = (user_agent or "").lower()
    if "mobile" in ua or "android" in ua or "iphone" in ua:
        return "mobile"
    if "tablet" in ua or "ipad" in ua:
        return "tablet"
    if ua:
        return "desktop"
    return "desconhecido"


@app.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    engine = request.app.state.engine
    banco_ok = db.verificar_conexao(engine)
    return HealthResponse(
        status="ok" if banco_ok else "degraded",
        banco="ok" if banco_ok else "indisponivel",
        ambiente=request.app.state.settings.ambiente,
        fila_pendente=request.app.state.gravador.pendentes,
    )


@app.post("/api/simulate", response_model=SimulacaoResponse)
def simular(
    payload: SimulacaoRequest,
    request: Request,
    gravador: GravadorAssincrono = Depends(get_gravador),
    user_agent: str | None = Header(default=None),
) -> SimulacaoResponse:
    resultado = calculations.simular(
        idade_atual=payload.idade_atual,
        idade_aposentadoria=payload.idade_aposentadoria,
        patrimonio_atual=payload.patrimonio_atual,
        renda_desejada=payload.renda_desejada,
        anos_usufruto=payload.anos_usufruto,
        taxa_retorno_real=payload.taxa_retorno_real,
    )

    simulacao_id = str(uuid.uuid4())
    criado_em = datetime.now(timezone.utc).replace(tzinfo=None)

    # Contexto anônimo: país informado pelo Front Door, sem IP nem dado pessoal (RNF-08).
    gravador.enfileirar(
        {
            "id": simulacao_id,
            "criado_em": criado_em,
            "idade_atual": payload.idade_atual,
            "idade_aposentadoria": payload.idade_aposentadoria,
            "anos_usufruto": payload.anos_usufruto,
            "patrimonio_atual": payload.patrimonio_atual,
            "renda_desejada": payload.renda_desejada,
            "taxa_retorno_real": payload.taxa_retorno_real,
            "aporte_mensal": resultado.aporte_mensal,
            "patrimonio_alvo": resultado.patrimonio_alvo,
            "total_aportado": resultado.total_aportado,
            "total_rendimentos": resultado.total_rendimentos,
            "versao_formula": resultado.versao_formula,
            "origem_pais": request.headers.get("X-Azure-ClientIP-Country")
            or request.headers.get("X-Country"),
            "origem_dispositivo": _dispositivo(user_agent),
        }
    )

    return SimulacaoResponse(
        id=simulacao_id,
        criado_em=criado_em,
        aporte_mensal=resultado.aporte_mensal,
        patrimonio_alvo=resultado.patrimonio_alvo,
        total_aportado=resultado.total_aportado,
        total_rendimentos=resultado.total_rendimentos,
        excedente=resultado.excedente,
        meta_ja_atingida=resultado.meta_ja_atingida,
        versao_formula=resultado.versao_formula,
        evolucao=[p.__dict__ for p in resultado.evolucao],
    )


@app.get("/api/simulations/{simulacao_id}", response_model=SimulacaoRegistro)
def obter_simulacao(simulacao_id: str, request: Request) -> SimulacaoRegistro:
    registro = db.buscar(request.app.state.engine, simulacao_id)
    if registro is None:
        raise HTTPException(status_code=404, detail="Simulação não encontrada")
    return SimulacaoRegistro(**registro)


def _autorizar_admin(request: Request, chave: str | None) -> None:
    esperada = request.app.state.settings.admin_api_key
    if not esperada or chave != esperada:
        raise HTTPException(status_code=401, detail="Chave administrativa inválida")


@app.get("/api/simulations", response_model=list[SimulacaoRegistro])
def listar_simulacoes(
    request: Request,
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
    limite: int = Query(default=1000, ge=1, le=5000),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> list[SimulacaoRegistro]:
    _autorizar_admin(request, x_api_key)
    registros = db.listar(request.app.state.engine, from_, to, limite)
    return [SimulacaoRegistro(**r) for r in registros]


@app.get("/api/admin/simulations/count")
def contar_simulacoes(
    request: Request,
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict:
    """Contagem por janela, usada para conferir a persistência no teste de carga."""
    _autorizar_admin(request, x_api_key)
    return {"total": db.contar(request.app.state.engine, from_, to)}


@app.delete("/api/admin/simulations")
def remover_simulacoes(
    request: Request,
    from_: datetime = Query(alias="from"),
    to: datetime = Query(),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict:
    """Limpeza dos dados gerados por teste de carga em uma janela conhecida."""
    _autorizar_admin(request, x_api_key)
    removidas = db.remover_intervalo(request.app.state.engine, from_, to)
    return {"removidas": removidas}


@app.post("/api/admin/purge")
def expurgar(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict:
    """Expurgo da janela de retenção (RNF-09), acionável por job agendado."""
    _autorizar_admin(request, x_api_key)
    removidas = db.expurgar(
        request.app.state.engine, request.app.state.settings.retencao_meses
    )
    return {"removidas": removidas}


@app.exception_handler(ValueError)
def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content={"detail": str(exc)}
    )


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
