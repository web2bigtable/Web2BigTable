---
name: decompose-split-by-entity
description: Specialized decomposition strategy for split-by-entity tasks requiring deep attribute extraction for a discrete list of subjects.
---

## When to Use
Use this strategy when a query identifies a specific set of independent subjects (entities) and requests a uniform set of high-density attributes for each. This pattern is ideal when:
- The entities belong to a clear category (e.g., products, organizations, creative works).
- Each entity requires "deep-dive" research across multiple technical, financial, or historical dimensions.
- The data for one entity does not depend on or overlap with the data of another.
- The output is expected to be a comprehensive, multi-column comparison table.

## Decomposition Template
1.  **Entity Enumeration:** Identify the full list of primary subjects. If the query provides a range (e.g., "all models in series X"), the first subtask must be to generate an exhaustive list of these entities.
2.  **Attribute Definition:** Standardize the required data points (metrics, dates, specifications) to ensure consistency across all workers.
3.  **Horizontal Partitioning:** Divide the list of entities into small batches. Assign each batch to a separate worker.
4.  **Deep-Dive Extraction:** Each worker performs targeted research for their assigned entities only, focusing on filling every required attribute column.
5.  **Vertical Synthesis:** A final pass aggregates the independent rows into a single unified table, ensuring formatting (units, date formats) is synchronized.

## Worker Assignment Rules
- **Batch Size:** Assign 3–5 complex entities per worker. For simpler entities (e.g., single-attribute lists), this can increase to 10. **Always prefer more workers with smaller batches** — each worker has a limited tool call budget, so smaller scope = higher completeness.
- **Specialization:** If the entities span different sub-categories or eras, group them by similarity to allow the worker to maintain context.
- **Verification:** For high-precision tasks (e.g., financial data or technical specs), assign a "Cross-Check" worker to verify 20% of the data points against primary sources.

## Required Columns Checklist
- **Primary Identifiers:** Official names, unique IDs, or parent organizations.
- **Temporal Metadata:** Launch/release dates, sunset/discontinuation dates, or specific "as of" timestamps.
- **Quantitative Metrics:** Technical specifications, financial figures, or performance scores (always include units).
- **Categorical Classifiers:** Type, status, or classification tags that allow for sorting/filtering.
- **Relational Data:** Associated people (e.g., leadership, creators) or secondary entities (e.g., locations, subsidiaries).

## Anti-Patterns
- **The "Breadth-First" Failure:** Attempting to find one specific attribute for *all* entities at once. This leads to high tool-call volume and frequent timeouts. Always research all attributes for a *subset* of entities.
- **Scope Creep:** Including "limited edition" or "variant" data when the query specifies "standard" or "core" range.
- **Attribute Omission:** Failing to capture secondary details (like "credits" or "requirements") because the worker focused only on the primary name and date.
- **Unit Inconsistency:** Mixing different measurement systems (e.g., metric vs. imperial) or date formats across different workers.
- **Missing "Zero" Values:** Leaving cells blank instead of explicitly stating "None" or "N/A" when an attribute is confirmed to be non-existent for a specific entity.