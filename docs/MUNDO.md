# ErgQuest — O mundo: Área Metropolitana de Lisboa

O mundo é a Área Metropolitana de Lisboa, com as estradas e a altimetria reais.
Tem **dois mapas**, e cada modalidade **evolui sozinha**, porque um atleta não é
obrigado a ter todos os ergómetros em casa.

| Modalidade | Mapa | Escada de zonas | Nível |
| :--- | :--- | :--- | :--- |
| Ciclismo | terra | §1 | próprio |
| Corrida | terra (o **mesmo** do ciclismo) | §1 (a mesma) | próprio |
| Remo | rio | §3 | próprio |
| Ginásio | — (fora do mundo) | — | sem nível: dá Robustez, que vale para todos |

- **Regras** (zonas, ordem, níveis, pontes, rio, serras): `ergquest/world/metro.py`.
- **Construção do mapa:** `ergquest/world/metrobuild.py` e `tools/build_metro.py`.
- **O que cada atleta pode usar, por desporto:** `ergquest/world/access.py`.
- **Aparelhos e troca de desporto:** `ergquest/devices/` e `ergquest/game/session.py`.

## 1. Mapa de terra (ciclismo e corrida)

**Só pavimento:** asfalto ou calçada. Ficam de fora:
- escadas (165 km);
- trilhos e caminhos (8 716 km);
- troços de terra ou gravilha (948 km);
- passeios desenhados à parte das ruas (3 005 km), que duplicariam a rua.

Entram estradas e ruas, ruas pedonais e praças, ciclovias e autoestradas (neste
mundo reina o ciclismo e a corrida). Sem informação de piso, uma estrada
assume-se asfaltada. Na cidade de Lisboa entra a malha toda; fora dela, a rede
principal.

**O mesmo mapa para os dois desportos:** os mesmos 8 614 km e as mesmas 60 613
interseções. A única diferença na navegação é que a bicicleta respeita os
sentidos únicos.

| # | Zona | Margem | Nível (ciclismo / corrida) | O que tem |
| :-: | :--- | :--- | :-: | :--- |
| 1 | Baixa | norte | 1 | Baixa, Chiado, Alfama, Castelo, Cais do Sodré |
| 2 | Centro | norte | 3 | Cidade de Lisboa: Avenidas Novas, Belém, Benfica, Parque das Nações, Monsanto… |
| 3 | Norte | norte | 6 | Odivelas, Loures, Mafra, **Serra Grande** |
| 4 | Este | norte | 9 | Sacavém, Póvoa, Alverca, Vila Franca de Xira |
| 5 | Oeste | norte | 12 | Amadora, Oeiras, Cascais, Sintra |
| 6 | Margem Sul · Norte | sul | 15 | Almada, Seixal, Barreiro (junto ao rio) |
| 7 | Margem Sul · Sul | sul | 18 | Sesimbra, Palmela, Setúbal, Arrábida, **Colo da Moura** |
| 8 | Margem Sul · Este | sul | 21 | Moita, Montijo, Alcochete, lezíria |
| 9 | Margem Sul · Oeste | sul | 24 | Costa da Caparica, Fonte da Telha, Cabo Espichel |

Os níveis são os mesmos nas duas modalidades, mas contam separadamente. Uma
ciclista de nível 9 com corrida de nível 4 tem o Norte e o Este abertos a
pedalar, e fechados a correr.

**Pontes:** são o único caminho entre margens e abrem no **nível 15** da
modalidade.

| Ponte | Ligação |
| :--- | :--- |
| Ponte 25 de Abril | Alcântara ↔ Almada |
| Ponte Vasco da Gama | Sacavém ↔ Montijo / Alcochete |
| Ponte Marechal Carmona | Vila Franca de Xira ↔ lezíria |
| Ponte da Lezíria (A10) | Carregado ↔ Benavente |

A margem de cada interseção vem da ligação real das estradas: tudo o que se
alcança a partir da Baixa sem atravessar uma ponte é a margem norte.

## 2. Extremidades e serras (mapa de terra)

- **Sem becos no fim do mapa:** as estradas cortadas pelo limite terrestre, ou
  que acabam a menos de 1,5 km dele, são unidas por **estradas de ligação**.
  Correm em linha reta, com a altimetria real do terreno e uma ondulação suave.
- **Duas serras fictícias** nascem nessas ligações, em ganchos para fora do mapa,
  e passam-se nos dois sentidos:

| Serra | Zona | Subida | Média | Cume | Descida |
| :--- | :--- | :-: | :-: | :-: | :-: |
| Serra Grande | Norte | 20 km | 10 % | ~2 050 m | 20 km |
| Colo da Moura | Margem Sul · Sul | 4 km | 9 % | ~380 m | 4 km |

## 3. Mapa do rio (remo)

O rio tem 105 km de faixas de remo e 113 docas. Cada troço do Tejo segue a zona
de terra ao lado, mas tem a **sua própria escada**, que abre com o nível de remo:

