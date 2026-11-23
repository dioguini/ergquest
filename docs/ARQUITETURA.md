# ErgQuest — Arquitetura

## 1. Visão geral

```
┌─────────────────────────── CLIENTE (desktop) ───────────────────────────┐
│  Sensores (BLE FTMS · ANT+ FE-C · cinta FC · footpod · remo)            │
│        ▼                                                                │
│  SensorHub ──► Física local (bicicleta/corrida/remo) ──► Avatar próprio │
│        │              ▲ declive/ERG para o rolo                         │
│        │              │                                                 │
│        ├─► HUD · telemóvel de pedidos · mapa · altimetria               │
│        │                                                                │
│        └─► Telemetria 1–4 Hz ──────────────┐   ◄── avatares remotos     │
└────────────────────────────────────────────┼───────(interpolados)──────┘
                                             │ WebSocket (TLS)
┌────────────────────────────── SERVIDOR ────┼────────────────────────────┐
│  Gateway de sessões                         ▼                           │
│  ├─ Shard de cidade (1 processo por cidade/zona)                        │
│  │   ├─ Física de verificação (mesmo código do cliente)                 │
│  │   ├─ Interest management (grelha espacial → quem vê quem)            │
│  │   ├─ OrderBoard por jogador (isolado: sem race conditions)           │
│  │   └─ Anti-cheat em linha (envelope, coerência, bot, física)          │
│  ├─ Serviço de desafios PvP (matchmaking, elegibilidade, resultados)    │
│  └─ Fila de eventos ──► Serviço analítico (fora do loop de jogo)        │
│                          ├─ TSS/rTSS, PMC (CTL/ATL/TSB), curvas         │
│                          ├─ Robustez (ginásio), progressão, XP          │
│                          ├─ Rankings / segmentos canónicos              │
│                          └─ Treinador → treinos (ERG/mundo/ecrã)        │
└─────────────────────────────────────────────────────────────────────────┘
```

### Princípios
1. **Um só núcleo de regras** (`ergquest/`), em Python puro e sem I/O, usado
   pelo cliente e pelo servidor. O que o cliente calcula, o servidor
   recalcula igual.
2. **O cliente manda na sua própria física** (latência zero na sensação de
   pedalar); o servidor **verifica**, não simula às cegas.
3. **Missões isoladas por jogador** no servidor: cada `OrderBoard` é um ator
   com estado próprio. Restaurantes são "fábricas" de pedidos, não recursos
   partilhados — nunca há disputa pelo mesmo pedido.
4. **O jogo em tempo real não espera pela análise.** As sessões terminadas
   entram numa fila; o serviço analítico calcula carga, progressão e
   rankings de forma assíncrona.

## 2. Rede

| Aspeto | Decisão |
| :--- | :--- |
| Transporte | WebSocket sobre TLS na fase 1 (simples, atravessa firewalls). UDP/QUIC só se a medição o justificar — a 1–4 Hz de telemetria a física local já esconde a latência. |
| Mensagens | `telemetry` (watts, FC, cadência/SPM, velocidade, distância na via, timestamp do sensor), `pos` (difundida a vizinhos), `order.*`, `challenge.*`. |
| Interpolação | Os avatares remotos são desenhados ~250 ms atrás, interpolados entre estados; extrapolação curta pela física se faltar um pacote. |
| Escala | Grelha espacial de 250 m por shard; cada jogador só recebe quem está nas células vizinhas. Centenas por cidade num único processo; mais → dividir por zona. |

## 3. Dados

| Armazém | Conteúdo |
| :--- | :--- |
| Estado quente (memória/Redis) | Posições, missões ativas, desafios em curso. |
| Base transacional (PostgreSQL) | Contas, perfis, desbloqueios, reputação, histórico de missões. |
| Armazém analítico | Amostras 1 Hz das sessões, `.fit` gerados, curvas, PMC diário. |
| Mapas | Grafo viário/fluvial do OSM + DEM, pré-processados offline em *tiles* por cidade. |

## 4. Componentes

