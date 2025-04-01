import json
import os
import pandas as pd
from rdflib import Graph, Namespace

def compute_pca_metrics():
    try:
        # Read input.json for paths
        with open('input.json', 'r') as f:
            config = json.load(f)
        
        kg_name = config['KG']  # "LungCancer-OriginalKG"
        rules_file = config['rules_file']  # "LungCancer-rules-short.csv"

        # Construct full paths
        kg_path = os.path.join('KG', kg_name, f"{kg_name}_with_status.nt")
        rules_path = os.path.join('Rules', rules_file)

        # Verify files exist
        if not os.path.exists(kg_path):
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

        # Query for valid and invalid triples based on validation status
        valid_query = """
        SELECT ?s ?p ?o WHERE {
            ?s ex:hasValidationStatus "valid" .
            ?s ?p ?o .
        }
        """
        invalid_query = """
        SELECT ?s ?p ?o WHERE {
            ?s ex:hasValidationStatus "invalid" .
            ?s ?p ?o .
        }
        """

        valid_facts = set((str(row[0]), str(row[1]), str(row[2])) for row in kg_graph.query(valid_query, initNs={'ex': EX}))
        invalid_facts = set((str(row[0]), str(row[1]), str(row[2])) for row in kg_graph.query(invalid_query, initNs={'ex': EX}))

        total_valid = len(valid_facts)
        total_invalid = len(invalid_facts)
        print(f"Found {total_valid} valid triples, {total_invalid} invalid triples.")

        # Process each rule to compute PCA_valid and PCA_invalid
        results = []
        for index, row in df_rules.iterrows():
            body = row['Body']
            head = row['Head']
            pca_confidence = row['PCA_Confidence']

            # Simplified: Assume rule predicts based on PCA_Confidence
            # In reality, you'd need to parse body/head and match against KG facts
            predicts_valid = pca_confidence > 0.5

            # Support: Count of facts correctly classified by rule
            support_valid = 0
            support_invalid = 0

            # E⁺(r, Σ)_valid: Positive entailed facts that are valid
            # E⁻(r, Σ)_valid: Negative entailed facts that are valid
            # Simplified: Assume all valid facts are positive, invalid are negative
            e_plus_valid = len(valid_facts) if predicts_valid else 0
            e_minus_valid = 0 if predicts_valid else len(valid_facts)
            e_plus_invalid = len(invalid_facts) if predicts_valid else 0
            e_minus_invalid = 0 if predicts_valid else len(invalid_facts)

            # Compute support (simplified, needs actual rule matching)
            if predicts_valid:
                support_valid = len(valid_facts)  # Assume rule correctly predicts all valid
            else:
                support_invalid = len(invalid_facts)  # Assume rule correctly predicts all invalid

            # Denominators for PCA_valid and PCA_invalid
            denom_valid = e_plus_valid + e_minus_valid
            denom_invalid = e_plus_invalid + e_minus_invalid

            # Compute PCA_valid and PCA_invalid
            pca_valid = support_valid / denom_valid if denom_valid > 0 else 0
            pca_invalid = support_invalid / denom_invalid if denom_invalid > 0 else 0

            # Collect results with all original metrics
            result = {
                'Body': body,
                'Head': head,
                'Head_Coverage': row['Head_Coverage'],
                'Std_Confidence': row['Std_Confidence'],
                'PCA_Confidence': pca_confidence,
                'Positive_Examples': row['Positive_Examples'],
                'Body_size': row['Body_size'],
                'PCA_Body_size': row['PCA_Body_size'],
                'Functional_variable': row['Functional_variable'],
                'PCA_valid': pca_valid,
                'PCA_invalid': pca_invalid
            }
            results.append(result)

        # Convert results to DataFrame and save
        results_df = pd.DataFrame(results)
        output_path = 'pca_metrics_with_all.csv'
        results_df.to_csv(output_path, index=False)
        print(f"Saved PCA metrics with all columns to {output_path}")

    except FileNotFoundError as e:
        print(f"Error: {e}")
        raise
    except Exception as e:
        print(f"Error during computation: {e}")
        raise

if __name__ == '__main__':
    compute_pca_metrics()
