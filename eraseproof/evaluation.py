"""Internal completion-trusting baseline and counts from actually observed scenario runs."""


def summarize(cases: list[dict]) -> dict:
    positives = {"FALSE_SUCCESS_DETECTED", "RESIDUAL_DATA_DETECTED"}
    return {
        "scenarios_executed": len(cases),
        "true_residual_cases": sum(c["ground_truth_residual"] is True for c in cases),
        "residual_cases_detected": sum(
            c["ground_truth_residual"] is True and c["result"] in positives for c in cases
        ),
        "false_positives": sum(
            c["ground_truth_residual"] is False and c["result"] in positives for c in cases
        ),
        "inconclusive_outcomes": sum(c["result"] == "INCONCLUSIVE" for c in cases),
        "unsupported_outcomes": sum(c["result"] == "UNSUPPORTED" for c in cases),
        "total_independent_probe_queries": sum(c["probe_queries"] for c in cases),
        "independently_checked_targets": sorted({t for c in cases for t in c["checked_targets"]}),
        "internal_completion_trusting_baseline": {
            "definition": "COMPLETED_REPORTED is treated as success without data queries; not a commercial comparison",
            "success_claims": sum(c["reported_state"] == "COMPLETED_REPORTED" for c in cases),
            "missed_residual_cases": sum(
                c["reported_state"] == "COMPLETED_REPORTED" and c["ground_truth_residual"] is True
                for c in cases
            ),
            "independent_probe_queries": 0,
        },
        "limitations": "Small synthetic controlled-fault cases; measured wall time includes scheduling/consistency delays. Probe commands exclude coordination, transport and evidence queries. Not an accuracy or throughput benchmark.",
    }
