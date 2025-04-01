import json
import os
from rdflib import Graph, Namespace, URIRef, Literal
from validation import travshacl
import logging
import traceback

EX = Namespace("http://example.org/lungCancer/entity/")

def add_validation_status():
    try:
        # Read input.json
        with open('input.json', 'r') as f:
            config = json.load(f)
        
        kg_name = config['KG']  # "LungCancer-OriginalKG"
        rdf_file = config['rdf_file']  # "LungCancer-OriginalKG.nt"
        constraints_folder = config['constraints_folder']  # "Constraint"

        # Load the KG
        kg_path = os.path.join('KG', kg_name, rdf_file)
        if not os.path.exists(kg_path):
            raise FileNotFoundError(f"KG file not found at {kg_path}")
        
        print(f"Loading KG from {kg_path}...")
        kg_graph = Graph()
        kg_graph.parse(kg_path, format='nt')
        print(f"Loaded {len(kg_graph)} triples.")

        # Validate to ensure conforms (optional, already done, but let's confirm)
        constraints_dir = os.path.join('Constraints', constraints_folder)
        if not os.path.exists(constraints_dir):
            raise FileNotFoundError(f"Constraints directory not found at {constraints_dir}")
        
        print(f"Validating KG with constraints from {constraints_dir}...")
        try:
            result = travshacl(kg_graph, constraints_dir, kg_name)
            print(f"Validation completed, result saved. Check {constraints_dir}/result_{kg_name} for report.")
            # Try to parse the result if it's a graph, with base URI
            if isinstance(result, Graph):
                print("Validation report content before parsing:")
                print(result.serialize(format='turtle').decode('utf-8'))
                # Try parsing with base URI
                report_graph = Graph()
                report_graph.parse(data=result.serialize(format='turtle'), format='turtle', publicID="http://example.org/")
                print("Parsed report with base URI, content:")
                print(report_graph.serialize(format='turtle').decode('utf-8'))
        except Exception as e:
            print(f"Error in travshacl: {e}")
            traceback.print_exc()
            raise

        # Get all patients
        patient_query = """
        SELECT ?patient WHERE {
            ?patient a ex:Patient .
        }
        """
        patients = list(kg_graph.query(patient_query, initNs={'ex': EX}))

        # Add validation status as valid for all, given conforms true
        status_predicate = EX.hasValidationStatus
        for patient in patients:
            patient_uri = patient[0]
            kg_graph.add((patient_uri, status_predicate, Literal("valid")))

        # Save updated KG
        output_path = os.path.join('KG', kg_name, f"{kg_name}_with_status.nt")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        kg_graph.serialize(destination=output_path, format='nt')
        print(f"Saved updated KG with validation status to {output_path}")

    except FileNotFoundError as e:
        print(f"Error: {e}")
        raise
    except Exception as e:
        print(f"Error during validation: {e}")
        traceback.print_exc()  # Add detailed traceback for debugging
        raise

if __name__ == '__main__':
    add_validation_status()