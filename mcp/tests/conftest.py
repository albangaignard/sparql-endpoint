from pathlib import Path

import pytest

import graph
import server

SAMPLE_TTL = """
@prefix schema: <http://schema.org/> .
<http://x/blast> a schema:SoftwareApplication ; schema:identifier "https://bio.tools/blast" .
<http://x/samtools> a schema:SoftwareApplication ; schema:identifier <https://bio.tools/samtools> .
<http://x/other> a schema:SoftwareApplication ; schema:identifier "https://example.org/other" .
"""


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    (tmp_path / "sample.ttl").write_text(SAMPLE_TTL)
    return tmp_path


@pytest.fixture(autouse=True)
def sample_store(data_dir, monkeypatch):
    """Never touch the network or the real dumps: serve a tiny local graph."""
    store = graph.GraphStore(data_dir, dumps=("sample.ttl",))
    monkeypatch.setattr(server, "store", store)
    return store
