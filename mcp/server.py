"""FastMCP server exposing RSEC SPARQL queries to LLM agents.

The RSEc RDF dumps are loaded in-process with rdflib (downloaded on first run
into RSEC_DATA_DIR), so no SPARQL endpoint has to be deployed.
"""

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from graph import GraphStore

log = logging.getLogger("rsec.server")


def _setup_logging() -> None:
    """Log to stderr (stdout carries the MCP protocol). RSEC_LOG_LEVEL=WARNING mutes it."""
    root = logging.getLogger("rsec")
    if root.handlers:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", "%H:%M:%S")
    )
    root.addHandler(handler)
    root.setLevel(os.environ.get("RSEC_LOG_LEVEL", "INFO").upper())
    root.propagate = False


_setup_logging()

DATA_DIR = Path(os.environ.get("RSEC_DATA_DIR", Path(__file__).parent / "data"))
store = GraphStore(DATA_DIR)


@asynccontextmanager
async def lifespan(_server):
    # Warm up in the background so the MCP handshake is not delayed by the
    # ~10 s load (plus the first-run download).
    async def warm():
        log.info("loading RSEc data in the background (first tool call waits for it)")
        try:
            await store.get()
            log.info("RSEc data ready: server can answer queries")
        except Exception:
            log.exception("could not load RSEc data; will retry on first tool call")

    task = asyncio.create_task(warm())
    try:
        yield
    finally:
        task.cancel()


mcp = FastMCP(
    "rsec-sparql",
    lifespan=lifespan,
    instructions=(
        "Access to the Research Software Ecosystem (RSEc) RDF data. "
        "Software is described with schema.org / Bioschemas."
    ),
)

# SPARQL query 5 from ui/index.html ("SoftwareApplication & bio.tools IDs").
BIOTOOLS_IDS_QUERY = """\
PREFIX schema: <http://schema.org/>
SELECT ?application ?biotools_ID
WHERE {{
  ?application schema:identifier ?biotools_ID .
  FILTER STRSTARTS(STR(?biotools_ID), "https://bio.tools")
}}
ORDER BY STR(?biotools_ID) ?application
LIMIT {limit} OFFSET {offset}
"""


def build_query(limit: int, offset: int) -> str:
    # limit/offset are ints validated by the tool signature, never free text.
    return BIOTOOLS_IDS_QUERY.format(limit=int(limit), offset=int(offset))


async def run_select(query: str) -> list[dict[str, str]]:
    """Run a SELECT query on the RSEc graph, return rows as {var: value}."""
    try:
        graph = await store.get()
    except Exception as e:
        raise ToolError(
            f"Could not load the RSEc RDF data into {store.data_dir} ({e!r}). "
            "Check network access to raw.githubusercontent.com, or place the "
            "*.ttl dumps in that directory (see RSEC_DATA_DIR)."
        ) from e
    result = await asyncio.to_thread(graph.query, query)
    return [
        {str(var): str(value) for var, value in row.asdict().items()} for row in result
    ]


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
async def list_software_with_biotools_ids(
    limit: Annotated[int, Field(ge=1, le=1000, description="Max rows to return")] = 100,
    offset: Annotated[int, Field(ge=0, description="Rows to skip, for paging")] = 0,
) -> dict:
    """List software applications of the RSEc RDF data that have a bio.tools identifier.

    Returns schema:SoftwareApplication resources whose schema:identifier starts
    with https://bio.tools, ordered by identifier. Page with limit/offset;
    if `count` equals `limit`, more rows may be available.
    """
    rows = await run_select(build_query(limit, offset))
    results = [
        {"application": r["application"], "biotools_id": r["biotools_ID"]} for r in rows
    ]
    return {"results": results, "limit": limit, "offset": offset, "count": len(results)}


if __name__ == "__main__":
    mcp.run(show_banner=False)  # stdio
