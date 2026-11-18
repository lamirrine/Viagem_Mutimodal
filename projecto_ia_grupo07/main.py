from __future__ import annotations

import json
import os
import sys

import buscas
from dominio import carregar_dados_rede, hhmm, problema_de_instancia
from gerador import DIR_INST, NIVEIS, escrever_tudo, gerar_instancias
from visualizacao import mapa_ascii, mapa_matplotlib, mostrar_solucao

# (rótulo, algoritmo, heurística, k, explicação)
OPCOES = [
    ("A* com h2  (recomendado)", "A*", "h2", None, "óptimo e muito rápido; usa a melhor heurística"),
    ("A* com h1", "A*", "h1", None, "óptimo; heurística simples (linha recta / velocidade máxima)"),
    ("A* sem heurística (h0)", "A*", "h0", None, "óptimo, mas expande muitos nós (igual ao custo uniforme)"),
    ("Custo uniforme (UCS)", "UCS", None, None, "óptimo, sem heurística"),
    ("Busca em largura (BFS)", "BFS", None, None, "menos acções, mas não o menor custo"),
    ("Busca em profundidade (DFS)", "DFS", None, None, "primeira solução encontrada; pode ser muito má"),
    ("Aprofundamento iterativo (IDS)", "IDS", None, None, "menos acções; repete trabalho (mostra re-expandidos)"),
    ("Gulosa com h1", "Gulosa", "h1", None, "rápida, não óptima"),
    ("Gulosa com h2", "Gulosa", "h2", None, "rápida, não óptima, mais informada"),
    ("Beam Search k = 10", "Beam", "h2", 10, "pouca memória; pode falhar ou piorar o percurso"),
    ("Beam Search k = 100", "Beam", "h2", 100, "feixe médio"),
    ("Beam Search k = 1000", "Beam", "h2", 1000, "feixe largo, quase sempre óptimo"),
]

def perguntar(msg, padrao=None):
    try:
        r = input(f"{msg}" + (f" [{padrao}]" if padrao is not None else "") + ": ").strip()
    except EOFError:
        print()
        sys.exit(0)
    return r if r else (None if padrao is None else str(padrao))


def escolher(titulo, itens, padrao=1, extra=None):
    print(f"\n{titulo}")
    for i, it in enumerate(itens, 1):
        linha = f"  {i:2d}) {it}"
        if extra and extra[i - 1]:
            linha += f"  — {extra[i - 1]}"
        print(linha)
    while True:
        r = perguntar("Escolha o número", padrao)
        if r and r.isdigit() and 1 <= int(r) <= len(itens):
            return int(r) - 1
        print(f"  Opção inválida: escreva um número de 1 a {len(itens)}.")


def numero(msg, padrao, tipo=float, minimo=None):
    while True:
        r = perguntar(msg, padrao)
        try:
            v = tipo(r.replace(",", "."))
            if minimo is not None and v < minimo:
                raise ValueError
            return v
        except (ValueError, AttributeError):
            print("  Valor inválido, tente outra vez.")


def hora(msg, padrao):
    while True:
        r = perguntar(msg, padrao)
        try:
            h, m = r.replace("h", ":").split(":")
            if 0 <= int(h) < 24 and 0 <= int(m) < 60:
                return int(h) * 60 + int(m)
        except (ValueError, AttributeError):
            pass
        print("  Escreva a hora no formato HH:MM (por exemplo 07:30).")


def escolher_paragem(dados, titulo, padrao=None):
    """Escolhe uma paragem por número da lista ou por parte do nome."""
    pars = sorted(dados["paragens"], key=lambda p: (p["zona"], p["nome"]))
    print(f"\n{titulo}")
    zona = None
    for i, p in enumerate(pars, 1):
        if p["zona"] != zona:
            zona = p["zona"]
            print(f"  -- {zona} --")
        print(f"   {i:2d}) {p['nome']}")
    while True:
        r = perguntar("Número da paragem, ou parte do nome", padrao)
        if r is None:
            continue
        if r.isdigit() and 1 <= int(r) <= len(pars):
            return pars[int(r) - 1]["id"]
        achados = [p for p in pars if r.lower() in p["nome"].lower()]
        if len(achados) == 1:
            return achados[0]["id"]
        if achados:
            print("  Várias paragens encontradas:", ", ".join(p["nome"] for p in achados))
        else:
            print("  Paragem não encontrada.")


