from rdflib import Graph, Namespace

# Initialize the RDF graph and the namespace
EX = Namespace("http://example.org/lungCancer/entity/")
kg_graph = Graph()

# Load your knowledge graph (this path should be updated with your actual file path)
kg_graph.parse("/Users/behnoosh/Desktop/Behnoosh_Thesis-main/KG/LC_Enriched_KG/LC_Enriched_KG_with_status.nt", format='nt')

# Define the PCA body size query
pca_body_size_query = """
SELECT (COUNT(DISTINCT ?patient) AS ?PCABodySize) WHERE {
    ?patient a ex:Patient ;
             ex:hasValidationStatus "valid" .
    ?patient ex:hasRelapse_Progression <http://example.org/lungCancer/entity/Progression> .
    ?patient ex:treatmentType <http://example.org/lungCancer/entity/Immunotherapy> .
    ?patient <http://example.org/lungCancer/entity/patientDrug> ?y .
}
"""

# Run the query to get the PCA body size
pcabodysize_result = kg_graph.query(pca_body_size_query, initNs={'ex': EX})

# Extract the result
pcabodysize = int(pcabodysize_result.bindings[0]['PCABodySize'].value) if pcabodysize_result.bindings else 0

# Print the result
print(f"PCA body size: {pcabodysize}")
