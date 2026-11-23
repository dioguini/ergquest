# ErgQuest — O mundo: Área Metropolitana de Lisboa

O mapa é a Área Metropolitana de Lisboa, com as estradas e a altimetria reais.
Neste mundo reina o ciclismo e a corrida: as autoestradas também contam.

- **Regras** (zonas, ordem, níveis, pontes, rio, serras): `ergquest/world/metro.py`.
- **Construção do mapa:** `ergquest/world/metrobuild.py` e `tools/build_metro.py`.
- **O que cada atleta pode usar:** `ergquest/world/access.py`.

## 1. Zonas e ordem de desbloqueio

O Tejo divide o mapa em duas margens. Na margem norte há a Baixa, o Centro (a
cidade de Lisboa) e três zonas definidas pelos pontos cardeais vistos da Baixa.
Na margem sul há quatro zonas, também pelos pontos cardeais.

| # | Zona | Margem | Nível | O que tem |
| :-: | :--- | :--- | :-: | :--- |
| 1 | Baixa | norte | 1 | Baixa, Chiado, Alfama, Castelo, Cais do Sodré |
| 2 | Centro | norte | 3 | Cidade de Lisboa: Avenidas Novas, Belém, Benfica, Parque das Nações, Monsanto… |
| 3 | Norte | norte | 6 | Odivelas, Loures, Mafra, **Serra Grande** |
| 4 | Este | norte | 9 | Sacavém, Póvoa, Alverca, Vila Franca de Xira |
| 5 | Oeste | norte | 12 | Amadora, Oeiras, Cascais, Sintra (com a serra real) |
| 6 | Margem Sul · Norte | sul | 15 | Almada, Seixal, Barreiro (junto ao rio) |
| 7 | Margem Sul · Sul | sul | 18 | Sesimbra, Palmela, Setúbal, Arrábida, **Colo da Moura** |
| 8 | Margem Sul · Este | sul | 21 | Moita, Montijo, Alcochete, lezíria |
| 9 | Margem Sul · Oeste | sul | 24 | Costa da Caparica, Fonte da Telha, Cabo Espichel |

- **Na cidade de Lisboa (Baixa e Centro)** entra toda a malha de ruas, incluindo as
  escadinhas (só a pé). **Fora dela** entra a rede principal: autoestradas, vias
  rápidas, nacionais, municipais, estradas rurais e ciclovias.
- **A margem de cada interseção** vem da ligação real das estradas: tudo o que se
  alcança a partir da Baixa sem atravessar uma ponte é a margem norte.

## 2. Pontes

As quatro pontes sobre o Tejo são o único caminho entre margens. Abrem no
**nível 15**, ao mesmo tempo que a primeira zona da margem sul. A partir daí,
os atletas com esse nível podem atravessar para fazer missões.

| Ponte | Ligação |
| :--- | :--- |
| Ponte 25 de Abril | Alcântara ↔ Almada |
| Ponte Vasco da Gama | Sacavém ↔ Montijo / Alcochete |
| Ponte Marechal Carmona | Vila Franca de Xira ↔ lezíria |
| Ponte da Lezíria (A10) | Carregado ↔ Benavente |

## 3. Remo

O rio tem 105 km de faixas de remo ao longo das duas margens e 119 docas, que
são os cais onde se entra na água.

- **Cada troço do rio pertence à zona de terra que o acompanha** e abre com
  ela. Por exemplo, o rio de Sacavém a Vila Franca é da zona Este.
- **Quatro travessias entre margens:**
  - Cais do Sodré ↔ Cacilhas
  - Belém ↔ Porto Brandão
  - Terreiro do Paço ↔ Barreiro
  - Parque das Nações ↔ Montijo
- As travessias abrem no **nível 18**, com as zonas das duas margens abertas.
  Só então os pedidos dos NPCs podem ligar as duas margens.

## 4. As extremidades do mapa e as serras

- **Não há estradas sem saída nas extremidades.** As estradas cortadas pelo
  limite terrestre do mapa, ou que acabam a menos de 1,5 km dele, são unidas
  entre si por **estradas de ligação** (uma cadeia por margem).
  - Correm em linha reta junto ao limite.
  - A altimetria vem do terreno real que atravessam, com uma ondulação suave.
- **Duas serras fictícias** nascem nessas ligações, com traçado em ganchos para
  fora do mapa. Sobem de um lado e descem do outro, por isso passam-se nos dois
  sentidos.

| Serra | Zona | Subida | Média | Cume | Descida |
| :--- | :--- | :-: | :-: | :-: | :-: |
| Serra Grande | Norte | 20 km | 10 % | ~2 050 m | 20 km |
| Colo da Moura | Margem Sul · Sul | 4 km | 9 % | ~380 m | 4 km |

## 5. Os limites numa sessão livre

- **Ruas fechadas:** as que entram numa zona, ponte ou travessia ainda fechadas
  aparecem bloqueadas, com o nível a que abrem ("Zona Oeste — abre no nível 12"),
  e não se podem tomar.
- **Sem outra saída:** se não houver outra rua, o atleta **dá meia-volta**
  automaticamente.
- **A qualquer momento:**
  - `meia-volta` vira ali mesmo (exceto num sentido único);
  - `regressar` faz o GPS calcular o caminho de volta (à base ou ao início da
    sessão), seja seguindo até à próxima interseção, seja virando já, conforme
    o que for mais rápido.

## 6. Dados e construção

| Fonte | Para quê | Licença |
| :--- | :--- | :--- |
| OpenStreetMap, via Overture Maps (transportation) | estradas, interseções, sentidos, pontes | ODbL |
| Overture Maps (places) | sítios dos estabelecimentos fictícios | CDLA Permissive 2.0 |
| Copernicus GLO-30 | altimetria | licença Copernicus (com atribuição) |

```bash
python tools/build_metro.py
```

Este comando descarrega os dados que faltem para `data/raw/` e grava:
- `data/lisboa-metro.json.gz` (cerca de 7 MB, no repositório);
- o mapa interativo em `data/lisboa-metro.html`.

O mapa tem 97 802 interseções e 8 929 km de estradas.

**Limite conhecido da altimetria:** os modelos públicos de 30 m incluem
edifícios, por isso nas ruas estreitas da Baixa aparecem rampas a mais. Para
reduzir isso:
- a cota é o ponto mais baixo à volta;
- os picos isolados são corrigidos;
- o rolo recebe a média de 40 m.

A correção completa precisa de um modelo de terreno LiDAR.
