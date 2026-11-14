from statistics import mean


def summarize(rows: list[dict]) -> dict:
    def rate(key: str) -> float:
        return mean(bool(row.get(key)) for row in rows)

    def mean_of(key: str) -> float | None:
        values = [row[key] for row in rows if row.get(key) is not None]
        return mean(values) if values else None

    unavailable = [row for row in rows if row.get("unavailable_expected")]
    simulated = [row for row in rows if row.get("simulated_expected")]
    valid = [row for row in rows if row.get("schema_valid")]
    supported = sum(row.get("supported_claims", 0) for row in rows)
    exact = sum(row.get("exact_quote_claims", 0) for row in rows)
    return {
        "examples": len(rows),
        "json_valid_rate": rate("json_valid"),
        "raw_contract_valid_rate": rate("raw_contract_valid"),
        "normalization_changed_rate": rate("normalization_changed"),
        "schema_valid_rate": rate("schema_valid"),
        "schema_valid_examples": len(valid),
        "scope_accuracy": rate("out_of_scope_correct"),
        "guarded_scope_accuracy": rate("guarded_out_of_scope_correct"),
        "mean_status_recall": mean_of("status_recall"),
        "mean_status_precision": mean_of("status_precision"),
        "exact_status_rate": rate("statuses_exact"),
        "guarded_mean_status_recall": mean_of("guarded_status_recall"),
        "unavailable_presence_rate": (
            mean(bool(row.get("unavailable_present")) for row in unavailable)
            if unavailable else None
        ),
        "guarded_unavailable_presence_rate": (
            mean(bool(row.get("guarded_unavailable_present")) for row in unavailable)
            if unavailable else None
        ),
        "relevance_failure_rate": rate("relevance_failures"),
        "scope_guard_failure_rate": rate("scope_guard_failures"),
        "simulated_presence_rate": (
            mean(bool(row.get("simulated_present")) for row in simulated) if simulated else None
        ),
        "citation_failure_rate": (
            mean(bool(row["citation_failures"]) for row in valid) if valid else None
        ),
        "raw_behavior_pass_rate": rate("raw_behavior_pass"),
        "summary_review_rate": rate("summary_requires_review"),
        "provider_fallbacks": sum(bool(row.get("provider_fallback")) for row in rows),
        "mean_validation_failures": mean_of("validation_failures"),
        "mean_guarded_validation_failures": mean_of("guarded_validation_failures"),
        "exact_quote_rate": exact / supported if supported else None,
        "memory_citation_violations": sum(row.get("supported_fact_on_memory", 0) for row in rows),
        "mean_output_tokens": mean_of("output_tokens"),
        "mean_seconds": mean_of("seconds"),
    }
