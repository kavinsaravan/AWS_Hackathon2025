#!/usr/bin/env python3
"""Sampled location features and heuristic labels; no forced unsafe percentile."""
from safety_dataset import SafetyDatasetGenerator, main

class FinalSafetyDataset(SafetyDatasetGenerator):
    def generate_dataset(self, num_samples=None, fetch=True):
        return super().generate_dataset(self.sample_size if num_samples is None else num_samples, fetch=fetch)

    def calculate_safety_label(self, lat, lng):
        return self.location_features(lat, lng)['is_unsafe']

    def save_csv(self, rows, filename='sf_safety_ml_dataset.csv', labels_only=False):
        return self.save_dataset(rows, filename, labels_only)

if __name__ == '__main__':
    main('sf_safety_ml_dataset.csv', default_samples=385)
