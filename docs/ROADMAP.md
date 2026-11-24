# ErgQuest — Roadmap

| Fase | Objetivo | Entregável verificável |
| :--- | :--- | :--- |
| **F0 · Fundação** ✅ | Interpretar o conceito; núcleo de regras puro e testado: modos Treino/Jogo/Livre, recados, táxi. | Demo sem hardware. |
| **F1 · Lisboa real** ✅ | A Área Metropolitana de Lisboa como mundo: 9 zonas com ordem de desbloqueio, 4 pontes e 4 travessias de remo bloqueadas por nível, 105 km de faixas de remo e 119 docas, estradas de ligação nas extremidades, Serra Grande e Colo da Moura, limites com meia-volta e regresso. | `data/lisboa-metro.json.gz` (97 802 interseções, 8 929 km de estradas); demo nas duas margens; mapa interativo publicado. Pendente: altimetria fina nas ruas estreitas da Baixa (modelo de terreno LiDAR). |
| **F2 · Vertical slice single-player** 🚧 | Aparelhos: protocolos Bluetooth (FTMS, FC, potência, passada) e ANT+ (FE-C, FC, potência, passada), requisitos por desporto e verificação na troca — **feitos, testados com aparelhos simulados**. Falta: testar com aparelhos reais, `.fit`, cliente pyglet 3D sobre o mapa de terra/rio, HUD com altimetria. | Um treino com ERG desligado no mundo e uma entrega, num rolo FTMS real, com `.fit`. |
| **F3 · Três desportos + ginásio + NPCs** | Passadeira (entregas, perseguições), remo no Tejo, pontos de troca, Robustez, recados ad-hoc e táxi (riquexó, bote-táxi). | Um *brick* bicicleta → corrida, um recado e uma corrida de táxi, cada um com o seu `.fit`. |
| **F4 · Multiplayer** | Servidor de shard por cidade (WebSocket), interest management, `OrderBoard` por jogador no servidor, anti-cheat em modo sombra, NPCs com sensores simulados. | 200 bots simulados numa cidade, < 100 ms de tick no servidor. |
| **F5 · E-sport** | Desafios instantâneos, segmentos canónicos, crits outdoor/indoor, velódromo, rankings por categoria W/kg, verificação de peso. | Um desafio cross-city entre dois clientes reais. |
| **F6 · Treinador** | Motor de recomendações: o plano prescreve os treinos e ajusta-se à carga que o jogo gerou (o efeito colateral). Londres e Nova Iorque. | Uma semana em que jogar ao fim de semana muda o treino de segunda. |
