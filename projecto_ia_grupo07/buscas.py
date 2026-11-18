"""Os 7 algoritmos de busca genéricos.

 1. BFS               com teste de objectivo na geração
 2. DFS               com controlo de ciclos no caminho e limite de profundidade
 3. IDS               aprofundamento iterativo, reporta nós re-expandidos
 4. UCS               heapq; entradas obsoletas descartadas ao retirar da fila
 5. Gulosa            f = h
 6. A*                f = g + h, versão em grafo (conjunto de fechados, com reabertura)
 7. Beam Search       feixe de largura k, ordenado por f = g + h

Todas devolvem um ``Resultado``. Estados possíveis:
    'ok'               solução encontrada
    'sem_solucao'      fronteira esgotada (nos algoritmos completos: não há solução)
    'limite_prof'      DFS/IDS atingiram o limite de profundidade sem solução
    'falhou_tempo'     excedeu o limite de tempo
    'falhou_memoria'   excedeu o limite de memória (registado por experiencias.py)
"""
from __future__ import annotations

import heapq
import time
from collections import deque
from dataclasses import dataclass, field
from itertools import count
from typing import Any, Callable, Dict, List, Optional

from problema import No, Problema, caminho


class LimiteTempo(Exception):
    pass


@dataclass
class Metricas:
    expandidos: int = 0
    gerados: int = 0
    fronteira_max: int = 0
    reexpandidos: int = 0     # só IDS
    iteracoes: int = 0        # só IDS / Beam (níveis)


@dataclass
class Resultado:
    estado: str
    no: Optional[No]
    metricas: Metricas
    tempo_s: float = 0.0

    @property
    def ok(self) -> bool:
        return self.estado == "ok"

    @property
    def custo(self) -> float:
        return self.no.g if self.no is not None else float("nan")

    @property
    def comprimento(self) -> int:
        return self.no.profundidade if self.no is not None else -1

    @property
    def caminho(self):
        return caminho(self.no) if self.no is not None else []


class _Controlo:
    """Verifica o limite de tempo a cada 256 chamadas."""

    def __init__(self, limite_s: Optional[float]):
        self.fim = time.perf_counter() + limite_s if limite_s else None
        self.n = 0

    def tick(self):
        self.n += 1
        if self.fim is not None and (self.n & 255) == 0 and time.perf_counter() > self.fim:
            raise LimiteTempo()


def _executar(corpo: Callable[[Metricas, _Controlo], Resultado], limite_s) -> Resultado:
    m = Metricas()
    ctrl = _Controlo(limite_s)
    t0 = time.perf_counter()
    try:
        r = corpo(m, ctrl)
    except LimiteTempo:
        r = Resultado("falhou_tempo", None, m)
    r.tempo_s = time.perf_counter() - t0
    return r


def _filho(p: Problema, no: No, a, s2) -> No:
    return No(s2, no, a, no.g + p.custo(no.estado, a, s2), no.profundidade + 1)

def bfs(p: Problema, limite_s: Optional[float] = None) -> Resultado:
    def corpo(m: Metricas, ctrl: _Controlo) -> Resultado:
        s0 = p.estado_inicial()
        raiz = No(s0)
        m.gerados = 1
        if p.e_objectivo(s0):
            return Resultado("ok", raiz, m)
        fronteira = deque([raiz])
        alcancados = {s0}
        while fronteira:
            m.fronteira_max = max(m.fronteira_max, len(fronteira))
            no = fronteira.popleft()
            m.expandidos += 1
            ctrl.tick()
            for a in p.accoes(no.estado):
                s2 = p.resultado(no.estado, a)
                if s2 in alcancados:
                    continue
                f = _filho(p, no, a, s2)
                m.gerados += 1
                if p.e_objectivo(s2):
                    return Resultado("ok", f, m)
                alcancados.add(s2)
                fronteira.append(f)
        return Resultado("sem_solucao", None, m)

    return _executar(corpo, limite_s)


# ---------------------------------------------------------------- 2. DFS / DLS
def _no_caminho(no: No, s2) -> bool:
    n = no
    while n is not None:
        if n.estado == s2:
            return True
        n = n.pai
    return False


def _dls(p: Problema, limite: int, m: Metricas, ctrl: _Controlo):
    """Busca em profundidade limitada, controlo de ciclos só no caminho.

    Devolve (no_objectivo | None, houve_corte).
    """
    raiz = No(p.estado_inicial())
    m.gerados += 1
    pilha: List[No] = [raiz]
    corte = False
    while pilha:
        m.fronteira_max = max(m.fronteira_max, len(pilha))
        no = pilha.pop()
        ctrl.tick()
        if p.e_objectivo(no.estado):
            return no, corte
        if no.profundidade >= limite:
            corte = True
            continue
        m.expandidos += 1
        filhos = []
        for a in p.accoes(no.estado):
            s2 = p.resultado(no.estado, a)
            if _no_caminho(no, s2):
                continue
            filhos.append(_filho(p, no, a, s2))
            m.gerados += 1
        pilha.extend(reversed(filhos))  # a 1.ª acção é explorada primeiro
    return None, corte


