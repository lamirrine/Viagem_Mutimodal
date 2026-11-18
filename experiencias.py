"""Bateria de experiências do P7: (algoritmo, instância) -> métricas, CSV e gráficos."""
from __future__ import annotations

import argparse
import csv
import json
import math
import multiprocessing as mp
import os
import platform
import random
import sys
import time
import tracemalloc
from typing import Dict, List, Optional

import pandas as pd

from buscas import executar
from dominio import (Rede, carregar_dados_rede, hhmm, problema_de_instancia)
from gerador import DIR_INST, SEMENTE, chegada_mais_cedo, escrever_tudo
from heuristicas import b_estrela

DIR = os.path.dirname(os.path.abspath(__file__))
DIR_RES = os.path.join(DIR, "resultados")
NIVEIS = ("pequena", "media", "grande")
LIMITE_MEM = 2 * 1024 ** 3

# (nome, algoritmo, heurística, k)
CONFIGS = [
    ("BFS", "BFS", None, None),
    ("DFS", "DFS", None, None),
    ("IDS", "IDS", None, None),
    ("UCS", "UCS", None, None),
    ("Gulosa h1", "Gulosa", "h1", None),
    ("Gulosa h2", "Gulosa", "h2", None),
    ("A* h0", "A*", "h0", None),
    ("A* h1", "A*", "h1", None),
    ("A* h2", "A*", "h2", None),
    ("Beam k=10", "Beam", "h2", 10),
    ("Beam k=100", "Beam", "h2", 100),
    ("Beam k=1000", "Beam", "h2", 1000),
]
LIMITE_PROF = 40  # profundidade máxima do DFS e do IDS


# ------------------------------------------------------------- execução isolada
def _medir(dados, inst, alg, heur, k, limite_s, medir_mem):
    p = problema_de_instancia(dados, inst)
    r = executar(alg, p, heur=heur, k=k, limite_prof=LIMITE_PROF, limite_s=limite_s)
    out = dict(estado=r.estado, custo=r.custo, comprimento=r.comprimento,
               expandidos=r.metricas.expandidos, gerados=r.metricas.gerados,
               fronteira_max=r.metricas.fronteira_max, reexpandidos=r.metricas.reexpandidos,
               tempo_s=r.tempo_s, memoria_mb=float("nan"))
    if medir_mem and r.estado in ("ok", "sem_solucao", "limite_prof") and r.tempo_s < limite_s / 3:
        p2 = problema_de_instancia(dados, inst)
        tracemalloc.start()
        try:
            executar(alg, p2, heur=heur, k=k, limite_prof=LIMITE_PROF, limite_s=limite_s * 3)
            out["memoria_mb"] = tracemalloc.get_traced_memory()[1] / 1024 ** 2
        finally:
            tracemalloc.stop()
    return out


def _filho(conn, dados, inst, alg, heur, k, limite_s, medir_mem):
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (LIMITE_MEM, LIMITE_MEM))
    except Exception:
        pass
    try:
        out = _medir(dados, inst, alg, heur, k, limite_s, medir_mem)
    except MemoryError:
        out = dict(estado="falhou_memoria")
    except Exception as e:  # pragma: no cover
        out = dict(estado=f"erro:{type(e).__name__}:{e}")
    conn.send(out)
    conn.close()


def executar_isolado(dados, inst, alg, heur, k, limite_s=60.0, medir_mem=True) -> dict:
    vazio = dict(custo=float("nan"), comprimento=-1, expandidos=0, gerados=0, fronteira_max=0,
                 reexpandidos=0, tempo_s=float("nan"), memoria_mb=float("nan"))
    if not hasattr(os, "fork"):  # Windows: sem isolamento (só limite de tempo)
        try:
            return {**vazio, **_medir(dados, inst, alg, heur, k, limite_s, medir_mem)}
        except MemoryError:
            return {**vazio, "estado": "falhou_memoria"}
    ctx = mp.get_context("fork")
    pai, filho = ctx.Pipe(duplex=False)
    proc = ctx.Process(target=_filho, args=(filho, dados, inst, alg, heur, k, limite_s, medir_mem))
    proc.start()
    filho.close()
    res = None
    if pai.poll(limite_s * (4 if medir_mem else 1) + 15):
        try:
            res = pai.recv()
        except EOFError:
            res = dict(estado="falhou_memoria")  # processo morto (provável falta de memória)
    else:
        res = dict(estado="falhou_tempo")
    proc.join(2)
    if proc.is_alive():
        proc.kill()
        proc.join()
    return {**vazio, **res}


