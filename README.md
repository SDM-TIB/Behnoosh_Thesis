# Behnoosh_Thesis
This repository contains the implementation of my master's thesis, which focuses on computing PCA-based validation scores for knowledge graphs. The goal is to calculate PCA_valid and PCA_invalid scores for entities in the KG by validating the graph against a set of SHACL-like constraints.
The pipeline involves:

1- Validating the knowledge graph using provided constraint rules (in .ttl format).

2- Enriching the KG with validation results (valid or invalid).

3- Calculating PCA scores based on the enriched graph.

4- Using these scores in symbolic prediction tasks.
