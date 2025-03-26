import rdflib
import pandas as pd
from pyshacl import validate

# Load the KG
kg = rdflib.Graph()
kg.parse("KG/Updated-LungCancer-OriginalKG.nt", format="nt")
for patient in ["3426_Patient", "3528_Patient", "3561_Patient", "3877_Patient", "6203_Patient"]:
    print(f"\nTriples for {patient}:")
    for s, p, o in kg.triples((rdflib.URIRef(f"http://example.org/lungCancer/entity/{patient}"), None, None)):
        print(f"{s} {p} {o}")
# Load the rules file
rules_df = pd.read_csv("Rules/LungCancer-rules-short.csv")
print(f"Loaded {len(rules_df)} rules.")

# Load SHACL shapes
shapes_graph = rdflib.Graph()
shapes_graph.parse("Constraint/shapes.ttl", format="turtle")
print("Loaded SHACL shapes from shapes.ttl")

# Validate KG against shapes.ttl
validation_result = validate(kg, shacl_graph=shapes_graph, inference='rdfs')
conforms, results_graph, results_text = validation_result
print(f"KG Conforms to SHACL: {conforms}")
if not conforms:
    print("Validation Issues:")
    print(results_text)

# Function to parse Body into SPARQL conditions
def parse_body_to_sparql(body):
    parts = body.split()
    conditions = []
    for i in range(0, len(parts), 3):
        subject, predicate, object = parts[i], parts[i+1], parts[i+2]
        predicate = f"<http://example.org/lungCancer/entity/{predicate}>"
        if object.startswith("?"):
            object = object
        else:
            object = f"<http://example.org/lungCancer/entity/{object}>" if object in ["Immunotherapy", "Intravenous_Chemotherapy", "Radiotherapy_To_Lung", "Progression", "Male", "FormerSmoker"] else f'"{object}"'
        if subject == "?a":
            conditions.append(f"?patient {predicate} {object} .")
    return " ".join(conditions)

# Function to get SHACL validation status for a patient
def is_patient_valid(patient_uri, kg, shapes_graph):
    # Explicitly check patient type and validate
    query = f"""
    PREFIX ex: <http://example.org/lungCancer/entity/>
    SELECT ?patient
    WHERE {{
        ?patient a ex:Patient .
        FILTER (?patient = <{patient_uri}>)
    }}
    """
    is_patient = bool(list(kg.query(query)))
    if not is_patient:
        return True  # Not a patient, assume valid
    validation_result = validate(kg, shacl_graph=shapes_graph, inference='rdfs', focus=rdflib.URIRef(patient_uri))
    conforms = validation_result[0]
    return conforms
