# RSEc MCP server: specification

Status: draft, describes the server as implemented on branch `mcp-draft` (2026-11-10).

## 1. Purpose

Let an LLM agent explore the Research Software Ecosystem (RSEc) RDF data without writing SPARQL: find bio.tools software by EDAM topic, operation or name, inspect its licenses, inputs and outputs, and decide whether two tools can be chained. Data model and queries: [data-model.md](data-model.md).

## 2. Scope

| In scope | Out of scope |
|----------|--------------|
| Read-only questions on bio.tools records (`https://bio.tools/<id>`) typed with EDAM | Writing or updating data |
| EDAM term lookup (topic, operation, data, format) and hierarchy | Running tools or checking that two tools really work together |
| Input/output compatibility from EDAM annotations | Free-form SPARQL from the agent |
| Single user, local process | Multi-user serving, authentication, remote deployment |
| Records of other dumps (biocontainers, Galaxy, Debian...) only as extra license sources | Searching or returning those records |

## 3. Architecture

- FastMCP server, stdio transport, one process ([server.py](../server.py)).
- Data in memory: the RSEc dumps and `EDAM.owl` parsed into one rdflib `Graph` ([graph_store.py](../graph_store.py)). No SPARQL endpoint, no Docker.
- Knowledge layer ([knowledge_graph.py](../knowledge_graph.py), [edam.py](../edam.py)): each tool call builds and runs SPARQL on the graph; nothing is precomputed. Ranking, grouping, paging and compatibility rules are done in Python on the rows.
- All queries go through `graph_store.run_query`, which serialises them (rdflib's SPARQL parser is not thread-safe). Tool calls run off the event loop.

```
MCP client --stdio--> server.py (tools) --> KnowledgeGraph / edam (SPARQL builders) --> run_query --> rdflib Graph
```

## 4. Tools

All tools are read-only (`readOnlyHint`) and closed-world (`openWorldHint: false`). Results are JSON objects. Tools are identified by their bio.tools id (`blast`, `biotools:blast` or `https://bio.tools/blast`; case-insensitive). EDAM terms by `topic_0080`, `edam:topic_0080` or the full IRI.

| Tool | Arguments | Returns |
|------|-----------|---------|
| `resolve_edam_term` | `text`, `kind?` (`topic`, `operation`, `data`, `format`), `limit` (1-50, default 10) | `results[]`: `id`, `label`, `kind`, `matched` (`label`, `synonym`, `definition`), `definition`, `synonyms`, `broader[]`, `n_tools` (tools annotated directly; `null` for data and formats) |
| `search_software` | `topics?[]`, `operations?[]`, `name_contains?`, `limit` (1-100, default 20), `offset` | `total`, `limit`, `offset`, `results[]`: `biotools_id`, `iri`, `name`, `description` (300 characters at most), `url`, `licenses[]`, `topics[]`, `operations[]` |
| `list_licenses` | `contains?`, `limit` (1-200, default 50) | `total`, `licenses[]`: `license`, `tools` |
| `get_software_io` | `tool` | `biotools_id`, `name`, `inputs[]`, `outputs[]` (each `name`, `data`, `formats[]`; `data` and formats are `{id, label}`), `note` when the tool has no annotation |
| `check_composability` | `producer`, `consumer` | `compatibility`, `matches[]` (`kind`, `output`, `input`), `note` when `unknown` |
| `list_software_with_biotools_ids` | `limit` (1-1000, default 100), `offset` | `results[]`: `application`, `biotools_id`; `limit`, `offset`, `count` |

### Rules

**Search.**
- Filters of different kinds are ANDed; several ids inside `topics` or inside `operations` are ORed.
- Narrower EDAM terms are always included: `topic_0080` also matches tools annotated with its sub-topics.
- `name_contains` is a case-insensitive substring of the tool name or id.
- Results are sorted by name (case-insensitive), then IRI. With no filter, all tools are listed.
- Licenses are shown in the results but cannot be searched with this tool (the `KnowledgeGraph.search_software` method supports a `licenses` filter, not exposed).
- Only bio.tools records are returned (IRI `https://bio.tools/<id>`).

**EDAM lookup.** Candidates are the terms where the label, a synonym (exact, narrow or broad) or the definition contains every word. Deprecated terms are left out. Ranking: exact label, exact synonym, all words in the label, all words in a synonym, all words in the definition; ties by shorter label.

**Licenses.** Values are free text in the data (`MIT`, `GPL-3.0`, `None`, `unknown`...). `list_licenses` merges case variants, shows the most frequent spelling and counts each tool once per license. A tool's license is its own, or that of a linked record from another dump (when loaded).

**Composability.** An output fits an input when the input's EDAM data type is the output's type or one of its broader terms (never the reverse). Formats then grade the match; the best match decides `compatibility`.

| `kind` | Condition | `compatibility` |
|--------|-----------|-----------------|
| `exact` | same data type, a shared format | `direct` |
| `subtype` | narrower data type, or narrower format | `direct` |
| `format_unspecified` | data types fit, a side has no format | `probable` |
| `needs_conversion` | data types fit, formats differ | `needs_conversion` |
| `generic_input` | input typed `data_0006` ("Data"), which accepts anything | `generic` |
| none | no output fits any input | `none` |
| not decidable | the producer has no output annotation, or the consumer no input annotation | `unknown` |

`matches` is sorted from the best kind to the weakest.

## 5. Errors

Bad input becomes an MCP tool error with a message the agent can act on, never a stack trace:

- unknown tool id: `Unknown bio.tools id 'x'. Did you mean: ...? Use search_software (name_contains=...) to find the id of a tool.`
- malformed EDAM id, or an id of the wrong kind (e.g. an operation passed in `topics`): the expected form is given (`topic_0091`, `operation_0292`...).
- invalid `kind`: the allowed values are listed.
- data not loadable (no network, no files): the message names `RSEC_DATA_DIR` and the hosts to reach.

Missing annotations are not errors: they are answered with `note` (`get_software_io`) or `compatibility: "unknown"` (`check_composability`).

## 6. Data and startup

| Source | Content |
|--------|---------|
| `bioschemas-dump.ttl` (RSEc `datasets/`, raw.githubusercontent.com) | bio.tools records as schema.org / Bioschemas |
| `EDAM.owl` (edamontology.org, latest release) | labels, synonyms, definitions, hierarchy |

- Missing files are downloaded on first start; existing files are never re-downloaded (delete the data directory to refresh). Downloads are written to a `.part` file and renamed, so a failed download leaves no half-written file.
- Loading runs in the background at startup, so the MCP handshake is not delayed; the first tool call waits for it. A failed load is retried on the next call.
- Other dumps (biocontainers, Galaxy, Debian...) are listed but disabled in `DUMPS` in `graph_store.py`.

| Variable | Default | Role |
|----------|---------|------|
| `RSEC_DATA_DIR` | `mcp/data` | where the files are stored |
| `RSEC_LOG_LEVEL` | `INFO` | logs go to stderr (stdout carries the protocol); `DEBUG` logs every SPARQL query with its time |

## 7. Non-functional requirements

| Requirement | Target | Status (2026-11-10, 740k triples) |
|-------------|--------|-----------------------------------|
| Time of a tool call, once the data is loaded | under 10 s | 0.01 s to 2 s |
| Start-up load | background, one time | about 7 s plus the first download |
| Memory | about 2 GB free | 1.5 GB measured with all dumps |
| Injection | nothing from the caller reaches a query unescaped | EDAM ids pass a strict regex, text goes through `Literal.n3()`, numbers are validated ints, tool ids through `[A-Za-z0-9_.~+-]` |
| Query shape | start from a tool IRI or an EDAM term; no `VALUES` list of terms joined to the whole tool pattern (over 10 s on the full data) | see [data-model.md](data-model.md) |
| Tests | no network, no real data | `./run_tests.sh`, tiny fixtures in `tests/fixtures`, plus a test that fails if triple-traversal helpers replace SPARQL |

## 8. Known limits

- About 34,000 tools; only about 4,000 have input/output annotations, so composability is often `unknown` (well-known tools can be in that gap).
- Compatible annotations do not prove that the tools have been run together.
- License text is not normalised beyond case.
- EDAM IRIs used in the dumps but absent from EDAM (about 135 junk ids) are ignored.
- One query at a time: concurrent tool calls queue behind each other.
- `find_downstream_tools` (tools that can consume a tool's outputs) exists in `knowledge_graph.py` and is tested, but is not exposed.
