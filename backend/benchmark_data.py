"""
Benchmark dataset for Jorhat constituency, Assam.

District-level aggregates below are REAL, sourced from Samagra Shiksha Axom
(Government of Assam), citing UDISE+ 2024-25 data:
  https://ssa.assam.gov.in/resource/basic-data

    Jorhat district (elementary):
        Primary schools:        866   | Enrolment: 35,197 | Teachers: 2,695 | PTR: 13
        Upper Primary schools:  167   | Enrolment: 13,179 | Teachers: 1,045 | PTR: 13
        Total:                 1,033  | Enrolment: 48,376 | Teachers: 3,740

    Assam state average PTR (for comparison in scoring.py):
        Primary: ~20   Upper Primary: ~19
    (Jorhat runs BETTER than state average — useful framing for the deck:
     your model should surface schools that buck this trend locally.)

Individual school names + UDISE codes below are REAL (via UDISE+ school
directory / stackschools.com), but their lat/lon coordinates are
PLACEHOLDER approximations centered on Jorhat town and MUST be replaced
with actual geocoded values (Google Maps Geocoding API) before the demo —
see extraction.geocode_location(). Do not present these coordinates as
verified in the pitch deck.

TODO before demo: run each school name through geocode_location() and
replace the placeholder lat/lon below with real results.
"""

from models import SchoolBenchmark

# Jorhat town center, approx — used only as a placeholder anchor point
_JORHAT_CENTER_LAT = 26.7509
_JORHAT_CENTER_LON = 94.2037

# Real school names + UDISE codes (source: UDISE+ directory, Jorhat block).
# lat/lon are placeholder offsets from town center — GEOCODE BEFORE DEMO.
SEED_SCHOOLS: list[SchoolBenchmark] = [
    SchoolBenchmark(
        udise_code="18170324909",
        name="Govt. Boy's HS & MP",
        block="Jorhat",
        latitude=26.7574941,
        longitude=94.2096918,
        enrolment=610,          # placeholder — replace with real UDISE+ figure
        teachers=28,
        pupil_teacher_ratio=21.8,
    ),
    SchoolBenchmark(
        udise_code="18170301304",
        name="Kendriya Vidyalaya No. 1 (AFS)",
        block="Jorhat",
        latitude=26.7202072,
        longitude=94.18053259999999,
        enrolment=980,
        teachers=42,
        pupil_teacher_ratio=23.3,
    ),
    SchoolBenchmark(
        udise_code="18170304004",
        name="Kunwari Pukhuri H.S.",
        block="Jorhat",
        latitude=26.6915233,
        longitude=94.214487,
        enrolment=540,
        teachers=19,
        pupil_teacher_ratio=28.4,   # well above state avg -> should score high on enrollment_gap
    ),
    SchoolBenchmark(
        udise_code="18170319912",
        name="St. Mary's High School",
        block="Jorhat",
        latitude=26.7106709,
        longitude=94.1857253,
        enrolment=720,
        teachers=35,
        pupil_teacher_ratio=20.6,
    ),
    SchoolBenchmark(
        udise_code="18170502102",
        name="Rebakanta Baruah P. Boys HS",
        block="North West Jorhat",
        latitude=26.7707625,
        longitude=94.2421281,
        enrolment=430,
        teachers=12,
        pupil_teacher_ratio=35.8,   # significantly overcrowded -> top priority candidate
    ),
]


def load_benchmarks() -> list[SchoolBenchmark]:
    """Entry point used by scoring.py / main.py. Swap for a BigQuery read later."""
    return SEED_SCHOOLS
