---
name: decompose-annual-rank-stats
description: Specialized decomposition strategy for annual-rank-stats tasks.
---

## When to Use
This strategy applies to queries requiring longitudinal data extraction or snapshots of competitive standings. Use this when the request involves:
- **Temporal Series:** Data spanning multiple discrete time units (months, fiscal years, or calendar years).
- **Ordinal Rankings:** Lists defined by a specific "Top N" position or hierarchical status.
- **Multi-Metric Reporting:** Requests for several distinct attributes (financial, biographical, or operational) for each time-rank coordinate.
- **Official Records:** Data sourced from periodic publications, award ceremonies, or regulatory filings.

## Decomposition Template
1. **Identify the Primary Pivot:** Determine if the data is primarily organized by time (e.g., Year X) or by rank (e.g., Rank 1-50).
2. **Define the Temporal/Ordinal Range:** Establish the exact boundaries (start/end dates or start/end ranks) and the required granularity (monthly vs. yearly).
3. **Partition by Unit of Authority:** Divide the task so each sub-task covers a specific, manageable slice of the pivot. 
    - *Principle:* Grouping by the primary pivot (e.g., one worker per year) ensures that the worker captures the complete "snapshot" for that period, maintaining internal consistency for rankings.
4. **Attribute Mapping:** List all required metrics for each entry. 
    - *Principle:* Distinguish between "Static Attributes" (e.g., Entity Name, Origin) and "Variable Metrics" (e.g., Value in Year X, Rank in Year X) to ensure workers look for both historical and fixed data points.
5. **Synthesis & Deduplication:** Consolidate sub-task outputs into a single chronological or ordinal table, ensuring that entities appearing in multiple periods are handled consistently.

## Worker Assignment Rules
- **Partitioning:** Assign 1–3 years (or 10–20 ranks) per worker depending on the number of required columns. **Always prefer more workers with narrower ranges** — each worker has a limited tool call budget, so smaller scope = higher completeness.
- **Overlap:** If the query asks for "changes" or "trends" between periods, ensure workers have access to the preceding period's data for context.
- **Verification:** Assign a dedicated verification worker if the data involves high-precision numbers (e.g., financial figures to the nearest decimal) or specific formatting requirements (e.g., specific ID codes).

## Required Columns Checklist
- **Primary Identifiers:** The unique name of the entity and its specific time/rank coordinate.
- **Quantitative Metrics:** Numerical values, currency, or counts associated with the specific period.
- **Qualitative Metadata:** Background info, categories, or descriptive attributes of the entity.
- **Standardized Codes:** Industry-standard identifiers (e.g., alphanumeric codes, abbreviations) often required for data interoperability.
- **Temporal Metadata:** Specific dates of occurrence or fiscal year designations.

## Anti-Patterns
- **The "Metric-First" Split:** Assigning one worker to find "Metric A" for all years and another for "Metric B." This leads to mismatched rows and inconsistent entity naming.
- **Boundary Omission:** Failing to specify if the start and end years/ranks are inclusive, leading to missing data at the edges of the range.
- **Ignoring Re-ranking:** Assuming an entity's rank remains static across years. Each time period must be treated as a fresh ranking unless otherwise specified.
- **Unit Inconsistency:** Collecting data in different scales (e.g., millions vs. billions) across different workers without a central normalization step.