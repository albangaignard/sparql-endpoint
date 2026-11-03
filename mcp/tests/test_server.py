import httpx
import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

import graph
import server


def test_build_query_keeps_query5_semantics():
    q = server.build_query(limit=10, offset=20)
    assert "?application schema:identifier ?biotools_ID" in q
    assert 'FILTER STRSTARTS(STR(?biotools_ID), "https://bio.tools")' in q
    # deterministic order, so that limit/offset paging is stable
    assert "ORDER BY STR(?biotools_ID) ?application" in q
    assert q.rstrip().endswith("LIMIT 10 OFFSET 20")


async def test_tool_returns_only_biotools_records():
    async with Client(server.mcp) as c:
        res = await c.call_tool("list_software_with_biotools_ids", {})

    assert res.data == {
        "results": [
            {"application": "http://x/blast", "biotools_id": "https://bio.tools/blast"},
            {"application": "http://x/samtools", "biotools_id": "https://bio.tools/samtools"},
        ],
        "limit": 100,
        "offset": 0,
        "count": 2,
    }


async def test_tool_pages_with_limit_and_offset():
    async with Client(server.mcp) as c:
        res = await c.call_tool("list_software_with_biotools_ids", {"limit": 1, "offset": 1})
    assert [r["biotools_id"] for r in res.data["results"]] == ["https://bio.tools/samtools"]


async def test_tool_reports_data_loading_failure(tmp_path, monkeypatch):
    bad = graph.GraphStore(
        tmp_path,
        dumps=("missing.ttl",),
        transport=httpx.MockTransport(lambda r: httpx.Response(404)),
    )
    monkeypatch.setattr(server, "store", bad)
    async with Client(server.mcp) as c:
        with pytest.raises(ToolError, match="RSEc RDF data"):
            await c.call_tool("list_software_with_biotools_ids", {})


@pytest.mark.parametrize("args", [{"limit": 0}, {"limit": 5000}, {"offset": -1}])
async def test_tool_rejects_out_of_range_paging(args):
    async with Client(server.mcp) as c:
        with pytest.raises(ToolError):
            await c.call_tool("list_software_with_biotools_ids", args)
