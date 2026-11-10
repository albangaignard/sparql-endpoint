# RSEc SPARQL MCP server

FastMCP server that lets an LLM agent query the RSEc RDF data. The data is loaded in-process with [rdflib](https://rdflib.readthedocs.io), so nothing else (Fuseki, Docker) has to be deployed.

## Tools

An agent typically goes: resolve EDAM terms -> search -> inspect inputs/outputs -> check whether two tools can be chained.

| Tool | Description |
|------|-------------|
| `resolve_edam_term(text, kind?, limit)` | EDAM terms (topic, operation, data, format) from free text such as "sequence alignment", via labels, synonyms and definitions. Returns the id to use elsewhere, the parent terms and how many tools carry the term |
| `search_software(topics?, operations?, name_contains?, limit, offset)` | bio.tools software by EDAM topic / operation (narrower terms always included) and name. Filters are ANDed, several ids inside one filter are ORed. Returns `total`, description, licenses (shown, not searchable), topics and operations |
| `list_licenses(contains?, limit)` | Licenses in use with tool counts, to get an overview (the data has many spellings: `GPL-3`, `GPL-3.0`, `GPL-3.0-or-later`...). Case variants are merged |
| `get_software_io(tool)` | A tool's inputs and outputs with EDAM data type and formats |
| `check_composability(producer, consumer)` | Can the outputs of A feed the inputs of B? `direct` / `probable` / `needs_conversion` / `generic` / `none` / `unknown`, with the matching output/input pairs |
| `list_software_with_biotools_ids(limit, offset)` | UI example query 5: applications with a `https://bio.tools` identifier |

Tools are identified by their bio.tools id (`blast`, or `https://bio.tools/blast`, case-insensitive).

### How composability is decided

An output fits an input when the output's EDAM **data type** is the same or **narrower** (a *Protein sequence* fits a *Sequence* input, not the reverse). The **formats** then grade the match:

| Kind | Meaning | Level |
|------|---------|-------|
| `exact` | same data type, a shared format | direct |
| `subtype` | narrower data type and/or narrower format (FASTA fits *FASTA-like*) | direct |
| `format_unspecified` | data types fit, but one side has no format annotation | probable |
| `needs_conversion` | data types fit, formats differ | needs_conversion |
| `generic_input` | input is typed with EDAM's root *Data*, which accepts anything | generic |

### What the data can and cannot answer

Measured on the current dumps (see [`docs/data-model.md`](docs/data-model.md)):

- About 34,000 bio.tools records; most have EDAM topics and operations, about 45% a license.
- Only about 4,000 tools have input/output annotations and 3,268 have both. For the others composability is `unknown`, and the tool says which side is missing. Well-known tools can fall in that gap (for example `ncbi_blast_plus` has none).
- A matching data type and format means the annotations are compatible, not that the tools have been run together.

## How to run

Prerequisites: [uv](https://docs.astral.sh/uv/) (it installs Python and the dependencies), internet access on first start, and about 2 GB of free RAM.

```bash
cd mcp
uv sync                   # install dependencies once
uv run python server.py   # start the server (stdio)
```

The server talks MCP over stdio, so started by hand it just waits silently for a client. Normally you do not run it yourself: an MCP client launches it (see [Connect an MCP client](#connect-an-mcp-client)). To try it without any client, use the next section.

On first start the server downloads the RSEc dumps (about 58 MB, the same files as in the root `docker-compose.yml`) and the EDAM ontology (3.4 MB, latest release from edamontology.org) into `mcp/data/`, then parses them (about 1.1M triples, roughly 10 s and 1.5 GB of RAM) and nothing else is precomputed: each tool call runs SPARQL queries on the loaded graph (set `RSEC_LOG_LEVEL=DEBUG` to log every query with its time). Loading starts in the background at startup and the first tool call waits for it; after that a call takes from a fraction of a second to a few seconds. Existing files are never re-downloaded, so to refresh the data delete `mcp/data/`.

| Variable | Default |
|----------|---------|
| `RSEC_DATA_DIR` | `mcp/data` (set it to `../data` to reuse the dumps of the Docker setup) |
| `RSEC_LOG_LEVEL` | `INFO` (use `WARNING` to silence the loading logs) |

Progress is logged to stderr (stdout carries the MCP protocol), so clients show it in the server's log pane. Example:

```
11:31:32 INFO rsec.server: loading RSEc data in the background (first tool call waits for it)
11:31:32 INFO rsec.graph_store: data directory .../mcp/data: 0 dump(s) present, 8 to download
11:31:32 INFO rsec.graph_store: [1/8] downloading https://raw.githubusercontent.com/.../bioschemas-dump.ttl
11:31:35 INFO rsec.graph_store: [1/8] downloaded bioschemas-dump.ttl (36.5 MB, 2.9 s)
...
11:31:41 INFO rsec.graph_store: loaded 1041170 triples from 8 files in 9.4 s
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

## Demo notebook

`notebooks/demo.ipynb` plays an agent on two questions with the real tools, called in-process like an MCP client would: *list tools that trim, align, quality-check and quantify RNA-seq reads*, and *can HISAT2 and Kallisto be composed, justified with EDAM terms?* It runs in about 30 s once the data is downloaded. The notebook is generated, so edit `notebooks/build_demo.py` rather than the `.ipynb`:

```bash
./run_tests.sh --notebook    # rebuild and execute it
uv run --with jupyterlab --with pandas --with seaborn jupyter lab notebooks/demo.ipynb   # explore it
```

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

Ask the agent, for example: *"Which tools do sequence alignment, and can the output of Clustal feed into BLAST?"* It should call `resolve_edam_term`, `search_software`, then `check_composability`. The first call waits for the data to download and load (about 10 s once the files are cached, more on the very first run). If it reports it could not load the data, check network access to `raw.githubusercontent.com`, or put the `*.ttl` dumps in `RSEC_DATA_DIR`.

## Unit tests

```bash
./run_tests.sh           # unit tests only (fast, no network)
./run_tests.sh --smoke   # + call the tool on the real data (downloads it on first run)
```

or directly: `uv run python -m unittest` (add `-v` to list each test, or name a module: `python -m unittest tests.test_knowledge_graph`).
The tests use only the standard library `unittest`. They use a tiny local graph and a mocked HTTP layer; they need neither network nor the real dumps.
