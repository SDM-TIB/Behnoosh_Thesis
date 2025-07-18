import sys
import json
from pathlib import Path
from rdflib import Graph, Namespace, URIRef, Literal
from rdflib.namespace import RDF, RDFS, XSD
import logging
from typing import Set, Optional, Dict, List, Tuple
import pandas as pd
import re
import os

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class CombinedKGProcessor:
    """
    A combined class that extends Knowledge Graphs with validation status information
    and then calculates complementary PCA confidence scores.
    """

    def __init__(self):
        # Define namespaces for KG validation
        self.SHACL = Namespace("http://www.w3.org/ns/shacl#")
        self.VALIDATION = Namespace("http://validation.org/")
        self.setup_namespaces()

        # Will be initialized with config
        self.config = None
        self.kg_graph = None
        self.pca_namespaces = {}
        self.default_ns = None

    def setup_namespaces(self):
        """Set up common RDF namespaces for validation"""
        self.namespaces = {
            'sh': self.SHACL,
            'validation': self.VALIDATION,
            'rdf': RDF,
            'rdfs': RDFS,
            'xsd': XSD
        }

    def load_combined_config(self, config_path: str) -> dict:
        """
        Load combined configuration from JSON file.

        Args:
            config_path (str): Path to configuration file

        Returns:
            dict: Configuration dictionary
        """
        try:
            config_file = Path(config_path)

            if not config_file.exists():
                raise FileNotFoundError(f"Configuration file not found: {config_path}")

            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)

            self.config = config
            logger.info(f"Successfully loaded configuration from {config_path}")
            return config

        except Exception as e:
            logger.error(f"Error loading configuration from {config_path}: {str(e)}")
            raise

    def load_kg(self, kg_path: str) -> Graph:
        """
        Load the knowledge graph from the specified path.

        Args:
            kg_path (str): Path to the KG file

        Returns:
            Graph: The loaded RDF graph
        """
        try:
            g = Graph()

            # Bind namespaces
            for prefix, namespace in self.namespaces.items():
                g.bind(prefix, namespace)

            # Determine file format based on extension
            file_ext = Path(kg_path).suffix.lower()
            format_map = {
                '.ttl': 'turtle',
                '.nt': 'nt',
                '.n3': 'n3',
                '.rdf': 'xml',
                '.xml': 'xml',
                '.jsonld': 'json-ld'
            }

            file_format = format_map.get(file_ext, 'turtle')
            g.parse(kg_path, format=file_format)

            logger.info(f"Successfully loaded KG from {kg_path} with {len(g)} triples")
            return g

        except Exception as e:
            logger.error(f"Error loading KG from {kg_path}: {str(e)}")
            raise

    def load_validation_report(self, validation_path: str) -> Graph:
        """
        Load the SHACL validation report.

        Args:
            validation_path (str): Path to the validation report file

        Returns:
            Graph: The validation report graph
        """
        try:
            validation_graph = Graph()

            # Bind namespaces
            for prefix, namespace in self.namespaces.items():
                validation_graph.bind(prefix, namespace)

            # Read the file content and fix missing prefix declaration
            with open(validation_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Check if the default prefix ":" is declared
            if ':report a sh:ValidationReport' in content and '@prefix : <' not in content:
                # Add missing default prefix declaration
                prefix_declaration = '@prefix : <http://validation.report/> .\n'

                # Find where to insert it (after existing @prefix declarations)
                lines = content.split('\n')
                insert_index = 0

                for i, line in enumerate(lines):
                    if line.strip().startswith('@prefix'):
                        insert_index = i + 1
                    elif line.strip() and not line.strip().startswith('@prefix'):
                        break

                # Insert the missing prefix
                lines.insert(insert_index, prefix_declaration)
                content = '\n'.join(lines)

            # Parse the corrected content
            validation_graph.parse(data=content, format='turtle')
            logger.info(f"Successfully loaded validation report from {validation_path}")
            return validation_graph

        except Exception as e:
            logger.error(f"Error loading validation report from {validation_path}: {str(e)}")
            raise

    def extract_violating_entities(self, validation_graph: Graph) -> Set[str]:
        """
        Extract entities that violate constraints from the SHACL validation report.

        Args:
            validation_graph (Graph): The validation report graph

        Returns:
            Set[str]: Set of entity URIs that have violations
        """
        violating_entities = set()

        # Simple query to get all focus nodes (entities with violations)
        query = """
        PREFIX sh: <http://www.w3.org/ns/shacl#>

        SELECT DISTINCT ?focusNode
        WHERE {
            ?result a sh:ValidationResult ;
                    sh:focusNode ?focusNode .
        }
        """

        # Execute query
        query_results = validation_graph.query(query)

        # Collect all violating entities
        for row in query_results:
            if row.focusNode:
                violating_entities.add(str(row.focusNode))

        logger.info(f"Found {len(violating_entities)} entities with violations")
        return violating_entities

    def add_validation_status_triples(self, kg_graph: Graph, violating_entities: Set[str]) -> Graph:
        """
        Add validation status as RDF triples to the knowledge graph.

        Args:
            kg_graph (Graph): The original knowledge graph
            violating_entities (Set[str]): Set of entity URIs that have violations

        Returns:
            Graph: Extended knowledge graph with validation status
        """
        extended_graph = kg_graph

        # Get all entities from the KG
        all_entities = set()
        for s, p, o in kg_graph:
            if isinstance(s, URIRef):
                all_entities.add(str(s))
            if isinstance(o, URIRef):
                all_entities.add(str(o))

        # Add validation status for all entities
        for entity_uri in all_entities:
            entity = URIRef(entity_uri)

            # Determine status: invalid if in violation report, valid otherwise
            if entity_uri in violating_entities:
                status = "invalid"
            else:
                status = "valid"

            extended_graph.add((entity, self.VALIDATION.hasValidationStatus,
                                Literal(status, datatype=XSD.string)))

        valid_count = len(all_entities) - len(violating_entities)
        invalid_count = len(violating_entities)

        logger.info(f"Added validation status: {valid_count} valid entities, {invalid_count} invalid entities")
        return extended_graph

    def save_extended_kg(self, extended_graph: Graph, output_path: str, output_format: str = 'turtle'):
        """
        Save the extended knowledge graph to file.

        Args:
            extended_graph (Graph): The extended knowledge graph
            output_path (str): Output file path
            output_format (str): Output format (turtle, nt, xml, etc.)
        """
        try:
            extended_graph.serialize(destination=output_path, format=output_format)
            logger.info(f"Successfully saved extended KG to {output_path}")
            logger.info(f"Extended KG contains {len(extended_graph)} triples")

        except Exception as e:
            logger.error(f"Error saving extended KG to {output_path}: {str(e)}")
            raise

    def _get_format_from_extension(self, extension: str) -> str:
        """Helper method to get RDF format from file extension"""
        format_map = {
            '.ttl': 'turtle',
            '.nt': 'nt',
            '.n3': 'n3',
            '.rdf': 'xml',
            '.xml': 'xml'
        }
        return format_map.get(extension.lower(), 'turtle')

    # PCA Calculator methods start here
    def setup_pca_settings(self, config: dict):
        """Setup PCA-specific settings from config"""
        settings = config.get('pca_settings', {})

        # Setup custom namespaces for PCA
        self.pca_namespaces = {}
        for prefix, uri in settings.get('namespaces', {}).items():
            self.pca_namespaces[prefix] = Namespace(uri)

        # Default namespace
        self.default_ns = Namespace(settings.get('default_namespace', 'http://example.org/'))

        # Validation settings
        self.validation_predicate = settings.get('validation_predicate', 'http://validation.org/hasValidationStatus')
        self.valid_values = settings.get('valid_values', ['valid'])
        self.invalid_values = settings.get('invalid_values', ['invalid'])

    def parse_rule_components(self, body: str, head: str) -> Dict:
        """Parse rule body and head into components"""
        body_patterns = self._extract_triple_patterns(body)
        head_pattern = self._extract_triple_patterns(head)[0] if head else None
        vars_in_head = self._extract_variables(head)

        return {
            'body_patterns': body_patterns,
            'head_pattern': head_pattern,
            'vars_in_head': vars_in_head
        }

    def _extract_triple_patterns(self, pattern_str: str) -> List[Tuple[str, str, str]]:
        """Extract triple patterns from a string"""
        patterns = []
        tokens = pattern_str.strip().split()
        tokens = [t for t in tokens if t]

        i = 0
        while i + 2 < len(tokens):
            subject = tokens[i]
            predicate = tokens[i + 1]
            obj = tokens[i + 2]
            patterns.append((subject, predicate, obj))
            i += 3

        return patterns

    def _extract_variables(self, pattern_str: str) -> List[str]:
        """Extract variable names from pattern string"""
        return list(set(re.findall(r'\?[a-zA-Z0-9_]+', pattern_str)))

    def create_combined_pca_query(self, rule_components: Dict) -> str:
        """Create SPARQL query to calculate PCA across all entities with validation status"""
        body_patterns = rule_components['body_patterns']
        head_pattern = rule_components['head_pattern']
        vars_in_head = rule_components['vars_in_head']

        # Get all variables
        all_vars = set(vars_in_head)
        for pattern in body_patterns:
            for item in pattern:
                if item.startswith('?'):
                    all_vars.add(item)

        # Create patterns
        body_sparql = self._create_sparql_patterns(body_patterns)
        head_sparql = self._create_head_sparql_pattern(head_pattern) if head_pattern else ""
        pca_head_pattern = self._create_pca_head_pattern(head_pattern)

        # Determine entity variable
        entity_var = '?a' if '?a' in all_vars else list(all_vars)[0] if all_vars else '?a'

        # Build namespace declarations
        ns_declarations = []
        for prefix, ns in self.pca_namespaces.items():
            ns_declarations.append(f"PREFIX {prefix}: <{ns}>")
        ns_declarations.append("PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>")

        # Create comprehensive query that calculates everything in one go
        query = f"""
{chr(10).join(ns_declarations)}

SELECT ?support_valid ?support_invalid ?pca_body_valid ?pca_body_invalid
WHERE {{
    # Count valid entities satisfying body AND head
    {{
        SELECT (COUNT(DISTINCT {entity_var}) AS ?support_valid)
        WHERE {{
            {entity_var} <{self.validation_predicate}> "{self.valid_values[0]}"^^xsd:string .
            {body_sparql}
            {head_sparql}
        }}
    }}

    # Count invalid entities satisfying body AND head
    {{
        SELECT (COUNT(DISTINCT {entity_var}) AS ?support_invalid)
        WHERE {{
            {entity_var} <{self.validation_predicate}> "{self.invalid_values[0]}"^^xsd:string .
            {body_sparql}
            {head_sparql}
        }}
    }}

    # Count valid entities satisfying body with ANY head value
    {{
        SELECT (COUNT(DISTINCT {entity_var}) AS ?pca_body_valid)
        WHERE {{
            {entity_var} <{self.validation_predicate}> "{self.valid_values[0]}"^^xsd:string .
            {body_sparql}
            {pca_head_pattern}
        }}
    }}

    # Count invalid entities satisfying body with ANY head value
    {{
        SELECT (COUNT(DISTINCT {entity_var}) AS ?pca_body_invalid)
        WHERE {{
            {entity_var} <{self.validation_predicate}> "{self.invalid_values[0]}"^^xsd:string .
            {body_sparql}
            {pca_head_pattern}
        }}
    }}
}}
"""
        return query

    def _create_sparql_patterns(self, patterns: List[Tuple[str, str, str]]) -> str:
        """Convert list of triple patterns to SPARQL pattern string"""
        sparql_patterns = []

        # Determine which namespace prefix to use
        default_prefix = None
        for prefix, ns in self.pca_namespaces.items():
            if str(ns) == str(self.default_ns):
                default_prefix = prefix
                break

        for s, p, o in patterns:
            if not o.startswith('?'):
                if default_prefix:
                    o_formatted = f'{default_prefix}:{o}'
                else:
                    o_formatted = f'<{self.default_ns}{o}>'
            else:
                o_formatted = o

            if default_prefix:
                p_formatted = f'{default_prefix}:{p}'
            else:
                p_formatted = f'<{self.default_ns}{p}>'

            sparql_patterns.append(f"{s} {p_formatted} {o_formatted} .")

        return '\n            '.join(sparql_patterns)

    def _create_head_sparql_pattern(self, head_pattern: Tuple[str, str, str]) -> str:
        """Create SPARQL pattern for head"""
        if not head_pattern:
            return ""

        s, p, o = head_pattern

        default_prefix = None
        for prefix, ns in self.pca_namespaces.items():
            if str(ns) == str(self.default_ns):
                default_prefix = prefix
                break

        if not o.startswith('?'):
            if default_prefix:
                o_formatted = f'{default_prefix}:{o}'
            else:
                o_formatted = f'<{self.default_ns}{o}>'
        else:
            o_formatted = o

        if default_prefix:
            p_formatted = f'{default_prefix}:{p}'
        else:
            p_formatted = f'<{self.default_ns}{p}>'

        return f"{s} {p_formatted} {o_formatted} ."

    def _create_pca_head_pattern(self, head_pattern: Tuple[str, str, str]) -> str:
        """Create PCA head pattern with placeholder variable"""
        if not head_pattern:
            return ""

        s, p, o = head_pattern
        placeholder = o + '1' if o.startswith('?') else '?X1'

        default_prefix = None
        for prefix, ns in self.pca_namespaces.items():
            if str(ns) == str(self.default_ns):
                default_prefix = prefix
                break

        if default_prefix:
            p_formatted = f'{default_prefix}:{p}'
        else:
            p_formatted = f'<{self.default_ns}{p}>'

        return f"{s} {p_formatted} {placeholder} ."

    def calculate_pca_scores(self, rules_csv_path: str, extended_kg_path: str) -> pd.DataFrame:
        """Calculate complementary PCA confidence scores for all rules"""
        # Load the extended KG with validation status
        self.kg_graph = self.load_kg(extended_kg_path)

        # Read rules
        df = pd.read_csv(rules_csv_path)

        # Initialize result columns
        df['PCA_valid'] = 0.0
        df['PCA_invalid'] = 0.0
        df['PCA_valid_proportion'] = 0.0
        df['PCA_invalid_proportion'] = 0.0
        df['Support_valid'] = 0
        df['Support_invalid'] = 0
        df['PCABody_valid'] = 0
        df['PCABody_invalid'] = 0

        print(f"\nProcessing {len(df)} rules...")
        print(f"Calculating complementary PCA scores...")

        for idx, row in df.iterrows():
            if idx % 100 == 0:
                print(f"Processing rule {idx + 1}/{len(df)}")

            body = row['Body']
            head = row['Head']

            try:
                rule_components = self.parse_rule_components(body, head)
                query = self.create_combined_pca_query(rule_components)

                # Execute query
                results = list(self.kg_graph.query(query))

                if results and len(results[0]) == 4:
                    support_valid = int(results[0][0]) if results[0][0] else 0
                    support_invalid = int(results[0][1]) if results[0][1] else 0
                    pca_body_valid = int(results[0][2]) if results[0][2] else 0
                    pca_body_invalid = int(results[0][3]) if results[0][3] else 0

                    # Store raw counts
                    df.at[idx, 'Support_valid'] = support_valid
                    df.at[idx, 'Support_invalid'] = support_invalid
                    df.at[idx, 'PCABody_valid'] = pca_body_valid
                    df.at[idx, 'PCABody_invalid'] = pca_body_invalid

                    # Calculate individual PCA scores
                    if pca_body_valid > 0:
                        df.at[idx, 'PCA_valid'] = support_valid / pca_body_valid
                    if pca_body_invalid > 0:
                        df.at[idx, 'PCA_invalid'] = support_invalid / pca_body_invalid

                    # Calculate proportions based on support
                    total_support = support_valid + support_invalid
                    if total_support > 0:
                        # These are complementary and sum to 1
                        df.at[idx, 'PCA_valid_proportion'] = support_valid / total_support
                        df.at[idx, 'PCA_invalid_proportion'] = support_invalid / total_support

                # Debug first rule
                if idx == 0:
                    print(f"\nFirst rule: {body} => {head}")
                    print(f"Support: valid={support_valid}, invalid={support_invalid}")
                    print(f"PCABody: valid={pca_body_valid}, invalid={pca_body_invalid}")
                    print(f"PCA: valid={df.at[idx, 'PCA_valid']:.4f}, invalid={df.at[idx, 'PCA_invalid']:.4f}")
                    print(
                        f"PCA proportions: valid={df.at[idx, 'PCA_valid_proportion']:.4f}, invalid={df.at[idx, 'PCA_invalid_proportion']:.4f}")

            except Exception as e:
                print(f"Error processing rule {idx}: {e}")

        print("\nPCA confidence calculation completed!")
        return df

    def process_complete_pipeline(self, config_path: str) -> str:
        """
        Main function to process the complete pipeline using configuration file.

        Args:
            config_path (str): Path to combined configuration file

        Returns:
            str: Path to the final PCA results file
        """
        try:
            # Load configuration
            config = self.load_combined_config(config_path)

            # Extract configuration values for validation extension
            input_config = config.get('input', {})
            output_config = config.get('output', {})

            kg_folder = input_config.get('kg_folder')
            kg_name = input_config.get('kg_name')
            kg_subfolder = input_config.get('kg_subfolder')
            kg_filename = input_config.get('kg_filename')
            validation_report_path = input_config.get('validation_report_path', 'Constraints/validationReport.ttl')

            if not kg_folder or not kg_name:
                raise ValueError("kg_folder and kg_name must be specified in config file")

            if not kg_subfolder or not kg_filename:
                raise ValueError("kg_subfolder and kg_filename must be specified in config file")

            # Construct file paths for validation
            kg_folder_path = Path(kg_folder)
            validation_report_path = validation_report_path.format(kg_name=kg_name)
            validation_report_full_path = kg_folder_path / validation_report_path

            # Construct KG file path using config values
            # Support placeholders in kg_subfolder and kg_filename
            kg_subfolder_resolved = kg_subfolder.format(kg_name=kg_name)
            kg_filename_resolved = kg_filename.format(kg_name=kg_name)
            kg_file_path = kg_folder_path / kg_subfolder_resolved / kg_filename_resolved

            if not kg_file_path.exists():
                raise FileNotFoundError(f"KG file not found at: {kg_file_path}")

            if not validation_report_full_path.exists():
                raise FileNotFoundError(f"Validation report not found at: {validation_report_full_path}")

            logger.info(f"Processing KG: {kg_file_path}")
            logger.info(f"Using validation report: {validation_report_full_path}")

            # STEP 1: Load KG and validation report
            kg_graph = self.load_kg(str(kg_file_path))
            validation_graph = self.load_validation_report(str(validation_report_full_path))

            # Extract violating entities from validation report
            violating_entities = self.extract_violating_entities(validation_graph)

            # Add validation status triples
            extended_graph = self.add_validation_status_triples(kg_graph, violating_entities)

            # Determine output path for extended KG
            output_folder = output_config.get('output_folder', kg_folder)
            output_folder = output_folder.format(kg_name=kg_name)
            output_folder_path = Path(output_folder)
            output_folder_path.mkdir(parents=True, exist_ok=True)

            # Create output filename for extended KG
            extended_kg_filename = f"{kg_name}_EnrichedKG_with_validation.nt"
            extended_kg_path = output_folder_path / extended_kg_filename

            # Save extended KG
            self.save_extended_kg(extended_graph, str(extended_kg_path), 'nt')

            # STEP 2: Setup PCA calculation
            self.setup_pca_settings(config)

            # Get PCA-specific paths
            rules_csv_path = input_config.get('rules_path')
            if not rules_csv_path:
                raise ValueError("rules_path must be specified in config file")

            # Create PCA output path
            pca_output_filename = f"{kg_name}_constraint-pca_results.csv"
            pca_output_path = output_folder_path / pca_output_filename

            # STEP 3: Calculate PCA scores
            logger.info("Starting PCA calculation...")
            df_results = self.calculate_pca_scores(rules_csv_path, str(extended_kg_path))

            # Save PCA results
            df_results.to_csv(pca_output_path, index=False)
            logger.info(f"PCA results saved to {pca_output_path}")

            # Display summary statistics
            self._display_pca_summary(df_results)

            return str(pca_output_path)

        except Exception as e:
            logger.error(f"Error processing complete pipeline: {str(e)}")
            raise

    def _display_pca_summary(self, df_results: pd.DataFrame):
        """Display summary statistics for PCA results"""
        print("\n" + "=" * 60)
        print("PIPELINE COMPLETED SUCCESSFULLY")
        print("=" * 60)

        print("\nSummary Statistics:")
        print(f"\nComplementary PCA Proportions (sum to 1):")
        print(f"  Average PCA_valid_proportion: {df_results['PCA_valid_proportion'].mean():.4f}")
        print(f"  Average PCA_invalid_proportion: {df_results['PCA_invalid_proportion'].mean():.4f}")

        # Verify complementary nature
        total_support = df_results['Support_valid'] + df_results['Support_invalid']
        proportion_sums = df_results['PCA_valid_proportion'] + df_results['PCA_invalid_proportion']
        non_zero_sums = proportion_sums[total_support > 0]
        print(f"\nVerification - Proportion sums for rules with support > 0:")
        print(f"  All equal to 1.0: {all(abs(s - 1.0) < 0.0001 for s in non_zero_sums)}")

        print(f"\nIndividual PCA scores:")
        print(f"  Average PCA_valid: {df_results['PCA_valid'].mean():.4f}")
        print(f"  Average PCA_invalid: {df_results['PCA_invalid'].mean():.4f}")
        print(f"  Rules with PCA_valid > 0: {(df_results['PCA_valid'] > 0).sum()}")
        print(f"  Rules with PCA_invalid > 0: {(df_results['PCA_invalid'] > 0).sum()}")
        print("=" * 60)


def main():
    """Main function to run the combined pipeline"""
    if len(sys.argv) != 2:
        print("Usage: python combined_kg_pipeline.py <combined_config_file.json>")
        print("Example: python combined_kg_pipeline.py combined_config.json")
        sys.exit(1)

    config_file = sys.argv[1]

    try:
        processor = CombinedKGProcessor()
        output_path = processor.process_complete_pipeline(config_file)

        print("\n" + "=" * 60)
        print("SUCCESS: Complete KG Processing Pipeline Finished")
        print("=" * 60)
        print(f"Final PCA results file: {output_path}")
        print("=" * 60)

    except Exception as e:
        print("=" * 60)
        print("ERROR: Pipeline Failed")
        print("=" * 60)
        print(f"Error: {str(e)}")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()