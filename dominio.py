""" Estado(parag, t, gasto, transb, linha, a_bordo)

    parag    índice da paragem onde o passageiro está
    t        instante actual, em minutos desde as 00:00 (inteiro)
    gasto    dinheiro gasto até agora, em MT (inteiro)
    transb   número de transbordos feitos até agora
    linha    índice do último serviço (linha) usado, ou -1 se ainda não viajou
    a_bordo  1 se está dentro do veículo da ``linha`` (continuar não exige espera
             nem nova tarifa), 0 se está na paragem / a pé

Acção (tuplo): (tipo, linha, destino, t_fim, tarifa)
    ('E', linha, parag, t_partida, tarifa)  ESPERA pela próxima partida da
        ``linha`` e EMBARCA (paga a tarifa; conta transbordo se a linha mudou).
    ('V', linha, prox_parag, t_chegada, 0)  VIAJA uma paragem na linha em que
        está a bordo (sem espera nem tarifa).
    ('A', -1, destino, t_chegada, 0)         CAMINHA até ``destino`` (<= 1,5 km).
    Sair do veículo é implícito: de um estado a bordo pode-se caminhar ou
    embarcar noutra linha.

Custo generalizado (minutos equivalentes):
    c(s,a,s') = (t' - t) + alfa * (gasto' - gasto) + beta * (transb' - transb)
"""
from __future__ import annotations

import json
import math
from bisect import bisect_left
from typing import Dict, List, NamedTuple, Optional, Sequence, Tuple

from heuristicas import Heuristicas
from problema import Problema

R_TERRA_KM = 6371.0088


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distância em linha recta  entre dois pontos em km."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R_TERRA_KM * math.asin(math.sqrt(a))


def hhmm(minutos: int) -> str:
    minutos = int(minutos)
    return f"{(minutos // 60) % 24:02d}:{minutos % 60:02d}"


def para_min(texto: str) -> int:
    h, m = texto.split(":")
    return int(h) * 60 + int(m)


class Estado(NamedTuple):
    parag: int
    t: int
    gasto: int
    transb: int
    linha: int
    a_bordo: int


class Linha:
    """Um serviço de transporte (numa direcção) sobre uma sequência de paragens."""

    __slots__ = ("idx", "nome", "modo", "paragens", "cum", "tarifa", "chapa",
                 "intervalo", "fase", "inicio", "fim", "deps", "pos")

    def __init__(self, idx: int, d: dict, ids_activos: Optional[set]):
        self.idx = idx
        self.nome = d["nome"]
        self.modo = d["modo"]
        self.tarifa = int(d["tarifa"])
        self.chapa = d["modo"] == "chapa"
        paragens, cum = [], []
        for p, c in zip(d["paragens"], d["cum"]):
            if ids_activos is None or p in ids_activos:
                paragens.append(p)
                cum.append(c)
        self.paragens = paragens
        self.cum = cum
        self.pos = {p: i for i, p in enumerate(paragens)}
        self.intervalo = d.get("intervalo")
        self.fase = d.get("fase", 0)
        self.inicio = d.get("inicio")
        self.fim = d.get("fim")
        if self.chapa:
            self.deps = None
        else:  # horário fixo: partidas na 1.ª paragem + deslocamento acumulado
            self.deps = [sorted(v + c for v in d["viagens"]) for c in cum]


