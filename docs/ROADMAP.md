# ErgQuest — Roadmap

| Fase | Objetivo | Entregável verificável |
| :--- | :--- | :--- |
| **F0 · Fundação** ✅ | Interpretar o conceito; núcleo de regras puro e testado: modos Treino/Jogo/Livre, recados, táxi. | Demo sem hardware. |
| **F1 · Lisboa real** ✅ | Grafo de ruas e rio do OpenStreetMap com altimetria (DEM), navegação por interseções, estabelecimentos fictícios em pontos reais, mapa 2D para validar. As regras de treino e jogo passam a correr sobre ruas verdadeiras. | `data/lisboa-centro.json` (4 860 interseções, 71 km de bicicleta, 161 km a pé); a demo corre nas ruas reais; mapa 2D. Pendente: altimetria fina nas ruas estreitas da Baixa (precisa de um modelo de terreno LiDAR). |
| **F2 · Vertical slice single-player** | Ligação a hardware (BLE FTMS, ANT+ FE-C), `.fit`, cliente pyglet 3D sobre o grafo de Lisboa, HUD com altimetria. Treino nas 4 combinações ERG × mundo/ecrã; no jogo, entregas de comida. | Um treino com ERG desligado no mundo e uma entrega, num rolo FTMS real, com `.fit`. |
| **F3 · Três desportos + ginásio + NPCs** | Passadeira (entregas, perseguições), remo no Tejo, pontos de troca, Robustez, recados ad-hoc e táxi (riquexó, bote-táxi). | Um *brick* bicicleta → corrida, um recado e uma corrida de táxi, cada um com o seu `.fit`. |
| **F4 · Multiplayer** | Servidor de shard por cidade (WebSocket), interest management, `OrderBoard` por jogador no servidor, anti-cheat em modo sombra, NPCs com sensores simulados. | 200 bots simulados numa cidade, < 100 ms de tick no servidor. |
| **F5 · E-sport** | Desafios instantâneos, segmentos canónicos, crits outdoor/indoor, velódromo, rankings por categoria W/kg, verificação de peso. | Um desafio cross-city entre dois clientes reais. |
| **F6 · Treinador** | Motor de recomendações: o plano prescreve os treinos e ajusta-se à carga que o jogo gerou (o efeito colateral). Londres e Nova Iorque. | Uma semana em que jogar ao fim de semana muda o treino de segunda. |
