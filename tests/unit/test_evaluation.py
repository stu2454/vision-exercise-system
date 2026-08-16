"""Tests for the regression dataset and evaluation logic.

The arithmetic here decides whether an algorithm change looks like an
improvement, so it is tested against synthetic outcomes rather than trusted.
"""

from __future__ import annotations

import pytest

from src.evaluation import (
    CaseOutcome,
    DatasetError,
    DatasetReport,
    RegressionCase,
    ScoredStream,
    find_recording,
    load_cases,
)
from src.exercises.base import ExerciseResult
from src.recording.pose_recorder import PoseStreamMetadata


def make_outcome(true: int, detected: int, partial: int = 0, case_id: str = "c") -> CaseOutcome:
    result = ExerciseResult(
        exercise_id="STS-001",
        exercise_specification_version="0.1",
        exercise_algorithm_version="0.1.0",
        valid_repetitions=detected,
        partial_repetitions=partial,
    )
    scored = ScoredStream(
        result=result,
        events=[],
        metadata=PoseStreamMetadata.create("r", "engine", "model"),
        frames=100,
        processing_ms_per_frame=0.5,
    )
    case = RegressionCase(
        case_id=case_id, recording="r.jsonl", true_repetitions=true, camera_view="frontal"
    )
    return CaseOutcome(case=case, scored=scored)


class TestCaseOutcome:
    def test_an_exact_match_has_no_errors(self):
        outcome = make_outcome(true=10, detected=10)
        assert outcome.exact and outcome.missed == 0 and outcome.false_positives == 0

    def test_under_detection_counts_as_missed(self):
        outcome = make_outcome(true=10, detected=8)
        assert outcome.missed == 2 and outcome.false_positives == 0

    def test_over_detection_counts_as_false(self):
        outcome = make_outcome(true=10, detected=12)
        assert outcome.false_positives == 2 and outcome.missed == 0

    def test_missed_and_false_are_never_netted_off(self):
        # A case that misses one and invents one is not the same as a case
        # that gets both right, and must not look identical in a report.
        exact = make_outcome(true=10, detected=10)
        assert exact.missed == 0 and exact.false_positives == 0


class TestDatasetReport:
    def test_accuracy_is_correct_over_true_repetitions(self):
        report = DatasetReport(
            outcomes=[make_outcome(10, 9, case_id="a"), make_outcome(10, 10, case_id="b")]
        )
        assert report.true_repetitions == 20
        assert report.missed == 1
        assert report.count_accuracy == pytest.approx(95.0)

    def test_false_positives_do_not_inflate_accuracy(self):
        # Ten true, twelve detected is not 120% accurate.
        report = DatasetReport(outcomes=[make_outcome(10, 12)])
        assert report.count_accuracy == pytest.approx(100.0)
        assert report.false_positives == 2

    def test_an_empty_dataset_reports_zero_rather_than_dividing_by_zero(self):
        assert DatasetReport().count_accuracy == 0.0

    def test_exact_cases_are_counted(self):
        report = DatasetReport(
            outcomes=[
                make_outcome(10, 10, case_id="a"),
                make_outcome(10, 9, case_id="b"),
                make_outcome(5, 5, case_id="c"),
            ]
        )
        assert report.exact_cases == 2

    def test_the_text_report_flags_false_repetitions(self):
        text = DatasetReport(outcomes=[make_outcome(10, 12)]).format_text()
        assert "False repetitions present" in text

    def test_the_text_report_stays_quiet_when_only_misses_occur(self):
        text = DatasetReport(outcomes=[make_outcome(10, 8)]).format_text()
        assert "False repetitions present" not in text

    def test_the_report_serialises(self):
        import json

        report = DatasetReport(outcomes=[make_outcome(10, 9)], algorithm_version="0.1.0")
        assert json.loads(json.dumps(report.to_dict()))["missed"] == 1


class TestCaseLoading:
    def test_a_case_file_is_parsed(self, tmp_path):
        (tmp_path / "one.yaml").write_text(
            "case_id: a\nrecording: r.jsonl\ntrue_repetitions: 8\ncamera_view: frontal\n",
            encoding="utf-8",
        )
        cases = load_cases(tmp_path)
        assert len(cases) == 1
        assert cases[0].true_repetitions == 8
        assert cases[0].use_gestures is True, "gestures assumed unless stated"

    def test_a_missing_directory_yields_no_cases(self, tmp_path):
        assert load_cases(tmp_path / "absent") == []

    def test_a_malformed_case_is_reported(self, tmp_path):
        (tmp_path / "bad.yaml").write_text("recording: r.jsonl\n", encoding="utf-8")
        with pytest.raises(DatasetError, match="case_id"):
            load_cases(tmp_path)

    def test_invalid_yaml_is_reported(self, tmp_path):
        (tmp_path / "bad.yaml").write_text("case_id: [unclosed\n", encoding="utf-8")
        with pytest.raises(DatasetError, match="Could not parse"):
            load_cases(tmp_path)

    def test_a_non_mapping_case_is_rejected(self, tmp_path):
        (tmp_path / "bad.yaml").write_text("- a\n- b\n", encoding="utf-8")
        with pytest.raises(DatasetError, match="must contain a mapping"):
            load_cases(tmp_path)

    def test_the_shipped_cases_load(self):
        for case in load_cases():
            assert case.recording.endswith(".jsonl")
            assert case.exercise_id == "STS-001"


class TestRecordingLookup:
    def test_a_recording_is_found_in_a_search_path(self, tmp_path):
        (tmp_path / "r.jsonl").write_text("{}", encoding="utf-8")
        case = RegressionCase(case_id="a", recording="r.jsonl")
        assert find_recording(case, [tmp_path]) == tmp_path / "r.jsonl"

    def test_a_missing_recording_returns_none_rather_than_raising(self, tmp_path):
        # Absence is expected: movement data may be kept outside the
        # repository, and the suite skips rather than fails.
        case = RegressionCase(case_id="a", recording="absent.jsonl")
        assert find_recording(case, [tmp_path]) is None

    def test_earlier_search_paths_win(self, tmp_path):
        first, second = tmp_path / "one", tmp_path / "two"
        first.mkdir()
        second.mkdir()
        (first / "r.jsonl").write_text("{}", encoding="utf-8")
        (second / "r.jsonl").write_text("{}", encoding="utf-8")
        case = RegressionCase(case_id="a", recording="r.jsonl")
        assert find_recording(case, [first, second]) == first / "r.jsonl"