class Rede:
    """Rede de transportes dependente do tempo (opcionalmente uma sub-rede)."""

    def __init__(self, dados: dict, paragens_activas: Optional[Sequence[int]] = None,
                 modo_ponta: str = "rampa"):
        par = dados["parametros"]
        self.fator = par["fator_desvio"]
        self.vel_pe = par["vel_a_pe_kmh"]
        self.max_pe_m = par["max_a_pe_m"]
        self.janelas_ponta = [tuple(j) for j in par["ponta"]]
        self.mult = par["mult_ponta"]
        self.rampa = par["rampa_min"]
        self.modo_ponta = modo_ponta  # 'rampa' (FIFO) ou 'degrau' (ingénuo)
        self.dados = dados
        self.todas = {p["id"]: p for p in dados["paragens"]}
        activos = set(paragens_activas) if paragens_activas is not None else set(self.todas)
        self.activas = sorted(activos)
        self.nomes = {i: self.todas[i]["nome"] for i in self.activas}
        ids = activos if paragens_activas is not None else None
        self.linhas: List[Linha] = []
        for d in dados["linhas"]:
            L = Linha(len(self.linhas), d, ids)
            if len(L.paragens) >= 2:
                self.linhas.append(L)
        for i, L in enumerate(self.linhas):
            L.idx = i
        self.por_paragem: Dict[int, List[Tuple[int, int]]] = {p: [] for p in self.activas}
        for L in self.linhas:
            for pos, p in enumerate(L.paragens):
                if pos < len(L.paragens) - 1:  # só tem sentido embarcar se houver paragens a seguir
                    self.por_paragem[p].append((L.idx, pos))
        self.a_pe: Dict[int, List[Tuple[int, int]]] = {p: [] for p in self.activas}
        for u in self.activas:
            for v in self.activas:
                if u == v:
                    continue
                dkm = self.geo(u, v) * self.fator
                if dkm * 1000 <= self.max_pe_m:
                    mn = max(1, math.ceil(dkm / self.vel_pe * 60 - 1e-9))
                    self.a_pe[u].append((v, mn))
        self._vmax: Optional[float] = None

    # ------------------------------------------------------------ geometria
    def geo(self, u: int, v: int) -> float:
        a, b = self.todas[u], self.todas[v]
        return haversine_km(a["lat"], a["lon"], b["lat"], b["lon"])

    # ------------------------------------------------------------ tempo
    def mult_ponta(self, t: float) -> float:
        """Multiplicador do tempo de viagem do chapa à hora t (>= 1)."""
        t = t % 1440
        melhor = 1.0
        for a, b in self.janelas_ponta:
            if a <= t <= b:
                return self.mult
            if self.modo_ponta == "rampa":
                d = a - t if t < a else t - b
                if d < self.rampa:
                    melhor = max(melhor, 1.0 + (self.mult - 1.0) * (1.0 - d / self.rampa))
        return melhor

    def proxima_partida(self, L: Linha, pos: int, t: int) -> Optional[int]:
        """Primeira partida da linha L, na posição ``pos``, em ou depois de t."""
        if L.chapa:
            base = L.inicio + L.cum[pos]
            primeira = base + L.fase
            ultima = L.fim + L.cum[pos]
            if t <= primeira:
                dep = primeira
            else:
                k = -(-(t - primeira) // L.intervalo)
                dep = primeira + k * L.intervalo
            return dep if dep <= ultima else None
        lst = L.deps[pos]
        i = bisect_left(lst, t)
        return lst[i] if i < len(lst) else None

    def hop(self, L: Linha, k: int, t: int) -> int:
        """Duração (min) de ir da posição k à k+1 da linha L, partindo (a bordo) no instante t."""
        d = L.cum[k + 1] - L.cum[k]
        if L.chapa:
            return math.ceil(d * self.mult_ponta(t) - 1e-9)
        return d

    def chegada(self, L: Linha, pi: int, pj: int, t: int) -> Optional[Tuple[int, int]]:
        """Esperar a próxima partida em pi e seguir a bordo até pj: (partida, chegada)."""
        dep = self.proxima_partida(L, pi, t)
        if dep is None:
            return None
        tt = dep
        for k in range(pi, pj):
            tt += self.hop(L, k, tt)
        return dep, tt

    # ------------------------------------------------------------ grafo estático
    def arestas_estaticas(self):
        for L in self.linhas:
            n = len(L.paragens)
            for i in range(n - 1):
                for j in range(i + 1, n):
                    yield L.paragens[i], L.paragens[j], L.cum[j] - L.cum[i], L.tarifa
        for u, lst in self.a_pe.items():
            for v, mn in lst:
                yield u, v, mn, 0

    @property
    def vmax_kmh(self) -> float:
        """Velocidade máxima efectiva da rede (km/h) medida em linha recta."""
        if self._vmax is None:
            v = 0.0
            for u, w, tmin, _ in self.arestas_estaticas():
                v = max(v, self.geo(u, w) / (tmin / 60.0))
            self._vmax = v
        return self._vmax

    def n_arestas(self) -> int:
        return sum(1 for _ in self.arestas_estaticas())

    # ------------------------------------------------------------ FIFO
    def verificar_fifo(self, passo: int = 1) -> List[Tuple[str, int, int, int]]:
        """Devolve as violações da propriedade FIFO: (linha, pi, pj, t).

        FIFO: se se chega à paragem mais tarde, nunca se chega mais cedo ao
        destino do troço. Para cada linha e cada par (i, j) varre-se o dia.
        """
        violacoes = []
        for L in self.linhas:
            n = len(L.paragens)
            for i in range(n - 1):
                for j in range(i + 1, n):
                    anterior = None
                    for t in range(0, 1441, passo):
                        r = self.chegada(L, i, j, t)
                        if r is None:
                            continue
                        if anterior is not None and r[1] < anterior:
                            violacoes.append((L.nome, i, j, t))
                            break
                        anterior = r[1]
        return violacoes


class ProblemaViagem(Problema):

    def __init__(self, rede: Rede, origem: int, destino: int, t0: int, limite: int,
                 orcamento: int, alfa: float = 0.5, beta: float = 0.0):
        self.rede = rede
        self.origem = origem
        self.destino = destino
        self.t0 = t0
        self.limite = limite
        self.orcamento = orcamento
        self.alfa = alfa
        self.beta = beta
        self.h = Heuristicas(rede, destino, alfa)

    # --- interface Problema
    def estado_inicial(self) -> Estado:
        return Estado(self.origem, self.t0, 0, 0, -1, 0)

    def accoes(self, s: Estado):
        r = self.rede
        t = s.t
        res = []
        if s.a_bordo:  # continuar no veículo: 1 paragem, sem espera nem tarifa
            L = r.linhas[s.linha]
            pos = L.pos[s.parag]
            if pos < len(L.paragens) - 1:
                arr = t + r.hop(L, pos, t)
                if arr <= self.limite:
                    res.append(("V", L.idx, L.paragens[pos + 1], arr, 0))
        for L_idx, pos in r.por_paragem[s.parag]:  # esperar e embarcar
            if s.a_bordo and L_idx == s.linha:
                continue
            L = r.linhas[L_idx]
            if s.gasto + L.tarifa > self.orcamento:
                continue
            dep = r.proxima_partida(L, pos, t)
            if dep is None or dep >= self.limite:
                continue
            res.append(("E", L_idx, s.parag, dep, L.tarifa))
        for q, mn in r.a_pe[s.parag]:  # caminhar
            if t + mn <= self.limite:
                res.append(("A", -1, q, t + mn, 0))
        return res

    def resultado(self, s: Estado, a) -> Estado:
        tipo = a[0]
        if tipo == "V":
            return Estado(a[2], a[3], s.gasto, s.transb, s.linha, 1)
        if tipo == "E":
            transb = s.transb + (1 if (s.linha != -1 and s.linha != a[1]) else 0)
            return Estado(s.parag, a[3], s.gasto + a[4], transb, a[1], 1)
        return Estado(a[2], a[3], s.gasto, s.transb, s.linha, 0)

    def custo(self, s: Estado, a, s2: Estado) -> float:
        return ((s2.t - s.t) + self.alfa * (s2.gasto - s.gasto)
                + self.beta * (s2.transb - s.transb))

    def e_objectivo(self, s: Estado) -> bool:
        return s.parag == self.destino

    def heuristica(self, s: Estado, nome: str = "h0") -> float:
        return self.h.valor(s, nome)

    # --- apresentação
    def descrever(self, s: Estado, a, s2: Estado) -> str:
        nome = self.rede.nomes
        if a[0] == "A":
            return (f"{hhmm(s.t)}  A pé: {nome[s.parag]} -> {nome[a[2]]} "
                    f"({s2.t - s.t} min), chega {hhmm(s2.t)}")
        L = self.rede.linhas[a[1]]
        if a[0] == "E":
            extra = "  [TRANSBORDO]" if s2.transb > s.transb else ""
            return (f"{hhmm(s.t)}  Espera {s2.t - s.t} min em {nome[s.parag]} e embarca em "
                    f"{L.nome} (parte {hhmm(s2.t)}, paga {a[4]} MT){extra}")
        return f"{hhmm(s.t)}    {L.nome}: {nome[s.parag]} -> {nome[a[2]]}, chega {hhmm(s2.t)}"


# ---------------------------------------------------------------- instâncias
def carregar_dados_rede(caminho: str) -> dict:
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)


def problema_de_instancia(dados_rede: dict, inst: dict, modo_ponta: str = "rampa",
                          alfa: Optional[float] = None, beta: Optional[float] = None) -> ProblemaViagem:
    rede = Rede(dados_rede, inst.get("paragens"), modo_ponta=modo_ponta)
    return ProblemaViagem(
        rede, inst["origem"], inst["destino"], inst["t0"], inst["limite"], inst["orcamento"],
        inst["alfa"] if alfa is None else alfa, inst["beta"] if beta is None else beta)
