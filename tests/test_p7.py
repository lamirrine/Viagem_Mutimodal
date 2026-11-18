"""Testes do P7 (>= 15). Mini-rede de 6 paragens com resultados calculados à mão.

Mini-rede (paragens 0..4 em linha, a ~2,2 km umas das outras; paragem 5 a ~0,56 km da 0):
    Linha A  chapa     0-1-2     cum 0,5,10   cada 10 min a partir das 06:00  tarifa 10 MT
    Linha B  autocarro 2-3-4     cum 0,6,12   partidas 12:15 e 12:40           tarifa  8 MT
    Linha C  comboio   0-4       cum 0,25     partidas 12:05 e 12:45            tarifa 20 MT
Partida às 12:00 (720) em 0, destino 4.
    Comboio:      espera 5 + 25 de viagem, chega 12:30 (750), 20 MT, 0 transbordos
    Chapa+autoc.: chega a 2 às 12:10, espera até 12:15, chega 12:27 (747), 18 MT, 1 transbordo
"""
import math

import pytest

from buscas import astar, beam, bfs, dfs, gulosa, ids, ucs
from dominio import Estado, ProblemaViagem, Rede, problema_de_instancia
from gerador import SEMENTE, construir_rede_base, gerar_instancias
from heuristicas import (b_estrela, enumerar_estados, h_estrela, verificar_admissibilidade,
                         verificar_consistencia)
from problema import Problema, caminho

PARAMS = {"fator_desvio": 1.3, "vel_a_pe_kmh": 5.0, "max_a_pe_m": 1500,
          "ponta": [[360, 510], [990, 1140]], "mult_ponta": 1.8, "rampa_min": 60}


def mini_dados():
    pars = [{"id": i, "nome": f"P{i}", "zona": "X", "lat": -25.90 + 0.02 * i, "lon": 32.5}
            for i in range(5)]
    pars.append({"id": 5, "nome": "P5", "zona": "X", "lat": -25.895, "lon": 32.5})
    linhas = [
        {"nome": "A", "modo": "chapa", "paragens": [0, 1, 2], "cum": [0, 5, 10], "tarifa": 10,
         "intervalo": 10, "fase": 0, "inicio": 360, "fim": 1200},
        {"nome": "B", "modo": "autocarro", "paragens": [2, 3, 4], "cum": [0, 6, 12], "tarifa": 8,
         "viagens": [735, 760]},
        {"nome": "C", "modo": "comboio", "paragens": [0, 4], "cum": [0, 25], "tarifa": 20,
         "viagens": [725, 765]},
    ]
    return {"parametros": PARAMS, "paragens": pars, "linhas": linhas, "modos": {}}


def mini(alfa=1.0, beta=10.0, limite=900, orcamento=100, destino=4, origem=0):
    return ProblemaViagem(Rede(mini_dados()), origem, destino, 720, limite, orcamento, alfa, beta)


@pytest.fixture(scope="session")
def dados():
    return construir_rede_base()


@pytest.fixture(scope="session")
def inst_pequenas(dados):
    return gerar_instancias(dados, "pequena", 3)


def problema_de(dados, inst, **kw):
    return problema_de_instancia(dados, inst, **kw)


# ---------------------------------------------------------------- formulação
def test_estado_inicial_imutavel_e_hashable():
    p = mini()
    s0 = p.estado_inicial()
    assert s0 == Estado(0, 720, 0, 0, -1, 0)
    assert hash(s0) == hash(Estado(0, 720, 0, 0, -1, 0))
    with pytest.raises(AttributeError):
        s0.t = 5


def test_sucessores_de_estado_conhecido():
    p = mini()
    acs = p.accoes(p.estado_inicial())
    # linha A (idx 0) parte às 12:00 da paragem 0; comboio C (idx 2) às 12:05; a pé até P5 (9 min)
    assert ("E", 0, 0, 720, 10) in acs
    assert ("E", 2, 0, 725, 20) in acs
    assert ("A", -1, 5, 729, 0) in acs
    assert len(acs) == 3


def test_transicao_e_custo_de_embarcar_e_viajar():
    p = mini()
    s0 = p.estado_inicial()
    a = ("E", 2, 0, 725, 20)
    s1 = p.resultado(s0, a)
    assert s1 == Estado(0, 725, 20, 0, 2, 1)
    assert p.custo(s0, a, s1) == pytest.approx(5 + 1.0 * 20)       # espera 5 + alfa * 20
    s2 = p.resultado(s1, ("V", 2, 4, 750, 0))
    assert s2 == Estado(4, 750, 20, 0, 2, 1)
    assert p.e_objectivo(s2) and not p.e_objectivo(s1)


