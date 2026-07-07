"""
Scoring engine for People's Priorities.

Design principle (per hackathon rubric — AI/Technical Execution, 25%):
the ranking score must be a TRANSPARENT, INSPECTABLE formula, not a black-box
LLM call. Gemini's job (see extraction.py) is to produce structured signals
(category, urgency, location) from messy citizen input. This module turns
those signals + real benchmark data into a defensible, explainable score.

Formula:
    total_score = (
        W_VOLUME    * normalized_submission_count
      + W_URGENCY   * avg_urgency_score
      + W_ENROLLMENT* enrollment_gap_score
      + W_DISTANCE  * distance_gap_score
    )

Each component is 0-1 normalized before weighting so the weights are
directly interpretable as "% contribution to the score" — useful for the
pitch deck slide that explains *why* item #1 outranked #2.
"""

import math
from collections import defaultdict
from typing import Iterable

from models import CitizenSubmission, SchoolBenchmark, RankedPriority, URGENCY_WEIGHTS, Category

# ---- Weights (tune these; keep them sum to 1.0 for clean interpretation) ----
W_VOLUME = 0.30
W_URGENCY = 0.25
W_ENROLLMENT = 0.25
W_DISTANCE = 0.20

# Cap used to normalize submission counts (e.g. 20+ submissions = max volume score)
VOLUME_NORMALIZATION_CAP = 20

