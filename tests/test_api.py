PAYLOAD = {
    "idade_atual": 35,
    "idade_aposentadoria": 65,
    "patrimonio_atual": 50000,
    "renda_desejada": 8000,
    "anos_usufruto": 25,
    "taxa_retorno_real": 0.04,
}


def _drenar(client):
    client.app.state.gravador.drenar()


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["banco"] == "ok"


def test_simular_retorna_resultado_e_serie(client):
    r = client.post("/api/simulate", json=PAYLOAD)
    assert r.status_code == 200
    body = r.json()
    assert body["aporte_mensal"] > 0
    assert body["patrimonio_alvo"] > 0
    assert body["moeda"] == "BRL"
    assert "estimativa" in body["aviso"].lower()
    assert len(body["evolucao"]) == 31


def test_simulacao_e_persistida_e_recuperavel(client):
    simulacao_id = client.post("/api/simulate", json=PAYLOAD).json()["id"]
    _drenar(client)

    r = client.get(f"/api/simulations/{simulacao_id}")
    assert r.status_code == 200
    registro = r.json()
    assert registro["id"] == simulacao_id
    assert registro["idade_atual"] == 35
    assert registro["versao_formula"]
    assert registro["origem_dispositivo"]


def test_simulacao_inexistente_retorna_404(client):
    assert client.get("/api/simulations/00000000-0000-0000-0000-000000000000").status_code == 404


def test_validacao_idade_aposentadoria(client):
    payload = {**PAYLOAD, "idade_aposentadoria": 30}
    assert client.post("/api/simulate", json=payload).status_code == 422


def test_validacao_valores_negativos(client):
    assert client.post("/api/simulate", json={**PAYLOAD, "patrimonio_atual": -1}).status_code == 422
    assert client.post("/api/simulate", json={**PAYLOAD, "renda_desejada": 0}).status_code == 422


def test_meta_ja_atingida(client):
    r = client.post(
        "/api/simulate",
        json={**PAYLOAD, "patrimonio_atual": 5_000_000, "renda_desejada": 3000},
    )
    body = r.json()
    assert body["aporte_mensal"] == 0
    assert body["meta_ja_atingida"] is True
    assert body["excedente"] > 0
    _drenar(client)
    assert client.get(f"/api/simulations/{body['id']}").status_code == 200


def test_listagem_admin_exige_chave(client):
    client.post("/api/simulate", json=PAYLOAD)
    _drenar(client)

    assert client.get("/api/simulations").status_code == 401
    assert client.get("/api/simulations", headers={"X-API-Key": "errada"}).status_code == 401

    r = client.get("/api/simulations", headers={"X-API-Key": "chave-de-teste"})
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_listagem_admin_filtra_periodo(client):
    client.post("/api/simulate", json=PAYLOAD)
    _drenar(client)
    headers = {"X-API-Key": "chave-de-teste"}

    vazio = client.get("/api/simulations?from=2000-01-01T00:00:00&to=2000-01-02T00:00:00", headers=headers)
    assert vazio.json() == []

    cheio = client.get("/api/simulations?from=2000-01-01T00:00:00", headers=headers)
    assert len(cheio.json()) == 1


def test_purge_exige_chave(client):
    assert client.post("/api/admin/purge").status_code == 401
    r = client.post("/api/admin/purge", headers={"X-API-Key": "chave-de-teste"})
    assert r.status_code == 200
    assert r.json() == {"removidas": 0}


def test_spa_servida_na_raiz(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Simulador de Aporte" in r.text
