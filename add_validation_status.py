import json
import os
from rdflib import Graph, Namespace, URIRef, Literal
from validation import travshacl

EX = Namespace("http://example.org/lungCancer/entity/")

def convert_sets_to_lists(obj):
    """Recursively convert sets to lists for JSON serialization."""
    if isinstance(obj, set):
        return list(obj)
    elif isinstance(obj, dict):
        return {key: convert_sets_to_lists(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_sets_to_lists(item) for item in obj]
    return obj

def add_validation_status():
    # Load input.json config
    with open('input.json', 'r') as f:
        config = json.load(f)

    kg_name = config['KG']  # LC_Enriched_KG
    rdf_file = config['rdf_file']  # LC_Enriched_KG.nt
    constraints_folder = config['constraints_folder']  # Constraint

    kg_path = os.path.join('KG', kg_name, rdf_file)
    constraints_path = os.path.join('Constraints', constraints_folder)

    # Load original KG
    g = Graph()
    g.parse(kg_path, format='nt')
    print(f"Loaded {len(g)} triples from original KG.")

    # Count total patients
    query = "SELECT (COUNT(DISTINCT ?patient) AS ?count) WHERE { ?patient a ex:Patient . }"
    result = g.query(query, initNs={'ex': EX})
    for row in result:
        print(f"Total patients in KG: {row[0]}")

    # Run SHACL validation
    result = travshacl(g, constraints_path, kg_name)
    print(f"Validation result: {json.dumps(convert_sets_to_lists(result), indent=2)}")

    # Identify invalid and valid patients
    invalid_uris = set()
    valid_uris = set()
    for shape_result in result.values():
        for triple in shape_result.get('invalid_instances', []):
            _, uri, _ = triple
            invalid_uris.add(str(uri))
        for triple in shape_result.get('valid_instances', []):  # If travshacl provides valid instances
            _, uri, _ = triple
            valid_uris.add(str(uri))

    total_evaluated = len(valid_uris | invalid_uris)
    print(f"Total patients validated by travshacl: {total_evaluated}")
    print(f"Valid patients identified: {len(valid_uris)}")
    print(f"Invalid patients identified: {len(invalid_uris)}")

    # Check for unevaluated patients
    query = "SELECT DISTINCT ?patient WHERE { ?patient a ex:Patient . }"
    patients = g.query(query, initNs={'ex': EX})
    patient_uris = {str(row[0]) for row in patients}
    unevaluated_uris = patient_uris - (valid_uris | invalid_uris)
    print(f"Unevaluated patients: {len(unevaluated_uris)}")

    # Create new graph including validation status
    enriched = Graph()
    for triple in g:
        enriched.add(triple)

    # Add validation status per patient
    for uri in patient_uris:
        if uri in invalid_uris:
            status = "invalid"
        elif uri in valid_uris:
            status = "valid"
        else:
            status = "not_evaluated"
        enriched.add((URIRef(uri), EX.hasValidationStatus, Literal(status)))

    # Save updated KG
    output_path = os.path.join('KG', kg_name, f"{kg_name}_with_status.nt")
    enriched.serialize(destination=output_path, format='nt')
    print(f"Validation status added. Saved to: {output_path}")

    # Verify counts in enriched KG
    enriched_query_valid = """
    SELECT (COUNT(DISTINCT ?patient) AS ?valid_count)
    WHERE { ?patient a ex:Patient ; ex:hasValidationStatus "valid" . }
    """
    result = enriched.query(enriched_query_valid, initNs={'ex': EX})
    for row in result:
        print(f"Valid patients in enriched KG: {row[0]}")

    enriched_query_invalid = """
    SELECT (COUNT(DISTINCT ?patient) AS ?invalid_count)
    WHERE { ?patient a ex:Patient ; ex:hasValidationStatus "invalid" . }
    """
    result = enriched.query(enriched_query_invalid, initNs={'ex': EX})
    for row in result:
        print(f"Invalid patients in enriched KG: {row[0]}")

    enriched_query_notevaluated = """
    SELECT (COUNT(DISTINCT ?patient) AS ?notevaluated_count)
    WHERE { ?patient a ex:Patient ; ex:hasValidationStatus "not_evaluated" . }
    """
    result = enriched.query(enriched_query_notevaluated, initNs={'ex': EX})
    for row in result:
        print(f"Not evaluated patients in enriched KG: {row[0]}")

    # Check for non-patient entities with validation status
    non_patient_query = """
    SELECT (COUNT(DISTINCT ?entity) AS ?count)
    WHERE {
        ?entity ex:hasValidationStatus ?status .
        FILTER NOT EXISTS { ?entity a ex:Patient . }
    }
    """
    result = enriched.query(non_patient_query, initNs={'ex': EX})
    for row in result:
        print(f"Non-patient entities with validation status: {row[0]}")

if __name__ == '__main__':
    add_validation_status()