def dfs(p: Problema, limite_prof: int = 50, limite_s: Optional[float] = None) -> Resultado:
    def corpo(m, ctrl):
        no, corte = _dls(p, limite_prof, m, ctrl)
        if no is not None:
            return Resultado("ok", no, m)
        return Resultado("limite_prof" if corte else "sem_solucao", None, m)

    return _executar(corpo, limite_s)


# ---------------------------------------------------------------- 3. IDS
def ids(p: Problema, max_prof: int = 60, limite_s: Optional[float] = None) -> Resultado:
    """Aprofundamento iterativo.

    ``reexpandidos`` = nós expandidos nas iterações anteriores à última (isto é,
    trabalho repetido). Devolve a solução com menos acções (como a BFS).
    """
    def corpo(m: Metricas, ctrl: _Controlo) -> Resultado:
        total_antes = 0
        for lim in range(0, max_prof + 1):
            mi = Metricas()
            mi.fronteira_max = m.fronteira_max
            try:
                no, corte = _dls(p, lim, mi, ctrl)
            finally:
                m.expandidos += mi.expandidos
                m.gerados += mi.gerados
                m.fronteira_max = max(m.fronteira_max, mi.fronteira_max)
                m.iteracoes = lim + 1
                m.reexpandidos = m.expandidos - mi.expandidos
            if no is not None:
                return Resultado("ok", no, m)
            if not corte:
                return Resultado("sem_solucao", None, m)
        return Resultado("limite_prof", None, m)

    return _executar(corpo, limite_s)


# ---------------------------------------------------------------- 4. UCS
def ucs(p: Problema, limite_s: Optional[float] = None) -> Resultado:
    """Custo uniforme com heapq. Entradas obsoletas são descartadas ao sair."""
    def corpo(m: Metricas, ctrl: _Controlo) -> Resultado:
        s0 = p.estado_inicial()
        raiz = No(s0)
        m.gerados = 1
        cont = count()
        heap = [(0.0, next(cont), raiz)]
        melhor = {s0: 0.0}
        fechado = set()
        while heap:
            m.fronteira_max = max(m.fronteira_max, len(heap))
            g, _, no = heapq.heappop(heap)
            if no.estado in fechado or g > melhor.get(no.estado, float("inf")):
                continue  # entrada obsoleta
            if p.e_objectivo(no.estado):
                return Resultado("ok", no, m)
            fechado.add(no.estado)
            m.expandidos += 1
            ctrl.tick()
            for a in p.accoes(no.estado):
                s2 = p.resultado(no.estado, a)
                if s2 in fechado:
                    continue
                f = _filho(p, no, a, s2)
                if f.g < melhor.get(s2, float("inf")):
                    melhor[s2] = f.g
                    m.gerados += 1
                    heapq.heappush(heap, (f.g, next(cont), f))
        return Resultado("sem_solucao", None, m)

    return _executar(corpo, limite_s)


# ---------------------------------------------------------------- 5. Gulosa
def gulosa(p: Problema, heur: str = "h1", limite_s: Optional[float] = None) -> Resultado:
    """Melhor escolha: f = h. Completa em grafos finitos (com explorados), não óptima."""
    def corpo(m: Metricas, ctrl: _Controlo) -> Resultado:
        s0 = p.estado_inicial()
        raiz = No(s0)
        m.gerados = 1
        cont = count()
        heap = [(p.heuristica(s0, heur), next(cont), raiz)]
        alcancados = {s0}
        while heap:
            m.fronteira_max = max(m.fronteira_max, len(heap))
            _, _, no = heapq.heappop(heap)
            if p.e_objectivo(no.estado):
                return Resultado("ok", no, m)
            m.expandidos += 1
            ctrl.tick()
            for a in p.accoes(no.estado):
                s2 = p.resultado(no.estado, a)
                if s2 in alcancados:
                    continue
                alcancados.add(s2)
                f = _filho(p, no, a, s2)
                m.gerados += 1
                heapq.heappush(heap, (p.heuristica(s2, heur), next(cont), f))
        return Resultado("sem_solucao", None, m)

    return _executar(corpo, limite_s)


