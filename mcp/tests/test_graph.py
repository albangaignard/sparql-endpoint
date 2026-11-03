import logging

import httpx
import pytest

import graph


def test_ensure_dumps_downloads_only_missing_files(tmp_path):
    (tmp_path / "a.ttl").write_text("# already here")
    requested = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.path)
        return httpx.Response(200, text="# fresh")

    paths = graph.ensure_dumps(
        tmp_path,
        base_url="https://example.org/d",
        dumps=("a.ttl", "b.ttl"),
        transport=httpx.MockTransport(handler),
    )

    assert requested == ["/d/b.ttl"]
    assert [p.name for p in paths] == ["a.ttl", "b.ttl"]
    assert (tmp_path / "a.ttl").read_text() == "# already here"
    assert (tmp_path / "b.ttl").read_text() == "# fresh"
    assert not list(tmp_path.glob("*.part"))


def test_ensure_dumps_keeps_no_partial_file_on_failure(tmp_path):
    transport = httpx.MockTransport(lambda r: httpx.Response(404))
    with pytest.raises(httpx.HTTPStatusError):
        graph.ensure_dumps(tmp_path / "dl", dumps=("a.ttl",), transport=transport)
    assert not list((tmp_path / "dl").iterdir())


async def test_store_loads_once(data_dir):
    store = graph.GraphStore(data_dir, dumps=("sample.ttl",))
    g1 = await store.get()
    g2 = await store.get()
    assert g1 is g2
    assert len(g1) == 6


async def test_store_retries_after_failed_load(tmp_path):
    transport = httpx.MockTransport(lambda r: httpx.Response(503))
    store = graph.GraphStore(tmp_path, dumps=("a.ttl",), transport=transport)
    with pytest.raises(httpx.HTTPStatusError):
        await store.get()
    (tmp_path / "a.ttl").write_text("<http://x/s> <http://x/p> <http://x/o> .")
    assert len(await store.get()) == 1


async def test_loading_is_logged(data_dir, caplog):
    # the "rsec" logger does not propagate to root, so attach caplog's handler to it
    rsec = logging.getLogger("rsec")
    rsec.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.INFO, logger="rsec"):
            await graph.GraphStore(data_dir, dumps=("sample.ttl",)).get()
    finally:
        rsec.removeHandler(caplog.handler)

    text = caplog.text
    assert "1 dump(s) present, 0 to download" in text
    assert "parsing sample.ttl" in text
    assert "parsed sample.ttl: +6 triples" in text
    assert "loaded 6 triples from 1 files" in text