def descrever(dados, inst):
    n = {p["id"]: p["nome"] for p in dados["paragens"]}
    return (f"{n[inst['origem']]} → {n[inst['destino']]}, partida {hhmm(inst['t0'])}, "
            f"chegar até {hhmm(inst['limite'])}, orçamento {inst['orcamento']} MT, "
            f"α={inst['alfa']}, β={inst['beta']}")


def carregar_base():
    with open(os.path.join(DIR_INST, "base.json"), encoding="utf-8") as f:
        return json.load(f)


def escolher_viagem(dados, actual):
    op = escolher("Que viagem quer estudar?",
                  ["Viagem base (Matola Gare → FENG-UEM, 07:00)",
                   "Uma viagem gerada automaticamente (pequena, média ou grande)",
                   "Criar a minha viagem (escolho origem, destino, hora…)",
                   "Carregar de um ficheiro .json"],
                  padrao=1)
    if op == 0:
        return carregar_base()
    if op == 1:
        nivel = list(NIVEIS)[escolher("Tamanho da instância:", ["Pequena (7 a 9 paragens)", "Média (14 a 18)",
                                                              "Grande (26 a 30)"], padrao=1)]
        lista = gerar_instancias(dados, nivel, 10)
        i = escolher(f"Instâncias {nivel}s (geradas com a semente 202607):",
                     [descrever(dados, x) for x in lista], padrao=1)
        return lista[i]
    if op == 2:
        o = escolher_paragem(dados, "ORIGEM — de onde parte?")
        d = escolher_paragem(dados, "DESTINO — para onde vai?")
        t0 = hora("Hora de partida (HH:MM)", "08:00")
        lim = hora("Tem de chegar até (HH:MM)", hhmm(t0 + 180))
        orc = numero("Orçamento máximo em MT", 80, int, 0)
        print("\nPesos do custo:  custo = minutos + α × MT gastos + β × transbordos")
        a = numero("α — quantos minutos vale 1 MT? (0 = o dinheiro não conta)", 0.5, float, 0)
        b = numero("β — quantos minutos vale 1 transbordo?", 5, float, 0)
        return {"nome": "minha viagem", "paragens": None, "origem": o, "destino": d, "t0": t0,
                "limite": lim, "orcamento": orc, "alfa": a, "beta": b}
    caminho = perguntar("Caminho do ficheiro .json")
    try:
        with open(caminho, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError, TypeError) as e:
        print(f"  Não consegui ler o ficheiro ({e}). Mantém-se a viagem actual.")
        return actual


def alterar_parametros(inst):
    print("\nValores actuais:", f"hora-limite {hhmm(inst['limite'])}, orçamento {inst['orcamento']} MT, "
                                f"α={inst['alfa']}, β={inst['beta']}")
    print("(Enter mantém o valor actual)")
    inst = dict(inst)
    inst["limite"] = hora("Tem de chegar até (HH:MM)", hhmm(inst["limite"]))
    inst["orcamento"] = numero("Orçamento máximo (MT)", inst["orcamento"], int, 0)
    inst["alfa"] = numero("α (minutos por MT)", inst["alfa"], float, 0)
    inst["beta"] = numero("β (minutos por transbordo)", inst["beta"], float, 0)
    return inst


