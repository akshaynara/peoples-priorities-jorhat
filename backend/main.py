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
from models import CitizenSubmission, SubmissionChannel
from extraction import extract_submission_fields, geocode_location
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
    Body: { "text": "...", "channel": "text" | "voice" | "sms" | "whatsapp" }
    For voice, the client runs Speech-to-Text (or browser Web Speech API in
    demo mode) BEFORE hitting this endpoint, and sends the transcript as `text`.
    """
    body = request.get_json(force=True)
    raw_text = body.get("text", "").strip()
    channel = SubmissionChannel(body.get("channel", "text"))

    if not raw_text:
        return jsonify({"error": "text is required"}), 400

    try:
        extracted = extract_submission_fields(raw_text, channel)
    except Exception as e:
        # Most common cause: Gemini free-tier rate limit (~15 req/min) hit
        # during rapid-fire testing/seeding. Return clean JSON instead of
        # crashing, so callers (like seed_data.py) can detect and retry.
        return jsonify({
            "error": "extraction_failed",
            "detail": str(e),
            "hint": "Often a Gemini rate limit (free tier ~15 req/min). Wait a few seconds and retry.",
        }), 503

    try:
        coords = geocode_location(extracted["location_name"])
    except Exception as e:
        return jsonify({"error": "geocoding_failed", "detail": str(e)}), 503

    lat, lon = coords if coords else (None, None)

    submission = CitizenSubmission(
        submission_id=str(uuid.uuid4()),
        raw_text=raw_text,
        language=extracted["language"],
        channel=channel,
        category=extracted["category"],
        urgency=extracted["urgency"],
        summary=extracted["summary"],
        location_name=extracted["location_name"],
        latitude=lat,
        longitude=lon,
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
