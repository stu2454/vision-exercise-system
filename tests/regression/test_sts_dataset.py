"""STS-001 against the regression dataset.

The check that stops an algorithm change being judged by a single successful
demonstration (Document 03 §29). It runs the real recordings when they are
present and skips when they are not, because recordings are movement data and
may be kept outside the repository.

The assertions are deliberately asymmetric. A false repetition fails; a
conservative miss does not. Detecting a repetition the participant did not
perform is the worse error (Document 03 §49, CLAUDE.md §21).
"""

from __future__ import annotations

import pytest

from src.evaluation import (
    DEFAULT_SEARCH_PATHS,
    evaluate_dataset,
    find_recording,
    load_cases,
)

MINIMUM_COUNT_ACCURACY = 93.0
"""Floor, not a target.

The engineering target of 95% (Document 03 §49) is currently met, at 95.6%
across 45 repetitions with no false positives. The floor sits below that so
an improvement raises it deliberately, rather than a regression sliding under
it unnoticed. One further miss would cost roughly 2.2 percentage points, so
this permits one and no more.

Both remaining misses are calibration repetitions in recordings made before
the start gesture existed. Neither gesture-delimited recording loses any.

The figure still describes four takes by one participant. Meeting a target on
this dataset is not evidence the algorithm is good, only that it has not got
worse on what has been recorded so far.
"""


@pytest.fixture(scope="module")
def dataset():
    cases = load_cases()
    if not cases:
        pytest.skip("no regression cases defined")
    available = [c for c in cases if find_recording(c) is not None]
    if not available:
        pytest.skip(
            "no regression recordings available; place pose streams in "
            "test_data/pose/ or recordings/"
        )
    report, _ = evaluate_dataset(available)
    return report


class TestDatasetIntegrity:
    def test_every_case_declares_ground_truth(self):
        for case in load_cases():
            assert case.true_repetitions > 0, f"{case.case_id} has no ground truth"

    def test_case_ids_are_unique(self):
        ids = [c.case_id for c in load_cases()]
        assert len(ids) == len(set(ids))

    def test_every_case_records_the_camera_view(self):
        # Camera placement is an open experimental variable; a case that does
        # not say where the camera was cannot take part in a comparison.
        for case in load_cases():
            assert case.camera_view != "unspecified", case.case_id


class TestErrorProfile:
    def test_no_false_repetitions(self, dataset):
        offenders = [
            o.case.case_id for o in dataset.outcomes if o.false_positives
        ]
        assert not offenders, f"false repetitions detected in {offenders}"

    def test_count_accuracy_holds(self, dataset):
        assert dataset.count_accuracy >= MINIMUM_COUNT_ACCURACY, (
            f"count agreement fell to {dataset.count_accuracy:.1f}%"
        )

    def test_no_case_is_wildly_wrong(self, dataset):
        # A single case losing more than two repetitions means something
        # structural, not a boundary effect.
        for outcome in dataset.outcomes:
            assert outcome.missed <= 2, f"{outcome.case.case_id} missed {outcome.missed}"

    def test_partial_repetitions_are_not_invented(self, dataset):
        for outcome in dataset.outcomes:
            assert (
                outcome.scored.result.partial_repetitions
                <= outcome.case.partial_repetitions + 1
            ), outcome.case.case_id


class TestReproducibility:
    def test_scoring_twice_gives_the_same_answer(self):
        # The whole basis of replay: the same recording must always produce
        # the same result (ADR-008).
        cases = [c for c in load_cases() if find_recording(c) is not None]
        if not cases:
            pytest.skip("no regression recordings available")
        first, _ = evaluate_dataset(cases[:1])
        second, _ = evaluate_dataset(cases[:1])
        assert first.to_dict()["outcomes"][0]["detected"] == (
            second.to_dict()["outcomes"][0]["detected"]
        )
        assert first.count_accuracy == second.count_accuracy


class TestPerformance:
    def test_processing_is_fast_enough_for_live_use(self, dataset):
        # Excludes pose inference, which dominates. This is the cost of
        # filtering, features, quality and the state machine, and it must
        # stay small against a 33 ms frame budget.
        assert dataset.mean_processing_ms < 5.0, (
            f"{dataset.mean_processing_ms:.2f} ms/frame downstream of pose"
        )
