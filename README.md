# ErgQuest

**Um mundo virtual *endless* que mistura treino e jogo indoor por ERG.**
Lisboa, Londres e Nova Iorque com a geografia e a altimetria reais. O
mesmo atleta pode:

- **Treinar**: cumprir um treino estruturado com ERG ligado ou desligado, na
  estrada virtual (escolhendo os caminhos) ou só no ecrã.
- **Jogar**: entregar comida, ajudar a polícia, fazer passeios de barco,
  aceitar recados de NPCs ou conduzir um táxi de riquexó. Dá XP e estrelas
  e desbloqueia restaurantes, esquadras e operadores fluviais.

Seja qual for a intenção, há um **efeito colateral na vida real**: a carga
entra na forma, na fadiga e no fitness (CTL/ATL/TSB).

| Documento | Conteúdo |
| :--- | :--- |
| [docs/CONCEITO.md](docs/CONCEITO.md) | O conceito original. |
| [docs/INTERPRETACAO.md](docs/INTERPRETACAO.md) | Leitura crítica: a tese, as tensões do conceito e como as resolvemos, decisões em aberto. |
| [docs/ARQUITETURA.md](docs/ARQUITETURA.md) | Cliente/servidor, rede, dados e componentes. |
| [docs/MUNDO.md](docs/MUNDO.md) | O mundo: mapa de terra (ciclismo e corrida) e mapa do rio (remo), níveis por modalidade, aparelhos e troca de desporto, pontes, serras, limites. |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Fases F0–F6. |

## Experimentar

Python ≥ 3.11, sem dependências.

```bash
python -m ergquest.demo                          # uma manhã de trabalho em Lisboa, sem hardware
python -m unittest discover -s tests -t .        # testes
python tools/build_metro.py                      # refaz o mapa da Área Metropolitana (precisa de rede)
```

A demo mostra um dia na Área Metropolitana de Lisboa (`data/lisboa-metro.json.gz`).
A Ana tem ciclismo 9, corrida 4 e remo 1, e tem rolo, passadeira e banda
cardíaca, mas não tem remo:
1. **Treino** 3 × 6′ ao limiar, com ERG desligado e no mundo.
2. **Jogo**: uma entrega de comida de bicicleta.
3. **Troca** para a corrida: o jogo verifica a passadeira e o mapa passa a ter
   as zonas da corrida. Tenta remar e não pode, porque não tem remo. Faz um
   recado a pé.
4. **Jogo**: um riquexó com dois passageiros até ao Castelo.
5. **Efeito colateral**: a forma real é uma só; o XP vai para cada modalidade.
6. **Livre**: chega ao limite da zona Oeste e o GPS leva-a de volta.
7. **Experiente**: o Rui (ciclismo 20, remo 14) atravessa a ponte e o rio.

## Banco de testes de aparelhos (Windows)

Para ligar e testar os aparelhos reais (rolo, banda cardíaca, remo) sem o jogo:
duplo clique em **`bancada.bat`**. Abre uma página no browser com:
- procura e ligação Bluetooth;
- dados em direto;
- ERG e declive do rolo;
- gravação de capturas para protocolos próprios;
- passadeira manual;
- verificação por modalidade.

O guia completo está em [docs/BANCADA.md](docs/BANCADA.md). Para experimentar sem
aparelhos, usa `bancada-simulada.bat` (ou `python -m ergquest.bench --sim`).

## O que já existe

| Módulo | O quê |
| :--- | :--- |
| `ergquest/shared/physics.py`, `load.py` | Física da bicicleta e carga (NP, TSS, rTSS, PMC). |
| `ergquest/shared/movement.py` | Esforço → movimento em bicicleta, corrida e remo, com veículos (riquexó, bote-táxi) e carga. |
| `ergquest/training/workout.py` | Treinos estruturados e cumprimento ±5 %. |
| `ergquest/training/setup.py` | ERG ligado/desligado × mundo/ecrã: o que o rolo recebe; sugestão de caminhos que encaixam nos blocos. |
| `ergquest/game/missions.py` | Telemóvel de pedidos por jogador, prazos pessoais, arrefecimento da comida, estrelas, pausa, abandono. |
| `ergquest/game/errands.py` | Recados ad-hoc de NPCs: plano antes de aceitar, paragens por ordem, prazo. |
| `ergquest/game/taxi.py` | Táxi (riquexó, bote-táxi): passageiros na física, cotação, conforto, segurança, licença. |
| `ergquest/game/rowing.py`, `chase.py` | Suavidade da remada; perseguição policial. |
| `ergquest/game/strength.py`, `progression.py` | Robustez (buff do ginásio); XP e nível **por modalidade** (ciclismo, corrida, remo); desbloqueios de zonas, cidades e estabelecimentos. |
| `ergquest/game/session.py`, `challenges.py`, `cities.py` | Modos de sessão, trocas de desporto, desafios PvP, catálogo de cidades, crits e velódromos. |
| `ergquest/world/` | O mundo real: Área Metropolitana de Lisboa (OpenStreetMap + Copernicus) → grafo jogável com 9 zonas, pontes e travessias bloqueadas por nível, rede de remo com docas, estradas de ligação nas extremidades e duas serras; GPS pela física de cada atleta, limites, meia-volta e regresso; destinos nas duas margens para experientes; mapa interativo. |
| `ergquest/devices/` | Bluetooth (FTMS, FC, potência, passada) e ANT+ (FE-C, FC, potência, passada): leitura, ERG e declive; o que cada desporto exige; verificação na troca de desporto; adaptadores para aparelhos sem FTMS (remo Domyos, passadeira manual), com os dados estimados fora dos rankings. |
| `ergquest/bench/` | Banco de testes de aparelhos: servidor local + página (Bluetooth real ou simulado), capturas para descodificar protocolos. |
| `ergquest/server/anticheat.py` | Validação da telemetria: limites humanos, coerência de sensores, bots, física. |

## Dados de mapa

Ruas © contribuidores do OpenStreetMap (ODbL), via Overture Maps; locais © Overture Maps Foundation; altimetria Copernicus GLO-30.
Ver [data/LICENCA.md](data/LICENCA.md).
