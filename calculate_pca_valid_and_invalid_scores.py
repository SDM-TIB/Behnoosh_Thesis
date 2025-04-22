import json
import os
import re
import pandas as pd
from rdflib import Graph, Namespace

# --------------------------------------------------------------------------- #
#  Helpers                                                                    #
# --------------------------------------------------------------------------- #
def get_all_variables(pattern: str):
    return set(re.findall(r"\?\w+", pattern))

def get_head_vars(head: str):
    p = head.strip().split()
    if len(p) < 3:
        raise ValueError(f"Invalid head: {head}")
    vars_ = [x for x in (p[0], p[2]) if x.startswith("?")]
    if not vars_:
        raise ValueError("Head must contain at least one variable")
    return vars_

def get_new_var(existing):
    v = "?y"
    while v in existing:
        v += "a"
    return v

# --------------------------------------------------------------------------- #
#  Compute PCA valid and invalid using SPARQL queries                         #
# --------------------------------------------------------------------------- #
def compute_pca_valid_invalid(kg_graph, body: str, head: str):
    """
    Compute PCA valid and PCA invalid using SPARQL queries, ensuring PCA_valid + PCA_invalid = 1.
    """
    try:
        EX = Namespace("http://example.org/lungCancer/entity/")

        # Expand short tokens to full IRIs
        replacements = {
            'hasStage': '<http://example.org/lungCancer/entity/hasStage>',
            'treatmentType': '<http://example.org/lungCancer/entity/treatmentType>',
            'patientDrug': '<http://example.org/lungCancer/entity/patientDrug>',
            'hasRelapse_Progression': '<http://example.org/lungCancer/entity/hasRelapse_Progression>',
            'hasGender': '<http://example.org/lungCancer/entity/hasGender>',
            'hasSmokingHabit': '<http://example.org/lungCancer/entity/hasSmokingHabit>',
            'IV': '<http://example.org/lungCancer/entity/IV>',
            'Immunotherapy': '<http://example.org/lungCancer/entity/Immunotherapy>',
            'Intravenous_Chemotherapy': '<http://example.org/lungCancer/entity/Intravenous_Chemotherapy>',
            'Progression': '<http://example.org/lungCancer/entity/Progression>',
            'Pemetrexed': '<http://example.org/lungCancer/entity/Pemetrexed>',
            'Paclitaxel': '<http://example.org/lungCancer/entity/Paclitaxel>',
            'Carboplatin': '<http://example.org/lungCancer/entity/Carboplatin>',
            'Cisplatin': '<http://example.org/lungCancer/entity/Cisplatin>',
            'Male': '<http://example.org/lungCancer/entity/Male>',
            'FormerSmoker': '<http://example.org/lungCancer/entity/FormerSmoker>',
            'Radiotherapy_To_Lung': '<http://example.org/lungCancer/entity/Radiotherapy_To_Lung>',
            'Nivolumab': '<http://example.org/lungCancer/entity/Nivolumab>'
        }
        body_formatted = body
        head_formatted = head
        # Apply replacements to whole tokens, handling end-of-string cases
        for k, v in replacements.items():
            body_formatted = re.sub(rf'\b{k}\b', v, body_formatted)
            head_formatted = re.sub(rf'\b{k}\b', v, head_formatted)

        # Replace ?a with ?patient
        body_formatted = body_formatted.replace("?a", "?patient")
        head_formatted = head_formatted.replace("?a", "?patient")

        # Get head variables
        head_vars = get_head_vars(head_formatted)
        if len(head_vars) != 1 or head_vars[0] != '?patient':
            raise ValueError(f"Expected head with ?patient, got: {head_vars}")

        # Parse head for PCA head pattern
        head_parts = head_formatted.strip().split()
        if len(head_parts) != 3:
            raise ValueError(f"Head must be a single triple pattern, got: {head_formatted}")
        head_subject, head_predicate, head_object = head_parts
        if head_subject != '?patient':
            raise ValueError(f"Head subject must be ?patient, got: {head_subject}")
        if not head_object.startswith('<') or not head_object.endswith('>'):
            raise ValueError(f"Head object must be a full IRI, got: {head_object}")

        # Split body into triples
        body_parts = body_formatted.strip().split()
        if len(body_parts) % 3 != 0:
            raise ValueError(f"Invalid body format, expected triples: {body_formatted}")
        
        body_triples = []
        for i in range(0, len(body_parts), 3):
            if i + 2 < len(body_parts):
                triple = f"{body_parts[i]} {body_parts[i+1]} {body_parts[i+2]}"
                body_triples.append(triple)
            else:
                raise ValueError(f"Incomplete triple in body: {body_formatted}")

        # Validate and format body triples
        formatted_body = []
        for triple in body_triples:
            parts = triple.strip().split()
            if len(parts) != 3:
                raise ValueError(f"Invalid triple pattern: {triple}")
            if not parts[0].startswith('?patient'):
                raise ValueError(f"Triple subject must be ?patient, got: {parts[0]}")
            if not parts[1].startswith('<') or not parts[1].endswith('>'):
                raise ValueError(f"Triple predicate must be a full IRI, got: {parts[1]}")
            if not parts[2].startswith('<') or not parts[2].endswith('>'):
                raise ValueError(f"Triple object must be a full IRI, got: {parts[2]}")
            formatted_body.append(triple)
        
        body_formatted = ' . '.join(formatted_body)

        # Compute Support for valid patients
        valid_support_query = f"""
        SELECT (COUNT(DISTINCT ?patient) AS ?Support) WHERE {{
            ?patient a ex:Patient ;
                     ex:hasValidationStatus "valid" .
            {body_formatted} .
            {head_formatted} .
        }}
        """
        valid_support_result = kg_graph.query(valid_support_query, initNs={'ex': EX})
        valid_support = int(valid_support_result.bindings[0]['Support'].value) if valid_support_result.bindings else 0

        # Compute Support for invalid patients
        invalid_support_query = f"""
        SELECT (COUNT(DISTINCT ?patient) AS ?Support) WHERE {{
            ?patient a ex:Patient ;
                     ex:hasValidationStatus "invalid" .
            {body_formatted} .
            {head_formatted} .
        }}
        """
        invalid_support_result = kg_graph.query(invalid_support_query, initNs={'ex': EX})
        invalid_support = int(invalid_support_result.bindings[0]['Support'].value) if invalid_support_result.bindings else 0

        # Compute PCA body size for valid patients
        valid_pca_body_size_query = f"""
        SELECT (COUNT(DISTINCT ?patient) AS ?PCABodySize) WHERE {{
            ?patient a ex:Patient ;
                     ex:hasValidationStatus "valid" .
            {body_formatted} .
            ?patient {head_predicate} ?y .
        }}
        """
        valid_pca_body_size_result = kg_graph.query(valid_pca_body_size_query, initNs={'ex': EX})
        valid_pca_body_size = int(valid_pca_body_size_result.bindings[0]['PCABodySize'].value) if valid_pca_body_size_result.bindings else 0

        # Compute PCA body size for invalid patients
        invalid_pca_body_size_query = f"""
        SELECT (COUNT(DISTINCT ?patient) AS ?PCABodySize) WHERE {{
            ?patient a ex:Patient ;
                     ex:hasValidationStatus "invalid" .
            {body_formatted} .
            ?patient {head_predicate} ?y .
        }}
        """
        invalid_pca_body_size_result = kg_graph.query(invalid_pca_body_size_query, initNs={'ex': EX})
        invalid_pca_body_size = int(invalid_pca_body_size_result.bindings[0]['PCABodySize'].value) if invalid_pca_body_size_result.bindings else 0

        # Normalize PCA valid and invalid to sum to 1
        total_support = valid_support + invalid_support
        if total_support == 0:
            pca_valid = 0.0
            pca_invalid = 0.0
        else:
            pca_valid = valid_support / total_support
            pca_invalid = invalid_support / total_support

        print(f"PCA valid: {pca_valid}")
        print(f"PCA invalid: {pca_invalid}")

        return pca_valid, pca_invalid

    except Exception as e:
        print(f"Error computing PCA for rule: {body} => {head}: {e}")
        return None, None

