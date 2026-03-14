---
name: decompose-temporal-event-logs
description: Specialized decomposition strategy for temporal-event-logs tasks.
---

## When to Use
This strategy applies to queries requiring a comprehensive, chronological record of occurrences for a specific entity or category over a multi-year or multi-decade span. Indicators include requests for "every instance," "all occurrences," or "complete history" of events, performances, or milestones. These tasks typically involve high row counts (50+) and require high-precision temporal metadata (exact dates) alongside specific performance metrics or location data.

## Decomposition Template
1. **Define the Temporal Boundary:** Identify the start and end points of the requested period. If the end date is in the future, establish a "current date" cutoff for data collection.
2. **Partition by Activity Density:** Divide the total timeline into segments. The principle is to balance the "event density" rather than just time. For example, if an entity was more active in later years, assign shorter time blocks (e.g., 2-year windows) for those periods and longer blocks (e.g., 10-year windows) for periods of low activity.
3. **Standardize Schema Across Workers:** Define a strict schema for all workers before data collection begins. This ensures that "Entity X" and "Metric Y" are captured consistently, preventing merge conflicts during the final synthesis.
4. **Identify Source-Specific Eras:** If the entity’s history spans different record-keeping eras (e.g., pre-digital vs. digital), assign workers based on these eras, as the search strategies and source reliability will differ.

## Worker Assignment Rules
*   **Row-Based Partitioning:** Aim for approximately 10–20 expected rows per worker to prevent context window overflow and ensure thoroughness. **Always prefer more workers with narrower time ranges** — each worker has a limited tool call budget, so smaller scope = higher completeness.
*   **Chronological Continuity:** Assign workers contiguous time blocks. Do not split a single high-activity year across two workers unless the volume exceeds 50 rows for that year alone.
*   **Overlap Buffers:** Instruct workers to search 3 months past their assigned end-date to ensure events that span across boundaries (e.g., a season or a multi-day series) are not truncated.
*   **Verification Worker:** For high-stakes datasets, assign a "Gap Auditor" worker to specifically look for missing dates between the assigned blocks of other workers.

## Required Columns Checklist
*   **Primary Temporal Marker:** Exact date or timestamp of the occurrence.
*   **Event Identifiers:** Formal names, levels, or categories of the event.
*   **Spatial Metadata:** Physical location, venue, or host environment.
*   **Performance Metrics:** Results, rankings, scores, or specific achievements.
*   **Relational Data:** Associated entities (e.g., participants, competitors, or supporting cast) involved in that specific event.

## Anti-Patterns
*   **The "Recent Bias" Trap:** Workers often find recent data easily but fail to locate historical records. **Principle:** Require workers to explicitly confirm the "first known instance" within their block.
*   **Schema Drift:** Different workers using different units or naming conventions for the same metric. **Principle:** Enforce a global data dictionary before workers start.
*   **The "Summary" Failure:** Workers providing a summary of a period instead of a row-by-row log. **Principle:** Explicitly forbid "representative examples" and mandate "exhaustive enumeration."
*   **Redundant Over-Allocation:** Assigning multiple workers to the same "current" year without specific sub-tasking, leading to duplicate rows and wasted tokens.