# ------------------------------------------------------------- bateria
def carregar_instancias(nivel: str, n: int) -> List[dict]:
    lst = []
    for i in range(1, n + 1):
        caminho = os.path.join(DIR_INST, f"{nivel}_{i:02d}.json")
        if not os.path.exists(caminho):
            escrever_tudo(max(n, 10))
        with open(caminho, encoding="utf-8") as f:
            lst.append(json.load(f))
    return lst


def correr_bateria(n: int, limite_s: float, medir_mem: bool, niveis=NIVEIS) -> pd.DataFrame:
    dados = carregar_dados_rede(os.path.join(DIR_INST, "rede_base.json"))
    linhas = []
    for nivel in niveis:
        for inst in carregar_instancias(nivel, n):
            rede = Rede(dados, inst.get("paragens"))
            tam = rede.n_arestas()
            for nome, alg, heur, k in CONFIGS:
                res = executar_isolado(dados, inst, alg, heur, k, limite_s, medir_mem)
                linhas.append(dict(nivel=nivel, instancia=inst["nome"], algoritmo=nome,
                                   n_paragens=len(rede.activas), tamanho=tam,
                                   alfa=inst["alfa"], beta=inst["beta"], **res))
                print(f"{inst['nome']:11} {nome:12} {res['estado']:14} custo={res['custo']:8.2f} "
                      f"exp={res['expandidos']:8} t={res['tempo_s']:.3f}s", flush=True)
    df = pd.DataFrame(linhas)
    # custo óptimo de referência: UCS se terminou, senão A* h2 (ambos óptimos)
    opt = {}
    for inst_nome, g in df.groupby("instancia"):
        for ref in ("UCS", "A* h2", "A* h1", "A* h0"):
            r = g[(g.algoritmo == ref) & (g.estado == "ok")]
            if len(r):
                opt[inst_nome] = float(r.custo.iloc[0])
                break
    df["custo_optimo"] = df.instancia.map(opt)
    df["razao_custo"] = df.custo / df.custo_optimo
    return df


def tabelas(df: pd.DataFrame) -> None:
    """Tabelas médias por nível (CSV + Markdown)."""
    ordem = [c[0] for c in CONFIGS]
    for nivel in NIVEIS:
        g = df[df.nivel == nivel]
        if g.empty:
            continue
        linhas = []
        for alg in ordem:
            a = g[g.algoritmo == alg]
            ok = a[a.estado == "ok"]
            n_tot = len(a)
            falhas = a[a.estado.str.startswith("falhou")]
            sem = a[a.estado == "sem_solucao"]
            linhas.append({
                "Algoritmo": alg, "Resolvidas": f"{len(ok)}/{n_tot}",
                "Falhou (tempo/mem)": f"{(a.estado == 'falhou_tempo').sum()}/{(a.estado == 'falhou_memoria').sum()}",
                "Sem solução (feixe/limite)": len(sem) + int((a.estado == "limite_prof").sum()),
                "Custo médio": ok.custo.mean(), "Custo/óptimo": ok.razao_custo.mean(),
                "Comprimento": ok.comprimento.mean(), "Expandidos": ok.expandidos.mean(),
                "Gerados": ok.gerados.mean(), "Fronteira máx.": ok.fronteira_max.mean(),
                "Tempo (s)": ok.tempo_s.mean(), "Memória (MB)": ok.memoria_mb.mean(),
                "Re-expandidos (IDS)": ok.reexpandidos.mean() if alg == "IDS" else float("nan")})
        t = pd.DataFrame(linhas)
        t.to_csv(os.path.join(DIR_RES, f"resumo_{nivel}.csv"), index=False, encoding="utf-8")
        with open(os.path.join(DIR_RES, f"resumo_{nivel}.md"), "w", encoding="utf-8") as f:
            f.write(t.to_markdown(index=False, floatfmt=".2f") if _tem_tabulate() else t.to_string(index=False))


