"""Build notebooks/demo.ipynb, the replayable demo of the RSEc MCP server.

    cd mcp
    uv run --with nbformat --with nbconvert --with ipykernel --with pandas \
        python notebooks/build_demo.py            # writes notebooks/demo.ipynb
    uv run --with nbformat --with nbconvert --with ipykernel --with pandas \
        jupyter nbconvert --to notebook --execute --inplace notebooks/demo.ipynb

(or `./run_tests.sh --notebook`, which does both).

The notebook replays the conversation of docs/demo.md. The questions and the
shortlist of tools are fixed, the tool calls are real: they go to server.py,
in-process, as an MCP client would send them.
"""

from pathlib import Path

import nbformat as nbf

MD, CODE = nbf.v4.new_markdown_cell, nbf.v4.new_code_cell

cells = [
    MD("""\
# RSEc MCP server: replaying a demo session

In [`docs/demo.md`](../docs/demo.md) a local LLM (Qwen, in LM Studio) uses the MCP server to answer three questions about metagenomics tools.
An LLM session cannot be repeated exactly, so this notebook **replays the same scenario with a fixed script**.
The questions and the shortlist of tools are written down; every answer below comes from a real call to the MCP tools of `server.py`, made in-process as an MCP client would.

1. *"I need to perform i) quality control on metagenomics data, and ii) quantify the abundance of species. Which tools can I use? Provide the bio.tools URLs and associated EDAM annotations."*
2. *"For all these tools, display their license."*
3. *"Also list their inputs and outputs, in terms of EDAM annotations."*

The shortlist of the session is FastQC, MultiQC, Kraken2, Bracken, MetaPhlAn and QIIME 2. The notebook checks it against the graph.
The first tool call loads about 740,000 triples (about 10 s once the files are downloaded); later calls are SPARQL queries on the loaded graph.
The whole notebook runs in about a minute."""),
    CODE("""\
import os, sys, time

os.environ.setdefault("RSEC_LOG_LEVEL", "WARNING")  # keep the loading logs out of the notebook
sys.path.insert(0, "..")                            # server.py lives in mcp/

import pandas as pd
from fastmcp import Client

import server

pd.set_option("display.max_colwidth", None)
pd.set_option("display.width", 160)

CALLS = []  # one entry per tool call, summarised at the end


async def tool(tool_name, /, **arguments):
    \"\"\"Call one MCP tool and return its result, as an agent would.\"\"\"
    t0 = time.perf_counter()
    async with Client(server.mcp) as client:
        result = (await client.call_tool(tool_name, arguments)).data
    CALLS.append({"tool": tool_name, "seconds": time.perf_counter() - t0})
    return result


# The shortlist of the LM Studio session (bio.tools ids are case-sensitive).
CANDIDATES = ["fastqc", "multiqc", "kraken2", "bracken", "metaphlan", "qiime2"]"""),
    MD("""\
## The tools the agent sees

The server describes its tools to the client (name, arguments, documentation). This is all the agent knows about the knowledge graph:
there is no SPARQL to write, and the agent cannot send a query of its own."""),
    CODE("""\
async with Client(server.mcp) as client:
    catalogue = await client.list_tools()

pd.DataFrame(
    [{"tool": t.name, "arguments": ", ".join(t.input_schema["properties"])} for t in catalogue]
)"""),
    MD("""\
## 1. Which tools, and what are their EDAM annotations?

### Step 1: from words to EDAM terms

Software is searched by EDAM id, so the agent first turns the needs into terms with `resolve_edam_term`.

The strategy is a lexical match on the EDAM ontology, done by one SPARQL query:

- A term is a candidate when its label, one of its synonyms or its definition contains **every word** of the request, as whole words and in any order. Deprecated terms are left out.
- Candidates are ranked by where the words are found: exact label, exact synonym, words in the label, words in a synonym, words in the definition (the `matched` column). Ties go to the shorter label.
- `kind` restricts the answer to one branch of EDAM (`topic`, `operation`, `data` or `format`). Without it, the same label can come back for several branches, as with *Taxonomic classification* below.

There is no semantic or fuzzy matching: "abundance estimation" finds nothing, because no EDAM term contains both words, so the agent has to rephrase (here, "species frequency")."""),
    CODE("""\
needs = ["sequencing quality control", "taxonomic classification", "species frequency", "metagenomics"]

rows = []
for text in needs:
    found = await tool("resolve_edam_term", text=text, limit=3)
    for r in found["results"]:
        rows.append({"asked": text, "id": r["id"], "label": r["label"], "kind": r["kind"], "matched": r["matched"]})

pd.DataFrame(rows)"""),
    MD("""\
### Step 2: software annotated with these terms

`search_software_by_operation` and `search_software_by_topic` list the tools annotated with a term or one of its narrower terms, 100 at a time.
The agent reads every page, then checks whether the shortlisted tools are in the lists."""),
    CODE("""\
async def all_software(kind, term_id):
    \"\"\"All the tools annotated with an EDAM operation or topic, page after page.\"\"\"
    found, offset = {}, 0
    while True:
        page = await tool(f"search_software_by_{kind}", **{kind: term_id}, limit=100, offset=offset)
        found.update({r["biotools_id"]: r["name"] for r in page["results"]})
        if page["count"] < page["limit"]:
            return found
        offset += page["limit"]


SEARCHES = {
    "Sequencing quality control": ("operation", "operation_3218"),
    "Taxonomic classification": ("operation", "operation_3460"),
    "Species frequency estimation": ("operation", "operation_3221"),
    "Metagenomics (topic)": ("topic", "topic_3174"),
}
listed = {name: await all_software(kind, term_id) for name, (kind, term_id) in SEARCHES.items()}

print("Tools annotated with each term (narrower terms included):")
print(pd.Series({name: len(ids) for name, ids in listed.items()}).to_string())

pd.DataFrame(
    {name: {t: "yes" if t in ids else "" for t in CANDIDATES} for name, ids in listed.items()}
).rename_axis("shortlisted tool")"""),
    MD("""\
### Step 3: the annotations of each shortlisted tool

`describe_software` returns everything the graph holds about a tool (a SPARQL `DESCRIBE`): EDAM topics and operations come as IRIs.
The agent gets their labels with `get_direct_term_parents`, which gives the label of the term it is asked about."""),
    CODE("""\
LABELS = {}


async def label(term_id):
    if term_id not in LABELS:
        LABELS[term_id] = (await tool("get_direct_term_parents", term=term_id))["term"]["label"]
    return LABELS[term_id]


async def labelled(iris):
    ids = sorted(iri.rsplit("/", 1)[-1] for iri in iris)
    return "; ".join([f"{i} ({await label(i)})" for i in ids])


rows = []
for t in CANDIDATES:
    described = await tool("describe_software", name=t)
    assert described["count"] == 1, t
    record = described["tools"][0]
    props = record["properties"]
    rows.append({
        "tool": props["schema:name"][0],
        "bio.tools URL": record["iri"],
        "operations": await labelled(props.get("schema:featureList", [])),
        "topics": await labelled(props.get("schema:applicationSubCategory", [])),
    })

pd.DataFrame(rows)"""),
    MD("""\
**What to notice.** The graph gives the exact labels of the EDAM ids, so the annotations can be checked:

- FastQC and MultiQC are annotated with *Sequencing quality control*, but not with the topic *Metagenomics*: they are general-purpose tools. An agent that intersects "quality control" and "metagenomics" would not find them.
- Bracken has neither *Taxonomic classification* nor *Species frequency estimation*; it is found through its topic (*Metagenomics*) only.
- Some labels in the LM Studio transcript are not the labels of the graph. For example `operation_2238` is *Statistical calculation* (not "Abundance estimation"), `topic_3168` is *Sequencing* (not "Metagenomics"), `operation_3933` is *Demultiplexing* (not "Relative abundance"). Calling the tools gives the labels as they are in EDAM.

## 2. Licenses

`get_license` gives the license text as written in the data (free text, possibly empty)."""),
    CODE("""\
rows = []
for t in CANDIDATES:
    result = await tool("get_license", tool=t)
    rows.append({"tool": result["name"], "license": ", ".join(result["licenses"]) or "(none)"})

pd.DataFrame(rows)"""),
    MD("""\
## 3. Inputs and outputs, in EDAM terms

`get_software_io` gives each input and output with its EDAM data type and formats.
When a tool has no annotation, the answer says so instead of guessing."""),
    CODE("""\
rows = []
for t in CANDIDATES:
    io = await tool("get_software_io", tool=t)
    for direction in ("inputs", "outputs"):
        for p in io[direction]:
            rows.append({
                "tool": io["name"],
                "direction": direction[:-1],
                "parameter": p["name"],
                "EDAM data": f'{p["data"]["id"]} ({p["data"]["label"]})',
                "EDAM formats": "; ".join(f'{f["id"]} ({f["label"]})' for f in p["formats"]),
            })
        if not io[direction]:
            rows.append({"tool": io["name"], "direction": direction[:-1], "parameter": "(not annotated)",
                         "EDAM data": "", "EDAM formats": ""})

pd.DataFrame(rows)"""),
    MD("""\
Bracken and QIIME 2 have no input/output annotation in the RSEc data, and MultiQC has outputs only: an agent has to say so, which is what the `note` of `get_software_io` is for. MetaPhlAn's output is listed twice because its record holds two output parameters with the same type and format.

## The tool calls of this notebook

Everything above came from these calls. The first one waits for the data to load; the others are SPARQL queries on the loaded graph."""),
    CODE("""\
(
    pd.DataFrame(CALLS)
    .groupby("tool")
    .agg(calls=("seconds", "count"), total_seconds=("seconds", "sum"), slowest_seconds=("seconds", "max"))
    .round(2)
    .sort_values("total_seconds", ascending=False)
)"""),
    MD("""\
## Run it again

```bash
cd mcp
./run_tests.sh --notebook      # rebuild and execute this notebook
uv run --with jupyterlab --with pandas jupyter lab notebooks/demo.ipynb   # explore it
```

The notebook is generated: edit `notebooks/build_demo.py` rather than the `.ipynb`. To plug the server into an LLM client such as LM Studio, see the README."""),
]

nb = nbf.v4.new_notebook(cells=cells)
nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
nbf.validate(nb)
out = Path(__file__).with_name("demo.ipynb")
nbf.write(nb, out)
print(f"wrote {out}")
