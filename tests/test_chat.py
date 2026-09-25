"""Testes do chatbot de recomendações (sem chamar o modelo real)."""

from __future__ import annotations

import pytest

from app import chat
from app.schemas import ChatMensagem, ContextoSimulacao

CONTEXTO = {
    "idade_atual": 35,
    "idade_aposentadoria": 65,
    "anos_usufruto": 25,
    "patrimonio_atual": 50000.0,
    "renda_desejada": 8000.0,
    "taxa_retorno_real": 0.04,
    "aporte_mensal": 3210.5,
    "patrimonio_alvo": 1500000.0,
    "total_aportado": 1155780.0,
    "total_rendimentos": 294220.0,
    "excedente": 0.0,
    "meta_ja_atingida": False,
}


def test_status_desabilitado_sem_endpoint(client, monkeypatch):
    monkeypatch.delenv("AZURE_AI_ENDPOINT", raising=False)
    r = client.get("/api/chat/status")
    assert r.status_code == 200
    assert r.json()["habilitado"] is False


def test_chat_retorna_503_sem_configuracao(client, monkeypatch):
    monkeypatch.delenv("AZURE_AI_ENDPOINT", raising=False)
    r = client.post("/api/chat", json={"pergunta": "Como reduzir o aporte?", "contexto": CONTEXTO})
    assert r.status_code == 503


def test_chat_usa_modelo_e_contexto(client, monkeypatch):
    capturado: dict[str, object] = {}

    def fake_responder(pergunta, contexto, historico, config):
        capturado["pergunta"] = pergunta
        capturado["aporte"] = contexto.aporte_mensal
        capturado["historico"] = len(historico)
        capturado["deployment"] = config.deployment
        return "Reduza a renda desejada ou adie a aposentadoria."

    monkeypatch.setenv("AZURE_AI_ENDPOINT", "https://exemplo.openai.azure.com/")
    monkeypatch.setenv("AZURE_AI_DEPLOYMENT", "gpt-4o-mini")
    monkeypatch.setattr(chat, "responder", fake_responder)

    assert client.get("/api/chat/status").json() == {
        "habilitado": True,
        "modelo": "gpt-4o-mini",
    }

    r = client.post(
        "/api/chat",
        json={
            "pergunta": "Como reduzir o aporte?",
            "contexto": CONTEXTO,
            "historico": [{"papel": "user", "conteudo": "oi"}],
        },
    )
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["resposta"].startswith("Reduza")
    assert corpo["modelo"] == "gpt-4o-mini"
    assert "recomendação de investimento" in corpo["aviso"]
    assert capturado == {
        "pergunta": "Como reduzir o aporte?",
        "aporte": 3210.5,
        "historico": 1,
        "deployment": "gpt-4o-mini",
    }


def test_chat_falha_do_modelo_vira_502(client, monkeypatch):
    def explode(*_args, **_kwargs):
        raise RuntimeError("timeout no modelo")

    monkeypatch.setenv("AZURE_AI_ENDPOINT", "https://exemplo.openai.azure.com/")
    monkeypatch.setattr(chat, "responder", explode)

    r = client.post("/api/chat", json={"pergunta": "E agora?", "contexto": CONTEXTO})
    assert r.status_code == 502
    assert "timeout" not in r.json()["detail"]


def test_chat_valida_pergunta(client, monkeypatch):
    monkeypatch.setenv("AZURE_AI_ENDPOINT", "https://exemplo.openai.azure.com/")
    r = client.post("/api/chat", json={"pergunta": "?", "contexto": CONTEXTO})
    assert r.status_code == 422


def test_responder_monta_prompt_com_numeros_e_historico(monkeypatch):
    enviado: dict[str, object] = {}

    class FakeCompletions:
        def create(self, **kwargs):
            enviado.update(kwargs)

            class Msg:
                content = " Resposta do modelo "

            class Escolha:
                message = Msg()

            class Resposta:
                choices = [Escolha()]

            return Resposta()

    class FakeCliente:
        chat = type("C", (), {"completions": FakeCompletions()})()

    monkeypatch.setattr(chat, "_cliente", lambda _endpoint: FakeCliente())
    config = chat.ChatConfig(endpoint="https://exemplo/", deployment="gpt-4o-mini")

    texto = chat.responder(
        "Posso me aposentar antes?",
        ContextoSimulacao(**CONTEXTO),
        [ChatMensagem(papel="user", conteudo="oi")],
        config,
    )

    assert texto == "Resposta do modelo"
    assert enviado["model"] == "gpt-4o-mini"
    mensagens = enviado["messages"]
    assert mensagens[0]["role"] == "system"
    assert "R$ 3.210,50" in mensagens[1]["content"]
    assert mensagens[-1]["content"] == "Posso me aposentar antes?"


def test_responder_sem_endpoint_levanta_erro():
    with pytest.raises(chat.ChatIndisponivelError):
        chat.responder(
            "oi",
            ContextoSimulacao(**CONTEXTO),
            [],
            chat.ChatConfig(endpoint="", deployment="gpt-4o-mini"),
        )
