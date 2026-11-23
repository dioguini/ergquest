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
| [docs/ROADMAP.md](docs/ROADMAP.md) | Fases F0–F6. |

## Experimentar

Python ≥ 3.11, sem dependências.

```bash
python -m ergquest.demo                          # uma manhã de trabalho em Lisboa, sem hardware
python -m unittest discover -s tests -t .        # testes
python tools/build_zone.py lisboa-centro         # descarrega e constrói Lisboa (precisa de rede)
```

A demo mostra um dia da Ana nas ruas reais de Lisboa (`data/lisboa-centro.json`):
1. **Treino** 3 × 6′ ao limiar, com ERG desligado e no mundo. No Cais do Sodré o
   jogo avalia os ramos reais da interseção e sugere o que encaixa nos blocos.
2. **Jogo**: uma entrega de comida.
3. **Jogo**: um recado ad-hoc, com o plano mostrado antes de aceitar.
4. **Jogo**: um riquexó com dois passageiros da Praça do Comércio ao Castelo, pela
   rota do GPS (Madalena, Limoeiro, Rua de Santiago), onde a física muda.
5. **Efeito colateral**: a carga, o CTL/ATL/TSB, o XP e os desbloqueios.

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
| `ergquest/game/strength.py`, `progression.py` | Robustez (buff do ginásio); XP, níveis, desbloqueios de zonas, cidades e estabelecimentos. |
| `ergquest/game/session.py`, `challenges.py`, `cities.py` | Modos de sessão, trocas de desporto, desafios PvP, catálogo de cidades, crits e velódromos. |
| `ergquest/world/` | O mundo real: OpenStreetMap + altimetria → grafo jogável (interseções, ruas com perfil, acesso por desporto, docas), rota mais rápida pela física de cada atleta, escolha nas interseções, estabelecimentos fictícios em sítios reais, mapa 2D. |
| `ergquest/server/anticheat.py` | Validação da telemetria: limites humanos, coerência de sensores, bots, física. |

## Dados de mapa

Ruas © contribuidores do OpenStreetMap (ODbL); altimetria Copernicus GLO-30.
Ver [data/LICENCA.md](data/LICENCA.md).