def test_transbordo_conta_quando_a_linha_muda():
    p = mini()
    s = Estado(2, 730, 10, 0, 0, 1)          # a bordo da linha A em P2
    acs = p.accoes(s)
    assert ("E", 1, 2, 735, 8) in acs        # embarcar no autocarro B
    s2 = p.resultado(s, ("E", 1, 2, 735, 8))
    assert s2.transb == 1
    assert p.custo(s, ("E", 1, 2, 735, 8), s2) == pytest.approx(5 + 8 + 10)  # beta = 10


def test_restricoes_hora_limite_e_orcamento():
    a_normal = mini().accoes(mini().estado_inicial())
    assert mini(limite=724).accoes(mini().estado_inicial()) != a_normal   # comboio sai às 12:05
    p = mini(orcamento=15)                   # não chega para o comboio (20 MT), chega para o chapa
    tipos = {(a[0], a[1]) for a in p.accoes(p.estado_inicial())}
    assert ("E", 2) not in tipos and ("E", 0) in tipos


def test_hora_de_ponta_e_rampa():
    r = Rede(mini_dados())
    assert r.mult_ponta(7 * 60) == pytest.approx(1.8)
    assert r.mult_ponta(12 * 60) == pytest.approx(1.0)
    assert r.mult_ponta(5 * 60 + 30) == pytest.approx(1.4)
    assert Rede(mini_dados(), modo_ponta="degrau").mult_ponta(5 * 60 + 30) == 1.0
    assert r.hop(r.linhas[0], 0, 7 * 60) == math.ceil(5 * 1.8)   # 9 min em hora de ponta


def test_fifo_da_rede_gerada_e_violacao_do_modelo_degrau(dados):
    assert Rede(dados).verificar_fifo(passo=3) == []
    assert len(Rede(dados, modo_ponta="degrau").verificar_fifo(passo=3)) > 0


# ---------------------------------------------------------------- algoritmos
def test_optimo_depende_de_alfa_e_beta():
    r = astar(mini(alfa=1.0, beta=10.0), "h2")
    assert r.ok and r.custo == pytest.approx(50.0) and r.comprimento == 2     # comboio
    r = astar(mini(alfa=0.0, beta=0.0), "h2")
    assert r.ok and r.custo == pytest.approx(27.0)                            # chapa + autocarro


def _sem_solucao(alg):
    p = mini(orcamento=5, origem=1, destino=4)   # sem dinheiro para nenhum serviço, sem a pé
    return {"bfs": lambda: bfs(p), "ucs": lambda: ucs(p), "astar": lambda: astar(p, "h0"),
            "gulosa": lambda: gulosa(p, "h1"), "ids": lambda: ids(p, 10),
            "dfs": lambda: dfs(p, 10), "beam": lambda: beam(p, 10)}[alg]()


@pytest.mark.parametrize("alg", ["bfs", "ucs", "astar", "gulosa", "ids", "dfs", "beam"])
def test_instancia_sem_solucao(alg):
    assert _sem_solucao(alg).estado == "sem_solucao"


def test_hora_limite_impossivel_nao_tem_solucao():
    assert ucs(mini(limite=740)).estado == "sem_solucao"   # comboio chega 12:30? (750) e chapa+bus 12:27 (747)


def test_ucs_e_astar_devolvem_o_mesmo_custo(dados, inst_pequenas):
    for inst in inst_pequenas:
        c = ucs(problema_de(dados, inst)).custo
        for h in ("h0", "h1", "h2"):
            assert astar(problema_de(dados, inst), h).custo == pytest.approx(c)


def test_astar_h2_expande_menos_que_h1_que_h0(dados, inst_pequenas):
    exp = {h: sum(astar(problema_de(dados, i), h).metricas.expandidos for i in inst_pequenas)
           for h in ("h0", "h1", "h2")}
    assert exp["h2"] <= exp["h1"] <= exp["h0"]


def test_bfs_ids_minimas_accoes_mas_nao_minimo_custo(dados, inst_pequenas):
    for inst in inst_pequenas:
        o = ucs(problema_de(dados, inst))
        b = bfs(problema_de(dados, inst))
        i = ids(problema_de(dados, inst), 40)
        assert b.comprimento <= o.comprimento and b.comprimento == i.comprimento
        assert b.custo >= o.custo - 1e-9 and i.custo >= o.custo - 1e-9
        assert i.metricas.reexpandidos >= 0


