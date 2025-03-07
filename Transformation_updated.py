import os
import re
from rdflib import Graph, URIRef, Namespace
from rdflib.namespace import SH, RDF
from typing import Dict, List, Tuple, Set, Optional


class TriplePattern:
    def __init__(self, predicate: URIRef, object_value: URIRef, in_filter: bool = False, is_not_exists: bool = False):
        self.predicate = predicate
        self.object = object_value
        self.in_filter = in_filter
        self.is_not_exists = is_not_exists

    def __str__(self):
        return f"({self.predicate}, {self.object}, {'NOT ' if self.is_not_exists else ''}FILTER)" if self.in_filter else f"({self.predicate}, {self.object})"


def extract_triple_patterns(query_text: str) -> List[TriplePattern]:
    """Extract all triple patterns from a SPARQL query."""
    patterns = []

    filter_match = re.search(r'FILTER (?:NOT )?EXISTS \{([^}]+)\}', query_text)
    main_query = query_text
    filter_query = ""
    is_not_exists = False

    if filter_match:
        filter_query = filter_match.group(1)
        main_query = query_text[:filter_match.start()]
        is_not_exists = "NOT EXISTS" in query_text[filter_match.start() - 4:filter_match.start() + 15]

    def extract_from_text(text: str, in_filter: bool) -> None:
        # Direct patterns with $this
        direct_matches = re.finditer(r'\$this\s+<([^>]+)>\s+(?:<([^>]+)>|\?(\w+))', text)
        for match in direct_matches:
            pred = URIRef(match.group(1).strip())
            obj = URIRef(match.group(2).strip()) if match.group(2) else None
            patterns.append(TriplePattern(pred, obj, in_filter, is_not_exists if in_filter else False))

        # Indirect patterns with variables
        var_matches = re.finditer(r'\?(\w+)\s+<([^>]+)>\s+\?(\w+)', text)
        for match in var_matches:
            pred = URIRef(match.group(2).strip())
            patterns.append(TriplePattern(pred, None, in_filter, is_not_exists if in_filter else False))

    extract_from_text(main_query, False)
    if filter_query:
        extract_from_text(filter_query, True)

    return patterns


def process_shacl_shapes(shacl_file: str) -> Dict[str, List[TriplePattern]]:
    """Process SHACL shapes to extract constraint patterns"""
    shapes_graph = Graph()
    shapes_graph.parse(shacl_file, format='turtle')

    constraint_patterns = {}

    for shape in shapes_graph.subjects(RDF.type, SH.NodeShape):
        for sparql in shapes_graph.objects(shape, SH.sparql):
            query = str(shapes_graph.value(sparql, SH.select))
            patterns = extract_triple_patterns(query)
            if patterns:
                constraint_patterns[str(shape)] = patterns

    return constraint_patterns


def process_validation_report(report_file: str) -> List[Tuple[str, str]]:
    """Process validation report to extract violations"""
    with open(report_file, 'r', encoding='utf-8') as f:
        content = f.read()

    prefixes = """
        @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
        @prefix : <http://example.org/> .
    """
    modified_content = prefixes + content

    report_graph = Graph()
    report_graph.parse(data=modified_content, format='turtle')

    violations = []
    validation_results = list(report_graph.subjects(RDF.type, SH.ValidationResult))

    for result in validation_results:
        focus_node = report_graph.value(result, SH.focusNode)
        source_shape = report_graph.value(result, SH.sourceShape)
        if focus_node and source_shape:
            violations.append((str(focus_node), str(source_shape)))

    return violations


def check_pattern_match(graph: Graph, subject: URIRef, pattern: TriplePattern) -> bool:
    """Check if a subject matches a triple pattern"""
    if pattern.object is None:
        matches = any(True for _ in graph.triples((subject, pattern.predicate, None)))
        return not matches if pattern.is_not_exists else matches
    matches = any(obj == pattern.object for _, _, obj in graph.triples((subject, pattern.predicate, None)))
    return not matches if pattern.is_not_exists else matches

def transform_triple(triple: Tuple[URIRef, URIRef, URIRef],
                     patterns: List[TriplePattern]) -> Optional[Tuple[URIRef, URIRef, URIRef]]:
    """Transform a triple based on constraint patterns"""
    subject, predicate, obj = triple

    matching_filter_pattern = None
    for pattern in patterns:
        if pattern.in_filter and pattern.predicate == predicate:
            matching_filter_pattern = pattern
            break

    if matching_filter_pattern:
        prefix = "No" if not matching_filter_pattern.is_not_exists else ""
        entity_name = str(obj).split('/')[-1]
        new_pred = URIRef(f"{str(predicate)}_{prefix}{entity_name}")
        new_obj = URIRef(f"{str(obj).rsplit('/', 1)[0]}/{prefix}{entity_name}")
        return (subject, new_pred, new_obj)

    return None

def transform(enriched_kg: Graph, kg_name: str) -> Graph:
    """Main transformation function"""
    try:
        print(f"\nStarting transformation process for {kg_name}...")

        constraints_dir = f"Constraints/{kg_name}/result_{kg_name}"
        shapes_file = f"Constraints/{kg_name}/{kg_name}.ttl"
        violation_report = f"{constraints_dir}/validationReport.ttl"
        output_dir = f"./Transformed_{kg_name}"
        os.makedirs(output_dir, exist_ok=True)
        output_file = f"{output_dir}/TransformedKG_{kg_name}.nt"

        print("Processing SHACL constraints...")
        constraint_patterns = process_shacl_shapes(shapes_file)
        print(f"Found patterns for {len(constraint_patterns)} shapes")

        print("Processing validation report...")
        violations = process_validation_report(violation_report)
        print(f"Found {len(violations)} violations")

        transformed_kg = Graph()
        transformed_kg += enriched_kg

        triples_to_remove: Set[Tuple[URIRef, URIRef, URIRef]] = set()
        triples_to_add: Set[Tuple[URIRef, URIRef, URIRef]] = set()

        for subject_uri, shape_uri in violations:
            subject = URIRef(subject_uri)
            patterns = constraint_patterns.get(shape_uri)

            if not patterns:
                continue

            condition_patterns = [p for p in patterns if not p.in_filter]
            filter_patterns = [p for p in patterns if p.in_filter]

            matches_conditions = all(
                check_pattern_match(transformed_kg, subject, pattern)
                for pattern in condition_patterns
            )

            if matches_conditions:
                for s, p, o in transformed_kg.triples((subject, None, None)):
                    transformed = transform_triple((s, p, o), filter_patterns)
                    if transformed:
                        triples_to_remove.add((s, p, o))
                        triples_to_add.add(transformed)

        print(f"Applying {len(triples_to_remove)} transformations...")
        for triple in triples_to_remove:
            transformed_kg.remove(triple)
        for triple in triples_to_add:
            transformed_kg.add(triple)

        print(f"Saving transformed KG to {output_file}...")
        transformed_kg.serialize(destination=output_file, format='nt')

        print("\nTransformation Summary:")
        print(f"Original triples: {len(list(enriched_kg))}")
        print(f"Transformed triples: {len(list(transformed_kg))}")
        print(f"Violations processed: {len(violations)}")
        print("Transformation completed successfully!")

        return transformed_kg

    except Exception as e:
        print(f"\nError during transformation: {str(e)}")
        raise
