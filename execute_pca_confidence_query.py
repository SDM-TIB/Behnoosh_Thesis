import json
import os
import pandas as pd
from rdflib import Graph, Namespace

def execute_pca_confidence_query():
    try:
        # Read input.json for paths
        with open('input.json', 'r') as f:
            config = json.load(f)
        
        kg_name = config['KG']  # "LungCancer-OriginalKG"
        rules_file = config['rules_file']  # "LungCancer-rules-short.csv"

        # Construct full paths
        kg_path = os.path.join('KG', kg_name, f"{kg_name}_with_status.nt")
        rules_path = os.path.join('Rules', rules_file)
        metrics_path = 'pca_metrics_with_all.csv'

        # Verify files exist
        if not os.path.exists(kg_path):
            raise FileNotFoundError(f"KG file not found at {kg_path}")
        if not os.path.exists(rules_path):
            raise FileNotFoundError(f"Rules file not found at {rules_path}")
        if not os.path.exists(metrics_path):
            raise FileNotFoundError(f"Metrics file not found at {metrics_path}")

        # Load rules
        print(f"Loading rules from {rules_path}...")
        df_rules = pd.read_csv(rules_path)
        print(f"Loaded {len(df_rules)} rules.")

        # Load metrics from step 3 with fallback encodings
        print(f"Loading metrics from {metrics_path}...")
        try:
            df_metrics = pd.read_csv(metrics_path, encoding='utf-8')
        except UnicodeDecodeError:
            print("UTF-8 encoding failed, trying 'latin1'...")
            try:
                df_metrics = pd.read_csv(metrics_path, encoding='latin1')
            except UnicodeDecodeError:
                print("'latin1' encoding failed, trying 'iso-8859-1'...")
                df_metrics = pd.read_csv(metrics_path, encoding='iso-8859-1')
        print(f"Loaded {len(df_metrics)} metrics.")

        # Load KG
        EX = Namespace("http://example.org/lungCancer/entity/")
        print(f"Loading KG from {kg_path}...")
        kg_graph = Graph()
        kg_graph.parse(kg_path, format='nt')
        print(f"Loaded {len(kg_graph)} triples.")

        # SPARQL query to compute PCA_Confidence for entities
        # Simplified: Assume PCA_Confidence is aggregated for entities based on validation status
        pca_confidence_query = """
        SELECT ?entity ?status (AVG(?confidence) as ?pca_confidence)
        WHERE {
            ?entity ex:hasValidationStatus ?status .
            ?entity ?p ?o .
            # Simplified: Assume entities are linked to rules via some property
            # In reality, you'd need to match rules to entities
            VALUES ?status { "valid" "invalid" }
        }
        GROUP BY ?entity ?status
        """

        # Execute the query
        print("Executing PCA_Confidence SPARQL query...")
        results = kg_graph.query(pca_confidence_query, initNs={'ex': EX})

        # Collect query results
        query_results = []
        for row in results:
            entity = str(row[0])
            status = str(row[1])
            pca_confidence = float(row[2]) if row[2] else 0.0
            query_results.append({
                'Entity': entity,
                'Status': status,
                'PCA_Confidence': pca_confidence
            })

        # Convert query results to DataFrame
        df_query = pd.DataFrame(query_results)
        print(f"Query returned {len(df_query)} results.")

        # Compare with PCA_valid and PCA_invalid from step 3
        # Simplified: Compare averages for valid/invalid entities
        valid_entities = df_query[df_query['Status'] == 'valid']
        invalid_entities = df_query[df_query['Status'] == 'invalid']

        avg_pca_conf_valid = valid_entities['PCA_Confidence'].mean() if not valid_entities.empty else 0
        avg_pca_conf_invalid = invalid_entities['PCA_Confidence'].mean() if not invalid_entities.empty else 0

        avg_pca_valid = df_metrics['PCA_valid'].mean()
        avg_pca_invalid = df_metrics['PCA_invalid'].mean()

        print(f"Average PCA_Confidence for valid entities: {avg_pca_conf_valid:.2f}")
        print(f"Average PCA_Confidence for invalid entities: {avg_pca_conf_invalid:.2f}")
        print(f"Average PCA_valid from step 3: {avg_pca_valid:.2f}")
        print(f"Average PCA_invalid from step 3: {avg_pca_invalid:.2f}")

        # Save query results for manual checking in step 5
        df_query.to_csv('pca_confidence_query_results.csv', index=False)
        print("Saved query results to pca_confidence_query_results.csv")

        # Save comparison
        comparison = {
            'Metric': ['PCA_Confidence_Valid', 'PCA_Confidence_Invalid', 'PCA_valid', 'PCA_invalid'],
            'Value': [avg_pca_conf_valid, avg_pca_conf_invalid, avg_pca_valid, avg_pca_invalid]
        }
        df_comparison = pd.DataFrame(comparison)
        df_comparison.to_csv('pca_comparison.csv', index=False)
        print("Saved comparison to pca_comparison.csv")

    except FileNotFoundError as e:
        print(f"Error: {e}")
        raise
    except Exception as e:
        print(f"Error during query execution: {e}")
        raise

if __name__ == '__main__':
    execute_pca_confidence_query()