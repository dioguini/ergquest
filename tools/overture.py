"""Leitura seletiva do Overture Maps (GeoParquet no S3 público) por caixa geográfica.

Os ficheiros são enormes mas estão ordenados no espaço: lê-se só o rodapé de
cada um (estatísticas por grupo de linhas) e depois apenas os grupos que
intersetam a caixa, com pedidos HTTP parciais (Range). Sem credenciais.

Dados: transportes © contribuidores do OpenStreetMap (ODbL) via Overture Maps
Foundation; locais © Overture Maps Foundation (CDLA Permissive 2.0).
"""
from __future__ import annotations

import io
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import pyarrow as pa
import pyarrow.parquet as pq

BUCKET = "https://overturemaps-us-west-2.s3.us-west-2.amazonaws.com"
UA = {"User-Agent": "ErgQuest-map-builder/0.1"}


class RangeFile(io.RawIOBase):
    """Ficheiro remoto só de leitura, com leituras por intervalo e cache de blocos."""

    BLOCK = 1 << 20

    def __init__(self, url: str, size: int):
        self.url, self.size, self.pos = url, size, 0
        self.cache: dict[int, bytes] = {}

    def readable(self): return True
    def seekable(self): return True
    def tell(self): return self.pos

    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else self.pos + off if whence == 1 else self.size + off
        return self.pos

    def _get(self, start: int, end: int) -> bytes:
        req = urllib.request.Request(self.url, headers={**UA, "Range": f"bytes={start}-{end - 1}"})
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    return r.read()
            except OSError:
                if attempt == 3:
                    raise
        raise RuntimeError("inalcançável")

    def read(self, n=-1):
        if n is None or n < 0:
            n = self.size - self.pos
        n = max(0, min(n, self.size - self.pos))
        if n == 0:
            return b""
        if n > 4 * self.BLOCK:                      # leituras grandes: direto
            data = self._get(self.pos, self.pos + n)
        else:
            out, p = [], self.pos
            while p < self.pos + n:
                b = p // self.BLOCK
                if b not in self.cache:
                    s = b * self.BLOCK
                    self.cache[b] = self._get(s, min(self.size, s + self.BLOCK))
                blk = self.cache[b]
                off = p - b * self.BLOCK
                take = min(len(blk) - off, self.pos + n - p)
                out.append(blk[off:off + take])
                p += take
            data = b"".join(out)
        self.pos += len(data)
        return data

    def readinto(self, b):
        data = self.read(len(b))
        b[:len(data)] = data
        return len(data)


def list_files(release: str, theme: str, kind: str) -> list[tuple[str, int]]:
    url = f"{BUCKET}/?list-type=2&prefix=release/{release}/theme={theme}/type={kind}/"
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        xml = r.read().decode()
    keys = re.findall(r"<Key>(.*?)</Key>", xml)
    sizes = [int(s) for s in re.findall(r"<Size>(\d+)</Size>", xml)]
    return [(f"{BUCKET}/{k}", s) for k, s in zip(keys, sizes) if k.endswith(".parquet")]


def latest_release() -> str:
    with urllib.request.urlopen(urllib.request.Request(f"{BUCKET}/?list-type=2&prefix=release/&delimiter=/",
                                                       headers=UA), timeout=60) as r:
        return sorted(re.findall(r"<Prefix>release/([^/]+)/</Prefix>", r.read().decode()))[-1]


def _bbox_cols(md) -> dict[str, int]:
    rg = md.row_group(0)
    return {rg.column(i).path_in_schema: i for i in range(rg.num_columns)}


def _hits(url: str, size: int, box) -> tuple[str, int, list[int]]:
    south, west, north, east = box
    f = pq.ParquetFile(RangeFile(url, size))
    md = f.metadata
    cols = _bbox_cols(md)
    ix = {k: cols[f"bbox.{k}"] for k in ("xmin", "xmax", "ymin", "ymax")}
    groups = []
    for g in range(md.num_row_groups):
        rg = md.row_group(g)
        st = {k: rg.column(i).statistics for k, i in ix.items()}
        if any(s is None or not s.has_min_max for s in st.values()):
            groups.append(g)
            continue
        if st["xmin"].min <= east and st["xmax"].max >= west and st["ymin"].min <= north and st["ymax"].max >= south:
            groups.append(g)
    return url, size, groups


def read_bbox(release: str, theme: str, kind: str, box, columns: list[str], log=print) -> pa.Table:
    """Linhas cujo bbox interseta `box` = (sul, oeste, norte, este)."""
    files = list_files(release, theme, kind)
    log(f"  {theme}/{kind}: {len(files)} ficheiros, a ler rodapés…")
    with ThreadPoolExecutor(8) as ex:
        hits = [h for h in ex.map(lambda fs: _hits(fs[0], fs[1], box), files) if h[2]]
    log(f"  {sum(len(h[2]) for h in hits)} grupos de linhas em {len(hits)} ficheiros")
    south, west, north, east = box
    tables = []
    for url, size, groups in hits:
        f = pq.ParquetFile(RangeFile(url, size))
        for g in groups:
            t = f.read_row_group(g, columns=columns + ["bbox"])
            b = t.column("bbox").combine_chunks()
            xmin, xmax = b.field("xmin"), b.field("xmax")
            ymin, ymax = b.field("ymin"), b.field("ymax")
            import pyarrow.compute as pc
            m = pc.and_(pc.and_(pc.less_equal(xmin, east), pc.greater_equal(xmax, west)),
                        pc.and_(pc.less_equal(ymin, north), pc.greater_equal(ymax, south)))
            t = t.filter(m)
            if t.num_rows:
                tables.append(t)
    return pa.concat_tables(tables, promote_options="default") if tables else None
