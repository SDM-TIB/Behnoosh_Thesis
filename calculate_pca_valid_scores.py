import json
import os
import pandas as pd
from rdflib import Graph, Namespace
import re

def get_all_variables(pattern):
    """Extract all variables from a pattern."""
    return set(re.findall(r'\?\w+', pattern))

def get_head_vars(head):
    """Get variables from the head, handling constants."""
    parts = head.strip().split()
    if len(parts) >= 3:
        subject = parts[0]
        object = parts[2]
        vars = []
        if subject.startswith('?'):
            vars.append(subject)
        if object.startswith('?'):
            vars.append(object)
        if not vars:
            raise ValueError("Head must have at least one variable")
        return vars
    raise ValueError("Invalid head format")

def get_new_var(existing_vars):
    """Generate a new variable not in existing_vars."""
    new_var = '?y'
    while new_var in existing_vars:
        new_var += 'a'
    return new_var

def compute_pca_valid(kg_graph, body, head):
    """Compute PCA valid for a given rule."""
    try:
        EX = Namespace("http://example.org/lungCancer/entity/")
        # Add URI prefixes to match KG namespace
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
        for key, value in replacements.items():
            body_formatted = body_formatted.replace(key, value)
            head_formatted = head_formatted.replace(key, value)

        # Replace ?a with ?patient before validation
        body_formatted = body_formatted.replace('?a', '?patient')
        head_formatted = head_formatted.replace('?a', '?patient')

        # Get head variables
        head_vars = get_head_vars(head_formatted)
        # Use ?patient as per your query
        if len(head_vars) == 1 and head_vars[0] == '?patient':
            head_vars_str = '?patient'
        else:
            raise ValueError(f"Expected head with ?patient, got: {head_vars}")

        # Parse head for PCA head pattern
        head_parts = head_formatted.strip().split()
        if len(head_parts) != 3:
            raise ValueError(f"Head must be a single triple pattern, got: {head_formatted}")
        head_subject, head_predicate, head_object = head_parts
        if head_subject != '?patient':
            raise ValueError(f"Head subject must be ?patient, got: {head_subject}")

        # Split body into individual triple patterns
        body_parts = body_formatted.strip().split()
        if len(body_parts) % 3 != 0:
            raise ValueError(f"Invalid body format, expected triples: {body_formatted}")
        
        # Group into triples
        body_triples = []
        for i in range(0, len(body_parts), 3):
            if i + 2 < len(body_parts):
                triple = f"{body_parts[i]} {body_parts[i+1]} {body_parts[i+2]}"
                body_triples.append(triple)
            else:
                raise ValueError(f"Incomplete triple in body: {body_formatted}")

        # Validate and format triples
        formatted_body = []
        for triple in body_triples:
            parts = triple.strip().split()
            if len(parts) != 3:
                raise ValueError(f"Invalid triple pattern: {triple}")
            if not parts[0].startswith('?patient'):
                raise ValueError(f"Triple subject must be ?patient, got: {parts[0]}")
            formatted_body.append(triple)
        
        body_formatted = ' . '.join(formatted_body)
        print(f"Formatted body for rule: {body_formatted}")

        # Support query for PCA valid
        support_query = f"""
        SELECT (COUNT(DISTINCT ?patient) AS ?Support) WHERE {{
            ?patient a ex:Patient ;
                     ex:hasValidationStatus "valid" .
            {body_formatted} .
            {head_formatted} .
        }}
        """
        print(f"Support query for valid: {support_query}")
        support_result = kg_graph.query(support_query, initNs={'ex': EX})
        support = int(support_result.bindings[0]['Support'].value) if support_result.bindings else 0
        print(f"Support for valid: {support}")

        # PCA body size query for PCA valid
        all_vars = get_all_variables(body_formatted + ' . ' + head_formatted)
        new_var = get_new_var(all_vars)
        pca_head_pattern = f"?patient {head_predicate} {new_var}"
        pcabodysize_query = f"""
        SELECT (COUNT(DISTINCT ?patient) AS ?PCABodySize) WHERE {{
            ?patient a ex:Patient ;
                     ex:hasValidationStatus "valid" .
            {body_formatted} .
            {pca_head_pattern} .
        }}
        """
        print(f"PCA body size query for valid: {pcabodysize_query}")
        pcabodysize_result = kg_graph.query(pcabodysize_query, initNs={'ex': EX})
        pcabodysize = int(pcabodysize_result.bindings[0]['PCABodySize'].value) if pcabodysize_result.bindings else 0
        print(f"PCA body size for valid: {pcabodysize}")

        # Compute PCA valid
        pca_valid = float(support) / float(pcabodysize) if pcabodysize > 0 else 0.0
        print(f"PCA valid: {pca_valid}")
        return pca_valid

    except Exception as e:
        print(f"Error computing PCA valid for rule: {body} => {head}: {e}")
        return None

def calculate_pca_valid_scores():
    try:
        # Read input.json
        script_dir = os.path.dirname(os.path.abspath(__file__))
        input_json_path = os.path.join(script_dir, 'input.json')
        with open(input_json_path, 'r') as f:
            config = json.load(f)
        
        kg_name = config['KG']  # "LC_Enriched_KG"
        rules_file = config['rules_file']  # "LungCancer-rules-short.csv"
        rdf_file = config.get('rdf_file', f"{kg_name}_with_status.nt")  # Fallback

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
            pca_valid = compute_pca_valid(kg_graph, body, head)

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
                'PCA_valid': pca_valid
            }
            results.append(result)

        # Save results
        results_df = pd.DataFrame(results)
        output_path = os.path.join(script_dir, 'pca_metrics_with_valid.csv')
        results_df.to_csv(output_path, index=False, encoding='utf-8')
        print(f"Saved PCA valid metrics to {output_path}")

    except FileNotFoundError as e:
        print(f"Error: {e}")
        raise
    except Exception as e:
        print(f"Error during computation: {e}")
        raise

if __name__ == '__main__':
    calculate_pca_valid_scores()