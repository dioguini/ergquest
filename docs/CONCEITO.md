# ErgQuest — Documento de Conceito e Arquitetura de Jogo

> Documento original do conceito, guardado tal como foi escrito. A leitura
> crítica, as decisões tomadas e as perguntas em aberto estão em
> [INTERPRETACAO.md](INTERPRETACAO.md).

**Visão:** Um mundo virtual *endless* que funde e-sport e treino indoor por ERG — combinando a imersão de mundo aberto do **Zwift**, a componente social/competitiva do **Strava** e a gestão fisiológica do **TrainingPeaks**.
**Repositório alvo:** [`dioguini/ergquest`](https://github.com/dioguini/ergquest)

---

## 1. Pilar Central: Perfil Único e as 4 Modalidades

Cada jogador controla um único atleta cujos atributos evoluem com base no esforço físico real. As modalidades complementam-se, obrigando a um treino equilibrado em vez de especialização isolada.

| Modalidade | Presença no Mundo Virtual | Tipo de Missões / Atividade | Mecânica Específica |
| :--- | :--- | :--- | :--- |
| **Ciclismo** | Sim (ruas, velódromos, circuitos) | Entregas de comida (estilo Uber Eats) e pequenas encomendas. | Gestão de tempo de arrefecimento da comida; multi-pedidos em níveis altos. |
| **Corrida** | Sim (ruas e zonas urbanas) | Entregas rápidas e apoio à polícia na perseguição de ladrões em fuga. | Picos de intensidade/sprint em perseguições; transição rápida a pé. |
| **Remo** | Sim (rios e barragens) | Entregas fluviais entre margens/docas e passeios contratados por empresas. | Qualidade técnica da remada ("suavidade" sem solavancos para passageiros). |
| **Ginásio** | Não (registo complementar) | Registo de sessões de força realizadas fora do mundo virtual. | **Efeito de *Buff* (*Side Effect*):** o treino de força é necessário para desbloquear o potencial máximo de desempenho no ciclismo, corrida e remo. |

---

## 2. Ciclo de Jogo (*Core Loop*), Missões e Navegação

### Interface de Pedidos ("Telemóvel")
- **Pedidos não sincronizados:** As missões surgem numa interface estilo ecrã de telemóvel. As fontes de pedidos são instanciadas por jogador (o Restaurante A pode emitir pedidos simultâneos para vários jogadores sem conflito).
- **Escalabilidade de dificuldade:** A exigência aumenta com o nível do atleta — prazos de entrega mais curtos, maior penalização térmica (comida fria) e exigência de maior suavidade na remada.
- **Multi-tarefa avançada:** Em níveis superiores, o jogador pode acumular múltiplos pedidos em simultâneo dentro da mesma modalidade (ex.: recolher no Restaurante A e aceitar logo um pedido no Restaurante B).
- **Avaliação e Penalizações:**
  - Cada missão concluída gera um **rating de 1 a 5 estrelas**.
  - É sempre possível **pausar ou terminar** a sessão; contudo, abandonar a meio de uma missão anula-a e aplica uma penalização no perfil/rating.

### Navegação, Transições e HUD
- **Controlo de rota:** Durante uma missão existe uma rota sugerida por GPS (mais rápida), mas o jogador pode escolher desvios manuais usando as setas do teclado (estilo Zwift).
- **Pontos de troca (Ciclismo ↔ Corrida):** Existe um ponto de troca em cada rua. Ao trocar de desporto, a bicicleta fica lá guardada, a sessão atual termina e inicia-se automaticamente a nova sessão.
- **Acesso ao Remo:** O jogador tem de se deslocar até junto do rio ou barragem para iniciar treinos ou missões de remo.
- **Modo Livre (*Free Ride/Run/Row*):** Possibilidade de entrar no mundo apenas para treinar livremente, ou continuar em modo livre após concluir uma missão. Toda a distância, tempo e esforço contam para a progressão.
- **HUD em ecrã:** Métricas de output em tempo real (potência/watts, frequência cardíaca, etc.) e perfil de altimetria visível durante missões.

---

## 3. Mundo Virtual, Mapas e Progressão (*Endless*)

- **Mapas iniciais:** **Londres**, **Lisboa** e **Nova Iorque**.
- **Fidelidade inicial:** Os mapas replicam a **geografia e altimetria reais** das cidades, mas o *rendering* visual e os estabelecimentos (restaurantes, esquadras, empresas fluviais) serão **fictícios** nesta fase.
- **Sistema de Desbloqueios:** A evolução de nível e consistência física desbloqueia progressivamente:
  - Novas zonas dentro da mesma cidade e novas cidades.
  - Novos clientes e fontes de pedidos (restaurantes, esquadras, operadores turísticos).
  - Novos desafios competitivos.
- **Mundo Povoado:** Convivência simultânea entre **NPCs** (peões e ciclistas que dão vida às ruas) e **outros jogadores reais** (em missões, treinos estruturados ou modo livre).

---

## 4. Fisiologia e Treino Individualizado

- **Métricas de Carga (estilo TrainingPeaks):** Cada sessão impacta a condição física do atleta (Forma, Fadiga, Carga/Fitness), criando uma ponte direta entre o esforço real e o estado do avatar.
- **Motor de Recomendações:** O jogo analisa a evolução do atleta e sugere treinos individualizados (incluindo o equilíbrio com o ginásio) para melhorar a capacidade física real, refletindo-se depois no rendimento competitivo dentro do jogo.

---

## 5. E-Sport, Rankings e Desafios PvP

### Recompensas e Classificações
- **Rewards Individuais:** Objetivos pessoais de volume ou consistência (ex.: X entregas concluídas num mês).
- **Rankings Globais:** Tabelas competitivas por especialidade e local (ex.: entregador mais rápido do Restaurante X, melhor ajudante da polícia, remador com a remada mais suave).

### Desafios Instantâneos ("No Momento")
- **Elegibilidade:** Disponível apenas entre jogadores que **não** estejam em missão nem em treino individualizado.
- **Regra de Acesso *Cross-City* e *Cross-Level*:** Qualquer nível pode desafiar qualquer nível. Se um jogador for desafiado para uma cidade que ainda não desbloqueou, **pode viajar lá para competir**, mas continua impedido de propor desafios nessa cidade até a desbloquear.
- **Formatos de Desafio:**
  - **Segmentos / Rotas:** Segmentos estilo Strava ou percursos predefinidos na cidade.
  - **Modo *Free*:** O desafiante desenha o ponto de partida, trajeto e meta diretamente no mapa.
  - **Criterium (Crit) Outdoor:** Circuitos urbanos fechados definidos em cada cidade.
  - **Criterium (Crit) Indoor:** 3 pistas de criterium indoor por cidade.
  - **Velódromo:** 1 velódromo por cidade com as várias modalidades oficiais de pista.

---

## 6. Arquitetura Técnica, Segurança e Pontos Críticos

- **Concorrência e Rede (*Multiplayer*):** Sincronização de posições em tempo real (WebSockets/UDP com interpolação no cliente) para suportar dezenas/centenas de jogadores por mapa sem *lag*, mantendo os pedidos de missão isolados no servidor por utilizador para evitar *race conditions*.
- **Segurança e *Anti-Cheat*:** Validação do lado do servidor (*server-side*) dos dados de telemetria (potência, ritmo cardíaco, cadência/SPM e curva de velocidade) para detetar anomalias físicas, *bots* ou adulteração de sensores Bluetooth/ANT+.
- **Gestão de Sessões e Persistência:** Separação clara entre o motor de jogo em tempo real e a base de dados analítica de treino (para calcular métricas estilo TrainingPeaks sem criar *bottlenecks* no servidor de jogo).
- **Núcleo partilhado:** Ligação a hardware FTMS/FE-C, leitura de GPX, modelo de dados de treino e UI organizados como núcleo partilhado antes de construir a camada de jogo e *multiplayer*.