# ---------------------------------------------------------------- 6. A*
def astar(p: Problema, heur: str = "h2", limite_s: Optional[float] = None) -> Resultado:
    def corpo(m: Metricas, ctrl: _Controlo) -> Resultado:
        s0 = p.estado_inicial()
        raiz = No(s0)
        m.gerados = 1
        cont = count()
        h0 = p.heuristica(s0, heur)
        heap = [(h0, h0, next(cont), raiz)]
        melhor = {s0: 0.0}
        fechado: Dict[Any, float] = {}
        while heap:
            m.fronteira_max = max(m.fronteira_max, len(heap))
            f, _, _, no = heapq.heappop(heap)
            if no.g > melhor.get(no.estado, float("inf")):
                continue  # obsoleta
            if p.e_objectivo(no.estado):
                return Resultado("ok", no, m)
            if no.estado in fechado and fechado[no.estado] <= no.g:
                continue
            fechado[no.estado] = no.g
            m.expandidos += 1
            ctrl.tick()
            for a in p.accoes(no.estado):
                s2 = p.resultado(no.estado, a)
                g2 = no.g + p.custo(no.estado, a, s2)
                if g2 < melhor.get(s2, float("inf")):
                    melhor[s2] = g2
                    h2 = p.heuristica(s2, heur)
                    if h2 == float("inf"):
                        continue  # beco sem saída: não alcança o objectivo
                    m.gerados += 1
                    heapq.heappush(heap, (g2 + h2, h2, next(cont),
                                          No(s2, no, a, g2, no.profundidade + 1)))
        return Resultado("sem_solucao", None, m)

    return _executar(corpo, limite_s)


# ---------------------------------------------------------------- 7. Beam Search
def beam(p: Problema, k: int = 10, heur: str = "h2", limite_s: Optional[float] = None) -> Resultado:
    """Busca em feixe de largura k.

    Em cada nível (nº de acções) expandem-se os nós do feixe, juntam-se os
    sucessores e ficam só os k com menor f = g + h. Não é completa nem óptima
    (o caminho óptimo pode ser descartado cedo). Memória O(k) por nível.
    Para quando o feixe fica vazio ou quando nenhum nó do feixe pode melhorar a
    melhor solução já encontrada (h admissível => f é um limite inferior).
    """
    def corpo(m: Metricas, ctrl: _Controlo) -> Resultado:
        s0 = p.estado_inicial()
        raiz = No(s0)
        m.gerados = 1
        if p.e_objectivo(s0):
            return Resultado("ok", raiz, m)
        feixe = [raiz]
        usados = {s0}
        melhor_obj: Optional[No] = None
        while feixe:
            m.iteracoes += 1
            cand: Dict[Any, No] = {}
            for no in feixe:
                m.expandidos += 1
                ctrl.tick()
                for a in p.accoes(no.estado):
                    s2 = p.resultado(no.estado, a)
                    f = _filho(p, no, a, s2)
                    m.gerados += 1
                    if p.e_objectivo(s2):
                        if melhor_obj is None or f.g < melhor_obj.g:
                            melhor_obj = f
                        continue
                    if s2 in usados:
                        continue
                    if s2 not in cand or f.g < cand[s2].g:
                        cand[s2] = f
            m.fronteira_max = max(m.fronteira_max, len(cand))
            ordenados = sorted(cand.values(),
                               key=lambda n: n.g + p.heuristica(n.estado, heur))
            if melhor_obj is not None:
                ordenados = [n for n in ordenados
                             if n.g + p.heuristica(n.estado, heur) < melhor_obj.g]
            feixe = ordenados[:k]
            for n in feixe:
                usados.add(n.estado)
        if melhor_obj is not None:
            return Resultado("ok", melhor_obj, m)
        return Resultado("sem_solucao", None, m)

    return _executar(corpo, limite_s)


# ---------------------------------------------------------------- registo
def executar(algoritmo: str, p: Problema, heur: Optional[str] = None,
             k: Optional[int] = None, limite_prof: int = 50,
             limite_s: Optional[float] = None) -> Resultado:
    """Despacho por nome: 'BFS','DFS','IDS','UCS','Gulosa','A*','Beam'."""
    if algoritmo == "BFS":
        return bfs(p, limite_s)
    if algoritmo == "DFS":
        return dfs(p, limite_prof, limite_s)
    if algoritmo == "IDS":
        return ids(p, limite_prof, limite_s)
    if algoritmo == "UCS":
        return ucs(p, limite_s)
    if algoritmo == "Gulosa":
        return gulosa(p, heur or "h1", limite_s)
    if algoritmo == "A*":
        return astar(p, heur or "h2", limite_s)
    if algoritmo == "Beam":
        return beam(p, k or 10, heur or "h2", limite_s)
    raise ValueError(f"algoritmo desconhecido: {algoritmo}")
