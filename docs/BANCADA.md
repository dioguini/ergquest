# Banco de testes de aparelhos — guia para Windows

O banco de testes é uma página no teu browser, servida por um pequeno
programa no teu PC. Serve para:
- ligar o **Wahoo KICKR Core**, a **Polar H10** e o **remo Domyos 500B**;
- ver os dados em direto;
- testar o ERG e o declive do rolo;
- gravar capturas do remo, para eu descodificar o protocolo dele;
- experimentar a **passadeira manual**.

Tudo o que acontece fica gravado numa pasta, que me envias no fim.

## 1. Preparar (uma vez)

1. **Python:** instala o Python 3.11 ou mais recente de <https://www.python.org/downloads/>.
   No instalador, marca **"Add python.exe to PATH"**.
2. **Código:** descarrega o ZIP do ramo e descompacta-o numa pasta, por exemplo
   `Documentos\ergquest`:
   <https://github.com/dioguini/ergquest/archive/refs/heads/claude/brave-wright-f72154.zip>
3. **Bluetooth:** confirma que o Bluetooth do PC está ligado. É preciso Bluetooth 4.0 (BLE) ou mais
   recente; quase todos os portáteis têm. **Não emparelhes** os aparelhos nas definições do Windows:
   o programa liga-se diretamente.
4. **KICKR Core:** atualiza o firmware na app Wahoo, para garantir que fala FTMS.

## 2. Abrir

- **`bancada.bat`** (duplo clique): da primeira vez instala a biblioteca Bluetooth
  (`bleak`) e depois abre a página no browser.
- **`bancada-simulada.bat`**: abre a mesma página com aparelhos simulados. Serve para
  conheceres a página sem pedalar.

A janela preta tem de ficar aberta enquanto testas. Fechá-la termina o programa.

> Antes de começar, **fecha as outras apps** ligadas aos aparelhos (Zwift, Wahoo,
> Polar Beat, Decathlon e-connected) e desliga o Bluetooth do telemóvel, se
> estiver ligado a algum deles. Cada aparelho aceita poucas ligações ao mesmo tempo.

## 3. O que testar

### A. Aparelhos (separador "Aparelhos")
1. Carrega em **Procurar**. Pedala um pouco no KICKR, mexe o remo, e veste a
   H10 com os elétrodos húmidos, para que todos acordem.
2. Cada aparelho deve aparecer reconhecido:
   - KICKR → **rolo**;
   - H10 → **banda cardíaca**;
   - Domyos → **Domyos (protocolo próprio)**, ou **remo** se afinal falar FTMS.
3. Liga os três. Abre **"características"** em cada um: essa lista também me ajuda.

### B. KICKR Core (separadores "Em direto" e "Rolo")
1. Pedala livremente. Em **Em direto** devem aparecer potência, cadência e velocidade.
2. **ERG:** no separador **Rolo**, aplica 150 W, depois 200 W e 250 W. Em cada um:
   - pedala 1 minuto;
   - muda de cadência (por exemplo, 80 e depois 95 rpm);
   - a potência deve manter-se perto do alvo.
3. **Declive:** aplica 0 %, 4 %, 8 % e 12 %. A resistência deve subir de forma
   clara, mantendo a mudança.
4. Em **Respostas do rolo** deve aparecer "OK" para cada comando. Se aparecer
   outro código, anota-o.

### C. Polar H10
- Em **Em direto** deve aparecer a frequência cardíaca, e em **Por aparelho** os
  intervalos RR (`rr_ms`).
- Compara com o relógio, se tiveres.

### D. Remo Domyos 500B (separador "Captura") — o mais importante
O protocolo deste remo não é público. Com esta captura eu descodifico-o.

1. Liga o remo e vê em **Por aparelho** se a coluna **Notificações** sobe quando remas.
2. Carrega em **Começar a gravar**.
3. Segue esta sequência. Em cada passo carrega no botão da marca, ou escreve-a, e
   **acrescenta o que o visor do remo mostra** (tempo, distância, remadas, calorias,
   nível), por exemplo `resistência 5 · visor 1:30, 310 m, 42 remadas, 18 kcal`:

   | Marca | O que fazer | Duração |
   | :--- | :--- | :-: |
   | parado | não remar | 30 s |
   | resistência 1 | remada leve e constante | 1 min |
   | resistência 5 | remada constante | 1 min |
   | resistência 10 | remada constante | 1 min |
   | ritmo 20/min | resistência 5, 20 remadas por minuto | 1 min |
   | ritmo 28/min | resistência 5, 28 remadas por minuto | 1 min |
   | sprint 10 remadas | 10 remadas fortes | — |
   | parado | não remar | 30 s |

4. Carrega em **Parar gravação**.
5. **Se as notificações não subirem** quando remas, o remo provavelmente precisa
   de um comando para começar a enviar dados. Não te preocupes: envia-me na mesma a
   pasta e a lista de características, e eu preparo os comandos a experimentar em
   **Enviar bytes a um aparelho**.

### E. Passadeira manual (separador "Passadeira")
1. Carrega em **Ligar passadeira manual**.
2. Num treino na tua passadeira, indica aqui a mesma velocidade e inclinação,
   com as teclas ↑ ↓ ← → ou os botões.
3. Carrega em **Simular pedido do jogo** e vê se o aviso se percebe a meio de uma corrida.
4. Diz-me se é prático ou incómodo. Por exemplo: preferias teclas maiores?
   Atalhos no telemóvel? Um aviso sonoro?

### F. Verificação (separador "Verificação")
Com tudo ligado deves ver:
- **Ciclismo:** pode jogar, com ERG/declive e rankings.
- **Corrida:** pode jogar com a passadeira manual, sem rankings (estimado).
- **Remo:** pode jogar, sem rankings, até a potência estimada estar afinada.

## 4. O que me enviar

1. **A pasta da sessão:** `C:\Users\<tu>\ErgQuest\bancada\<data-hora>\`, comprimida em ZIP (botão direito →
   *Enviar para* → *Pasta comprimida*). Tem:
   - `eventos.log`;
   - `aparelhos.json`;
   - `notificacoes.csv`;
   - `leituras.csv`.
2. **Notas tuas:** o que funcionou, o que não funcionou, o que foi confuso, e o que
   gostavas de ver na página.
3. **Fotografias do visor do remo,** se der jeito: ajudam a confirmar as unidades.

Não há dados pessoais nos ficheiros, só os nomes e endereços Bluetooth dos aparelhos e os valores medidos.

## 5. Problemas comuns

| Sintoma | O que fazer |
| :--- | :--- |
| "Não encontrei o Python" | Reinstala o Python com "Add python.exe to PATH" marcado. |
| A procura não encontra nada | Confirma o Bluetooth ligado; acorda os aparelhos; aproxima o PC. |
| Um aparelho não liga | Fecha as outras apps; desliga o Bluetooth do telemóvel; tenta de novo. |
| ERG sem efeito | Confirma "controlo concedido" no separador Rolo; atualiza o firmware do KICKR. |
| A página não abre | Abre `http://127.0.0.1:8787/` à mão no browser. |
