"""Load the RSEc RDF dumps into an in-memory rdflib graph.

Dumps are the same files the root docker-compose.yml feeds to Fuseki. Missing
files are downloaded on first use; existing files are never re-downloaded.
"""

import asyncio
import logging
import time
from pathlib import Path

import httpx
from rdflib import Graph

log = logging.getLogger("rsec.graph")

BASE_URL = (
    "https://raw.githubusercontent.com/research-software-ecosystem/content"
    "/refs/heads/master/datasets"
)
DUMPS = (
    "bioschemas-dump.ttl",
    "bioschemas-biii-dump.ttl",
    "bioconda-dump.ttl",
    "biocontainers-dump.ttl",
    "debian-dump.ttl",
    "galaxy-dump.ttl",
    "galaxyworkflow-dump.ttl",
    "workflowhub-dump.ttl",
)


def _mb(path: Path) -> str:
    return f"{path.stat().st_size / 1e6:.1f} MB"


def ensure_dumps(
    data_dir: Path,
    base_url: str = BASE_URL,
    dumps: tuple[str, ...] = DUMPS,
    transport: httpx.BaseTransport | None = None,
) -> list[Path]:
    """Return local paths of all dumps, downloading the missing ones."""
    data_dir.mkdir(parents=True, exist_ok=True)
    paths = [data_dir / name for name in dumps]
    missing = [p for p in paths if not p.exists()]
    log.info(
        "data directory %s: %d dump(s) present, %d to download",
        data_dir, len(paths) - len(missing), len(missing),
    )
    if missing:
        with httpx.Client(
            transport=transport, follow_redirects=True, timeout=120
        ) as client:
            for i, path in enumerate(missing, 1):
                url = f"{base_url}/{path.name}"
                log.info("[%d/%d] downloading %s", i, len(missing), url)
                t0 = time.perf_counter()
                resp = client.get(url)
                resp.raise_for_status()
                tmp = path.with_name(path.name + ".part")
                tmp.write_bytes(resp.content)
                tmp.replace(path)  # atomic: no half-written dump is ever kept
                log.info(
                    "[%d/%d] downloaded %s (%s, %.1f s)",
                    i, len(missing), path.name, _mb(path), time.perf_counter() - t0,
                )
    return paths


def load_graph(paths: list[Path]) -> Graph:
    g = Graph()
    t_start = time.perf_counter()
    for i, path in enumerate(paths, 1):
        before, t0 = len(g), time.perf_counter()
        log.info("[%d/%d] parsing %s (%s)", i, len(paths), path.name, _mb(path))
        g.parse(path, format="turtle")
        log.info(
            "[%d/%d] parsed %s: +%d triples (%d total, %.1f s)",
            i, len(paths), path.name, len(g) - before, len(g), time.perf_counter() - t0,
        )
    log.info(
        "loaded %d triples from %d files in %.1f s",
        len(g), len(paths), time.perf_counter() - t_start,
    )
    return g


class GraphStore:
    """Loads the graph once, lazily, off the event loop."""

    def __init__(
        self,
        data_dir: Path,
        base_url: str = BASE_URL,
        dumps: tuple[str, ...] = DUMPS,
        transport: httpx.BaseTransport | None = None,
    ):
        self.data_dir = data_dir
        self._args = (base_url, dumps, transport)
        self._graph: Graph | None = None
        self._lock = asyncio.Lock()

    def _load(self) -> Graph:
        return load_graph(ensure_dumps(self.data_dir, *self._args))

    async def get(self) -> Graph:
        async with self._lock:
            if self._graph is None:  # a failed load is retried on the next call
                self._graph = await asyncio.to_thread(self._load)
            return self._graph