### 4.1 Já no núcleo (`ergquest/shared`, `ergquest/training`)
| Componente | Estado |
| :--- | :--- |
| Física da bicicleta (potência ↔ velocidade, declive para o rolo) | feito |
| Carga: NP, TSS, rTSS, CTL/ATL/TSB | feito |
| Movimento por desporto, veículo e carga | feito |
| Treinos estruturados e cumprimento ±5 % | feito |

### 4.2 A construir
| Componente | Notas |
| :--- | :--- |
| Ligação a hardware: BLE (FTMS, potência, FC, CSC), ANT+ FE-C, remos FTMS | Só no cliente. Vários sensores em simultâneo, com prioridade por métrica. |
| Sensores simulados | Testes, *bots* de carga e NPCs. |
| Ficheiros `.fit` (escrever/ler), treinos `.zwo/.mrc/.erg` | Exportar para Strava, Garmin, TrainingPeaks. |
| Zonas, curva de potência, picos | Categorias W/kg e anti-cheat. |
| Mapas: grafo OSM + DEM, navegação, mapa 2D | `ergquest/world/` — feito; falta correr sobre os dados reais. |
| Registo de ginásio | Alimenta a Robustez. |
| Motor de recomendações | Prescreve os treinos e ajusta-se à carga que o jogo gerou. |
| Cliente gráfico: mundo 3D, HUD, telemóvel, mapa | Fase 1 em Python/pyglet. |

### 4.3 Altimetria: limites conhecidos
Os DEM públicos de 30 m (Copernicus GLO-30, SRTM) são modelos de **superfície**:
em ruas estreitas a célula vizinha pode ser um telhado. Mitigações no grafo:
- a cota do chão é o mínimo à volta do ponto;
- picos isolados nas interseções são corrigidos;
- os troços curtos são rampas uniformes;
- o rolo recebe a média de 40 m.

Os totais das subidas batem com a realidade (Rua do Alecrim ≈ 43 m, Castelo ≈
100 m, avenidas ribeirinhas planas). As ruas estreitas da Baixa ainda mostram
desníveis a mais. A solução é um modelo de **terreno** LiDAR de alta resolução.

## 5. Estrutura deste repositório

```
ergquest/
  shared/          núcleo partilhado por cliente e servidor
    physics.py     potência ↔ velocidade, declive
    load.py        NP, TSS, rTSS, PMC
    movement.py    esforço → movimento por desporto, veículo e carga
  training/        MODO TREINO
    workout.py     passos, alvo, cumprimento ±5 %
    setup.py       ERG ligado/desligado × mundo/ecrã; sugestão de caminhos
  game/            MODO JOGO e regras comuns
    session.py     modos TRAINING / MISSION / FREE, trocas de desporto
    missions.py    entregas, polícia, barco: telemóvel, prazos, estrelas
    errands.py     recados ad-hoc de NPCs (plano → compromisso)
    taxi.py        riquexó e bote-táxi: passageiros na física
    rowing.py      suavidade da remada
    chase.py       perseguição policial
    strength.py    Robustez (buff do ginásio)
    progression.py XP, níveis, desbloqueios (zonas, cidades, estabelecimentos)
    challenges.py  desafios PvP
    cities.py      catálogo de cidades, zonas, crits, velódromos
  world/           O MUNDO REAL
    osm.py         leitura OpenStreetMap, projeção local, acesso por desporto
    dem.py         altimetria Copernicus GLO-30 (GeoTIFF) ou SRTM (.hgt)
    graph.py       grafo: interseções, ruas com perfil, docas, âncoras
    navigation.py  rota mais rápida (física), posição, escolha nas interseções
    places.py      estabelecimentos fictícios em sítios reais
    mapview.py     mapa 2D (HTML/SVG)
    zones.py       caixas geográficas das zonas
  server/
    anticheat.py   validação da telemetria
  demo.py          um dia em Lisboa, sem hardware
tools/
  build_zone.py    descarrega OSM + DEM e constrói data/<zona>.json e .html
tests/
```
