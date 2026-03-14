---
name: decompose-split-by-time-period
description: Specialized decomposition strategy for tasks requiring exhaustive data collection over a continuous chronological range.
---

## When to Use
Use this strategy when a query requires a comprehensive list of events, product releases, or periodic data points across a long, defined time range (e.g., multiple years or decades). This is indicated by requests for "every," "all," or "complete list" where the primary index for the data is a timestamp, date, or fiscal period. It is especially effective when the expected volume of data points exceeds the context window of a single model pass.

## Decomposition Template
1. **Define the Boundary**: Identify the absolute start and end points of the requested period.
2. **Segment the Timeline**: Divide the total duration into equal, manageable blocks (e.g., 2-year, 5-year, or 12-month segments). The size of the segment should be inversely proportional to the expected density of data (high-frequency events require smaller windows).
3. **Standardize the Schema**: Define a uniform data structure (columns) that every worker must follow to ensure seamless merging.
4. **Assign Parallel Research**: Assign each segment to a separate worker. Each worker is responsible for exhaustive discovery within their specific window, including "edge" cases that fall on the start or end dates of their segment.
5. **Consolidate and Sort**: A final step must merge all worker outputs, remove potential duplicates at the segment boundaries, and sort the entire dataset chronologically.

## Worker Assignment Rules
- **Density-Based Partitioning**: Limit each worker to a range expected to yield 10–20 records. If a single year is known to be "event-heavy," assign that year to its own worker. **Always prefer more workers with narrower ranges** — each worker has a limited tool call budget, so smaller scope = higher completeness.
- **Overlap Handling**: Instruct workers to strictly adhere to `[Start Date, End Date]` boundaries to prevent double-counting or gaps.
- **Verification Workers**: For high-precision tasks (e.g., financial data or legal records), assign a secondary worker to cross-verify a random 10% sample of the primary worker's findings.

## Required Columns Checklist
- **Primary Temporal Marker**: The specific date, month, or year of the occurrence.
- **Entity Identifiers**: Names, models, or titles that uniquely identify the record.
- **Categorical Metadata**: Attributes that classify the entity (e.g., type, sector, or level).
- **Quantitative Metrics**: Numerical values associated with the record (e.g., counts, prices, or performance stats).
- **Contextual Details**: Qualitative descriptions or secondary attributes (e.g., locations, participants, or specific features).

## Constraint Propagation — CRITICAL
Every subtask prompt MUST carry forward ALL constraints from the original query:
- **Inclusion/exclusion filters**: any "excluding X", "only Y", "different from Z" clauses
- **Scope boundaries**: exact categories, date ranges, geographic regions, product families
- **Terminology requirements**: exact column names, value formats, unit conventions
- **Negative constraints**: what to omit is as important as what to include

When writing subtask descriptions, copy the original query's filter clauses verbatim into each subtask. Workers are stateless — if a constraint is not in the subtask prompt, it does not exist for that worker.

## Exhaustive Coverage
Each worker MUST aim for exhaustive discovery within their assigned segment. Do not settle for the first list found — actively search for items that might be missing:
- **All sub-categories and variants** of the entity being cataloged (e.g., different editions, tiers, regional variants, OEM-only versions, limited releases)
- **Items that only appear in specialized sources** — mainstream summary pages often omit niche, low-volume, or region-specific entries
- **Cross-reference at least 2 independent sources** per segment to catch items that one source alone may omit (e.g., Wikipedia + official manufacturer pages + domain-specific databases)

The orchestrator should explicitly list the known variant categories in each subtask prompt so workers know what to look for.

## Format Specification
Each subtask description MUST include a concrete "Format Example" showing the exact columns and value conventions expected. This prevents schema drift across workers.

Include in each subtask prompt:
1. The exact column headers in order
2. One example row with correctly formatted values
3. Any value conventions (e.g., how to represent missing data, required units, full names vs abbreviations)

Workers must follow this format exactly — no abbreviating values, no changing column order, no omitting columns.

## Anti-Patterns
- **The "Recent Bias" Gap**: Workers often find modern data easily but struggle with older records. Ensure workers are prompted to use archive-specific search queries for earlier segments.
- **Boundary Omission**: Failing to define whether the start/end dates are inclusive, leading to missing data on the first or last day of a period.
- **Schema Drift**: Workers modifying column headers or data formats (e.g., switching from YYYY-MM-DD to MM/DD/YY), making automated merging impossible.
- **Surface-Level Search**: Relying on a single summary list that might be incomplete. Workers should be required to cross-reference at least two distinct sources for each time segment.