---
name: decompose-geographic-registries
description: Specialized decomposition strategy for geographic-registries tasks.
---

## When to Use
Use this strategy when a query requires a comprehensive census of entities defined by spatial, administrative, or regulatory boundaries. These tasks typically involve "all-of" requests (e.g., every protected site in a region) or specific lists of high-value assets (e.g., corporate entities on a specific exchange). The data usually requires a mix of static identifiers, temporal metadata (designation dates), and dynamic administrative details (current leadership or contact info).

## Decomposition Template
1.  **Define the Boundary & Source Hierarchy:** Identify the primary geographic or regulatory container (e.g., Region A, Exchange B). Determine if the registry is maintained by a single central authority or multiple regional bodies.
2.  **Partition by Administrative Sub-unit:** Divide the search space into the smallest logical administrative units (e.g., Sub-region X, State Y, or Category Z). This prevents "middle-of-the-list" omissions common in large datasets.
3.  **Temporal Filtering:** Apply the specific time-cutoff requested (e.g., "established before Year X" or "active during Year Y").
4.  **Attribute Extraction (Per Entity):** For each identified entity, extract three layers of data:
    *   *Core Identifiers:* Official name and unique registry ID.
    *   *Spatial/Administrative Context:* Precise location and the governing body responsible for the entity.
    *   *Status Metadata:* Dates of designation, current operational status, and official contact/web references.
5.  **Cross-Reference Verification:** Compare the compiled list against a secondary source (e.g., a map vs. a text-based registry) to ensure no entities were missed due to naming variations or recent status changes.

## Worker Assignment Rules
*   **Row Limits:** Assign a maximum of 10–15 entities per worker. Geographic registries often have dense, multi-column requirements that lead to fatigue and skipped rows. **Always prefer more workers with narrower scope** — each worker has a limited tool call budget, so smaller scope = higher completeness.
*   **Partitioning Logic:** Partition by geographic sub-region or alphabetical clusters of entity names.
*   **Verification Layer:** For "comprehensive" lists, always assign a "Gap Checker" worker whose sole task is to find entities present in the source but missing from the primary workers' outputs.

## Required Columns Checklist
*   **Official Nomenclature:** Primary names and any required localized or alternative aliases.
*   **Temporal Markers:** Specific dates or years of entry into the registry.
*   **Administrative Ownership:** The specific public or private body currently managing the entity.
*   **Locational Specifics:** Granular address data or sub-regional coordinates.
*   **Reference Links:** Direct URLs to the official registry entry or governing document for each entity.

## Anti-Patterns
*   **The "Top-Heavy" Omission:** Relying on a single "Top 10" or "Featured" list which often excludes smaller or more recent entries in a registry.
*   **Boundary Bleed:** Including entities that are near the geographic boundary but not legally within the administrative jurisdiction.
*   **Stale Status:** Failing to verify if an entity's status has changed (e.g., a site that was de-listed or a company that moved exchanges) relative to the requested time-frame.
*   **Naming Collisions:** Treating two entities with similar names in different sub-regions as a single entry, or failing to recognize that a single entity spans multiple sub-regions.