"""Dispositivos: ergómetros e sensores por Bluetooth (BLE) e ANT+.

* `ble`  — perfis Bluetooth: FTMS (rolo, passadeira, remo), frequência
  cardíaca, potência, passada (RSC); controlo ERG e simulação de declive.
* `ant`  — ANT+: FE-C (rolo, passadeira, remo), frequência cardíaca,
  potência, passada; mensagens da antena USB; controlo FE-C.
* `hub`  — tipos de dispositivo, o que cada desporto exige, a verificação na
  troca de desporto, e a junção das leituras de vários sensores.
* `sim`  — dispositivos simulados que falam os mesmos protocolos (testes e
  demonstração sem hardware).

Os descodificadores são funções puras (bytes → leitura). O transporte real
usa `bleak` (Bluetooth) e `pyusb` (antena ANT+), ambos opcionais.
"""
