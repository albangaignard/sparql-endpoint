# RSEc data model (as used by the MCP tools)

Observed on the dumps downloaded on 2026-11-03. Re-check these numbers when the upstream dumps change.

`graph_store.py` currently loads only `bioschemas-dump.ttl` and `EDAM.owl` (about 740k triples; the other dumps are commented out in `DUMPS`). The counts in the table below were taken with all the dumps loaded (about 1.04M triples), so the Linked-records license path (`UNION` in `_LICENSE`) returns nothing until they are re-enabled.

| Need | Where it is | Notes |
|------|-------------|-------|
| Tool identity | `schema:SoftwareApplication` with IRI `https://bio.tools/<id>` (34,177) | Other dumps (biocontainers, Galaxy, Debian...) have their own IRIs and point to the bio.tools record with `schema:identifier` |
| Name, description, homepage | `schema:name`, `schema:description`, `schema:url` | |
| EDAM topics | `schema:applicationSubCategory` -> `edam:topic_NNNN` | A few hundred values are operations/data instead; ignored |
| EDAM operations | `schema:featureList` -> `edam:operation_NNNN` | |
| License | `schema:license`, free-text literal | `MIT` 7.3k, `GPL-3.0` 5.2k, but also `None`, `Not licensed`, `unknown`, `GPL (>= 2)`, `perl_5`... Linked records (biocontainers) often carry the license when the bio.tools record has none |
| Inputs / outputs | `bioschemas:input` / `bioschemas:output` (namespace `http://bioschemas.org/`, not https) -> blank node of type `bioschemas:types/FormalParameter` | 4,079 tools with inputs, 3,388 with outputs, 3,268 with both |
| Parameter typing | `schema:additionalType` -> `edam:data_NNNN` (exactly one), `schema:encodingFormat` -> `edam:format_NNNN` (0 to 7; 31% have none), `schema:name` | Some inputs/outputs of Galaxy/Debian records are plain literals (`fasta`, `tabular`); ignored |
| EDAM labels and hierarchy | not in the dumps; loaded from `https://edamontology.org/EDAM.owl` | 3,541 classes, 1,120 deprecated. About 135 IRIs used in the dumps do not exist in EDAM (junk ids such as `operation__R9Fv...`) |

## How the tools query the graph

No index is built at startup: every tool call runs SPARQL with rdflib through `graph_store.run_query`, which serialises the runs because rdflib's SPARQL parser is not thread-safe. The server only parses the dumps in the background at startup (about 7 s for the 740k triples). Tests fail if the triple-traversal helpers (`subjects`, `objects`, `value`...) come back.

rdflib has no query optimiser, so each query starts from something selective (a tool IRI or an EDAM term) and reaches the rest through a property path. A `VALUES` list of terms joined to the whole tool pattern took more than 10 s on the full data (30 s for the per-term tool counts), which is why the term is either the subject of a `UNION` branch or the `VALUES` list is only used on a small set (one result page, a few hundred candidate terms).

Shared fragments of `knowledge_graph.py`:

```sparql
# _PREFIXES
PREFIX schema: <http://schema.org/>
PREFIX bs: <http://bioschemas.org/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

# _TOOL: a tool is a bio.tools record
?tool a schema:SoftwareApplication ; schema:name ?name .

# _ONLY_BIOTOOLS: ignore the records of the other dumps
FILTER REGEX(STR(?tool), "^https://bio.tools/[A-Za-z0-9_.~+-]+$")

# _LICENSE: own license, or the one of a linked record (biocontainers, Galaxy...)
{ ?tool schema:license ?license } UNION { ?record schema:identifier ?tool ; schema:license ?license }
```

Timings below were measured on 2026-11-10 on the 740k-triple graph (10 s budget per query).

## Queries by tool

Every query below is complete and can be pasted into a SPARQL console on the loaded graph (dumps + `EDAM.owl`). Values such as `topic_0080` or `clustalw` are examples: the code substitutes the tool arguments. Timings are for the example shown.

### `search_software` (`KnowledgeGraph.search_software`)

One `SELECT DISTINCT ?tool ?name` built from the arguments, then a second query for the details of the page returned. Names are de-duplicated, sorted and paged in Python (`total`, `limit`, `offset`). Ids go through `edam.normalize` (strict regex) and text through `rdflib.Literal.n3()`, so nothing user-supplied is spliced raw.

