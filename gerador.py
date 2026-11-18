from __future__ import annotations

import json
import math
import os
import random
import sys
from typing import Dict, List, Optional

from dominio import Rede, haversine_km

SEMENTE = 2026 * 100 + 7  # 202607
DIR = os.path.dirname(os.path.abspath(__file__))
DIR_INST = os.path.join(DIR, "instancias")

# id, nome, zona, lat, lon
PARAGENS = [
    (0, "Baixa", "Maputo", -25.9718, 32.5715),
    (1, "Museu", "Maputo", -25.9686, 32.5892),
    (2, "Xipamanine", "Maputo", -25.9440, 32.5640),
    (3, "Benfica", "Maputo", -25.9014, 32.5540),
    (4, "Zimpeto", "Maputo", -25.8475, 32.5782),
    (5, "Matola Gare", "Matola", -25.8845, 32.4618),
    (6, "Machava", "Matola", -25.9240, 32.4790),
    (7, "Matola Jardim", "Matola", -25.9500, 32.4680),
    (8, "Costa do Sol", "Maputo", -25.9230, 32.6280),
    (9, "Terminal do Ferry (Maputo)", "Maputo", -25.9776, 32.5719),
    (10, "Katembe (Terminal)", "Katembe", -25.9992, 32.5663),
    (11, "Estacao CFM", "Maputo", -25.9709, 32.5743),
    (12, "Alto Mae", "Maputo", -25.9650, 32.5810),
    (13, "Polana", "Maputo", -25.9570, 32.5960),
    (14, "Sommerschield", "Maputo", -25.9450, 32.5920),
    (15, "Malhangalene", "Maputo", -25.9500, 32.5750),
    (16, "Mercado Central", "Maputo", -25.9640, 32.5760),
    (17, "Junta", "Maputo", -25.9480, 32.5870),
    (18, "FENG-UEM", "Maputo", -25.9221, 32.5512),
    (19, "Maxaquene", "Maputo", -25.9380, 32.5870),
    (20, "Mavalane", "Maputo", -25.9200, 32.5726),
    (21, "Hulene", "Maputo", -25.9330, 32.5700),
    (22, "Mahotas", "Maputo", -25.9190, 32.6010),
    (23, "Magoanine", "Maputo", -25.8920, 32.5890),
    (24, "Laulane", "Maputo", -25.9230, 32.5470),
    (25, "Fomento", "Matola", -25.9420, 32.4620),
    (26, "Liberdade", "Matola", -25.9430, 32.4930),
    (27, "Matola Rio", "Matola", -25.9770, 32.4440),
    (28, "Praca dos Combatentes", "Maputo", -25.9560, 32.5600),
    (29, "Katembe Centro", "Katembe", -26.0120, 32.5560),
]

# modo -> (tarifa MT, velocidade km/h)
MODOS = {
    "chapa": (15, 22.0),
    "autocarro": (10, 20.0),
    "comboio": (20, 40.0),
    "ferry": (25, 12.0),
}

# (nome, modo, [paragens], desvio_opcional, tarifa_opcional)
LINHAS = [
    ("Chapa C1 Baixa-FENG", "chapa", [0, 16, 15, 17, 1, 18], None, None),
    ("Chapa C2 Baixa-Costa do Sol", "chapa", [0, 12, 13, 18, 8], None, None),
    ("Chapa C3 Xipamanine-Baixa", "chapa", [2, 15, 16, 0], None, None),
    ("Chapa C4 Xipamanine-Laulane", "chapa", [2, 21, 3, 24], None, None),
    ("Chapa C5 Zimpeto-Baixa", "chapa", [4, 23, 20, 21, 2, 15, 0], None, 20),
    ("Chapa C6 Laulane-Museu", "chapa", [24, 3, 19, 17, 1], None, None),
    ("Chapa C7 Matola Gare-Liberdade", "chapa", [5, 7, 6, 26], None, None),
    ("Chapa C8 Matola Rio-Liberdade", "chapa", [27, 5, 25, 26], None, None),
    ("Chapa C9 Machava-Xipamanine", "chapa", [6, 24, 3, 21, 2], None, 20),
    ("Chapa C10 Katembe-Baixa (Ponte)", "chapa", [29, 10, 0], 2.6, 30),
    ("Chapa C11 Mahotas-FENG", "chapa", [22, 8, 18], None, None),
    ("Chapa C12 Praca Combatentes-Museu", "chapa", [28, 15, 17, 14, 1], None, None),
    ("Autocarro B1 Baixa-Zimpeto", "autocarro", [0, 2, 21, 20, 23, 4], None, None),
    ("Autocarro B2 Baixa-Matola Gare", "autocarro", [0, 16, 24, 6, 26, 5], 1.15, 15),
    ("Autocarro B3 Museu-Costa do Sol", "autocarro", [1, 13, 18, 22, 8], None, None),
    ("Autocarro B4 Baixa-Polana", "autocarro", [9, 0, 12, 13, 14], None, None),
    ("Comboio T1 CFM-Matola Rio", "comboio", [11, 6, 5, 27], 1.2, None),
    ("Ferry F1 Maputo-Katembe", "ferry", [9, 10], 1.0, None),
]


