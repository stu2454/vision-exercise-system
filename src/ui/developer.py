"""Developer overlay (Document 03 §44, CLAUDE.md §26).

Developer mode may be ugly. It must make algorithm behaviour legible: what the
pose engine saw, how much it is trusted, how fast the loop is running, and
whether anything is being recorded.

Everything drawn here is derived from canonical landmark *names*. No pose-
engine landmark index appears in this module, so the overlay keeps working
unchanged if the pose engine is replaced.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import cv2
import numpy as np

from src.pose.models import CANONICAL_CONNECTIONS, PoseFrame
from src.pose.quality import PoseQualityReport, PoseQualityStatus

_FONT = cv2.FONT_HERSHEY_SIMPLEX

_STATUS_COLOURS: dict[PoseQualityStatus, tuple[int, int, int]] = {
    PoseQualityStatus.GOOD: (80, 200, 80),
    PoseQualityStatus.DEGRADED: (40, 190, 240),
    PoseQualityStatus.INSUFFICIENT: (60, 60, 235),
}

_HIGH_CONFIDENCE = (80, 220, 120)
_MEDIUM_CONFIDENCE = (40, 190, 240)
_LOW_CONFIDENCE = (70, 70, 235)


@dataclass
class DeveloperHud:
    """Values shown on the developer heads-up display.

    Attributes:
        mode: What the sandbox is currently doing, e.g. "LIVE" or "REPLAY".
        source_label: Provenance of the current frame.
        frame_index: Index of the current frame within the source.
        timestamp_ms: Source timestamp of the current frame.
        fps: Measured end-to-end loop rate, if known.
        inference_ms: Mean pose inference time, if known.
        recording_video: Whether video is being written.
        recording_pose: Whether a pose stream is being written.
        recording_id: Identifier of the current recording, if any.
        recorded_frames: Pose frames written so far.
        show_skeleton: Whether the skeleton overlay is enabled.
        message: Transient developer message, e.g. "recording saved".
    """

    mode: str = "LIVE"
    source_label: str = ""
    frame_index: int = 0
    timestamp_ms: float = 0.0
    fps: Optional[float] = None
    inference_ms: Optional[float] = None
    recording_video: bool = False
    recording_pose: bool = False
    recording_id: str = ""
    recorded_frames: int = 0
    show_skeleton: bool = True
    message: str = ""


def confidence_colour(confidence: float) -> tuple[int, int, int]:
    """BGR colour encoding how much a landmark is trusted."""
    if confidence >= 0.60:
        return _HIGH_CONFIDENCE
    if confidence >= 0.30:
        return _MEDIUM_CONFIDENCE
    return _LOW_CONFIDENCE


def draw_skeleton(image: np.ndarray, pose: PoseFrame) -> None:
    """Draw canonical landmarks and connections onto `image` in place."""
    if not pose.has_person:
        return
    height, width = image.shape[:2]

    def to_pixels(name: str) -> Optional[tuple[int, int]]:
        landmark = pose.get(name)
        if landmark is None:
            return None
        return int(landmark.x * width), int(landmark.y * height)

    for start_name, end_name in CANONICAL_CONNECTIONS:
        start = to_pixels(start_name)
        end = to_pixels(end_name)
        if start is None or end is None:
            continue
        start_landmark = pose.landmarks[start_name]
        end_landmark = pose.landmarks[end_name]
        colour = confidence_colour(
            min(start_landmark.confidence, end_landmark.confidence)
        )
        cv2.line(image, start, end, colour, 2, cv2.LINE_AA)

    for name, landmark in pose.landmarks.items():
        point = to_pixels(name)
        if point is None:
            continue
        cv2.circle(image, point, 4, confidence_colour(landmark.confidence), -1, cv2.LINE_AA)


def _draw_text_block(
    image: np.ndarray, lines: Sequence[tuple[str, tuple[int, int, int]]]
) -> None:
    """Draw a translucent panel of coloured text lines at the top left."""
    if not lines:
        return
    line_height = 20
    padding = 8
    panel_height = padding * 2 + line_height * len(lines)
    panel_width = 330
    overlay = image.copy()
    cv2.rectangle(overlay, (0, 0), (panel_width, panel_height), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.55, image, 0.45, 0, image)
    for row, (text, colour) in enumerate(lines):
        y = padding + line_height * (row + 1) - 5
        cv2.putText(
            image, text, (padding, y), _FONT, 0.5, colour, 1, cv2.LINE_AA
        )


def _format_optional(value: Optional[float], suffix: str, digits: int = 1) -> str:
    return "—" if value is None else f"{value:.{digits}f}{suffix}"


def draw_developer_overlay(
    image: np.ndarray,
    pose: PoseFrame,
    quality: Optional[PoseQualityReport],
    hud: DeveloperHud,
) -> np.ndarray:
    """Return a copy of `image` annotated with pose and diagnostics.

    The input image is not modified, so the frame written to a video recording
    stays free of overlay graphics.
    """
    annotated = image.copy()
    if hud.show_skeleton:
        draw_skeleton(annotated, pose)

    white = (240, 240, 240)
    grey = (170, 170, 170)
    status = quality.status if quality else PoseQualityStatus.INSUFFICIENT
    status_colour = _STATUS_COLOURS[status]

    lines: list[tuple[str, tuple[int, int, int]]] = [
        (f"{hud.mode}  {hud.source_label}", white),
        (
            f"frame {hud.frame_index}   t {hud.timestamp_ms / 1000.0:6.2f}s   "
            f"fps {_format_optional(hud.fps, '')}",
            white,
        ),
        (f"pose inference  {_format_optional(hud.inference_ms, ' ms')}", white),
        (f"pose quality    {status.value}", status_colour),
    ]

    if quality is not None:
        lines.append(
            (
                f"person conf {pose.person_confidence:.2f}   "
                f"required conf {quality.confidence:.2f}",
                grey,
            )
        )
        if quality.instantaneous_status is not quality.status:
            lines.append(
                (f"instantaneous   {quality.instantaneous_status.value}", grey)
            )
        if quality.reasons:
            lines.append((", ".join(quality.reasons)[:44], status_colour))
        problem_landmarks = (
            quality.missing_required + quality.low_confidence + quality.clipped
        )
        if problem_landmarks:
            lines.append((", ".join(sorted(set(problem_landmarks)))[:44], grey))

    if hud.recording_pose or hud.recording_video:
        targets = []
        if hud.recording_video:
            targets.append("video")
        if hud.recording_pose:
            targets.append("pose")
        lines.append(
            (
                f"REC {'+'.join(targets)}  {hud.recording_id}  "
                f"{hud.recorded_frames} frames",
                (60, 60, 235),
            )
        )
    if hud.message:
        lines.append((hud.message[:44], (40, 190, 240)))

    _draw_text_block(annotated, lines)

    if hud.recording_video or hud.recording_pose:
        cv2.circle(annotated, (annotated.shape[1] - 26, 26), 10, (60, 60, 235), -1)
        cv2.putText(
            annotated,
            "REC",
            (annotated.shape[1] - 76, 32),
            _FONT,
            0.6,
            (60, 60, 235),
            2,
            cv2.LINE_AA,
        )

    return annotated
