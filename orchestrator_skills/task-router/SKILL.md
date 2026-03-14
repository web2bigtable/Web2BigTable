---
name: task-router
description: Identifies the task type and directs the orchestrator to the correct decompose skill.
---

## How to Use
1. Read the user's query and identify the primary organizational axis (time, entity, category, or rank).
2. Match it against the task types below.
3. Call `read_orchestrator_skill("decompose-<matched_type>")` to load the specialized strategy.

## Task Types

### split-by-rank-segment
**Match when:** The query asks for a specific "Top N" list or a numbered ranking (e.g., "Top 50 movies," "100 best-selling albums"). The request relies on a pre-existing ordinal sequence.
**Load skill:** `decompose-split-by-rank-segment`
**Key signal:** Presence of ordinal numbers, "Top [X]," or "Ranked" phrasing.

### split-by-time-period
**Match when:** The query specifies a continuous chronological range or a multi-year history (e.g., "from 2010 to 2024," "all releases in the 1990s").
**Load skill:** `decompose-split-by-time-period`
**Key signal:** Date ranges, decades, or "year-by-year" requirements.

### split-by-entity
**Match when:** The query lists specific, discrete subjects like brand names, individual people, or specific product models that require deep attribute extraction (e.g., "Nikon Z6, Sony A7IV, and Canon R6").
**Load skill:** `decompose-split-by-entity`
**Key signal:** Proper nouns of specific products, companies, or individuals.

### split-by-category
**Match when:** The query is organized by broad domain classifications, geographic regions, or institutional departments (e.g., "by country," "academic subjects," or "sports leagues").
**Load skill:** `decompose-split-by-category`
**Key signal:** Use of "by [Category Name]" or lists of distinct sectors/regions.

### annual-rank-stats
**Match when:** The query asks for annual statistics, yearly rankings, or season-by-season performance data (e.g., "annual GDP rankings," "yearly box office leaders," "season stats for each year").
**Load skill:** `decompose-annual-rank-stats`
**Key signal:** "annual," "yearly," "per season," combined with rankings or statistics.

### entity-benchmarking
**Match when:** The query requires collecting multi-attribute specifications or benchmark data across a defined set of entities (e.g., "compare specs of these 10 laptops," "benchmark all models in this product line").
**Load skill:** `decompose-entity-benchmarking`
**Key signal:** Spec sheets, benchmark comparisons, multi-attribute tables for known entities.

### geographic-registries
**Match when:** The query involves location-based registries, inventories, or catalogs organized by geographic boundaries (e.g., "all UNESCO sites by country," "hospitals in each province," "national parks by state").
**Load skill:** `decompose-geographic-registries`
**Key signal:** Geographic partitioning, "by country/state/region," registry or inventory language.

### temporal-event-logs
**Match when:** The query asks for a chronological log of discrete events, incidents, or occurrences (e.g., "all earthquakes above magnitude 6 since 2000," "product recall history," "timeline of policy changes").
**Load skill:** `decompose-temporal-event-logs`
**Key signal:** Event logs, incident histories, timelines of discrete occurrences (not continuous product releases — use split-by-time-period for those).

## Default Fallback
If no type matches clearly, use general decomposition principles:
- Split by entity or category to ensure data independence.
- Keep each worker load under 30 rows to prevent context loss.
- Explicitly list all required columns/attributes in every subtask description.