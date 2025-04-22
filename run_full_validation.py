import json
import os
from rdflib import Graph, Namespace
from validation import travshacl
import logging
import traceback

EX = Namespace("http://example.org/lungCancer/entity/")  # Updated prefix from input.json

def run_full_validation():
    try:
        # Read input.json
        with open('input.json', 'r') as f:
            config = json.load(f)
        
        kg_name = config['KG']  # "LC_Enriched_KG"
        rdf_file = config['rdf_file']  # "LC_Enriched_KG.nt"
        constraints_folder = config['constraints_folder']  # "Constraint"

        # Construct full paths
        kg_path = os.path.join('KG', kg_name, rdf_file)  # KG/LLC_Enriched_KG/LC_Enriched_KG.nt
        constraints_dir = os.path.join('Constraints', constraints_folder)  # Constraints/Constraint/

        # Verify files exist
        if not os.path.exists(kg_path):
            raise FileNotFoundError(f"KG file not found at {kg_path}")
        if not os.path.exists(constraints_dir):
            raise FileNotFoundError(f"Constraints directory not found at {constraints_dir}")

        # Debug: Check LC.ttl content
        shapes_file = os.path.join(constraints_dir, 'LC.ttl')
        if os.path.exists(shapes_file):
            with open(shapes_file, 'r') as f:
                shapes_content = f.read()
            print(f"Content of LC.ttl:\n{shapes_content}")
        else:
            print(f"LC.ttl not found at {shapes_file}")

        # Load the KG to ensure it's complete
        print(f"Loading KG from {kg_path} to validate all patients...")
        kg_graph = Graph()
        kg_graph.parse(kg_path, format='nt')
        print(f"Loaded {len(kg_graph)} triples.")

        # Count patients for verification, assuming type ex:Patient under the given prefix
        patient_count_query = """
        SELECT (COUNT(?patient) AS ?count) WHERE {
            ?patient a ex:Patient .
        }
        """
        patient_count = list(kg_graph.query(patient_count_query, initNs={'ex': EX}))[0][0]
        print(f"Found {patient_count} patients, ensuring all included in validation.")

        # Debug: Print constraints_dir content before validation
        print(f"Validating with constraints from {constraints_dir}, listing files:")
        for root, dirs, files in os.walk(constraints_dir):
            for file in files:
                print(f"Found file: {os.path.join(root, file)}")

        # Validate using travshacl
        print(f"Validating entire KG with constraints from {constraints_dir}...")
        try:
            result = travshacl(kg_graph, constraints_dir, kg_name)
            print(f"Validation completed, result saved. Check {constraints_dir}/result_{kg_name} for report.")
            # Try to parse the result if it's a graph
            if isinstance(result, Graph):
                print("Validation report content:")
                print(result.serialize(format='turtle').decode('utf-8'))
        except Exception as e:
            print(f"Error in travshacl: {e}")
            traceback.print_exc()
            raise

    except FileNotFoundError as e:
        print(f"Error: {e}")
        raise
    except Exception as e:
        print(f"Error during validation: {e}")
        traceback.print_exc()  # Add detailed traceback for debugging
        raise

if __name__ == '__main__':
    run_full_validation()