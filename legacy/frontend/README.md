# Archived frontend experiments

These files were moved from `src/` on October 21, 2026 after checking the active application's imports. They are retained for reference and are excluded from CRA's application compilation by living outside `src/`.

- `src/services/`: experimental logistic models, multi-factor analyzers, optimization/data collection and the optional hotspot client.
- `src/components/`: unused route details, safety factors, time tolerance and hotspot controls/layer.
- `src/data/mockData.ts`: historical development fixtures.

The current application uses `src/services/graphhopper.ts` and `src/services/routeSafety.ts` in the repository root, with the Python incident scorer. These archived models do not determine current route ranking. Model comments and example coefficients do not establish validated training or accuracy.

This is a reference archive, not a standalone application. Original imports and aliases are preserved for context; restoring a component requires reviewing its dependencies, compatibility with current Route types, data provenance, error handling and tests. The archived hotspot client now propagates missing configuration, network failures and unsuccessful HTTP responses instead of presenting invented hotspot data.

Backend hotspot implementations and the existing deployed HotspotDetector function were preserved. Moving unused browser files does not authorize removing deployed resources. Older documentation may mention the former source paths; those paths now live under this directory.
