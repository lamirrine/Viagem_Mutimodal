from __future__ import annotations

import heapq
import math
from collections import defaultdict
from typing import Callable, Dict, Hashable, Iterable, List, Tuple

INF = math.inf


class Heuristicas:
    def __init__(self, rede, destino: int, alfa: float):
        self.alfa = alfa
        self.destino = destino
        vmax = rede.vmax_kmh
        self.h1: Dict[int, float] = {
            p: rede.geo(p, destino) / vmax * 60.0 for p in rede.activas}
        entrada_t: Dict[int, List[Tuple[int, int]]] = defaultdict(list)
        entrada_m: Dict[int, List[Tuple[int, int]]] = defaultdict(list)
        for u, v, tmin, tar in rede.arestas_estaticas():
            entrada_t[v].append((u, tmin))
            entrada_m[v].append((u, tar))
        self.DT = self._dijkstra_reverso(rede.activas, entrada_t, destino)
        self.DM = self._dijkstra_reverso(rede.activas, entrada_m, destino)
        # DM a bordo: o passageiro pode continuar na linha sem pagar mais
        self.DMb: Dict[Tuple[int, int], float] = {}
        for L in rede.linhas:
            for pos in range(len(L.paragens)):
                self.DMb[(L.idx, pos)] = min(self.DM[q] for q in L.paragens[pos:])
        self._pos = {L.idx: L.pos for L in rede.linhas}
        # DT/DM infinitos: o destino é inalcançável a partir de p (mesmo sem restrições)

    @staticmethod
    def _dijkstra_reverso(nos, entrada, destino):
        dist = {p: INF for p in nos}
        dist[destino] = 0
        pq = [(0, destino)]
        while pq:
            d, v = heapq.heappop(pq)
            if d > dist[v]:
                continue
            for u, w in entrada.get(v, ()):
                nd = d + w
                if nd < dist[u]:
                    dist[u] = nd
                    heapq.heappush(pq, (nd, u))
        return dist

    def valor(self, s, nome: str) -> float:
        if nome == "h0":
            return 0.0
        if nome == "h1":
            return self.h1[s.parag]
        if nome == "h2":
            dt = self.DT[s.parag]
            if dt == INF:
                return INF
            m = (self.DMb[(s.linha, self._pos[s.linha][s.parag])] if s.a_bordo
                 else self.DM[s.parag])
            if m == INF:
                return INF
            return dt + self.alfa * m
        raise ValueError(f"heurística desconhecida: {nome}")

def b_estrela(N: int, d: int, tol: float = 1e-9) -> float:
    """Factor de ramificação efectivo: resolve N + 1 = 1 + b + b^2 + ... + b^d.

    N = nós gerados, d = profundidade da solução (nº de acções). Bissecção.
    """
    if d <= 0:
        return float("nan")
    if N <= d:
        return 1.0

    def soma(b: float) -> float:
        if abs(b - 1.0) < 1e-12:
            return d + 1.0
        return (b ** (d + 1) - 1.0) / (b - 1.0)

    lo, hi = 1.0, float(N)
    while hi - lo > tol:
        mid = (lo + hi) / 2
        if soma(mid) < N + 1:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


# ------------------------------------------------- verificações empíricas
def enumerar_estados(problema, limite_estados: int = 2_000_000):
    """Todos os estados alcançáveis e as arestas (s, a, s2, c).

    Só para instâncias pequenas. Devolve (estados, arestas) com arestas como
    dict estado -> lista de (s2, custo).
    """
    s0 = problema.estado_inicial()
    vistos = {s0}
    pilha = [s0]
    arestas: Dict[Hashable, List[Tuple[Hashable, float]]] = {}
    while pilha:
        s = pilha.pop()
        lst = []
        for a in problema.accoes(s):
            s2 = problema.resultado(s, a)
            lst.append((s2, problema.custo(s, a, s2)))
            if s2 not in vistos:
                vistos.add(s2)
                if len(vistos) > limite_estados:
                    raise MemoryError("instância demasiado grande para enumerar")
                pilha.append(s2)
        arestas[s] = lst
    return vistos, arestas


def h_estrela(problema, estados: Iterable[Hashable], arestas) -> Dict[Hashable, float]:
    reverso: Dict[Hashable, List[Tuple[Hashable, float]]] = defaultdict(list)
    for s, lst in arestas.items():
        for s2, c in lst:
            reverso[s2].append((s, c))
    dist = {s: INF for s in estados}
    pq = []
    for s in estados:
        if problema.e_objectivo(s):
            dist[s] = 0.0
            pq.append((0.0, id(s), s))
    heapq.heapify(pq)
    cont = 0
    while pq:
        d, _, v = heapq.heappop(pq)
        if d > dist[v]:
            continue
        for u, c in reverso.get(v, ()):
            nd = d + c
            if nd < dist[u]:
                dist[u] = nd
                cont += 1
                heapq.heappush(pq, (nd, cont, u))
    return dist


def verificar_admissibilidade(problema, nome: str, estados, hstar, eps: float = 1e-9):
    """Devolve a lista de estados onde h(s) > h*(s) (vazia = admissível)."""
    return [s for s in estados
            if hstar[s] != INF and problema.heuristica(s, nome) > hstar[s] + eps]


def verificar_consistencia(problema, nome: str, arestas, eps: float = 1e-9):
    """Devolve as arestas onde h(s) > c + h(s2) (vazia = consistente)."""
    mau = []
    for s, lst in arestas.items():
        hs = problema.heuristica(s, nome)
        for s2, c in lst:
            h2 = problema.heuristica(s2, nome)
            if h2 != INF and hs > c + h2 + eps:
                mau.append((s, s2, c))
    return mau
