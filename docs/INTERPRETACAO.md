# ErgQuest — Interpretação do Conceito

Este documento lê o [conceito](CONCEITO.md) com olhos de quem o vai construir:
como se organiza o produto, onde as regras chocam umas com as outras, como as
resolvemos (e o código que já o faz), e o que fica para decidir.

---

## 1. Um atleta, duas intenções, um efeito colateral

O ErgQuest mistura jogo e treino, mas **não os confunde**. Em cada sessão o
atleta escolhe a sua intenção:

```
                     ┌──────────────── PERFIL ÚNICO ────────────────┐
                     │ FTP · limiares · peso · Robustez · nível · XP │
                     └───────────────────────┬───────────────────────┘
          ┌──────────────────────────────────┼──────────────────────────────────┐
          ▼                                  ▼                                  ▼
   TREINO (cumprir)                    JOGO (divertir-se)                LIVRE (andar)
   treino estruturado,           entregas · polícia · barco ·        Free Ride/Run/Row
   prescrito ou escolhido        recados ad-hoc · táxi               no mundo
          │                                  │                                  │
          └───────────────► EFEITO COLATERAL NA VIDA REAL ◄─────────────────────┘
                   a carga (TSS) de tudo entra na forma, fadiga e fitness
                                (CTL / ATL / TSB)
```

| | Treino | Jogo | Livre |
| :--- | :--- | :--- | :--- |
| Objetivo | cumprir o que o treino pede | fazer trabalhos, ganhar estrelas, desbloquear | andar, explorar |
| Mede-se por | cumprimento do alvo (% do tempo a ±5 %) | estrelas 1–5, prazos, conforto | — |
| Conta para a forma real | sim | **sim — o "side effect"** | sim |
| XP | sim (pelo esforço) | sim (esforço + estrelas) | sim (esforço) |
| Desbloqueia estabelecimentos | não | **sim** | não |
| Pode ser desafiado (PvP) | não | não, durante um trabalho | sim |

Código: `ergquest/game/session.py` (`Mode.TRAINING`, `Mode.MISSION`, `Mode.FREE`).

---

## 2. TREINO: ERG ligado/desligado × no mundo/só no ecrã

Um treino estruturado (prescrito pelo motor de recomendações ou escolhido) é
feito de uma de quatro maneiras (`ergquest/training/setup.py`):

| ERG | Onde | Quem manda | Como é |
| :--- | :--- | :--- | :--- |
| ligado | ecrã | **o rolo** (watts-alvo) | o treino no ecrã, só pedalar |
| ligado | mundo | **o rolo** (watts-alvo) | o avatar anda pelo mundo com a física e o declive real, mas o declive não se sente; o atleta escolhe os caminhos |
| desligado | mundo | **o atleta** (o rolo recebe o declive da estrada) | entra na estrada e cumpre o alvo com as mudanças, como lá fora; escolhe os caminhos nas interseções |
| desligado | ecrã | **o atleta** (rolo em plano) | só o treino no ecrã; cumpre o alvo com as mudanças |

- **Escolher o caminho com ERG desligado importa.** Uma rampa de 10 % num
  bloco de recuperação, ou uma descida num bloco de limiar, tornam o alvo
  difícil de cumprir. Em cada interseção o jogo **sugere** o ramo que encaixa
  nos próximos blocos (`rank_branches`, com a física real). A sugestão não
  obriga: as setas decidem.
- **Num passo livre** (sem alvo), mesmo com ERG ligado, o rolo passa a simulação.
- **O cumprimento** mede-se bloco a bloco: % do tempo a ±5 % do alvo
  (`ergquest/training/workout.py`).
- **Sem estrelas nem pedidos.** Um treino não é um trabalho do jogo.

---

## 3. JOGO: o "mood" de jogar

Sem treino marcado. O atleta vai divertir-se, e esse divertimento tem
**efeito colateral**: cansa (ATL), constrói forma (CTL) e muda o TSB de
amanhã, como qualquer treino. No jogo, dá XP e estrelas e **desbloqueia
estabelecimentos**: cada 5 trabalhos de um tipo abrem mais um restaurante,
esquadra ou operador fluvial (`Profile.establishments_unlocked`).

| Trabalho | Desporto | O que torna difícil | Código |
| :--- | :--- | :--- | :--- |
| Entrega de comida / encomendas | bicicleta | prazo + a comida arrefece; multi-pedidos em níveis altos | `missions.py` |
| Apoio à polícia | corrida | sprints do ladrão (anunciados 5 s antes, por causa da passadeira) | `chase.py` |
| Ferry / passeio de barco | remo | suavidade da remada | `rowing.py`, `missions.py` |
| **Recados ad-hoc** | bicicleta ou corrida | cumprir o plano aceite: paragens por ordem e prazo | `errands.py` |
| **Táxi** | riquexó (bicicleta) ou bote-táxi (remo) | **a massa dos passageiros muda a física**; conforto e segurança | `taxi.py` |

### 3.1 Recados ad-hoc ("moço dos recados")
Qualquer NPC pode acenar com um pedido: *«Vai ao alfaiate buscar o fato e
depois ao sapateiro buscar os sapatos.»* **Antes de aceitar**, o ErgQuest mostra
o plano calculado para *este* atleta:

```
Inês: «Vai ao alfaiate buscar o fato e depois ao sapateiro buscar os sapatos.»
  1. → Alfaiate do Largo    1.51 km  + 29 m
  2. → Sapateiro da Esquina 1.32 km  + 32 m · a carregar 1.5 kg
  3. → Casa de Inês         0.76 km  + 10 m · a carregar 2.7 kg
  Total 3.59 km, +72 m · prazo 31.8 min · precisa de 58% do limiar (Z2) · ~18 TSS · 185 XP
```

