"""
Data models for People's Priorities.

These define the shape of data moving through the pipeline:
citizen submission -> Gemini extraction -> scoring engine -> ranked output.

Kept as plain dataclasses (not pydantic) to minimize dependencies for a
Cloud Run / Cloud Functions prototype. Swap to pydantic later if you add
FastAPI request validation.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class Category(str, Enum):
    SCHOOL_UPGRADE = "school_upgrade"
    VOCATIONAL_CENTRE = "vocational_centre"
    ROAD_INFRASTRUCTURE = "road_infrastructure"
    HEALTH_FACILITY = "health_facility"
    WATER_SANITATION = "water_sanitation"
    OTHER = "other"


class Urgency(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SubmissionChannel(str, Enum):
    VOICE = "voice"
    TEXT = "text"
    PHOTO = "photo"
    SMS = "sms"
    WHATSAPP = "whatsapp"


# Numeric weight so urgency can feed directly into the scoring formula
URGENCY_WEIGHTS = {
    Urgency.LOW: 1.0,
    Urgency.MEDIUM: 2.0,
    Urgency.HIGH: 3.0,
    Urgency.CRITICAL: 4.0,
}


@dataclass
class CitizenSubmission:
    """A single citizen submission after Gemini extraction."""
    submission_id: str
    raw_text: str                      # original text, or transcript if voice
    language: str                      # e.g. "hi", "en", "as" (Assamese)
    channel: SubmissionChannel

    # Fields populated by Gemini extraction (see extraction.py)
    category: Category = Category.OTHER
    urgency: Urgency = Urgency.MEDIUM
    summary: str = ""                  # one-line AI-generated summary
    location_name: str = ""            # e.g. "Titabor, Jorhat"
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    submitted_at: datetime = field(default_factory=datetime.utcnow)
    ward: str = "Jorhat"


@dataclass
class SchoolBenchmark:
    """
    Benchmark record for a single school, used to compute enrollment
    and infrastructure gaps. Seed this from real UDISE+ / Samagra Shiksha
    data (see benchmark_data.py) rather than mock numbers.
    """
    udise_code: str
    name: str
    block: str                         # e.g. "Jorhat", "North West Jorhat"
    latitude: float
    longitude: float
    enrolment: int
    capacity: Optional[int] = None     # if unknown, gap falls back to PTR-based logic
    teachers: Optional[int] = None
    pupil_teacher_ratio: Optional[float] = None


@dataclass
class RankedPriority:
    """Output of the scoring engine — one ranked development work item."""
    cluster_id: str
    category: Category
    location_name: str
    latitude: float
    longitude: float

    submission_count: int              # how many citizen submissions in this cluster
    avg_urgency_score: float
    enrollment_gap_score: float
    distance_gap_score: float
    total_score: float

    ai_justification: str = ""         # Gemini-generated plain-language rationale
    linked_submission_ids: list[str] = field(default_factory=list)
