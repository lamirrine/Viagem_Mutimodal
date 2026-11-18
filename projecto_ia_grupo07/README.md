# Projecto IA I 2026 — Grupo 07 (Laboral)
## P7 — Viagem multimodal Maputo–Matola–Katembe com horários
Algoritmo avançado: **Beam Search (k = 10; 100; 1000)** · Semente: **202607** (2026 × 100 + 7)

## Requisitos
Python ≥ 3.10; `pip install -r requirements.txt` (pytest, matplotlib, pandas, tabulate).
Nenhuma biblioteca de busca é usada: os 7 algoritmos estão implementados de raiz em `buscas.py`.

## Estrutura
| Ficheiro | Conteúdo |
|---|---|
| `problema.py` | classe abstracta `Problema`, classe `No`, função `caminho(no)` |
| `dominio.py` | rede dependente do tempo, estado, acções, custo, FIFO, `ProblemaViagem` |
| `buscas.py` | BFS, DFS, IDS, UCS, Gulosa, A*, Beam Search (genéricos) |
| `heuristicas.py` | h0, h1, h2; factor de ramificação efectivo b*; verificação h ≤ h* |
| `gerador.py` | rede base + horários + instâncias (semente 202607) |
| `experiencias.py` | bateria, CSV, tabelas, gráficos, b*, cenários α, análise do Beam |
| `visualizacao.py` | solução passo a passo, mapa ASCII/matplotlib |
| `main.py` | menu guiado: resolver, comparar os 12 algoritmos, escolher/criar viagem, alterar α/β |
| `tests/` | 30 testes pytest |
| `instancias/` | `rede_base.json`, `base.json`, `pequena_XX`, `media_XX`, `grande_XX` |
| `resultados/` | CSV, tabelas, gráficos |

## Como executar
```bash
python gerador.py                      # (re)gera rede e instâncias (determinístico)
python -m pytest -q                    # testes
python main.py                         # menu guiado (listas numeradas; Enter = valor recomendado)
python main.py --demo                  # instância base com A* h2
python experiencias.py                 # bateria completa (60 s e 2 GB por execução)
python experiencias.py --n 3 --limite-tempo 10   # versão rápida
python experiencias.py --extras        # b*, cenários alfa, análise do Beam, referência da base
python experiencias.py --so-graficos   # refaz tabelas e gráficos a partir do CSV
```

## Modelo (resumo)
* **Estado** `(parag, t, gasto, transb, linha, a_bordo)` — NamedTuple (imutável, hashable).
* **Acções** `E` esperar+embarcar (paga tarifa, conta transbordo se muda de linha), `V` viajar uma
  paragem a bordo, `A` caminhar (≤ 1,5 km, 5 km/h).
* **Custo** `c = Δt + α·Δdinheiro + β·Δtransbordos`; restrições: chegar até à hora-limite e gastar ≤ orçamento.
* **Hora de ponta** (06:00–08:30 e 16:30–19:00): tempo do chapa × 1,8, com rampa linear de 60 min
  fora da janela para preservar a propriedade **FIFO** (`Rede.verificar_fifo`).
* **h1** = distância em linha recta / velocidade máxima da rede. **h2** = tempo mínimo + α·tarifa mínima no
  grafo estático relaxado (`heuristicas.py`). Ambas admissíveis e consistentes (testes automáticos).

## Reprodutibilidade
Todos os resultados saem de `python gerador.py` + `python experiencias.py` com a semente 202607.
`resultados/ambiente.txt` regista a máquina. Tempos dependem da máquina; contagens de nós não.

## Git
Fazer commits regulares; todos os membros devem aparecer no histórico (podem editar ficheiros
no GitHub). A pasta `.git` entra no ZIP final `IA_PROJECTO_GRUPO_07_LAB.zip`.
