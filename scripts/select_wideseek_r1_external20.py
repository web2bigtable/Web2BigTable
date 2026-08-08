#!/usr/bin/env python3
"""Build the fixed 20-example high-search external skill-induction split.

The source records are selected by 1-based line number from the pinned
WideSeek-R1 width_20k.jsonl file.  The script refuses to run if either source
file has a different SHA256, validates the Markdown tables and unique keys,
and recomputes the lexical-overlap audit against the pinned WideSearch test
set before writing any output.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
import re
import tempfile
import urllib.request
from pathlib import Path


TRAIN_REVISION = "bd03eb2ccc171a2e1dade48c499b82fe040757f5"
TEST_REVISION = "d9134a1661dd0a5402d1a7c5e0bfda7333ec81ba"
TRAIN_SHA256 = "7e2c17a5eac063850ff908927378e8a678370726b7c41ca53b824d723f892855"
TEST_SHA256 = "402285fc1bc28b662c363d0ea04103f8be79b6a38f6035471985dc45b4ada143"
MAX_LEXICAL_COSINE = 0.30

TRAIN_URL = (
    "https://huggingface.co/datasets/RLinf/WideSeek-R1-train-data/resolve/"
    "main/width_20k.jsonl"
)
TEST_URL = (
    "https://huggingface.co/datasets/RLinf/WideSeek-R1-test-data/resolve/"
    "main/test.jsonl"
)

# The line list was frozen before running Web2BigTable on the external split.
# Every answer has at least 50 rows, 7 columns, and 350 populated cells.
# Candidates were manually reviewed for retrieval burden, ambiguity, topic
# diversity, and semantic overlap after deterministic quality/lexical filters.
# No benchmark scores were used.
SELECTIONS = [
    (
        11279,
        "cross_domain_join",
        "MLS first-round draft picks and university histories, 2015-2017",
        "63 players; join draft records with university location and founding data",
    ),
    (
        14530,
        "multi_series_aggregation",
        "Magic: The Gathering Pro Tours and World Championships, 1996-2006",
        "63 events across seasons; recover dates, venues, formats, winners, and prizes",
    ),
    (
        18306,
        "cross_domain_join",
        "Best Picture winners adapted from literary works through 2016",
        "59 films; join award history to original works, authors, and literary forms",
    ),
    (
        2022,
        "historical_registry_enrichment",
        "Colonial Brazil governors, viceroys, and governing juntas, 1549-1808",
        "58 administrations; align terms, titles, capitals, monarchs, and biographies",
    ),
    (
        11498,
        "cross_entity_join",
        "Record signings for 2016-17 Premier League, La Liga, and Bundesliga clubs",
        "58 clubs; identify each record transfer and enrich player and transaction data",
    ),
    (
        4841,
        "historical_registry_enrichment",
        "Westbound Blue Riband record voyages, 1838-1952",
        "56 voyages; reconcile operators, flags, dates, speeds, passage times, and routes",
    ),
    (
        17057,
        "cross_domain_join",
        "NBA Coach of the Year winners through 2016-17",
        "55 award rows; join season records and playoff outcomes to coach alma maters",
    ),
    (
        9261,
        "cross_domain_join",
        "British prime ministers through 2017",
        "54 officeholders; combine term and party history with biographies and universities",
    ),
    (
        14087,
        "entity_attribute_join",
        "ALCO diesel-electric locomotive models, 1924-1969",
        "54 models; recover technical specifications, production spans, and production totals",
    ),
    (
        18962,
        "cross_domain_join",
        "Stephen King theatrical adaptations and top-billed roles, 1980-1993",
        "18 films expanded to 54 actor-role rows; join source, production, billing, and role data",
    ),
    (
        16659,
        "multi_series_aggregation",
        "East Asian sporting and diplomatic events, 1950-2017",
        "53 events from 13 series; reconcile dates, hosts, political names, and main venues",
    ),
    (
        19493,
        "cross_domain_join",
        "California 2016 congressional district election results",
        "53 districts; join election outcomes with winners' education and incumbency history",
    ),
    (
        3227,
        "multi_series_aggregation",
        "Big Four beauty-pageant winners, 2005-2017",
        "52 editions across four pageants; recover dates, hosts, winners, delegations, and field sizes",
    ),
    (
        7383,
        "cross_region_registry",
        "MLB, NPB, and KBO team stadiums in 2017",
        "52 teams across three countries; join team membership to venue specifications",
    ),
    (
        17733,
        "entity_attribute_join",
        "Madhya Pradesh district demographics from the 2011 census",
        "51 districts; assemble seven geographic and demographic attributes per district",
    ),
    (
        8878,
        "entity_attribute_join",
        "Top 50 tallest occupied buildings as of 2017",
        "50 buildings; combine ranking, dimensional, completion, and structural attributes",
    ),
    (
        2003,
        "multi_series_aggregation",
        "Performed operas by Verdi, Wagner, and Puccini",
        "50 operas across three composers; reconcile librettists, genres, dates, venues, and cities",
    ),
    (
        7853,
        "cross_domain_join",
        "World's 50 most valuable sports teams in July 2017",
        "50 ranked teams; join valuations to leagues, countries, owners, and founding years",
    ),
    (
        8738,
        "cross_domain_join",
        "Grammy Album of the Year nominees, 2008-2017",
        "50 nominations; join award outcomes with album genre and label metadata",
    ),
    (
        12293,
        "cross_domain_join",
        "Top 50 best-selling video games through 2017",
        "50 games; join historical sales with developer, publisher, platform, release, and director data",
    ),
]

STOPWORDS = set(
    "the a an of to and in for on with by from as at is are be all every each "
    "this that data table list provide compile dataset information research "
    "need want require please including include into based according output "
    "organized create".split()
)
BOILERPLATE_MARKERS = (
    "Please output the organized data",
    "Please output the result",
    "The column names are as follows",
    "Do not ask me any questions",
    "Output only the table",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


def core_question(text: str) -> str:
    cut = len(text)
    for marker in BOILERPLATE_MARKERS:
        position = text.find(marker)
        if position >= 0:
            cut = min(cut, position)
    return text[:cut].strip()


def tokens(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) > 1 and token not in STOPWORDS
    ]


def normalize_text(text: str) -> str:
    return re.sub(r"\W+", " ", text.lower()).strip()


def normalize_column(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def parse_markdown_table(answer: str) -> tuple[list[str], list[list[str]]]:
    lines = [
        line.strip()
        for line in answer.splitlines()
        if line.strip().startswith("|") and line.strip().endswith("|")
    ]
    if len(lines) < 3:
        raise ValueError("answer does not contain a Markdown table")
    cells = [[cell.strip() for cell in line.split("|")[1:-1]] for line in lines]
    header, rows = cells[0], cells[2:]
    if not header or any(len(row) != len(header) for row in rows):
        raise ValueError("inconsistent Markdown table width")
    return header, rows


def validate_record(record: dict) -> tuple[int, int]:
    header, rows = parse_markdown_table(record["answer"])
    if any(not cell for row in rows for cell in row):
        raise ValueError("empty answer cell")
    normalized_header = [normalize_column(column) for column in header]
    unique_columns = [normalize_column(column) for column in record["unique_columns"]]
    if not unique_columns or any(column not in normalized_header for column in unique_columns):
        raise ValueError("unique_columns does not match the answer header")
    indices = [normalized_header.index(column) for column in unique_columns]
    keys = [tuple(normalize_column(row[index]) for index in indices) for row in rows]
    if any(not all(key) for key in keys) or len(set(keys)) != len(keys):
        raise ValueError("empty or duplicate unique key")
    if not (50 <= len(rows) <= 92 and 7 <= len(header) <= 10):
        raise ValueError("table dimensions are outside the frozen selection bounds")
    return len(rows), len(header)


def lexical_audit(train: list[dict], test: list[dict], selected_indices: list[int]) -> dict[int, dict]:
    documents = [tokens(core_question(record["question"])) for record in train]
    document_frequency: collections.Counter[str] = collections.Counter()
    for document in documents:
        document_frequency.update(set(document))
    total = len(documents)
    inverse_document_frequency = {
        token: math.log((total + 1) / (frequency + 1)) + 1
        for token, frequency in document_frequency.items()
        if 2 <= frequency < 0.95 * total
    }

    test_norms: list[float] = []
    inverted_test: dict[str, list[tuple[int, float]]] = collections.defaultdict(list)
    for test_index, record in enumerate(test):
        counts = collections.Counter(
            token for token in tokens(record["query"]) if token in inverse_document_frequency
        )
        vector = {
            token: (1 + math.log(count)) * inverse_document_frequency[token]
            for token, count in counts.items()
        }
        test_norms.append(math.sqrt(sum(weight * weight for weight in vector.values())) or 1.0)
        for token, weight in vector.items():
            inverted_test[token].append((test_index, weight))

    result: dict[int, dict] = {}
    normalized_test_questions = {normalize_text(record["query"]) for record in test}
    for source_index in selected_indices:
        counts = collections.Counter(
            token
            for token in documents[source_index]
            if token in inverse_document_frequency
        )
        vector = {
            token: (1 + math.log(count)) * inverse_document_frequency[token]
            for token, count in counts.items()
        }
        vector_norm = math.sqrt(sum(weight * weight for weight in vector.values())) or 1.0
        dots: dict[int, float] = collections.defaultdict(float)
        for token, weight in vector.items():
            for test_index, test_weight in inverted_test.get(token, ()):
                dots[test_index] += weight * test_weight
        similarity, nearest_index = max(
            (
                (dot / (vector_norm * test_norms[test_index]), test_index)
                for test_index, dot in dots.items()
            ),
            default=(0.0, -1),
        )
        exact_duplicate = normalize_text(train[source_index]["question"]) in normalized_test_questions
        result[source_index] = {
            "exact_normalized_question_duplicate": exact_duplicate,
            "max_lexical_cosine": round(similarity, 6),
            "nearest_test_id": test[nearest_index]["instance_id"] if nearest_index >= 0 else None,
        }
    return result


def download(url: str, destination: Path) -> None:
    print(f"Downloading {url}")
    urllib.request.urlretrieve(url, destination)


def build(train_path: Path, test_path: Path, output_dir: Path) -> None:
    if sha256_file(train_path) != TRAIN_SHA256:
        raise SystemExit(f"Unexpected training-file SHA256: {sha256_file(train_path)}")
    if sha256_file(test_path) != TEST_SHA256:
        raise SystemExit(f"Unexpected test-file SHA256: {sha256_file(test_path)}")

    train = load_jsonl(train_path)
    test = load_jsonl(test_path)
    if len(train) != 20_000 or len(test) != 200:
        raise SystemExit(f"Unexpected row counts: train={len(train)}, test={len(test)}")

    selected_zero_based = [line_number - 1 for line_number, _, _, _ in SELECTIONS]
    audit = lexical_audit(train, test, selected_zero_based)
    output_records: list[dict] = []
    manifest_records: list[dict] = []
    for line_number, pattern, topic, retrieval_burden_basis in SELECTIONS:
        source_index = line_number - 1
        source = train[source_index]
        row_count, column_count = validate_record(source)
        audit_record = audit[source_index]
        if audit_record["exact_normalized_question_duplicate"]:
            raise SystemExit(f"Exact test duplicate detected at source line {line_number}")
        if audit_record["max_lexical_cosine"] >= MAX_LEXICAL_COSINE:
            raise SystemExit(
                f"Lexical threshold exceeded at source line {line_number}: "
                f"{audit_record['max_lexical_cosine']}"
            )
        question_hash = hashlib.sha256(source["question"].encode("utf-8")).hexdigest()
        sample_id = f"wsr1-{question_hash[:12]}"
        output_records.append(
            {
                "sample_id": sample_id,
                "question": source["question"],
                "answer": source["answer"],
                "unique_columns": source["unique_columns"],
            }
        )
        manifest_records.append(
            {
                "sample_id": sample_id,
                "source_line_1_based": line_number,
                "question_sha256": question_hash,
                "topic": topic,
                "decomposition_pattern": pattern,
                "answer_rows": row_count,
                "answer_columns": column_count,
                "answer_cells": row_count * column_count,
                "estimated_retrieval_burden_basis": retrieval_burden_basis,
                **audit_record,
                "review_status": "format_and_plausibility_reviewed_not_exhaustively_fact_checked",
            }
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = output_dir / "wideseek_r1_external20.jsonl"
    manifest_path = output_dir / "wideseek_r1_external20.manifest.json"
    dataset_path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in output_records),
        encoding="utf-8",
    )
    pattern_counts = collections.Counter(
        record["decomposition_pattern"] for record in manifest_records
    )
    manifest = {
        "name": "WideSeek-R1 High-Search External-20 for Web2BigTable skill induction",
        "selection_frozen_before_benchmark_execution": True,
        "selection_uses_benchmark_scores": False,
        "source": {
            "repository": "RLinf/WideSeek-R1-train-data",
            "file": "width_20k.jsonl",
            "revision": TRAIN_REVISION,
            "sha256": TRAIN_SHA256,
            "license": "Apache-2.0",
        },
        "contamination_audit_target": {
            "repository": "RLinf/WideSeek-R1-test-data",
            "file": "test.jsonl",
            "revision": TEST_REVISION,
            "sha256": TEST_SHA256,
            "rows": len(test),
        },
        "selection_rules": {
            "source_answer_rows": "50-92 inclusive",
            "source_answer_columns": "7-10 inclusive",
            "minimum_populated_answer_cells": 350,
            "empty_cells_allowed": False,
            "unique_key_must_be_present_and_unique": True,
            "exact_normalized_test_question_duplicate_allowed": False,
            "maximum_tfidf_lexical_cosine_to_any_test_question": MAX_LEXICAL_COSINE,
            "manual_review": (
                "format, boundedness, ambiguity, estimated retrieval burden, topic diversity, "
                "and semantic test overlap"
            ),
            "high_search_definition": (
                "large reference table plus per-entity enrichment or aggregation across multiple "
                "series; actual web-search calls must be measured during execution"
            ),
        },
        "summary": {
            "records": len(manifest_records),
            "pattern_counts": dict(sorted(pattern_counts.items())),
            "answer_rows_min": min(record["answer_rows"] for record in manifest_records),
            "answer_rows_max": max(record["answer_rows"] for record in manifest_records),
            "answer_columns_min": min(record["answer_columns"] for record in manifest_records),
            "answer_columns_max": max(record["answer_columns"] for record in manifest_records),
            "answer_cells_min": min(record["answer_cells"] for record in manifest_records),
            "answer_cells_max": max(record["answer_cells"] for record in manifest_records),
            "answer_cells_total": sum(record["answer_cells"] for record in manifest_records),
            "maximum_observed_lexical_cosine": max(
                record["max_lexical_cosine"] for record in manifest_records
            ),
        },
        "records": manifest_records,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote {dataset_path}")
    print(f"Wrote {manifest_path}")
    print(json.dumps(manifest["summary"], ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", type=Path, help="Pinned width_20k.jsonl")
    parser.add_argument("--test", type=Path, help="Pinned WideSearch test.jsonl")
    parser.add_argument("--output-dir", type=Path, default=Path("data/revision"))
    args = parser.parse_args()

    if bool(args.train) != bool(args.test):
        parser.error("provide both --train and --test, or neither")
    if args.train and args.test:
        build(args.train, args.test, args.output_dir)
        return
    with tempfile.TemporaryDirectory(prefix="wideseek-r1-external20-") as temporary:
        temporary_path = Path(temporary)
        train_path = temporary_path / "width_20k.jsonl"
        test_path = temporary_path / "test.jsonl"
        download(TRAIN_URL, train_path)
        download(TEST_URL, test_path)
        build(train_path, test_path, args.output_dir)


if __name__ == "__main__":
    main()