def _tem_tabulate() -> bool:
    try:
        import tabulate  # noqa: F401
        return True
    except Exception:
        return False


def graficos(df: pd.DataFrame) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    estilos = {"BFS": ("tab:blue", "o"), "DFS": ("tab:cyan", "v"), "IDS": ("tab:purple", "s"),
               "UCS": ("tab:green", "^"), "Gulosa h1": ("tab:olive", "x"), "Gulosa h2": ("gold", "+"),
               "A* h0": ("tab:gray", "D"), "A* h1": ("tab:orange", "<"), "A* h2": ("tab:red", "*"),
               "Beam k=10": ("tab:brown", "p"), "Beam k=100": ("tab:pink", "h"),
               "Beam k=1000": ("black", ".")}
    ok = df[df.estado == "ok"]
    for coluna, ylabel, nome, titulo in (
            ("expandidos", "Nós expandidos (escala log)", "grafico1_expandidos_vs_tamanho.png",
             "Nós expandidos vs. tamanho da instância"),
            ("tempo_s", "Tempo (s, escala log)", "grafico2_tempo_vs_tamanho.png",
             "Tempo vs. tamanho da instância")):
        fig, ax = plt.subplots(figsize=(8.5, 5.5))
        for alg, (cor, mk) in estilos.items():
            a = ok[ok.algoritmo == alg]
            if len(a):
                ax.scatter(a.tamanho, a[coluna].clip(lower=1e-4 if coluna == "tempo_s" else 0.9),
                           marker=mk, color=cor, label=alg, s=22, alpha=0.75)
        ax.set_yscale("log")
        ax.set_xlabel("Tamanho da instância (nº de ligações estáticas da sub-rede)")
        ax.set_ylabel(ylabel)
        ax.set_title(titulo)
        ax.grid(True, which="both", alpha=0.3)
        ax.legend(fontsize=7, ncol=2)
        fig.tight_layout()
        fig.savefig(os.path.join(DIR_RES, nome), dpi=150)
        plt.close(fig)
    fig, ax = plt.subplots(figsize=(7, 6.5))
    d = ok.dropna(subset=["custo_optimo"])
    lim = max(d.custo.max(), d.custo_optimo.max()) * 1.05 if len(d) else 1
    ax.plot([0, lim], [0, lim], "k--", linewidth=0.8, label="óptimo (y = x)")
    for alg, (cor, mk) in estilos.items():
        a = d[d.algoritmo == alg]
        if len(a):
            ax.scatter(a.custo_optimo, a.custo, color=cor, marker=mk, s=28, label=alg, alpha=0.8)
    ax.set_xlabel("Custo óptimo (UCS / A*)")
    ax.set_ylabel("Custo obtido")
    ax.set_title("Custo obtido vs. custo óptimo")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=7, ncol=2)
    fig.tight_layout()
    fig.savefig(os.path.join(DIR_RES, "grafico3_custo_vs_optimo.png"), dpi=150)
    plt.close(fig)


# ------------------------------------------------------------- extras
def tabela_bstar(dados, n: int, limite_s: float) -> pd.DataFrame:
    linhas = []
    for nivel in NIVEIS:
        for inst in carregar_instancias(nivel, n):
            reg = dict(nivel=nivel, instancia=inst["nome"])
            for h in ("h0", "h1", "h2"):
                p = problema_de_instancia(dados, inst)
                r = executar("A*", p, heur=h, limite_s=limite_s)
                reg[f"exp_{h}"] = r.metricas.expandidos
                reg[f"ger_{h}"] = r.metricas.gerados
                if r.ok:
                    reg["d"] = r.comprimento
                    reg[f"bstar_{h}"] = b_estrela(r.metricas.gerados, r.comprimento)
            linhas.append(reg)
    df = pd.DataFrame(linhas)
    df.to_csv(os.path.join(DIR_RES, "bstar.csv"), index=False, encoding="utf-8")
    return df


