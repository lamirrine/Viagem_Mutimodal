"""Visualização do estado e da solução"""
from __future__ import annotations

from dominio import hhmm
from problema import caminho


def mostrar_estado(p, s) -> str:
    nome = p.rede.nomes[s.parag]
    linha = p.rede.linhas[s.linha].nome if s.linha != -1 else "-"
    bordo = "a bordo" if s.a_bordo else "na paragem/a pé"
    return (f"[{hhmm(s.t)}] {nome} ({bordo}) | linha: {linha} | gasto: {s.gasto} MT "
            f"| transbordos: {s.transb}")


def mostrar_solucao(p, resultado) -> str:
    """Solução passo a passo (ASCII)."""
    if not resultado.ok:
        return f"Sem solução ({resultado.estado})."
    passos = caminho(resultado.no)
    out = [f"Origem: {p.rede.nomes[p.origem]}  ->  Destino: {p.rede.nomes[p.destino]}",
           f"Partida {hhmm(p.t0)}, hora-limite {hhmm(p.limite)}, orçamento {p.orcamento} MT, "
           f"alfa={p.alfa}, beta={p.beta}", "-" * 78]
    for i in range(1, len(passos)):
        a, s2 = passos[i]
        s = passos[i - 1][1]
        out.append(f"{i:2d}. {p.descrever(s, a, s2)}   (g={resultado_g(passos, i, p):.1f})")
    s = passos[-1][1]
    out += ["-" * 78, f"Chegada {hhmm(s.t)} | tempo total {s.t - p.t0} min | gasto {s.gasto} MT "
            f"| transbordos {s.transb} | custo generalizado {resultado.custo:.2f}"]
    return "\n".join(out)


def resultado_g(passos, i, p) -> float:
    g = 0.0
    for k in range(1, i + 1):
        g += p.custo(passos[k - 1][1], passos[k][0], passos[k][1])
    return g


def mapa_ascii(p, resultado, largura=60, altura=22) -> str:
    """Mapa ASCII: paragens como pontos, percurso marcado com números/letras."""
    r = p.rede
    ids = r.activas
    lats = [r.todas[i]["lat"] for i in ids]
    lons = [r.todas[i]["lon"] for i in ids]
    la0, la1, lo0, lo1 = min(lats), max(lats), min(lons), max(lons)
    grelha = [[" "] * largura for _ in range(altura)]

    def pos(i):
        y = int((la1 - r.todas[i]["lat"]) / max(la1 - la0, 1e-9) * (altura - 1))
        x = int((r.todas[i]["lon"] - lo0) / max(lo1 - lo0, 1e-9) * (largura - 1))
        return y, x
    for i in ids:
        y, x = pos(i)
        grelha[y][x] = "."
    if resultado.ok:
        seq = []
        for _, s in caminho(resultado.no):
            if not seq or seq[-1] != s.parag:
                seq.append(s.parag)
        for k, i in enumerate(seq):
            y, x = pos(i)
            grelha[y][x] = "O" if k == 0 else ("D" if k == len(seq) - 1 else "*")
    return "\n".join("".join(l) for l in grelha) + "\n(O origem, * paragens do percurso, D destino, . outras)"


def mapa_matplotlib(p, resultado, ficheiro=None):
    import matplotlib.pyplot as plt
    r = p.rede
    fig, ax = plt.subplots(figsize=(7, 7))
    for i in r.activas:
        d = r.todas[i]
        ax.plot(d["lon"], d["lat"], "o", color="lightgray")
        ax.annotate(d["nome"], (d["lon"], d["lat"]), fontsize=6)
    if resultado.ok:
        seq = [s.parag for _, s in caminho(resultado.no)]
        xs = [r.todas[i]["lon"] for i in seq]
        ys = [r.todas[i]["lat"] for i in seq]
        ax.plot(xs, ys, "-r", linewidth=2)
        ax.plot(xs[0], ys[0], "go", markersize=9)
        ax.plot(xs[-1], ys[-1], "bs", markersize=9)
    ax.set_title("Percurso encontrado")
    if ficheiro:
        fig.savefig(ficheiro, dpi=150)
    else:
        plt.show()
    plt.close(fig)