Ao aceitar, fica comprometido: tem de passar pelas paragens por ordem e chegar
dentro do prazo. O que se recolhe pelo caminho pesa nas pernas seguintes.
Falhar não apaga o esforço (a carga conta), mas não dá XP e custa reputação.

### 3.2 Táxi
Um riquexó tem 65 kg e muito mais arrasto. Com dois passageiros e bagagem
(+146 kg), a física muda por completo:

```
🚕 Riquexó → Castelo de São Jorge: Beatriz (52 kg + 5 kg), Rui (69 kg + 20 kg)
   1.85 km, +72 m · +146 kg a bordo
   sozinho 12.7 min · com eles 25.1 min · prazo 29.9 min
   rampa mais dura (9 %): ≥ 374 W para não ir mais devagar do que a pé
```

Os passageiros avaliam a **pontualidade**, o **conforto** (solavancos e
andar mais devagar do que a pé) e a **segurança** (velocidade a descer).
Conduzir um táxi exige **licença**: nível e Robustez mínimos. É aqui que o
ginásio se nota.

### 3.3 Prazos pessoais com margem em esforço
Todos os prazos se calculam com a física e os limiares do próprio atleta: o
prazo é o tempo a fazer o percurso a `intensidade × (1 − margem)`. A
intensidade sobe e a margem encolhe com o nível (65 % → 85 % do limiar;
margem 20 % → 4 %). Medir a folga em esforço, e não em minutos, é
importante: na bicicleta a velocidade cresce com a raiz cúbica da potência,
e uma folga de 50 % no tempo dava prazos que se cumpriam a passear.

---

## 4. Tensões no conceito e como as resolvemos

### 4.1 "Atributos que evoluem" vs. e-sport justo
**A velocidade no mundo vem só da física** (watts, peso, veículo, carga,
declive). O nível nunca dá velocidade, senão um jogador antigo ganhava a um
atleta mais forte. Há dois tipos de atributo:
- **Capacidades medidas** (FTP, curva de potência, limiares, CTL/ATL/TSB): vêm dos dados.
- **Atributos de jogo** (nível, XP, reputação, desbloqueios, licenças): sobem com o jogo e o esforço, sem mexer na física.

Por isso "qualquer nível desafia qualquer nível" funciona. Os rankings usam
**categorias por W/kg**.

### 4.2 O *buff* do ginásio
O ginásio não multiplica watts. Alimenta a **Robustez** (0–1, regularidade
nas últimas 4 semanas, `strength.py`), que:
- multiplica o XP (0,85× → 1,15×);
- abre os escalões altos de nível (é o "potencial máximo");
- dá mais pedidos em simultâneo e encomendas mais pesadas;
- dá a **licença de táxi**.

Nunca conta nos desafios PvP. Como o ginásio não é verificável, uma sessão com
FC registada vale mais do que uma manual.

### 4.3 Rankings por restaurante com pedidos instanciados
Cada fonte de pedidos tem **entregas canónicas** (pares fixos, como os
segmentos Strava). O ranking usa só essas.

### 4.4 Ergómetros não viram
As setas escolhem o ramo na **próxima interseção**. No remo, o barco segue
o canal do rio.

### 4.5 Trocar bicicleta ↔ corrida é físico
Fecha-se a sessão (com o seu `.fit`), a bicicleta fica no ponto de troca e o
mundo espera que o atleta mude de máquina. Não se troca com trabalhos em curso.

### 4.6 Pausar vs. abandonar
Pausar é livre: o prazo congela e a comida arrefece a 25 %. **Abandonar**
anula o trabalho e custa reputação (mais se já levava a comida ou o passageiro).

---

## 5. Mundo *endless* com cidades reais
- Ruas e rios do OpenStreetMap (licença ODbL, exige atribuição). Altimetria de um DEM público (Copernicus GLO-30 ou SRTM).
- Os estabelecimentos são fictícios e gerados por semente sobre os edifícios reais. A mesma semente dá a mesma cidade a todos.
- Os pedidos, recados e corridas de táxi geram-se a partir do grafo e nunca se esgotam.

## 6. Anti-cheat
Validação no servidor (`server/anticheat.py`), com cinco verificações:
1. limites humanos de W/kg;
2. coerência entre sensores (potência sem cadência, FC parada ou que não responde);
3. assinatura de bot (potência sem variação humana, degraus impossíveis);
4. distância recalculada pela física;
5. tempo das amostras.

O resultado é uma confiança por sessão. Uma sessão suspeita sai dos rankings
e vai para revisão; nunca há ban automático.

## 7. Decisões em aberto
1. **Cliente gráfico:** recomendo Python/pyglet na fase 1. Mais tarde, um motor de jogo (Godot), com os sensores num processo Python local.
2. **Navegador:** não recomendo. O Bluetooth do browser não tem ANT+ nem funciona em Safari ou Firefox.
3. **Treino no ecrã dá XP?** Assumi que sim (pelo esforço). A alternativa é só o treino no mundo contar para o jogo.
4. **Táxi a pé?** Assumi riquexó e bote-táxi. A corrida fica com recados e polícia.
5. **Registo do ginásio:** manual, importado (Garmin), ou ambos?
6. **Modelo de negócio** e **primeira cidade jogável** (proponho Lisboa: Baixa → Chiado → Castelo, e o Tejo).
