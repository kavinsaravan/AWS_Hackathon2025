#!/usr/bin/env python3
"""Export sampled SF location features with binary heuristic safety labels."""
from safety_dataset import SafetyDatasetGenerator, main

def generate_binary_safety_dataset(num_samples=10000, seed=42, filename='sf_safety_binary.csv', labels_only=False):
    generator = SafetyDatasetGenerator(seed=seed)
    rows = generator.generate_dataset(num_samples)
    return generator.save_dataset(rows, filename, labels_only)

if __name__ == '__main__':
    main('sf_safety_binary.csv')