def _hop_min(a: int, b: int, vel: float, desvio: float, fator: float, par: dict) -> int:
    pa = {p[0]: p for p in PARAGENS}
    d = haversine_km(pa[a][3], pa[a][4], pa[b][3], pa[b][4]) * fator * desvio
    return max(1, math.ceil(d / vel * 60 - 1e-9))


def construir_rede_base(semente: int = SEMENTE) -> dict:
    """Constrói o dicionário da rede com horários gerados pela semente."""
    rng = random.Random(semente)
    par = {"fator_desvio": 1.3, "vel_a_pe_kmh": 5.0, "max_a_pe_m": 1500,
           "ponta": [[360, 510], [990, 1140]], "mult_ponta": 1.8, "rampa_min": 60}
    dados = {"semente": semente, "parametros": par,
             "modos": {m: {"tarifa": t, "vel_kmh": v} for m, (t, v) in MODOS.items()},
             "paragens": [{"id": i, "nome": n, "zona": z, "lat": la, "lon": lo}
                          for i, n, z, la, lo in PARAGENS],
             "linhas": []}

    def gerar(nome, modo, seq, desvio, tarifa):
        vel = MODOS[modo][1]
        tar = tarifa if tarifa is not None else MODOS[modo][0]
        d = desvio if desvio is not None else 1.0
        cum = [0]
        for a, b in zip(seq, seq[1:]):
            cum.append(cum[-1] + _hop_min(a, b, vel, d, par["fator_desvio"], par))
        L = {"nome": nome, "modo": modo, "paragens": list(seq), "cum": cum, "tarifa": tar}
        if modo == "chapa":
            X = rng.choice([6, 8, 10, 12, 15])
            L.update(intervalo=X, fase=rng.randrange(X), inicio=5 * 60, fim=21 * 60)
        else:
            if modo == "autocarro":
                hw, ini, fim, jit = rng.choice([20, 25, 30]), 330, 1260, 3
            elif modo == "comboio":
                hw, ini, fim, jit = rng.choice([30, 40, 45]), 300 + rng.randrange(15), 1230, 2
            else:
                hw, ini, fim, jit = rng.choice([30, 40]), 330 + rng.randrange(10), 1230, 0
            viagens, t = [], ini
            while t <= fim:
                viagens.append(int(t))
                t += hw + (rng.randint(-jit, jit) if jit else 0)
            L["viagens"] = viagens
            L["intervalo_nominal"] = hw
        return L

    for nome, modo, seq, desvio, tarifa in LINHAS:
        for sentido, s in (("", seq), (" (volta)", list(reversed(seq)))):
            dados["linhas"].append(gerar(nome + sentido, modo, s, desvio, tarifa))
    return dados


# ------------------------------------------------------------------ instâncias
NIVEIS = {
    #            nº de paragens  folga tempo (min)  folga dinheiro (MT)
    "pequena": dict(n_par=(7, 9), folga_t=(30, 50), folga_m=(10, 25)),
    "media":   dict(n_par=(14, 18), folga_t=(40, 70), folga_m=(15, 35)),
    "grande":  dict(n_par=(26, 30), folga_t=(50, 90), folga_m=(20, 50)),
}


def _vizinhos(rede: Rede) -> Dict[int, set]:
    viz = {p: set() for p in rede.activas}
    for u, v, _, _ in rede.arestas_estaticas():
        viz[u].add(v)
        viz[v].add(u)
    return viz


def _subconjunto(dados: dict, n: int, rng: random.Random) -> List[int]:
    """Sub-rede ligada com n paragens (crescimento aleatório a partir de uma paragem)."""
    rede = Rede(dados)
    viz = _vizinhos(rede)
    ids = sorted(viz)
    while True:
        escolhidas = [rng.choice(ids)]
        fronteira = set(viz[escolhidas[0]])
        while len(escolhidas) < n and fronteira:
            x = rng.choice(sorted(fronteira))
            escolhidas.append(x)
            fronteira |= viz[x]
            fronteira -= set(escolhidas)
        if len(escolhidas) == n:
            return sorted(escolhidas)