| # | Zona do rio | Margem | Nível de remo | Troço |
| :-: | :--- | :--- | :-: | :--- |
| 1 | Tejo · Baixa | norte | 1 | Cais do Sodré, Terreiro do Paço |
| 2 | Tejo · Centro | norte | 3 | Alcântara, Belém, Xabregas, Parque das Nações |
| 3 | Tejo · Este | norte | 6 | Sacavém, Póvoa, Alverca, Vila Franca |
| 4 | Tejo · Oeste | norte | 9 | Algés, Oeiras, Cascais |
| 5 | Tejo Sul · Norte | sul | 12 | Cacilhas, Seixal, Barreiro |
| 6 | Tejo Sul · Este | sul | 15 | Moita, Montijo, Alcochete |
| 7 | Tejo Sul · Oeste | sul | 18 | Trafaria, Porto Brandão |

**Travessias entre margens:** Cais do Sodré ↔ Cacilhas, Belém ↔ Porto Brandão,
Terreiro do Paço ↔ Barreiro e Parque das Nações ↔ Montijo. Abrem no **nível 12
de remo**. A partir daí, os pedidos dos NPCs podem ligar as duas margens.

## 4. Aparelhos e troca de desporto

Ao começar uma sessão, e a cada troca, o jogo verifica os aparelhos ligados
(Bluetooth ou ANT+):

| Desporto | Obrigatório (um destes) | Recomendado |
| :--- | :--- | :--- |
| Ciclismo | rolo (FTMS / FE-C) ou medidor de potência | banda cardíaca |
| Corrida | passadeira (FTMS / FE-C) ou sensor de passada | banda cardíaca |
| Remo | remo (FTMS / FE-C) | banda cardíaca |
| Ginásio | — | banda cardíaca |

A banda cardíaca passa a obrigatória se o atleta o pedir nas preferências.

**A troca:**
- **Bicicleta ↔ corrida:** em qualquer rua. A bicicleta fica guardada no sítio.
- **Para o remo:** numa doca.
- **O mapa muda com a troca:** a terra fica com os níveis da nova modalidade; no
  remo passa a ser o rio.
- **Zona fechada:** se a zona onde o atleta está estiver fechada para o novo
  desporto, a troca não se faz e o jogo diz porquê ("a zona Norte ainda está
  fechada para run").
- **Aparelho em falta:** a sessão atual continua e o jogo diz o que falta ligar
  ("sem aparelho para remo: liga um remo").

**Protocolos implementados** (`ergquest/devices/`):
- **Bluetooth:**
  - FTMS (rolo, passadeira e remo, com ERG, simulação de declive, velocidade e
    inclinação);
  - frequência cardíaca (com intervalos RR);
  - potência (com cadência pelo pedaleiro);
  - passada (RSC).
- **ANT+:**
  - FE-C (rolo, passadeira e remo, com ERG e simulação de declive);
  - frequência cardíaca, potência e passada (SDM);
  - mensagens da antena USB.

Quando há vários aparelhos, cada métrica vem do mais fiável: a potência dos
pedais antes da do rolo, e a frequência cardíaca da banda antes da do aparelho.
Se um aparelho se cala, o seguinte assume. A chave da rede ANT+ é licenciada:
define-se em `ERGQUEST_ANTPLUS_KEY`.

## 5. Os limites numa sessão livre

- **Ruas fechadas:** as que entram numa zona, ponte ou travessia ainda fechada
  **para a modalidade em uso** aparecem bloqueadas, com o nível a que abrem, e não
  se podem tomar.
- **Sem outra saída:** o atleta **dá meia-volta** automaticamente.
- **A qualquer momento:** `meia-volta` (vira ali mesmo) e `regressar` (o GPS leva
  de volta pelo lado mais rápido).

## 6. Dados e construção

| Fonte | Para quê | Licença |
| :--- | :--- | :--- |
| OpenStreetMap, via Overture Maps (transportation) | estradas, piso, interseções, sentidos, pontes | ODbL |
| Overture Maps (places) | sítios dos estabelecimentos fictícios | CDLA Permissive 2.0 |
| Copernicus GLO-30 | altimetria | licença Copernicus (com atribuição) |

```bash
python tools/build_metro.py
```

Este comando descarrega o que faltar para `data/raw/`, mostra quantos km saem
por cada motivo, e grava:
- `data/lisboa-metro.json.gz` (cerca de 5 MB, no repositório);
- o mapa interativo em `data/lisboa-metro.html`.

**Limite conhecido da altimetria:** os modelos públicos de 30 m incluem
edifícios, por isso nas ruas estreitas da Baixa aparecem rampas a mais. Para
reduzir isso:
- a cota é o ponto mais baixo à volta;
- os picos isolados são corrigidos;
- o rolo recebe a média de 40 m.

A correção completa precisa de um modelo de terreno LiDAR.