def _resumo_percurso(p, no) -> dict:
    estados = []
    n = no
    while n is not None:
        estados.append(n)
        n = n.pai
    estados.reverse()
    s = estados[-1].estado
    linhas, passos = [], []
    for a in estados[1:]:
        if a.accao[0] == "E":
            linhas.append(p.rede.linhas[a.accao[1]].nome)
        elif a.accao[0] == "A" and (not passos or passos[-1] != "a pé"):
            linhas.append("a pé")
    return dict(chegada=hhmm(s.t), tempo_min=s.t - p.t0, dinheiro_mt=s.gasto, transbordos=s.transb,
                percurso=" > ".join(linhas), custo=no.g)


def cenarios_alfa(dados) -> pd.DataFrame:
    """Percurso óptimo (A* h2) para alfa = 0, 0,5, 2 em pares O-D fixos, sem folgas apertadas."""
    rede = Rede(dados)
    pares = [(5, 18, "07:00"), (4, 29, "08:00"), (29, 1, "17:00"), (27, 8, "12:00"), (10, 18, "09:00")]
    linhas = []
    for o, d, hora in pares:
        h, m = hora.split(":")
        t0 = int(h) * 60 + int(m)
        for beta in (0.0, 5.0):
            for alfa in (0.0, 0.5, 2.0):
                inst = dict(origem=o, destino=d, t0=t0, limite=t0 + 360, orcamento=300,
                            alfa=alfa, beta=beta, paragens=None)
                p = problema_de_instancia(dados, inst)
                r = executar("A*", p, heur="h2", limite_s=60)
                if r.ok:
                    linhas.append(dict(origem=rede.nomes[o], destino=rede.nomes[d], partida=hora,
                                       alfa=alfa, beta=beta, **_resumo_percurso(p, r.no)))
    df = pd.DataFrame(linhas)
    df.to_csv(os.path.join(DIR_RES, "cenarios_alfa.csv"), index=False, encoding="utf-8")
    return df


def diagnostico_beam(p, k: int, heur: str = "h2"):
    ref = executar("A*", p, heur="h2")
    if not ref.ok:
        return None
    opt_estados = {n for _, n in ref.caminho}
    s0 = p.estado_inicial()
    from problema import No
    feixe = [No(s0)]
    usados = {s0}
    nivel = 0
    while feixe:
        nivel += 1
        cand = {}
        for no in feixe:
            for a in p.accoes(no.estado):
                s2 = p.resultado(no.estado, a)
                if p.e_objectivo(s2) or s2 in usados:
                    continue
                f = No(s2, no, a, no.g + p.custo(no.estado, a, s2), no.profundidade + 1)
                if s2 not in cand or f.g < cand[s2].g:
                    cand[s2] = f
        ordenados = sorted(cand.values(), key=lambda n: n.g + p.heuristica(n.estado, heur))
        for rank, n in enumerate(ordenados):
            if n.estado in opt_estados and rank >= k:
                fk = ordenados[k - 1].g + p.heuristica(ordenados[k - 1].estado, heur)
                return dict(nivel=nivel, rank=rank + 1, f_optimo=n.g + p.heuristica(n.estado, heur),
                            f_kesimo=fk, accao_optima=n.accao, estado=n.estado,
                            n_candidatos=len(ordenados))
        feixe = ordenados[:k]
        usados.update(n.estado for n in feixe)
    return None