**By topic, with narrower topics** (`topics=["topic_0080"]`, `include_subterms=True`, the default). The query starts from the term and walks down. 1.7 s, 6,649 rows.

```sparql
PREFIX schema: <http://schema.org/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT DISTINCT ?tool ?name WHERE {
  ?topic rdfs:subClassOf* <http://edamontology.org/topic_0080> .
  ?tool schema:applicationSubCategory ?topic .
  ?tool a schema:SoftwareApplication ; schema:name ?name .
  FILTER REGEX(STR(?tool), "^https://bio.tools/[A-Za-z0-9_.~+-]+$")
}
```

**By topic, exact term only** (`include_subterms=False`):

```sparql
PREFIX schema: <http://schema.org/>

SELECT DISTINCT ?tool ?name WHERE {
  ?tool schema:applicationSubCategory <http://edamontology.org/topic_0080> .
  ?tool a schema:SoftwareApplication ; schema:name ?name .
  FILTER REGEX(STR(?tool), "^https://bio.tools/[A-Za-z0-9_.~+-]+$")
}
```

**By operation** (`operations=["operation_0292"]`): same as the topic query, with `schema:featureList` in place of `schema:applicationSubCategory`.

```sparql
PREFIX schema: <http://schema.org/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT DISTINCT ?tool ?name WHERE {
  ?op rdfs:subClassOf* <http://edamontology.org/operation_0292> .
  ?tool schema:featureList ?op .
  ?tool a schema:SoftwareApplication ; schema:name ?name .
  FILTER REGEX(STR(?tool), "^https://bio.tools/[A-Za-z0-9_.~+-]+$")
}
```

**Several topics, plus an operation** (`topics=["topic_0080", "topic_3168"]`, `operations=["operation_0292"]`). Topics are alternatives (`UNION`, each branch with its own variable), topics and operations together are a conjunction. 1.3 s, 769 rows.

```sparql
PREFIX schema: <http://schema.org/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT DISTINCT ?tool ?name WHERE {
  { ?topic rdfs:subClassOf* <http://edamontology.org/topic_0080> . ?tool schema:applicationSubCategory ?topic . }
  UNION
  { ?topic rdfs:subClassOf* <http://edamontology.org/topic_3168> . ?tool schema:applicationSubCategory ?topic . }
  ?op rdfs:subClassOf* <http://edamontology.org/operation_0292> .
  ?tool schema:featureList ?op .
  ?tool a schema:SoftwareApplication ; schema:name ?name .
  FILTER REGEX(STR(?tool), "^https://bio.tools/[A-Za-z0-9_.~+-]+$")
}
```

**By license** (`licenses=["gpl-3.0"]`, compared in lower case; supported by `KnowledgeGraph.search_software` but not exposed by the `search_software` tool, which only shows licenses). The license is the tool's own, or the one of a record from another dump that points to it with `schema:identifier`. 1.0 s, 4,359 rows.

```sparql
PREFIX schema: <http://schema.org/>

SELECT DISTINCT ?tool ?name WHERE {
  ?tool a schema:SoftwareApplication ; schema:name ?name .
  { ?tool schema:license ?license }
  UNION
  { ?record schema:identifier ?tool ; schema:license ?license }
  FILTER REGEX(STR(?tool), "^https://bio.tools/[A-Za-z0-9_.~+-]+$")
  FILTER (LCASE(STR(?license)) IN ("gpl-3.0"))
}
```

**By name** (`name_contains="blast"`, matches the name or the id). 1.2 s, 93 rows.

```sparql
PREFIX schema: <http://schema.org/>

SELECT DISTINCT ?tool ?name WHERE {
  ?tool a schema:SoftwareApplication ; schema:name ?name .
  FILTER REGEX(STR(?tool), "^https://bio.tools/[A-Za-z0-9_.~+-]+$")
  FILTER (CONTAINS(LCASE(?name), "blast") || CONTAINS(LCASE(STR(?tool)), "blast"))
}
```

**All filters at once** (`operations=["operation_0292"]`, `licenses=["MIT"]`, `name_contains="clustal"`): the patterns of each argument are joined in one group, the license and name conditions in one `FILTER`. 1.6 s.