def correr_um(dados, inst):
    i = escolher("Que algoritmo quer usar?", [o[0] for o in OPCOES], padrao=1,
                 extra=[o[4] for o in OPCOES])
    _, alg, heur, k, _ = OPCOES[i]
    print("\nLimites (Enter = valores recomendados)")
    ls = numero("Tempo máximo em segundos", 60, float, 1)
    lp = 40
    if alg in ("DFS", "IDS"):
        lp = numero("Profundidade máxima (nº de acções)", 40, int, 1)
    p = problema_de_instancia(dados, inst)
    r = buscas.executar(alg, p, heur=heur, k=k, limite_prof=lp, limite_s=ls)
    print("\n" + mostrar_solucao(p, r))
    m = r.metricas
    nomes = {"ok": "solução encontrada", "sem_solucao": "sem solução",
             "limite_prof": "limite de profundidade atingido", "falhou_tempo": "excedeu o tempo máximo"}
    print(f"\nResultado: {nomes.get(r.estado, r.estado)}")
    print(f"  custo {r.custo:.2f} | acções {r.comprimento} | nós expandidos {m.expandidos} | "
          f"gerados {m.gerados} | fronteira máx. {m.fronteira_max} | tempo {r.tempo_s:.3f} s"
          + (f" | re-expandidos {m.reexpandidos}" if alg == "IDS" else ""))
    if r.ok:
        print("\n" + mapa_ascii(p, r))
        if perguntar("Abrir o mapa gráfico (matplotlib)? (s/n)", "n").lower().startswith("s"):
            mapa_matplotlib(p, r)
    return p, r


def comparar_todos(dados, inst):
    print("\nA correr os 12 algoritmos (máx. 10 s cada)…\n")
    cab = f"{'Algoritmo':<32}{'Estado':<16}{'Custo':>8}{'Acções':>8}{'Expand.':>10}{'Tempo(s)':>10}"
    print(cab)
    print("-" * len(cab))
    linhas, melhor = [], None
    for rot, alg, heur, k, _ in OPCOES:
        p = problema_de_instancia(dados, inst)
        r = buscas.executar(alg, p, heur=heur, k=k, limite_prof=40, limite_s=10)
        linhas.append((rot, r))
        if r.ok and (melhor is None or r.custo < melhor):
            melhor = r.custo
    for rot, r in linhas:
        est = {"ok": "ok", "sem_solucao": "sem solução", "limite_prof": "limite prof.",
               "falhou_tempo": "falhou (tempo)"}.get(r.estado, r.estado)
        marca = "  ← melhor" if r.ok and abs(r.custo - melhor) < 1e-9 else ""
        custo = f"{r.custo:8.1f}" if r.ok else f"{'—':>8}"
        acc = f"{r.comprimento:8d}" if r.ok else f"{'—':>8}"
        print(f"{rot:<32}{est:<16}{custo}{acc}{r.metricas.expandidos:10d}{r.tempo_s:10.3f}{marca}")
    print("\nO custo mais baixo é o óptimo; A* e UCS devem coincidir com ele.")


def menu():
    base = os.path.join(DIR_INST, "rede_base.json")
    if not os.path.exists(base):
        escrever_tudo()
    dados = carregar_dados_rede(base)
    inst = carregar_base()
    print("=" * 66)
    print(" P7 — Viagem multimodal Maputo–Matola–Katembe (Grupo 07)")
    print("=" * 66)
    while True:
        print(f"\nViagem actual: {descrever(dados, inst)}")
        op = escolher("O que quer fazer?",
                      ["Resolver a viagem com um algoritmo (mostra o percurso passo a passo)",
                       "Comparar todos os algoritmos nesta viagem",
                       "Escolher outra viagem",
                       "Alterar hora-limite, orçamento, α ou β",
                       "Sair"], padrao=1)
        if op == 0:
            correr_um(dados, inst)
        elif op == 1:
            comparar_todos(dados, inst)
        elif op == 2:
            inst = escolher_viagem(dados, inst)
        elif op == 3:
            inst = alterar_parametros(inst)
        else:
            print("Até à próxima.")
            return


if __name__ == "__main__":
    if "--demo" in sys.argv:
        dados = carregar_dados_rede(os.path.join(DIR_INST, "rede_base.json"))
        inst = carregar_base()
        p = problema_de_instancia(dados, inst)
        r = buscas.executar("A*", p, heur="h2", limite_s=60)
        print(mostrar_solucao(p, r))
        m = r.metricas
        print(f"\nMétricas: estado={r.estado} custo={r.custo:.2f} comprimento={r.comprimento} "
              f"expandidos={m.expandidos} gerados={m.gerados} fronteira_max={m.fronteira_max} "
              f"re-expandidos={m.reexpandidos} tempo={r.tempo_s:.3f}s")
        print("\n" + mapa_ascii(p, r))
    else:
        menu()
