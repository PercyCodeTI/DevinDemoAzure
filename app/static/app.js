const campos = [
  "idade_atual",
  "idade_aposentadoria",
  "patrimonio_atual",
  "renda_desejada",
  "anos_usufruto",
  "taxa_retorno_real",
];

const brl = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  maximumFractionDigits: 2,
});

// Rótulos do eixo Y: forma compacta para caber na margem do gráfico.
const brlCompacto = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  notation: "compact",
  maximumFractionDigits: 1,
});

// Limites espelham os do backend (app/schemas.py).
const limites = {
  idade_atual: { min: 18, max: 100, inteiro: true },
  idade_aposentadoria: { min: 19, max: 110, inteiro: true },
  patrimonio_atual: { min: 0, max: 1_000_000_000, inteiro: false },
  renda_desejada: { min: 0.01, max: 10_000_000, inteiro: false },
  anos_usufruto: { min: 1, max: 60, inteiro: true },
  taxa_retorno_real: { min: 0, max: 50, inteiro: false },
};

function limparErros() {
  document.querySelectorAll(".erro").forEach((e) => (e.textContent = ""));
  document.querySelectorAll("input").forEach((i) => i.classList.remove("invalido"));
  const geral = document.getElementById("erro-geral");
  geral.hidden = true;
  geral.textContent = "";
}

function marcarErro(campo, mensagem) {
  document.querySelector(`[data-erro="${campo}"]`).textContent = mensagem;
  document.getElementById(campo).classList.add("invalido");
}

function lerValores() {
  const v = {};
  campos.forEach((c) => (v[c] = document.getElementById(c).value.trim()));
  return v;
}

// Validação no frontend (RF-06 / A1): sem chamada ao backend se houver erro.
function validar(v) {
  let ok = true;
  campos.forEach((c) => {
    if (v[c] === "") {
      marcarErro(c, "Campo obrigatório");
      ok = false;
    } else if (Number.isNaN(Number(v[c]))) {
      marcarErro(c, "Informe um número válido");
      ok = false;
    } else if (Number(v[c]) < 0) {
      marcarErro(c, "Valor não pode ser negativo");
      ok = false;
    }
  });
  if (!ok) return false;

  campos.forEach((c) => {
    const limite = limites[c];
    const valor = Number(v[c]);
    if (limite.inteiro && !Number.isInteger(valor)) {
      marcarErro(c, "Informe um número inteiro");
      ok = false;
    } else if (valor < limite.min || valor > limite.max) {
      marcarErro(c, `Informe um valor entre ${limite.min} e ${limite.max}`);
      ok = false;
    }
  });
  if (!ok) return false;
  if (Number(v.idade_aposentadoria) <= Number(v.idade_atual)) {
    marcarErro("idade_aposentadoria", "Deve ser maior que a idade atual");
    ok = false;
  }
  return ok;
}

function desenharGrafico(evolucao) {
  const largura = 800;
  const altura = 320;
  const margem = { topo: 16, direita: 16, baixo: 32, esquerda: 104 };
  const areaL = largura - margem.esquerda - margem.direita;
  const areaA = altura - margem.topo - margem.baixo;
  const maxY = Math.max(...evolucao.map((p) => p.patrimonio), 1);
  const n = evolucao.length;
  const passo = areaL / Math.max(n - 1, 1);
  const barra = Math.max(Math.min(passo * 0.6, 28), 3);

  const y = (valor) => margem.topo + areaA - (valor / maxY) * areaA;

  const eixos = [0, 0.25, 0.5, 0.75, 1]
    .map((f) => {
      const valor = maxY * f;
      const py = y(valor);
      return `<line x1="${margem.esquerda}" y1="${py}" x2="${largura - margem.direita}" y2="${py}" stroke="#e2e8f0" />
        <text x="${margem.esquerda - 8}" y="${py + 4}" text-anchor="end" font-size="11" fill="#64748b"><title>${brl.format(
        valor
      )}</title>${brlCompacto.format(valor).replace(/\s/g, " ")}</text>`;
    })
    .join("");

  const barras = evolucao
    .map((p, idx) => {
      const x = margem.esquerda + idx * passo - barra / 2;
      const yAport = y(p.total_aportado);
      const yTotal = y(p.patrimonio);
      const hAport = margem.topo + areaA - yAport;
      const hRend = yAport - yTotal;
      return `<rect x="${x}" y="${yAport}" width="${barra}" height="${Math.max(hAport, 0)}" fill="#93c5fd"><title>Ano ${p.ano} (idade ${p.idade}) — aportado ${brl.format(p.total_aportado)}</title></rect>
        <rect x="${x}" y="${yTotal}" width="${barra}" height="${Math.max(hRend, 0)}" fill="#1d4ed8"><title>Ano ${p.ano} (idade ${p.idade}) — rendimentos ${brl.format(p.total_rendimentos)}</title></rect>`;
    })
    .join("");

  const rotulos = evolucao
    .filter((_, idx) => idx % Math.ceil(n / 8) === 0 || idx === n - 1)
    .map((p) => {
      const idx = evolucao.indexOf(p);
      const x = margem.esquerda + idx * passo;
      return `<text x="${x}" y="${altura - 10}" text-anchor="middle" font-size="11" fill="#64748b">${p.idade}</text>`;
    })
    .join("");

  document.getElementById("grafico").innerHTML = `
    <svg viewBox="0 0 ${largura} ${altura}" role="img" aria-label="Evolução anual do patrimônio">
      ${eixos}${barras}${rotulos}
      <text x="${largura / 2}" y="${altura - 22}" text-anchor="middle" font-size="11" fill="#94a3b8">idade</text>
    </svg>`;
}

async function simular(evento) {
  evento.preventDefault();
  limparErros();
  const v = lerValores();
  if (!validar(v)) return;

  const btn = document.getElementById("btn");
  btn.disabled = true;
  try {
    const resposta = await fetch("/api/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        idade_atual: Number(v.idade_atual),
        idade_aposentadoria: Number(v.idade_aposentadoria),
        patrimonio_atual: Number(v.patrimonio_atual),
        renda_desejada: Number(v.renda_desejada),
        anos_usufruto: Number(v.anos_usufruto),
        taxa_retorno_real: Number(v.taxa_retorno_real) / 100,
      }),
    });

    if (!resposta.ok) {
      const erro = await resposta.json().catch(() => ({}));
      throw new Error(
        typeof erro.detail === "string" ? erro.detail : "Não foi possível simular agora."
      );
    }

    const dados = await resposta.json();
    document.getElementById("aporte").textContent = brl.format(dados.aporte_mensal);
    document.getElementById("alvo").textContent = brl.format(dados.patrimonio_alvo);
    document.getElementById("aportado").textContent = brl.format(dados.total_aportado);
    document.getElementById("rendimentos").textContent = brl.format(dados.total_rendimentos);
    document.getElementById("sim-id").textContent = dados.id;
    document.getElementById("aviso").textContent = dados.aviso;

    const badge = document.getElementById("meta-atingida");
    badge.hidden = !dados.meta_ja_atingida;
    if (dados.meta_ja_atingida) {
      badge.textContent = `Meta já atingida — excedente de ${brl.format(dados.excedente)}`;
    }

    desenharGrafico(dados.evolucao);
    document.getElementById("resultado").hidden = false;
  } catch (erro) {
    const geral = document.getElementById("erro-geral");
    geral.textContent = erro.message;
    geral.hidden = false;
  } finally {
    btn.disabled = false;
  }
}

document.getElementById("form").addEventListener("submit", simular);