```sparql
PREFIX schema: <http://schema.org/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT DISTINCT ?tool ?name WHERE {
  ?op rdfs:subClassOf* <http://edamontology.org/operation_0292> .
  ?tool schema:featureList ?op .
  ?tool a schema:SoftwareApplication ; schema:name ?name .
  { ?tool schema:license ?license }
  UNION
  { ?record schema:identifier ?tool ; schema:license ?license }
  FILTER REGEX(STR(?tool), "^https://bio.tools/[A-Za-z0-9_.~+-]+$")
  FILTER (LCASE(STR(?license)) IN ("mit")
          && (CONTAINS(LCASE(?name), "clustal") || CONTAINS(LCASE(STR(?tool)), "clustal")))
}
```

**Details of the page returned** (`_summaries`): description, url, licenses and labelled topics and operations of the (at most `limit`) tools of the page, in one query. 0.01 to 0.02 s.

```sparql
PREFIX schema: <http://schema.org/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?tool ?field ?val ?label WHERE {
  VALUES ?tool { <https://bio.tools/blast> <https://bio.tools/clustalw> <https://bio.tools/jalview> }
  { ?tool schema:description ?val BIND("description" AS ?field) }
  UNION { ?tool schema:url ?val BIND("url" AS ?field) }
  UNION { ?tool schema:applicationSubCategory ?val
          FILTER STRSTARTS(STR(?val), "http://edamontology.org/topic_")
          OPTIONAL { ?val rdfs:label ?label }
          BIND("topic" AS ?field) }
  UNION { ?tool schema:featureList ?val
          FILTER STRSTARTS(STR(?val), "http://edamontology.org/operation_")
          OPTIONAL { ?val rdfs:label ?label }
          BIND("operation" AS ?field) }
  UNION { { ?tool schema:license ?val } UNION { ?record schema:identifier ?tool ; schema:license ?val }
          BIND("license" AS ?field) }
}
```

### `list_licenses` (`KnowledgeGraph.list_licenses`)

One query; the licenses are grouped by case-insensitive spelling in Python (the most frequent spelling is shown, each tool is counted once per license). With `contains="gpl"` the query gets one more line, `FILTER CONTAINS(LCASE(STR(?license)), "gpl")`. 0.5 s, 15,526 rows.

```sparql
PREFIX schema: <http://schema.org/>

SELECT DISTINCT ?tool ?license WHERE {
  { ?tool schema:license ?license }
  UNION
  { ?record schema:identifier ?tool ; schema:license ?license }
  ?tool a schema:SoftwareApplication ; schema:name ?name .
  FILTER REGEX(STR(?tool), "^https://bio.tools/[A-Za-z0-9_.~+-]+$")
}
```

### `resolve_edam_term` (`KnowledgeGraph.resolve_edam_term`, `edam.search`)

Three steps for `text="sequence alignment"`.

**1. Candidate terms** (`edam._q_search`): one field (label, synonym or definition) contains every word. `kind="operation"` restricts the IRI prefix to `.../operation_`; without `kind` it is `http://edamontology.org/`. Deprecated terms are left out. Ranking is then done in Python (exact label, exact synonym, all words in label, all words in a synonym, all words in the definition; ties by shorter label). 0.55 s, 91 candidates.

```sparql
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
PREFIX oio: <http://www.geneontology.org/formats/oboInOwl#>

SELECT DISTINCT ?term WHERE {
  { ?term rdfs:label ?text }
  UNION { ?term oio:hasExactSynonym ?text }
  UNION { ?term oio:hasNarrowSynonym ?text }
  UNION { ?term oio:hasBroadSynonym ?text }
  UNION { ?term oio:hasDefinition ?text }
  FILTER (REGEX(STR(?term), "^http://edamontology.org/(topic|operation|data|format)_[0-9]{4}$")
          && STRSTARTS(STR(?term), "http://edamontology.org/"))
  FILTER (CONTAINS(LCASE(STR(?text)), "sequence") && CONTAINS(LCASE(STR(?text)), "alignment"))
  FILTER NOT EXISTS { ?term owl:deprecated "true"^^xsd:boolean }
}
```