# Function to calculate PCA_valid and PCA_invalid with SHACL validation
def calculate_pca_scores(kg, rule, shapes_graph):
    body_conditions = parse_body_to_sparql(rule['Body'])
    head_predicate = "<http://example.org/lungCancer/entity/patientDrug>"
    head_object = '"Nivolumab"'

    print(f"\nRule {rule.name}: {rule['Body']} -> {rule['Head']}")

    # Query for all patients matching Body and Head
    all_patients_query = f"""
    SELECT DISTINCT ?patient
    WHERE {{
        {body_conditions}
        ?patient {head_predicate} {head_object} .
    }}
    """
    all_patients = [row['patient'] for row in kg.query(all_patients_query)]

    # Filter valid and invalid patients using SHACL
    valid_patients = [p for p in all_patients if is_patient_valid(p, kg, shapes_graph)]
    invalid_patients = [p for p in all_patients if not is_patient_valid(p, kg, shapes_graph)]

    # Handle empty patient lists
    valid_filter = f"FILTER (?patient IN ({', '.join(f'<{p}>' for p in valid_patients)}))" if valid_patients else "FILTER (1 = 0)"
    invalid_filter = f"FILTER (?patient IN ({', '.join(f'<{p}>' for p in invalid_patients)}))" if invalid_patients else "FILTER (1 = 0)"

    # support^valid
    support_valid_query = f"""
    SELECT (COUNT(DISTINCT ?patient) AS ?valid_count)
    WHERE {{
        {body_conditions}
        ?patient {head_predicate} {head_object} .
        ?patient <http://example.org/lungCancer/entity/hasValidationReport> <http://example.org/lungCancer/entity/Valid> .
        {valid_filter}
    }}
    """
    # support^invalid
    support_invalid_query = f"""
SELECT (COUNT(DISTINCT ?patient) AS ?invalid_count)
WHERE {{
    {{ {body_conditions}
       ?patient {head_predicate} {head_object} .
       ?patient <http://example.org/lungCancer/entity/hasValidationReport> <http://example.org/lungCancer/entity/Invalid> .
       {valid_filter} }}
    UNION
    {{ {body_conditions}
       ?patient {head_predicate} {head_object} .
       {invalid_filter} }}
}}
"""
    # E⁺_valid
    e_plus_valid_query = f"""
    SELECT (COUNT(DISTINCT ?patient) AS ?e_plus_valid)
    WHERE {{
        {body_conditions}
        ?patient <http://example.org/lungCancer/entity/hasValidationReport> <http://example.org/lungCancer/entity/Valid> .
        {valid_filter}
    }}
    """
    # E⁺_invalid
    e_plus_invalid_query = f"""
    SELECT (COUNT(DISTINCT ?patient) AS ?e_plus_invalid)
    WHERE {{
        {{ {body_conditions}
           ?patient <http://example.org/lungCancer/entity/hasValidationReport> <http://example.org/lungCancer/entity/Invalid> . }}
        UNION
        {{ {body_conditions}
           {invalid_filter} }}
    }}
    """
    # hE⁻_valid
    h_e_minus_valid_query = f"""
    SELECT (COUNT(DISTINCT ?patient) AS ?h_e_minus_valid)
    WHERE {{
        {body_conditions}
        ?patient <http://example.org/lungCancer/entity/hasValidationReport> <http://example.org/lungCancer/entity/Valid> .
        {valid_filter}
        FILTER NOT EXISTS {{ ?patient {head_predicate} {head_object} }}
    }}
    """
    # hE⁻_invalid
    h_e_minus_invalid_query = f"""
    SELECT (COUNT(DISTINCT ?patient) AS ?h_e_minus_invalid)
    WHERE {{
        {{ {body_conditions}
           ?patient <http://example.org/lungCancer/entity/hasValidationReport> <http://example.org/lungCancer/entity/Invalid> .
           FILTER NOT EXISTS {{ ?patient {head_predicate} {head_object} }} }}
        UNION
        {{ {body_conditions}
           {invalid_filter}
           FILTER NOT EXISTS {{ ?patient {head_predicate} {head_object} }} }}
    }}
    """

    support_valid = list(kg.query(support_valid_query))[0][0].toPython() if list(kg.query(support_valid_query)) else 0
    support_invalid = list(kg.query(support_invalid_query))[0][0].toPython() if list(kg.query(support_invalid_query)) else 0
    e_plus_valid = list(kg.query(e_plus_valid_query))[0][0].toPython() if list(kg.query(e_plus_valid_query)) else 0
    e_plus_invalid = list(kg.query(e_plus_invalid_query))[0][0].toPython() if list(kg.query(e_plus_invalid_query)) else 0
    h_e_minus_valid = list(kg.query(h_e_minus_valid_query))[0][0].toPython() if list(kg.query(h_e_minus_valid_query)) else 0
    h_e_minus_invalid = list(kg.query(h_e_minus_invalid_query))[0][0].toPython() if list(kg.query(h_e_minus_invalid_query)) else 0

    print(f"support_valid: {support_valid}, support_invalid: {support_invalid}")
    print(f"e_plus_valid: {e_plus_valid}, e_plus_invalid: {e_plus_invalid}")
    print(f"h_e_minus_valid: {h_e_minus_valid}, h_e_minus_invalid: {h_e_minus_invalid}")

    denominator_valid = e_plus_valid + h_e_minus_valid
    denominator_invalid = e_plus_invalid + h_e_minus_invalid

    pca_valid = support_valid / denominator_valid if denominator_valid > 0 else 0
    pca_invalid = support_invalid / denominator_invalid if denominator_invalid > 0 else 0

    return pca_valid, pca_invalid

# Calculate for all rules
for index, rule in rules_df.iterrows():
    pca_valid, pca_invalid = calculate_pca_scores(kg, rule, shapes_graph)
    print(f"Rule {index}: PCA_valid: {pca_valid}, PCA_invalid: {pca_invalid}")
    print(f"CSV PCA_Confidence: {rule['PCA_Confidence']}")