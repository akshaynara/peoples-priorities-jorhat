"""
Smoke test — proves the scoring engine works end-to-end WITHOUT needing
Gemini/Maps API keys. Run this first, today, before wiring up live APIs.

    python test_scoring_smoke.py
"""

import uuid
from datetime import datetime

from models import CitizenSubmission, Category, Urgency, SubmissionChannel
from benchmark_data import load_benchmarks, _JORHAT_CENTER_LAT, _JORHAT_CENTER_LON
from scoring import rank_priorities


def fake_submission(category, urgency, lat_offset, lon_offset, location_name):
    return CitizenSubmission(
        submission_id=str(uuid.uuid4()),
        raw_text="(synthetic seed submission for demo)",
        language="en",
        channel=SubmissionChannel.TEXT,
        category=category,
        urgency=urgency,
        summary=f"Request related to {category.value} near {location_name}",
        location_name=location_name,
        latitude=_JORHAT_CENTER_LAT + lat_offset,
        longitude=_JORHAT_CENTER_LON + lon_offset,
        submitted_at=datetime.utcnow(),
    )


def build_seed_submissions() -> list[CitizenSubmission]:
    """
    15 synthetic submissions clustered around real school locations from
    benchmark_data.py, mixing urgency levels. This is what you seed the
    dashboard with for Day 4 (per the original plan) so it looks alive.
    """
    subs = []

    # Cluster 1: near Rebakanta Baruah P. Boys HS (overcrowded, PTR 35.8)
    # -> should rank #1: high enrollment gap + several submissions
    for i in range(6):
        subs.append(fake_submission(
            Category.SCHOOL_UPGRADE,
            Urgency.HIGH if i % 2 == 0 else Urgency.CRITICAL,
            0.06, 0.05, "North West Jorhat"
        ))

    # Cluster 2: near Kunwari Pukhuri H.S. (PTR 28.4)
    for i in range(4):
        subs.append(fake_submission(
            Category.SCHOOL_UPGRADE,
            Urgency.MEDIUM,
            0.03, -0.02, "Kunwari Pukhuri area"
        ))

    # Cluster 3: low-urgency, low-volume — should rank near the bottom
    for i in range(2):
        subs.append(fake_submission(
            Category.SCHOOL_UPGRADE,
            Urgency.LOW,
            -0.015, -0.01, "Near St. Mary's"
        ))

    # Cluster 4: different category entirely, to prove clustering separates by category
    for i in range(3):
        subs.append(fake_submission(
            Category.ROAD_INFRASTRUCTURE,
            Urgency.HIGH,
            0.01, 0.01, "Jorhat town center"
        ))

    return subs


if __name__ == "__main__":
    submissions = build_seed_submissions()
    benchmarks = load_benchmarks()

    ranked = rank_priorities(submissions, benchmarks)

    print(f"\n{'='*70}\nRANKED PRIORITIES — Jorhat Constituency (smoke test)\n{'='*70}\n")
    for i, r in enumerate(ranked, 1):
        print(f"#{i}  [{r.category.value}]  {r.location_name}")
        print(f"     Score: {r.total_score}  |  Submissions: {r.submission_count}")
        print(f"     Breakdown -> urgency: {r.avg_urgency_score}, "
              f"enrollment_gap: {r.enrollment_gap_score}, "
              f"distance_gap: {r.distance_gap_score}")
        print()

    assert len(ranked) > 0, "No ranked priorities produced — check clustering logic"
    assert ranked[0].total_score >= ranked[-1].total_score, "Ranking order is broken"
    print("✅ Smoke test passed: scoring pipeline runs end-to-end and produces a valid ranking.\n")
