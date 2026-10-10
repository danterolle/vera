from vera.evaluation.runner import run_evaluation


def test_controlled_evaluation_passes(settings) -> None:
    report = run_evaluation(settings)
    assert report.passed
    assert report.routing_accuracy == 1.0
    assert report.retrieval_success_rate == 1.0
    assert report.detector_accuracy == 1.0
    assert report.grounding_rate == 1.0
    assert report.unsupported_claims == 0
    assert report.total_model_calls == 0
    assert report.total_tool_calls == 0