# --------------------------------------------------------------------------- #
#  End-to-end pipeline                                                        #
# --------------------------------------------------------------------------- #
def calculate_pca_valid_invalid_scores():
    try:
        # Read input.json
        script_dir = os.path.dirname(os.path.abspath(__file__))
        input_json_path = os.path.join(script_dir, 'input.json')
        with open(input_json_path, 'r') as f:
            config = json.load(f)

        kg_name = config['KG']
        rules_file = config['rules_file']
        rdf_file = config.get('rdf_file', f"{kg_name}_with_status.nt")

        # Construct full paths
        kg_path = os.path.join(script_dir, 'KG', kg_name, rdf_file)
        rules_path = os.path.join(script_dir, 'Rules', rules_file)

        # Verify files exist
        if not os.path.exists(kg_path):
            kg_dir = os.path.join(script_dir, 'KG', kg_name)
            if os.path.exists(kg_dir):
                print(f"Available files in {kg_dir}: {os.listdir(kg_dir)}")
            raise FileNotFoundError(f"KG file not found at {kg_path}")
        if not os.path.exists(rules_path):
            raise FileNotFoundError(f"Rules file not found at {rules_path}")

        # Load rules
        print(f"Loading rules from {rules_path}...")
        df_rules = pd.read_csv(rules_path)
        required_columns = ['Body', 'Head', 'Head_Coverage', 'Std_Confidence', 'PCA_Confidence',
                            'Positive_Examples', 'Body_size', 'PCA_Body_size', 'Functional_variable']
        for col in required_columns:
            if col not in df_rules.columns:
                raise ValueError(f"Rules file must have {col} column")
        print(f"Loaded {len(df_rules)} rules.")

        # Load KG
        EX = Namespace("http://example.org/lungCancer/entity/")
        print(f"Loading KG from {kg_path}...")
        kg_graph = Graph()
        kg_graph.parse(kg_path, format='nt')
        print(f"Loaded {len(kg_graph)} triples.")

        # Debug total patients
        patient_query = """
        SELECT (COUNT(DISTINCT ?patient) as ?count) WHERE {
            ?patient a ex:Patient .
        }
        """
        patient_result = kg_graph.query(patient_query, initNs={'ex': EX})
        patient_count = int(patient_result.bindings[0]['count'].value) if patient_result.bindings else 0
        print(f"Total patients: {patient_count}")

        # Debug validation status
        status_query = """
        SELECT ?status (COUNT(DISTINCT ?patient) as ?count) WHERE {
            ?patient a ex:Patient .
            OPTIONAL { ?patient ex:hasValidationStatus ?status . }
        } GROUP BY ?status
        """
        status_result = kg_graph.query(status_query, initNs={'ex': EX})
        print("Validation status counts for patients:")
        for row in status_result:
            status = row[0] if row[0] else "No status"
            print(f"Status: {status}, Count: {row[1]}")

        # Process each rule
        results = []
        for index, row in df_rules.iterrows():
            body = row['Body']
            head = row['Head']

            # Compute PCA valid and invalid
            pca_valid, pca_invalid = compute_pca_valid_invalid(kg_graph, body, head)

            result = {
                'Body': body,
                'Head': head,
                'Head_Coverage': row['Head_Coverage'],
                'Std_Confidence': row['Std_Confidence'],
                'PCA_Confidence': row['PCA_Confidence'],
                'Positive_Examples': row['Positive_Examples'],
                'Body_size': row['Body_size'],
                'PCA_Body_size': row['PCA_Body_size'],
                'Functional_variable': row['Functional_variable'],
                'PCA_valid': pca_valid,
                'PCA_invalid': pca_invalid
            }
            results.append(result)

        # Save results
        results_df = pd.DataFrame(results)
        output_path = os.path.join(script_dir, 'pca_metrics_with_all.csv')
        results_df.to_csv(output_path, index=False, encoding='utf-8')
        print(f"Saved PCA metrics with all columns to {output_path}")

    except FileNotFoundError as e:
        print(f"Error: {e}")
        raise
    except Exception as e:
        print(f"Error during computation: {e}")
        raise

if __name__ == "__main__":
    calculate_pca_valid_invalid_scores()