def analise_beam(dados, n_pares: int = 150) -> pd.DataFrame:
    """Pergunta de análise do P7: onde o Beam (k=10) falha ou piora, e porquê."""
    rng = random.Random(SEMENTE)
    rede = Rede(dados)
    ids = rede.activas
    linhas = []
    tentativas = 0
    while len(linhas) < n_pares and tentativas < n_pares * 5:
        tentativas += 1
        o, d = rng.sample(ids, 2)
        if rede.geo(o, d) < 3.0:
            continue
        t0 = rng.randrange(6 * 60, 18 * 60, 5)
        ea = chegada_mais_cedo(rede, o, d, t0)
        if ea is None:
            continue
        inst = dict(origem=o, destino=d, t0=t0, limite=ea[0] + 90, orcamento=ea[1] + 60,
                    alfa=rng.choice([0.0, 0.5, 2.0]), beta=rng.choice([0.0, 5.0]), paragens=None)
        p = problema_de_instancia(dados, inst)
        ref = executar("A*", p, heur="h2", limite_s=60)
        if not ref.ok:
            continue
        # maior espera por serviço de horário fixo no percurso óptimo
        esp = 0
        usa_fixo = False
        nos = []
        n_ = ref.no
        while n_ is not None:
            nos.append(n_)
            n_ = n_.pai
        nos.reverse()
        for ant, no in zip(nos, nos[1:]):
            if no.accao[0] == "E":
                esp = max(esp, no.estado.t - ant.estado.t)
                if not p.rede.linhas[no.accao[1]].chapa:
                    usa_fixo = True
        reg = dict(origem=rede.nomes[o], destino=rede.nomes[d], t0=hhmm(t0), alfa=inst["alfa"],
                   beta=inst["beta"], custo_optimo=ref.custo, comprimento_optimo=ref.comprimento,
                   max_espera_optimo=esp, usa_horario_fixo=usa_fixo)
        for k in (10, 100):
            r = executar("Beam", p, heur="h2", k=k, limite_s=60)
            reg[f"beam{k}_estado"] = "ok" if r.ok else "falhou"
            reg[f"beam{k}_custo"] = r.custo
            reg[f"beam{k}_razao"] = r.custo / ref.custo if r.ok else float("nan")
        linhas.append(reg)
    df = pd.DataFrame(linhas)
    df.to_csv(os.path.join(DIR_RES, "analise_beam.csv"), index=False, encoding="utf-8")
    return df


def referencia_base(dados, limite_s: float) -> pd.DataFrame:
    with open(os.path.join(DIR_INST, "base.json"), encoding="utf-8") as f:
        inst = json.load(f)
    linhas = []
    for nome, alg, heur, k in CONFIGS:
        r = executar_isolado(dados, inst, alg, heur, k, limite_s, True)
        linhas.append(dict(algoritmo=nome, **r))
    df = pd.DataFrame(linhas)
    df.to_csv(os.path.join(DIR_RES, "base_referencia.csv"), index=False, encoding="utf-8")
    return df


# ------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10, help="instâncias por nível")
    ap.add_argument("--limite-tempo", type=float, default=60.0)
    ap.add_argument("--sem-memoria", action="store_true", help="não medir memória (mais rápido)")
    ap.add_argument("--so-graficos", action="store_true")
    ap.add_argument("--extras", action="store_true", help="b*, cenários alfa, análise Beam, base")
    ap.add_argument("--niveis", default=",".join(NIVEIS))
    a = ap.parse_args(argv)
    os.makedirs(DIR_RES, exist_ok=True)
    dados = carregar_dados_rede(os.path.join(DIR_INST, "rede_base.json"))

    caminho_csv = os.path.join(DIR_RES, "resultados.csv")
    if a.so_graficos:
        df = pd.read_csv(caminho_csv)
    elif a.extras:
        df = None
    else:
        t0 = time.time()
        df = correr_bateria(a.n, a.limite_tempo, not a.sem_memoria, a.niveis.split(","))
        df.to_csv(caminho_csv, index=False, encoding="utf-8")
        print(f"Bateria concluída em {time.time() - t0:.0f} s -> {caminho_csv}")
    if df is not None:
        tabelas(df)
        graficos(df)
    if a.extras:
        print(tabela_bstar(dados, a.n, a.limite_tempo).groupby("nivel").mean(numeric_only=True).round(2))
        print(cenarios_alfa(dados).to_string())
        print(referencia_base(dados, a.limite_tempo).to_string())
        df_b = analise_beam(dados)
        print(df_b.describe().round(2))
    with open(os.path.join(DIR_RES, "ambiente.txt"), "w", encoding="utf-8") as f:
        f.write(f"Python {platform.python_version()} | {platform.platform()} | "
                f"CPU: {platform.processor() or platform.machine()} | cores: {os.cpu_count()} | "
                f"semente {SEMENTE} | limite tempo {a.limite_tempo}s | limite memória 2 GB\n")


if __name__ == "__main__":
    main()