def test_dfs_e_gulosa_nao_sao_melhores_que_o_optimo(dados, inst_pequenas):
    for inst in inst_pequenas:
        o = ucs(problema_de(dados, inst)).custo
        assert dfs(problema_de(dados, inst), 40).custo >= o - 1e-9
        assert gulosa(problema_de(dados, inst), "h2").custo >= o - 1e-9


def test_beam_largo_e_optimo_e_k_pequeno_nunca_melhora(dados, inst_pequenas):
    for inst in inst_pequenas:
        o = ucs(problema_de(dados, inst)).custo
        assert beam(problema_de(dados, inst), 1000).custo == pytest.approx(o)
        r = beam(problema_de(dados, inst), 1)
        assert (not r.ok) or r.custo >= o - 1e-9


def test_caminho_reconstroi_a_solucao():
    p = mini()
    r = astar(p, "h2")
    c = caminho(r.no)
    assert c[0] == (None, p.estado_inicial()) and len(c) == r.comprimento + 1
    assert c[-1][1].parag == 4
    for (a, s), (_, s_ant) in zip(c[1:], c[:-1]):
        assert p.resultado(s_ant, a) == s


class Grafo(Problema):
    """Outro domínio (grafo explícito): os algoritmos não conhecem o P7."""
    ARESTAS = {"S": [("A", 1), ("B", 4)], "A": [("B", 2), ("G", 12)], "B": [("G", 5)], "G": []}

    def estado_inicial(self): return "S"
    def accoes(self, s): return self.ARESTAS[s]
    def resultado(self, s, a): return a[0]
    def custo(self, s, a, s2): return a[1]
    def e_objectivo(self, s): return s == "G"


def test_algoritmos_sao_genericos():
    assert ucs(Grafo()).custo == 8 and astar(Grafo()).custo == 8     # S-A-B-G = 1+2+5
    assert bfs(Grafo()).comprimento == 2 and ids(Grafo(), 5).comprimento == 2


# ---------------------------------------------------------------- heurísticas
def _pequena_minima(inst_pequenas):
    return min(inst_pequenas, key=lambda i: i["limite"] - i["t0"])


def test_admissibilidade_h1_h2_todos_os_estados_da_instancia_pequena(dados, inst_pequenas):
    p = problema_de(dados, _pequena_minima(inst_pequenas))
    estados, arestas = enumerar_estados(p)
    hstar = h_estrela(p, estados, arestas)
    assert len(estados) > 50
    for h in ("h0", "h1", "h2"):
        assert verificar_admissibilidade(p, h, estados, hstar) == []


def test_consistencia_e_dominancia_h2_sobre_h1(dados, inst_pequenas):
    p = problema_de(dados, _pequena_minima(inst_pequenas))
    estados, arestas = enumerar_estados(p)
    for h in ("h1", "h2"):
        assert verificar_consistencia(p, h, arestas) == []
    assert all(p.heuristica(s, "h2") >= p.heuristica(s, "h1") - 1e-9 for s in estados)


def test_h2_admissivel_e_consistente_a_bordo_na_minirede():
    p = mini(alfa=1.0, beta=10.0)
    est, ar = enumerar_estados(p)
    hs = h_estrela(p, est, ar)
    assert verificar_admissibilidade(p, "h2", est, hs) == []
    assert verificar_consistencia(p, "h2", ar) == []


def test_factor_de_ramificacao_efectivo():
    assert b_estrela(12, 2) == pytest.approx(3.0, abs=1e-6)     # 12 + 1 = 1 + 3 + 9
    assert b_estrela(30, 1) == pytest.approx(30.0, abs=1e-4)
    assert 1.0 < b_estrela(500, 6) < 4.0


# ---------------------------------------------------------------- gerador
def test_gerador_reproduzivel_com_a_semente(dados):
    assert SEMENTE == 2026 * 100 + 7 == 202607
    assert gerar_instancias(dados, "pequena", 2) == gerar_instancias(dados, "pequena", 2)
    assert construir_rede_base() == construir_rede_base()


def test_instancias_geradas_tem_solucao(dados):
    for nivel in ("pequena", "media", "grande"):
        for inst in gerar_instancias(dados, nivel, 2):
            assert astar(problema_de(dados, inst), "h2", limite_s=30).ok


def test_rede_tem_requisitos_do_enunciado(dados):
    assert len(dados["paragens"]) >= 25
    modos = {l["modo"] for l in dados["linhas"]}
    assert {"chapa", "autocarro", "comboio", "ferry"} <= modos      # + a pé = 5 modos
    assert dados["parametros"]["vel_a_pe_kmh"] == 5.0 and dados["parametros"]["max_a_pe_m"] == 1500
