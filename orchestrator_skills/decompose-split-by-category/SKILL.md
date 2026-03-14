---
name: decompose-split-by-category
description: Specialized decomposition strategy for split-by-category tasks.
---

## When to Use
This strategy is ideal for queries requiring a comprehensive census or list of entities that are naturally organized by a fixed, high-level taxonomy. Use this when the request specifies a set of discrete "buckets" (e.g., organizational tiers, geographic zones, or professional classifications) and requires multiple attributes for every entity within those buckets. The data shape is typically a multi-row table where rows are grouped by a primary categorical header.

## Decomposition Template
1.  **Identify the Primary Partition Key:** Determine the highest-level category mentioned in the prompt (e.g., "Classification A", "Region B").
2.  **Define the Scope per Subtask:** Assign one or more full categories to each worker. Do not split a single category across multiple workers unless the entity count per category exceeds the worker's processing limit.
3.  **Standardize Attribute Extraction:** Define a uniform set of "Entity Attributes" (e.g., "Identifier X", "Metric Y", "Status Z") that every worker must retrieve to ensure the final merged table is consistent.
4.  **Temporal/Constraint Alignment:** If the query specifies a time range (e.g., "Year X to Year Y") or a threshold (e.g., "Value > N"), include these constraints in every subtask definition to prevent workers from returning out-of-scope data.

## Worker Assignment Rules
*   **Load Balancing:** Aim for 10–20 entities per worker. If a single category (e.g., "Category A") contains 50+ entities, further decompose that subtask by a secondary attribute (e.g., "Category A - Sub-group 1"). **Always prefer more workers with narrower scope** — each worker has a limited tool call budget, so smaller scope = higher completeness.
*   **Isolation:** Each worker should be responsible for the complete lifecycle of their assigned category—from discovery of the entity list to the retrieval of specific metadata.
*   **Redundancy/Verification:** For high-precision tasks, assign a "Verification Worker" to cross-check 10% of the entries from each category against a second source.

## Required Columns Checklist
*   **Categorical Headers:** The primary and secondary labels used to group the data.
*   **Unique Identifiers:** The specific name or ID of the entity being described.
*   **Quantitative Metrics:** Numerical values, scores, or rankings associated with the entity.
*   **Temporal Metadata:** Years, seasons, or timestamps indicating when the data was recorded.
*   **Source/Reference Links:** Direct URLs or citations for the specific data points retrieved.
*   **Status Indicators:** Current state or classification (e.g., "Active", "Completed", "Pending").

## Anti-Patterns
*   **The "Truncation Trap":** Assigning too many categories to a single worker, leading to incomplete tables or "cut-off" responses due to output token limits.
*   **Inconsistent Schema:** Failing to enforce a strict column list, resulting in workers returning different types of data for different categories (e.g., Worker A provides "Metric X" while Worker B provides "Metric Y").
*   **Missing "Null" Values:** Workers omitting entities because certain attributes are missing. Workers should be instructed to use "N/A" or "Unknown" to maintain the integrity of the list.
*   **Overlapping Scopes:** Assigning the same category to two workers without clear boundaries, leading to duplicate rows in the final output.