"""
Cloud Run entrypoint for People's Priorities backend.

Runs fully in DEMO_MODE (zero API keys) today; automatically switches to
live Gemini + Maps once GEMINI_API_KEY / GOOGLE_MAPS_API_KEY are exported.
See config.py for the detection logic.

Endpoints:
  POST /submit    -> intake a citizen submission
  GET  /rankings  -> return current ranked priorities
  GET  /status    -> demo mode status + submission count (handy for judges/debug)
  GET  /health    -> liveness check
"""

import uuid
from datetime import datetime

from flask import Flask, request, jsonify

from config import DEMO_MODE, GEMINI_LIVE, MAPS_LIVE
from models import CitizenSubmission, SubmissionChannel, Category
from extraction import extract_submission_fields, extract_from_photo, geocode_location, generate_priority_memo
from scoring import rank_priorities
from benchmark_data import load_benchmarks

app = Flask(__name__)


@app.after_request
def add_cors_headers(response):
    """
    Manual CORS (no flask-cors dependency needed) so the frontend — served
    separately via Firebase Hosting or opened as a local file — can call
    this API directly.
    """
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


@app.route("/submit", methods=["OPTIONS"])
@app.route("/rankings", methods=["OPTIONS"])
def cors_preflight():
    return "", 204

# --- Prototype in-memory store. Swap for Firestore before final deploy. ---
# from google.cloud import firestore
# db = firestore.Client()
# See firestore_store.py for a drop-in replacement with the same interface.
SUBMISSIONS: list[CitizenSubmission] = []


@app.route("/submit", methods=["POST"])
def submit():
    """
    Body: { "text": "...", "channel": "text" | "voice" | "sms" | "whatsapp",
            "photo_base64": "..." (optional), "photo_mime_type": "..." (optional) }

    Text-only submissions work as before. If photo_base64 is present, the
    photo is analyzed directly via Gemini's multimodal vision (with any
    accompanying text as supporting context) — this is what lets a citizen
    submit just a photo of a pothole or damaged classroom with no text at
    all, directly answering the problem statement's explicit call for
    photo intake alongside voice/text.

    For voice, the client runs Speech-to-Text (or browser Web Speech API in
    demo mode) BEFORE hitting this endpoint, and sends the transcript as `text`.
    """
    body = request.get_json(force=True)
    raw_text = body.get("text", "").strip()
    channel = SubmissionChannel(body.get("channel", "text"))
    photo_base64 = body.get("photo_base64", "")
    photo_mime_type = body.get("photo_mime_type", "image/jpeg")

    if not raw_text and not photo_base64:
        return jsonify({"error": "text or photo is required"}), 400

    try:
        if photo_base64:
            extracted = extract_from_photo(photo_base64, photo_mime_type, text_hint=raw_text)
        else:
            extracted = extract_submission_fields(raw_text, channel)
    except Exception as e:
        # Most common cause: Gemini free-tier rate limit hit during rapid
        # testing/seeding. Return clean JSON instead of crashing, so callers
        # (like seed_data.py) can detect and retry.
        return jsonify({
            "error": "extraction_failed",
            "detail": str(e),
            "hint": "Often a Gemini rate limit. Wait a few seconds and retry.",
        }), 503

    try:
        coords = geocode_location(extracted["location_name"])
    except Exception as e:
        return jsonify({"error": "geocoding_failed", "detail": str(e)}), 503

    lat, lon = coords if coords else (None, None)

    submission = CitizenSubmission(
        submission_id=str(uuid.uuid4()),
        raw_text=raw_text or "(photo submission)",
        language=extracted["language"],
        channel=channel,
        category=extracted["category"],
        urgency=extracted["urgency"],
        summary=extracted["summary"],
        location_name=extracted["location_name"],
        latitude=lat,
        longitude=lon,
        has_photo=bool(photo_base64),
        submitted_at=datetime.utcnow(),
    )

    if lat is None:
        return jsonify({
            "submission_id": submission.submission_id,
            "warning": "location could not be resolved; flagged for manual review",
            "extracted": {**extracted, "category": extracted["category"].value,
                          "urgency": extracted["urgency"].value},
        }), 202

    SUBMISSIONS.append(submission)
    return jsonify({
        "submission_id": submission.submission_id,
        "extracted": {**extracted, "category": extracted["category"].value,
                      "urgency": extracted["urgency"].value},
        "location": {"lat": lat, "lon": lon},
        "demo_mode": DEMO_MODE,
    }), 201


@app.route("/rankings", methods=["GET"])
def rankings():
    benchmarks = load_benchmarks()
    ranked = rank_priorities(SUBMISSIONS, benchmarks)
    return jsonify([
        {
            "cluster_id": r.cluster_id,
            "category": r.category.value,
            "location_name": r.location_name,
            "latitude": r.latitude,
            "longitude": r.longitude,
            "submission_count": r.submission_count,
            "total_score": r.total_score,
            "score_breakdown": {
                "urgency": r.avg_urgency_score,
                "enrollment_gap": r.enrollment_gap_score,
                "distance_gap": r.distance_gap_score,
            },
            "ai_justification": r.ai_justification,
        }
        for r in ranked
    ])


@app.route("/generate_memo", methods=["POST", "OPTIONS"])
def generate_memo():
    """
    Body: { "cluster_id": "..." } — matches a cluster_id from the current
    /rankings response. Re-runs ranking (clusters aren't persisted with
    stable IDs between requests, consistent with the rest of this
    prototype's in-memory design) and generates a formal action memo for
    the matching priority using Gemini.

    This turns the ranked list from something a human has to interpret
    into something an MP's office could immediately forward to the
    relevant department.
    """
    if request.method == "OPTIONS":
        return "", 204

    body = request.get_json(force=True)
    cluster_id = body.get("cluster_id", "")

    benchmarks = load_benchmarks()
    ranked = rank_priorities(SUBMISSIONS, benchmarks)
    match = next((r for r in ranked if r.cluster_id == cluster_id), None)

    if not match:
        return jsonify({"error": "cluster_not_found",
                         "hint": "Rankings may have changed since you loaded them — refresh and retry."}), 404

    sample_submission = next(
        (s for s in SUBMISSIONS if s.submission_id in match.linked_submission_ids), None
    )
    sample_text = sample_submission.raw_text if sample_submission else ""

    try:
        memo_text = generate_priority_memo(
            category=match.category.value,
            location_name=match.location_name,
            submission_count=match.submission_count,
            urgency_score=match.avg_urgency_score,
            enrollment_gap=match.enrollment_gap_score,
            distance_gap=match.distance_gap_score,
            total_score=match.total_score,
            sample_text=sample_text,
        )
    except Exception as e:
        return jsonify({"error": "memo_generation_failed", "detail": str(e)}), 503

    return jsonify({"memo": memo_text, "cluster_id": cluster_id})


@app.route("/status", methods=["GET"])
def status():
    return jsonify({
        "demo_mode": DEMO_MODE,
        "submission_count": len(SUBMISSIONS),
        "extraction": "live (Gemini)" if GEMINI_LIVE else "demo (rule-based)",
        "geocoding": "live (Google Maps)" if MAPS_LIVE else "demo (local gazetteer)",
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
