"""Arranque do banco de testes: `py -m ergquest.bench [--sim] [--port 8787] [--pasta ...]`."""
from __future__ import annotations

import argparse
import sys
import time
import webbrowser
from pathlib import Path

from .core import Bench
from .server import serve


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="ergquest.bench", description="Banco de testes de aparelhos do ErgQuest")
    ap.add_argument("--sim", action="store_true", help="aparelhos simulados (sem Bluetooth)")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--pasta", default=str(Path.home() / "ErgQuest" / "bancada"), help="onde gravar")
    ap.add_argument("--sem-browser", action="store_true", help="não abrir o browser")
    a = ap.parse_args(argv)

    if a.sim:
        from .backend import SimBackend as factory
    else:
        try:
            from .backend import BleBackend as factory
            import bleak  # noqa: F401
        except ImportError:
            print("Falta a biblioteca Bluetooth. Instala-a com:  py -m pip install bleak==0.22.3")
            print("(ou corre com --sim para experimentar sem aparelhos)")
            sys.exit(1)
    bench = Bench(factory, a.pasta)
    serve(bench, a.port)
    url = f"http://127.0.0.1:{a.port}/"
    print(f"Banco de testes do ErgQuest em {url}")
    print(f"Gravações em {bench.recorder.dir}")
    print("Fecha esta janela (ou Ctrl+C) para terminar.")
    if not a.sem_browser:
        webbrowser.open(url)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for address in list(bench.links):
            try:
                bench.disconnect(address)
            except Exception:
                pass
        bench.recorder.close()


if __name__ == "__main__":
    main()