def chegada_mais_cedo(rede: Rede, o: int, d: int, t0: int):
    import heapq
    melhor = {o: (t0, 0)}
    pq = [(t0, 0, o)]
    while pq:
        t, money, u = heapq.heappop(pq)
        if melhor.get(u, (1e9, 0))[0] < t:
            continue
        if u == d:
            return t, money
        for L_idx, pos in rede.por_paragem[u]:
            L = rede.linhas[L_idx]
            for j in range(pos + 1, len(L.paragens)):
                r = rede.chegada(L, pos, j, t)
                if r is None:
                    break
                v = L.paragens[j]
                if r[1] < melhor.get(v, (1e9, 0))[0]:
                    melhor[v] = (r[1], money + L.tarifa)
                    heapq.heappush(pq, (r[1], money + L.tarifa, v))
        for v, mn in rede.a_pe[u]:
            if t + mn < melhor.get(v, (1e9, 0))[0]:
                melhor[v] = (t + mn, money)
                heapq.heappush(pq, (t + mn, money, v))
    return None


def gerar_instancia(dados: dict, nivel: str, rng: random.Random, nome: str) -> dict:
    cfg = NIVEIS[nivel]
    while True:
        n = rng.randint(*cfg["n_par"])
        sub = _subconjunto(dados, n, rng) if n < len(dados["paragens"]) else \
            sorted(p["id"] for p in dados["paragens"])
        rede = Rede(dados, sub)
        if nivel == "pequena":
            o, d = rng.sample(sub, 2)
            if rede.geo(o, d) < 1.0:
                continue
        else:  # pares distantes => soluções mais profundas (25% mais distantes da sub-rede)
            pares = sorted(((rede.geo(u, v), u, v) for u in sub for v in sub if u != v),
                           reverse=True)
            _, o, d = rng.choice(pares[:max(1, len(pares) // 4)])
        t0 = rng.randrange(6 * 60, 17 * 60 + 1, 5)
        r = chegada_mais_cedo(rede, o, d, t0)
        if r is None:
            continue
        t_ea, dinheiro = r
        limite = t_ea + rng.randint(*cfg["folga_t"])
        orcamento = dinheiro + rng.randint(*cfg["folga_m"])
        return {"nome": nome, "nivel": nivel, "paragens": sub if n < len(dados["paragens"]) else None,
                "origem": o, "destino": d, "t0": t0, "limite": limite, "orcamento": orcamento,
                "alfa": rng.choice([0.0, 0.5, 2.0]), "beta": rng.choice([0.0, 5.0]),
                "chegada_mais_cedo": t_ea, "semente": SEMENTE}


def gerar_instancias(dados: dict, nivel: str, n: int = 10, semente: int = SEMENTE) -> List[dict]:
    rng = random.Random(f"{semente}-{nivel}")
    return [gerar_instancia(dados, nivel, rng, f"{nivel}_{i + 1:02d}") for i in range(n)]


def instancia_base(dados: dict) -> dict:
    rede = Rede(dados)
    t0 = 7 * 60
    t_ea, dinheiro = chegada_mais_cedo(rede, 5, 18, t0)
    return {"nome": "base", "nivel": "base", "paragens": None, "origem": 5, "destino": 18,
            "t0": t0, "limite": t_ea + 30, "orcamento": dinheiro + 20,
            "alfa": 0.5, "beta": 5.0, "chegada_mais_cedo": t_ea, "semente": SEMENTE}


def escrever_tudo(n_por_nivel: int = 10) -> None:
    os.makedirs(DIR_INST, exist_ok=True)
    dados = construir_rede_base()
    with open(os.path.join(DIR_INST, "rede_base.json"), "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=1)
    with open(os.path.join(DIR_INST, "base.json"), "w", encoding="utf-8") as f:
        json.dump(instancia_base(dados), f, ensure_ascii=False, indent=1)
    for nivel in NIVEIS:
        for inst in gerar_instancias(dados, nivel, n_por_nivel):
            with open(os.path.join(DIR_INST, inst["nome"] + ".json"), "w", encoding="utf-8") as f:
                json.dump(inst, f, ensure_ascii=False, indent=1)
    print("Instâncias escritas em", DIR_INST)


if __name__ == "__main__":
    escrever_tudo(int(sys.argv[1]) if len(sys.argv) > 1 else 10)
