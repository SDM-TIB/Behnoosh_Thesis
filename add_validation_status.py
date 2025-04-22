import json
import os
import logging
import traceback
from rdflib import Graph, Namespace, URIRef, Literal
from validation import travshacl

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

EX = Namespace("http://example.org/lungCancer/entity/")

def add_validation_status():
    try:
        # Read input.json
        with open('input.json', 'r') as f:
            config = json.load(f)
        
        kg_name = config['KG']  # "LungCancer-OriginalKG"
        rdf_file = config['rdf_file']  # "LC_Enriched_KG.nt"
        constraints_folder = config['constraints_folder']  # "Constraint"

        # Load the KG
        kg_path = os.path.join('KG', kg_name, rdf_file)
        if not os.path.exists(kg_path):
            raise FileNotFoundError(f"KG file not found at {kg_path}")
        
        print(f"Loading KG from {kg_path}...")
        kg_graph = Graph()
        kg_graph.parse(kg_path, format='nt')
        print(f"Loaded {len(kg_graph)} triples.")

        # Validate using travshacl
        constraints_dir = os.path.join('Constraints', constraints_folder)
        if not os.path.exists(constraints_dir):
            raise FileNotFoundError(f"Constraints directory not found at {constraints_dir}")
        
        print(f"Validating KG with constraints from {constraints_dir}...")
        try:
            result = travshacl(kg_graph, constraints_dir, kg_name)
            print(f"Validation completed, result saved. Check {constraints_dir}/result_{kg_name} for report.")
        except Exception as e:
            print(f"Error in travshacl: {e}")
            traceback.print_exc()
            raise

        # Process Trav-SHACL result to identify invalid patients
        invalid_patients = set()
        if isinstance(result, dict):
            for shape, data in result.items():
                if shape != 'unbound':
                    for instance in data['invalid_instances']:
                        _, patient_uri, _ = instance
                        invalid_patients.add(patient_uri)
            print(f"Found {len(invalid_patients)} invalid patients.")
        else:
            print("Unexpected result format from travshacl:", type(result))
            raise ValueError("Trav-SHACL result is not a dictionary")

        # Get all patients
        patient_query = """
        SELECT ?patient WHERE {
            ?patient a ex:Patient .
        }
        """
        patients = list(kg_graph.query(patient_query, initNs={'ex': EX}))
        print(f"Total patients: {len(patients)}")

        # Add validation status based on Trav-SHACL result
        status_predicate = EX.hasValidationStatus
        for patient in patients:
            patient_uri = patient[0]
            status = "invalid" if str(patient_uri) in invalid_patients else "valid"
            kg_graph.add((patient_uri, status_predicate, Literal(status)))

        # Save updated KG
        output_path = os.path.join('KG', kg_name, f"{kg_name}_with_status.nt")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        kg_graph.serialize(destination=output_path, format='nt')
        print(f"Saved updated KG with validation status to {output_path}")

        # Verify counts in the updated KG
        valid_count = len(list(kg_graph.subjects(status_predicate, Literal("valid"))))
        invalid_count = len(list(kg_graph.subjects(status_predicate, Literal("invalid"))))
        print(f"Valid patients in updated KG: {valid_count}")
        print(f"Invalid patients in updated KG: {invalid_count}")

    except FileNotFoundError as e:
        print(f"Error: {e}")
        raise
    except Exception as e:
        print(f"Error during validation: {e}")
        traceback.print_exc()
        raise

if __name__ == '__main__':
    add_validation_status()