**2. Term details** of the candidates, then of their parents (to label `broader`): the "EDAM term details" query below. 0.01 to 0.02 s each.

**3. Tools per term** (`_n_tools`): the tools annotated directly with each topic or operation hit (narrower terms not counted), with one `UNION` branch per term, each starting from the term. 0.02 s. A topic hit uses `schema:applicationSubCategory` in its branch, an operation hit `schema:featureList`.

```sparql
PREFIX schema: <http://schema.org/>

SELECT ?term (COUNT(DISTINCT ?tool) AS ?n) WHERE {
  { ?tool schema:featureList <http://edamontology.org/operation_0292> .
    ?tool a schema:SoftwareApplication ; schema:name ?name .
    FILTER REGEX(STR(?tool), "^https://bio.tools/[A-Za-z0-9_.~+-]+$")
    BIND(<http://edamontology.org/operation_0292> AS ?term) }
  UNION
  { ?tool schema:applicationSubCategory <http://edamontology.org/topic_0080> .
    ?tool a schema:SoftwareApplication ; schema:name ?name .
    FILTER REGEX(STR(?tool), "^https://bio.tools/[A-Za-z0-9_.~+-]+$")
    BIND(<http://edamontology.org/topic_0080> AS ?term) }
} GROUP BY ?term
```

### `get_software_io` (`KnowledgeGraph.get_software_io`)

`resolve_tool` checks the id (see "Tool lookup"), then one query fetches every input and output of the tool (0.01 s). Rows are grouped in Python into one parameter per (parameter node, data type) with its set of formats; parameters without `schema:additionalType` are dropped. Data and format terms are then labelled with the "EDAM term details" query.

```sparql
PREFIX schema: <http://schema.org/>
PREFIX bs: <http://bioschemas.org/>

SELECT ?dir ?param ?name ?dtype ?fmt WHERE {
  { <https://bio.tools/clustalw> bs:input ?param . BIND("input" AS ?dir) }
  UNION
  { <https://bio.tools/clustalw> bs:output ?param . BIND("output" AS ?dir) }
  ?param schema:additionalType ?dtype .
  OPTIONAL { ?param schema:name ?name }
  OPTIONAL { ?param schema:encodingFormat ?fmt }
}
```

### `check_composability` (`KnowledgeGraph.check_composability`)

`resolve_tool` for both tools, the query above once for the producer (keeping its outputs) and once for the consumer (keeping its inputs), the "EDAM ancestors" query on the output data types and formats, then the "EDAM term details" query to label the matches. 0.65 s for `clustalw` -> `jalview`, nearly all of it the lower-case fallback of `resolve_tool` (`jalview` is stored as `Jalview`); with exact ids it is about 0.01 s.

The matching rules (`_match`) are in Python. An output can feed an input when the input data type is the output type or one of its broader terms; formats then decide between `exact`, `subtype`, `format_unspecified` and `needs_conversion`. An input typed `data_0006` ("Data") is the separate, weakest `generic_input` tier.

### `find_downstream_tools` (`KnowledgeGraph.find_downstream_tools`)

Implemented and tested in `knowledge_graph.py` but not exposed as an MCP tool in `server.py`. It reads the producer's outputs with the `get_software_io` query, then one query for the candidate consumers: inputs whose data type is an output's type or one of its broader terms, starting from the producer IRI. Candidates are ranked in Python and the page details are fetched as for `search_software`. 0.56 s, 1,197 rows for `clustalw`.

```sparql
PREFIX schema: <http://schema.org/>
PREFIX bs: <http://bioschemas.org/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT DISTINCT ?tool ?tname ?param ?name ?dtype ?fmt WHERE {
  <https://bio.tools/clustalw> bs:output ?out .
  ?out schema:additionalType ?outtype .
  ?outtype rdfs:subClassOf* ?dtype .
  ?param schema:additionalType ?dtype .
  ?tool bs:input ?param .
  ?tool a schema:SoftwareApplication ; schema:name ?tname .
  OPTIONAL { ?param schema:name ?name }
  OPTIONAL { ?param schema:encodingFormat ?fmt }
  FILTER REGEX(STR(?tool), "^https://bio.tools/[A-Za-z0-9_.~+-]+$")
  FILTER (?tool != <https://bio.tools/clustalw>)
}
```

