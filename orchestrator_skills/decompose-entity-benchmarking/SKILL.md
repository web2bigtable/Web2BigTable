---
name: decompose-entity-benchmarking
description: Specialized decomposition strategy for entity-benchmarking tasks involving multi-attribute data collection across a defined set of entities.
---

## When to Use
This strategy applies when a query requires a structured comparison of multiple distinct entities (e.g., products, organizations, or programs) against a set of standardized metrics. Key indicators include:
- Requests for "all models/types" within a specific category or time range.
- Requirements for deep attribute extraction (e.g., technical specs, pricing, or entry requirements) across a list of entities.
- Comparison across multiple independent ranking systems or performance benchmarks.
- Data that must be synthesized into a unified table from disparate primary sources.

## Decomposition Template
1.  **Scope Definition:** Identify the boundary conditions (e.g., "Region X only," "Time Period Y," or "Category Z"). Define the "Universe of Entities" to prevent over-collection or missing niche entries.
2.  **Entity Partitioning:** Divide the total entity list into logical groups. The principle is to group entities that likely share a common primary source (e.g., grouping by parent organization, manufacturer, or alliance) to minimize redundant navigation for workers.
3.  **Attribute Standardization:** Define a "Master Schema" for all workers. This ensures that if Worker A finds "Metric X," Worker B is also looking for "Metric X" using the same units or definitions.
4.  **Temporal/Version Alignment:** Explicitly instruct workers to verify the specific version or year requested (e.g., "Current 2025 specs" vs. "Historical 2015 specs") to avoid mixing data from different cycles.
5.  **Synthesis & Deduplication:** A final step to merge partitioned tables, ensuring that entities appearing in multiple categories are not duplicated and that formatting is consistent.

## Worker Assignment Rules
- **Partition Size:** Assign 3–5 major entities (or 10–15 minor line items) per worker to maintain high data precision and prevent search fatigue. **Always prefer more workers with smaller batches** — each worker has a limited tool call budget, so smaller scope = higher completeness.
- **Domain Grouping:** Assign entities from the same "family" or "brand" to the same worker to leverage site-specific navigation patterns.
- **Verification Workers:** If the data involves high-stakes metrics (e.g., financial fees or legal requirements), assign a secondary worker to "Spot Check" 20% of the rows found by the primary workers.

## Required Columns Checklist
- **Primary Identifiers:** Unique names, official IDs, or model numbers.
- **Categorical Metadata:** Parent groups, alliances, or sub-categories.
- **Temporal Metadata:** Release dates, effective years, or application cycles.
- **Primary Metrics:** The core performance or specification data requested.
- **Access Metadata:** Official source URLs, direct links to documentation, or "last updated" timestamps.
- **Constraint Flags:** Columns indicating if an entity meets specific filters (e.g., "Standard Range Only" or "US Market Only").

## Anti-Patterns
- **The "Generalist" Failure:** Assigning one worker to find "all entities" in a broad category. This leads to missing niche entities or truncated lists.
- **Metric Drift:** Failing to define units (e.g., "Currency A" vs "Currency B"), leading to a table with incomparable data.
- **Source Homogenization:** Relying on a single aggregator site that may be outdated. Workers should be instructed to seek official primary sources for each entity group.
- **Ignoring "Program-Specific" Nuance:** Treating a large organization as a monolith when attributes (like deadlines or fees) actually vary by specific sub-entity or department.