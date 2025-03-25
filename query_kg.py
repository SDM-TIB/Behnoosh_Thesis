from rdflib import Graph

# Load the updated knowledge graph file
g = Graph()
g.parse("/Users/behnoosh/Desktop/Master_Arbeit/Behnoosh_Thesis/KG/Updated-LungCancer-OriginalKG.nt", format="nt")

# SPARQL query to find patients and their validation reports
query = """
PREFIX lc: <http://example.org/lungCancer/entity/>
SELECT ?patient ?report
WHERE {
    ?patient lc:hasValidationReport ?report .
}
"""

# Run the query and print results
results = g.query(query)
print("Patients and their validation reports:")
for row in results:
    print(f"Patient: {row.patient}, Report: {row.report}")