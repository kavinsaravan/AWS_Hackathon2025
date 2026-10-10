#!/usr/bin/env python3
"""Reproducible SF feature dataset; required source failures abort generation."""
from safety_dataset import SafetyDatasetGenerator, main

class OptimizedSafetyDatasetGenerator(SafetyDatasetGenerator):
    fetch_data_parallel = SafetyDatasetGenerator.fetch_all_data

    def calculate_risk_for_location(self, lat, lng):
        return self.location_features(lat, lng)['is_unsafe']

    def generate_binary_dataset(self, num_samples=10000):
        return self.generate_dataset(num_samples, fetch=not self._loaded)

    def save_binary_csv(self, rows, filename='sf_safety_binary_production.csv', labels_only=False):
        return self.save_dataset(rows, filename, labels_only)

    def run(self, num_samples=10000):
        return self.save_binary_csv(self.generate_dataset(num_samples))

if __name__ == '__main__':
    main('sf_safety_binary_production.csv')
