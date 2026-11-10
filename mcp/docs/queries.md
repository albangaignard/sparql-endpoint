
```sparql
01: PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
02: PREFIX schema: <http://schema.org/>
03: PREFIX bioconda: <https://github.com/bioconda/bioconda-recipes/tree/master/recipes/>
04: PREFIX edam: <http://edamontology.org/> 
05: 
06: SELECT ?bioconda ?op_label WHERE {
07:   VALUES ?bioconda { bioconda:admixture bioconda:abricate }
08:     ?bioconda schema:identifier ?id .
09:     ?id schema:featureList ?op .
10:     ?op rdfs:subClassOf* ?parent .
11:     ?parent rdfs:subClassOf+ edam:operation_0004 ;
12:             rdfs:label ?op_label .
13: }
```

Query 1. This SPARQL query shows how the RSEc linked data helps in semantically cross-linking bioinformatics software and packages. Here, for two Bioconda packages, we dynamically extract the EDAM annotations describing what the tools do (line 9) from the bio.tools entry (line 8), and we also collect all inherited annotations from the EDAM ontology itself (line 11, rdfs:subClassOf*  SPARQL property path) 

```
01: PREFIX edam: <http://edamontology.org/>
02: PREFIX schema: <http://schema.org/>
03: PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
04: PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
05: 
06: SELECT ?label (COUNT (?application) AS ?count)
07: WHERE {
08:      ?application schema:applicationSubCategory ?class .
09:     ?class  rdfs:label ?label ;
10:             rdfs:subClassOf* ?uri .
11:    ?uri rdfs:label "Genetic variation" .
12: }
13: GROUP BY ?class ?label
14: ORDER BY DESC(?count)
```

Query 2. This SPARQL query counts recursively the number of entries annotated with the given EDAM topic “Genetic variation” (line 11) and all of its subtopics by traversing the EDAM hierarchy (line 10, rdfs:subClassOf*  property). Results are ordered by decreasing count.
