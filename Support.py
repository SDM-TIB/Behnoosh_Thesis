from rdflib import Graph, Namespace

# Load your RDF graph
kg_graph = Graph()
kg_graph.parse("/Users/behnoosh/Desktop/Behnoosh_Thesis-main/KG/LC_Enriched_KG/LC_Enriched_KG_with_status.nt", format="nt")

# Define the namespaces
EX = Namespace("http://example.org/lungCancer/entity/")

# Define the SPARQL query
query = """
SELECT (COUNT(DISTINCT ?patient) AS ?Support) WHERE {
    ?patient a ex:Patient ;
             ex:hasValidationStatus "valid" .
    ?patient ex:hasRelapse_Progression <http://example.org/lungCancer/entity/Progression> .
    ?patient ex:treatmentType <http://example.org/lungCancer/entity/Immunotherapy> .
    ?patient ex:patientDrug <http://example.org/lungCancer/entity/Nivolumab> .
}
"""

# Run the query
results = kg_graph.query(query, initNs={'ex': EX})

# Print the result
for row in results:
    print(f"Support: {row['Support']}")
