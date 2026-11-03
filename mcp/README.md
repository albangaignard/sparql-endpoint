# RSEc SPARQL MCP server

FastMCP server that lets an LLM agent query the RSEc RDF data. The data is loaded in-process with [rdflib](https://rdflib.readthedocs.io), so nothing else (Fuseki, Docker) has to be deployed.

## Tools

| Tool | Wraps | Description |
|------|-------|-------------|
| `list_software_with_biotools_ids(limit=100, offset=0)` | UI example query 5 | `schema:SoftwareApplication` resources with a `https://bio.tools` identifier, ordered by identifier, paged |

## How to run

Prerequisites: [uv](https://docs.astral.sh/uv/) (it installs Python and the dependencies), internet access on first start, and about 2 GB of free RAM.

```bash
cd mcp
uv sync                   # install dependencies once
uv run python server.py   # start the server (stdio)
```

The server talks MCP over stdio, so started by hand it just waits silently for a client. Normally you do not run it yourself: an MCP client launches it (see [Connect an MCP client](#connect-an-mcp-client)). To try it without any client, use the next section.

On first start the server downloads the RSEc dumps (about 58 MB, the same files as in the root `docker-compose.yml`) into `mcp/data/`, then parses them (about 1M triples, roughly 10 s and 1.5 GB of RAM). Loading starts in the background at startup; the first tool call waits for it, later calls take well under a second. Existing files are never re-downloaded, so to refresh the data delete `mcp/data/`.

| Variable | Default |
|----------|---------|
| `RSEC_DATA_DIR` | `mcp/data` (set it to `../data` to reuse the dumps of the Docker setup) |
| `RSEC_LOG_LEVEL` | `INFO` (use `WARNING` to silence the loading logs) |

Progress is logged to stderr (stdout carries the MCP protocol), so clients show it in the server's log pane. Example:

```
11:31:32 INFO rsec.server: loading RSEc data in the background (first tool call waits for it)
11:31:32 INFO rsec.graph: data directory .../mcp/data: 0 dump(s) present, 8 to download
11:31:32 INFO rsec.graph: [1/8] downloading https://raw.githubusercontent.com/.../bioschemas-dump.ttl
11:31:35 INFO rsec.graph: [1/8] downloaded bioschemas-dump.ttl (36.5 MB, 2.9 s)
...
11:31:41 INFO rsec.graph: loaded 1041170 triples from 8 files in 9.4 s
11:31:41 INFO rsec.server: RSEc data ready: server can answer queries
```

## Quick test (no MCP client needed)

The `fastmcp` command line, installed with the project, starts the server, calls it and prints the result:

```bash
cd mcp
uv run fastmcp list server.py                                        # show the tools
uv run fastmcp call server.py list_software_with_biotools_ids limit=3   # call one
```

The second command should print three entries like this (the first run is slower while the data downloads and loads):

```json
{
  "results": [
    { "application": "https://github.com/galaxyproject/tools-iuc/tree/master/tools/abricate",
      "biotools_id": "https://bio.tools/ABRicate" },
    ...
  ],
  "limit": 3, "offset": 0, "count": 3
}
```

Add `offset=3` to get the next page. Add `--json` for raw JSON output.

## Connect an MCP client

The server speaks stdio: the client launches it. Most clients (Claude Desktop, Claude Code, Cursor, VS Code...) read the same `mcpServers` JSON. Replace `/absolute/path/to` with the location of this repo.

```json
{
  "mcpServers": {
    "rsec-sparql": {
      "command": "uv",
      "args": [
        "--directory", "/absolute/path/to/RSEc_SPARQL_endpoint/mcp",
        "run", "python", "server.py"
      ]
    }
  }
}
```

Where to put it:

| Client | File |
|--------|------|
| Claude Code (project, shareable) | `.mcp.json` at the repo root |
| Claude Desktop (macOS) | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Cursor | `.cursor/mcp.json` |

If `uv` is not found by a GUI client, use its full path (`which uv`, e.g. `/opt/homebrew/bin/uv`) in `command`.

To use another data directory, add `"env": { "RSEC_DATA_DIR": "/path/to/dumps" }` next to `args`. (The `fastmcp list/call` quick test above does not forward environment variables to the server; use the defaults there.)

Equivalent one-liner for Claude Code:

```bash
claude mcp add rsec-sparql -- uv --directory /absolute/path/to/RSEc_SPARQL_endpoint/mcp run python server.py
```

### Check it works

Ask the agent, for example: *"List 10 software applications that have a bio.tools identifier."* It should call `list_software_with_biotools_ids` with `limit=10`. The first call can take 15 s or more while the data downloads and loads. If it reports it could not load the data, check network access to `raw.githubusercontent.com`, or put the `*.ttl` dumps in `RSEC_DATA_DIR`.

## Unit tests

```bash
./run_tests.sh           # unit tests only (fast, no network)
./run_tests.sh --smoke   # + call the tool on the real data (downloads it on first run)
```

or directly: `uv run pytest`.
Tests use a tiny local graph and a mocked HTTP layer; they need neither network nor the real dumps.
