---
name: decompose-split-by-rank-segment
description: Specialized decomposition strategy for split-by-rank-segment tasks.
---

## When to Use
This strategy is applicable when a query requests a specific "Top N" or "Bottom N" subset from a recognized, authoritative, and pre-ordered list. It is indicated by queries that specify a numerical range (e.g., 1-50, 51-100) and require multiple attributes for each entity within that ordinal sequence. Use this when the source data is likely to be published as a structured index or annual leaderboard.

## Decomposition Template
1. **Identify the Authoritative Source and Version:** Determine the specific organization, publication, or index that maintains the ranking and the exact time period or version requested.
2. **Segment the Rank Range:** Divide the total requested range into equal, manageable segments (e.g., segments of 25 or 50). The principle is to prevent context-window overflow and ensure high-precision retrieval for each specific ordinal position.
3. **Define Attribute Extraction Requirements:** For each segment, specify the primary entity name and all secondary metrics or metadata required by the query.
4. **Synthesize and Re-order:** Consolidate the outputs from all segments into a single structure, ensuring the ordinal integrity (1 to N) is preserved and no gaps exist between segments.

## Worker Assignment Rules
- **Partitioning:** Assign one worker per 25-50 rows. Smaller segments are preferred if the query requires more than 3-4 complex attributes per entity.
- **Overlap Prevention:** Ensure segment boundaries are explicit (e.g., Worker 1: Ranks 1-25; Worker 2: Ranks 26-50) to avoid duplicate entries.
- **Verification:** If the ranking is subject to frequent updates or multiple versions (e.g., "Preliminary" vs "Final"), assign a verification worker to cross-reference the top and bottom entities of each segment against the source index.

## Required Columns Checklist
- **Ordinal Identifier:** The specific rank or position number (essential for maintaining sequence).
- **Primary Entity Name:** The name of the individual, company, or object being ranked.
- **Quantitative Metrics:** The specific values that determined the ranking (e.g., volume, revenue, score).
- **Temporal Metadata:** Dates related to the entity's history or the data collection period (e.g., founding year, date of measurement).
- **Categorical Attributes:** Descriptive traits required for the final output (e.g., location, type, classification).

## Anti-Patterns
- **The "Missing Middle" Error:** Failing to define explicit start/end points for segments, leading to gaps in the sequence (e.g., skipping ranks 25-26).
- **Attribute Drift:** Workers in different segments extracting different types of data for the same column (e.g., one worker providing "Year Founded" while another provides "Age").
- **Source Mismatch:** Using a different version of a list for different segments (e.g., using the 2023 list for ranks 1-25 and the 2024 list for ranks 26-50).
- **Unordered Synthesis:** Merging worker outputs without re-sorting, resulting in a table where Rank 26 appears before Rank 1.