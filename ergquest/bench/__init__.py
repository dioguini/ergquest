"""Banco de testes de aparelhos: uma página local para ligar, ver e gravar.

    py -m ergquest.bench            (Windows; abre o browser)
    python -m ergquest.bench --sim  (sem hardware: aparelhos simulados)

Procura aparelhos Bluetooth, liga-se, mostra os dados em direto, controla o
rolo (ERG e declive), grava capturas das notificações (para descodificar
protocolos próprios, como o dos remos Domyos), simula a passadeira manual e
verifica que modalidades os aparelhos ligados permitem. Tudo o que acontece
fica numa pasta em ~/ErgQuest/bancada/ para enviar como feedback.
"""