### `list_software_with_biotools_ids` (`server.py`)

The only query that is a fixed template (`limit` and `offset` are validated ints). 0.4 s.

```sparql
PREFIX schema: <http://schema.org/>

SELECT ?application ?biotools_ID
WHERE {
  ?application schema:identifier ?biotools_ID .
  FILTER STRSTARTS(STR(?biotools_ID), "https://bio.tools")
}
ORDER BY STR(?biotools_ID) ?application
LIMIT 100 OFFSET 0
```

### Tool lookup (`KnowledgeGraph.resolve_tool`)

Shared by every tool that takes a bio.tools id (`blast`, `biotools:blast` and `https://bio.tools/blast` are all accepted). Three queries, each run only if the previous one found nothing.

**1. Exact IRI.** Under 0.01 s.

```sparql
PREFIX schema: <http://schema.org/>

SELECT ?name WHERE { <https://bio.tools/blast> a schema:SoftwareApplication ; schema:name ?name }
```

**2. Other case** (ids are case-sensitive in the IRIs, users are not). 0.65 s.

```sparql
PREFIX schema: <http://schema.org/>

SELECT ?tool ?name WHERE {
  ?tool a schema:SoftwareApplication ; schema:name ?name .
  FILTER (LCASE(STR(?tool)) = "https://bio.tools/jalview")
}
```

**3. Unknown id**: list every id, to suggest close ones with `difflib` in the error message. 0.5 s, 34,177 rows.

```sparql
PREFIX schema: <http://schema.org/>

SELECT DISTINCT ?tool WHERE {
  ?tool a schema:SoftwareApplication .
  FILTER REGEX(STR(?tool), "^https://bio.tools/[A-Za-z0-9_.~+-]+$")
}
```

## EDAM queries (`edam.py`)

EDAM is not in the dumps; `EDAM.owl` is loaded in the same graph. Only numbered classes are used (`ID_REGEX`: `topic|operation|data|format` followed by four digits), which leaves out annotation properties, root classes and the junk ids found in the dumps. `edam.is_edam` and `edam.normalize` make an IRI safe to embed in a query.

### EDAM term details

`edam.terms(g, iris)` returns label, definition, synonyms (exact, narrow and broad) and direct parents of a list of terms, with `VALUES` on that list (never more than a few hundred terms). Terms without a label are dropped. `edam.labels` is this query, keeping only the labels. 0.01 to 0.02 s for 3 to 470 terms.

```sparql
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX oio: <http://www.geneontology.org/formats/oboInOwl#>

SELECT ?term ?field ?val WHERE {
  VALUES ?term { <http://edamontology.org/data_0863> <http://edamontology.org/data_2044> <http://edamontology.org/format_1929> }
  { ?term a owl:Class ; rdfs:label ?val BIND("label" AS ?field) }
  UNION { ?term oio:hasDefinition ?val BIND("definition" AS ?field) }
  UNION { ?term oio:hasExactSynonym ?val BIND("synonym" AS ?field) }
  UNION { ?term oio:hasNarrowSynonym ?val BIND("synonym" AS ?field) }
  UNION { ?term oio:hasBroadSynonym ?val BIND("synonym" AS ?field) }
  UNION { ?term rdfs:subClassOf ?val
          FILTER REGEX(STR(?val), "^http://edamontology.org/(topic|operation|data|format)_[0-9]{4}$")
          BIND("parent" AS ?field) }
}
```

### EDAM ancestors

`edam.ancestors(g, iris)` gives, for each IRI, the term itself and all its broader terms (transitive). The property path starts from the listed terms. An IRI that is not an EDAM class keeps only itself. 0.01 s for 2 terms (86 rows).

```sparql
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?term ?ancestor WHERE {
  VALUES ?term { <http://edamontology.org/data_0863> <http://edamontology.org/format_1929> }
  ?term rdfs:subClassOf* ?ancestor .
  FILTER REGEX(STR(?ancestor), "^http://edamontology.org/(topic|operation|data|format)_[0-9]{4}$")
}
```

### Narrower terms

There is no narrower-terms query: `search_software` walks down from the term with `?topic rdfs:subClassOf* <term> . ?tool schema:applicationSubCategory ?topic`.