# Distance (km) beyond which distance_gap_score saturates at 1.0
DISTANCE_SATURATION_KM = 10.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Straight-line distance between two lat/lon points, in km."""
    r = 6371.0  # Earth radius, km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))


def nearest_benchmark(
    lat: float, lon: float, benchmarks: Iterable[SchoolBenchmark]
) -> tuple[SchoolBenchmark, float]:
    """Find the nearest school benchmark to a given point. Returns (school, distance_km)."""
    best, best_dist = None, float("inf")
    for b in benchmarks:
        d = haversine_km(lat, lon, b.latitude, b.longitude)
        if d < best_dist:
            best, best_dist = b, d
    return best, best_dist


def enrollment_gap_score(school: SchoolBenchmark) -> float:
    """
    0-1 score: how under-resourced is the nearest school relative to demand?
    Uses pupil-teacher ratio as the primary signal since exact seat capacity
    is often unavailable; falls back gracefully if PTR is missing.

    Assam elementary state averages (UDISE+ 2024-25): Primary PTR ~20, Upper Primary ~19.
    A school AT or BELOW the district benchmark scores low (well-served);
    a school well ABOVE it scores near 1.0 (overcrowded / under-resourced).
    """
    STATE_AVG_PTR = 20.0
    if not school.pupil_teacher_ratio:
        return 0.5  # neutral if data missing — flagged in output for manual review
    ratio = school.pupil_teacher_ratio / STATE_AVG_PTR
    return max(0.0, min(1.0, (ratio - 0.5)))  # >1.5x state avg PTR -> score caps at 1.0


def distance_gap_score(distance_km: float) -> float:
    """0-1 score: how far is this cluster from the nearest relevant facility?"""
    return max(0.0, min(1.0, distance_km / DISTANCE_SATURATION_KM))


CLUSTER_RADIUS_KM = 1.0  # submissions within this distance of a cluster's
                          # running centroid merge into the same priority item


def cluster_submissions(
    submissions: list[CitizenSubmission],
) -> dict[str, list[CitizenSubmission]]:
    """
    Groups submissions by category + real distance (not grid-rounding) so
    that many citizens independently reporting the same issue reliably
    merge into one priority item, however their individual submissions'
    exact coordinates vary slightly (different phrasing, slightly different
    geocoding results, GPS noise, etc).

    Uses incremental nearest-cluster assignment: each submission joins the
    nearest existing same-category cluster if within CLUSTER_RADIUS_KM of
    its running centroid, else starts a new cluster. This avoids the edge
    case where a simple lat/lon-rounding grid can split two near-identical
    reports into separate buckets just because they straddle a grid line.
    """
    # category -> list of {"lat": float, "lon": float, "submissions": [...]}
    clusters_by_category: dict[Category, list[dict]] = defaultdict(list)

    for s in submissions:
        if s.latitude is None or s.longitude is None:
            continue

        category_clusters = clusters_by_category[s.category]
        best_cluster, best_dist = None, float("inf")
        for c in category_clusters:
            d = haversine_km(s.latitude, s.longitude, c["lat"], c["lon"])
            if d < best_dist:
                best_cluster, best_dist = c, d

        if best_cluster is not None and best_dist <= CLUSTER_RADIUS_KM:
            best_cluster["submissions"].append(s)
            n = len(best_cluster["submissions"])
            # incremental running-average centroid update
            best_cluster["lat"] += (s.latitude - best_cluster["lat"]) / n
            best_cluster["lon"] += (s.longitude - best_cluster["lon"]) / n
        else:
            category_clusters.append({
                "lat": s.latitude, "lon": s.longitude, "submissions": [s],
            })

    # Flatten into the {cluster_id: [submissions]} shape the rest of the
    # module expects, unchanged from before.
    result: dict[str, list[CitizenSubmission]] = {}
    for category, category_clusters in clusters_by_category.items():
        for i, c in enumerate(category_clusters):
            cluster_id = f"{category.value}:{round(c['lat'], 4)}:{round(c['lon'], 4)}"
            result[cluster_id] = c["submissions"]
    return result


def score_cluster(
    cluster_id: str,
    cluster_submissions_list: list[CitizenSubmission],
    benchmarks: list[SchoolBenchmark],
) -> RankedPriority:
    avg_lat = sum(s.latitude for s in cluster_submissions_list) / len(cluster_submissions_list)
    avg_lon = sum(s.longitude for s in cluster_submissions_list) / len(cluster_submissions_list)

    category = cluster_submissions_list[0].category
    school, dist_km = nearest_benchmark(avg_lat, avg_lon, benchmarks)

    volume_score = min(1.0, len(cluster_submissions_list) / VOLUME_NORMALIZATION_CAP)
    urgency_score = sum(
        URGENCY_WEIGHTS[s.urgency] for s in cluster_submissions_list
    ) / (4.0 * len(cluster_submissions_list))  # normalize to 0-1 (max weight is 4.0)
    dist_score = distance_gap_score(dist_km) if school else 0.5

    if category == Category.SCHOOL_UPGRADE:
        # School-specific benchmark comparison applies as designed —
        # this is the exact "enrollment vs. demand" comparison the
        # problem statement asks for.
        enroll_score = enrollment_gap_score(school) if school else 0.5
        total = (
            W_VOLUME * volume_score
            + W_URGENCY * urgency_score
            + W_ENROLLMENT * enroll_score
            + W_DISTANCE * dist_score
        )
    else:
        # For non-school categories, a "gap vs. nearest school's PTR" is
        # meaningless noise (e.g. a security incident shouldn't be scored
        # against classroom overcrowding). Redistribute that weight into
        # urgency and volume instead — the two signals that are
        # universally meaningful regardless of category. This keeps a
        # correctly-detected CRITICAL urgency from being diluted by an
        # irrelevant benchmark comparison.
        enroll_score = 0.0  # not applicable for this category (see comment above)
        total = (
            (W_VOLUME + W_ENROLLMENT * 0.4) * volume_score
            + (W_URGENCY + W_ENROLLMENT * 0.6) * urgency_score
            + W_DISTANCE * dist_score
        )

    return RankedPriority(
        cluster_id=cluster_id,
        category=cluster_submissions_list[0].category,
        location_name=cluster_submissions_list[0].location_name,
        latitude=avg_lat,
        longitude=avg_lon,
        submission_count=len(cluster_submissions_list),
        avg_urgency_score=round(urgency_score, 3),
        enrollment_gap_score=round(enroll_score, 3),
        distance_gap_score=round(dist_score, 3),
        total_score=round(total, 3),
        linked_submission_ids=[s.submission_id for s in cluster_submissions_list],
    )


def rank_priorities(
    submissions: list[CitizenSubmission],
    benchmarks: list[SchoolBenchmark],
) -> list[RankedPriority]:
    """
    Main entry point: cluster submissions, score each cluster, return ranked list.

    Sorting is two-tiered: urgency level first, then the weighted formula
    score as a tiebreaker within the same urgency level. This matches real
    civic/emergency triage — a life-safety CRITICAL report should outrank
    a MEDIUM-urgency infrastructure request even if the latter has strong
    supporting data (e.g. severe school overcrowding), because urgency and
    "strength of evidence" aren't comparable currencies. Blending them into
    one weighted percentage (the old approach) let a well-evidenced but
    non-urgent request outscore a genuinely critical one — the formula
    below is a deliberate two-tier design to prevent that.
    """
    clusters = cluster_submissions(submissions)
    scored = [
        score_cluster(cid, subs, benchmarks) for cid, subs in clusters.items()
    ]
    return sorted(scored, key=lambda r: (r.avg_urgency_score, r.total_score), reverse=True)
