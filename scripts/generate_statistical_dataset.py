#!/usr/bin/env python3
"""Export a reproducible location sample; sample size does not prove label accuracy."""
from safety_dataset import SafetyDatasetGenerator, main

class StatisticalSafetyDataset(SafetyDatasetGenerator):
    def save_dataset(self, rows, filename='sf_safety_statistical.csv', labels_only=False):
        return super().save_dataset(rows, filename, labels_only)

    def calculate_real_safety(self, lat, lng):
        return self.location_features(lat, lng)['is_unsafe']

    def generate_statistical_dataset(self):
        return self.generate_dataset(self.sample_size)

if __name__ == '__main__':
    main('sf_safety_statistical.csv', default_samples=385)
