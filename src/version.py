"""Version identifiers.

Document 03 §34 requires several independently tracked versions. Only the
versions that exist at the current build stage are defined here; exercise
specification and algorithm versions arrive with Build 5 (STS-001).
"""

APPLICATION_VERSION = "0.1.0"
"""Version of the application as a whole."""

POSE_STREAM_FORMAT_VERSION = "0.2"
"""Version of the recorded canonical pose-stream file format.

0.2 added `measured_fps` to the metadata record. Readers tolerate its absence,
so 0.1 recordings still replay; they simply carry no trustworthy frame rate.
"""
