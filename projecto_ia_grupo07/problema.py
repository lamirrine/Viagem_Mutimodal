"""Interface genérica de problemas de busca"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Hashable, Iterable, List, Optional, Tuple


class Problema(ABC):

    @abstractmethod
    def estado_inicial(self) -> Hashable:
        """Devolve o estado inicial."""

    @abstractmethod
    def accoes(self, s: Hashable) -> Iterable[Any]:
        """Acções aplicáveis em s"""

    @abstractmethod
    def resultado(self, s: Hashable, a: Any) -> Hashable:
        """Modelo de transição: estado que resulta de aplicar ``a`` em ``s``."""

    @abstractmethod
    def custo(self, s: Hashable, a: Any, s2: Hashable) -> float:
        """Custo (>= 0) do passo s --a--> s2."""

    @abstractmethod
    def e_objectivo(self, s: Hashable) -> bool:
        """Teste de objectivo."""

    def heuristica(self, s: Hashable, nome: str = "h0") -> float:
        """Estimativa do custo restante. Por omissão, h0 = 0."""
        return 0.0


class No:

    __slots__ = ("estado", "pai", "accao", "g", "profundidade")

    def __init__(self, estado, pai: Optional["No"] = None, accao: Any = None,
                 g: float = 0.0, profundidade: int = 0):
        self.estado = estado
        self.pai = pai
        self.accao = accao
        self.g = g
        self.profundidade = profundidade

    def __repr__(self) -> str: 
        return f"No({self.estado}, g={self.g:.2f}, prof={self.profundidade})"


def caminho(no: No) -> List[Tuple[Any, Hashable]]:
    """Reconstrói a solução: lista de pares (acção, estado) da raiz até ``no``."""
    passos: List[Tuple[Any, Hashable]] = []
    n: Optional[No] = no
    while n is not None:
        passos.append((n.accao, n.estado))
        n = n.pai
    passos.reverse()
    return passos
