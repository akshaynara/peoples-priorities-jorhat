"""
Seed script — submits a batch of realistic, varied citizen requests through
your LIVE API (real Gemini + real Maps) so the dashboard fills up properly
for your demo recording.

Run this with your server already running in another terminal tab:

    python3 seed_data.py

Deliberately varied across:
  - category (school, road, health, water, vocational)
  - urgency (low to critical)
  - location (spread across real Jorhat places from the gazetteer)
  - language style (Hindi, Assamese-flavored, English, mixed)

This hits your live Gemini + Maps APIs, so it will use a small amount of
your free-tier quota (well within limits — 16 requests total).
"""

import time
import requests

API_BASE = "http://localhost:8080"

SEED_SUBMISSIONS = [
    # --- School upgrade cluster: North West Jorhat (should rank high — real overcrowded school) ---
    ("North West Jorhat school mein bahut zyada bachche hain, ek classroom mein 60 se zyada students hain, teachers bahut kam hain", "high"),
    ("Humar school, North West Jorhat te, chatra bisi hoi ase, teacher kom, notun teacher lagibo lage", "high"),
    ("The school in North West Jorhat urgently needs more teachers, classrooms are severely overcrowded", "critical"),
    ("North West Jorhat mein school ka infrastructure bahut purana ho gaya hai, naye classrooms chahiye", "medium"),

    # --- School cluster: Kunwari Pukhuri ---
    ("Kunwari Pukhuri school mein bathroom facilities bahut kharab hain, bachchon ko dikkat hoti hai", "medium"),
    ("Kunwari Pukhuri area ke school mein library nahi hai, bachche padhai ke liye bahar jaate hain", "low"),

    # --- Road infrastructure: Jorhat town ---
    ("Jorhat town center mein road pe bahut bade gaddhe hain, do-pahiya vahan ke liye khatarnak hai", "high"),
    ("Jorhat town mein street lights kaam nahi kar rahi, raat mein bahut andhera rehta hai", "medium"),
    ("Main road near Jorhat town has been under repair for 6 months, causing daily traffic jams", "high"),

    # --- Health facility: Titabor ---
    ("Titabor PHC mein dawaiyon ki bahut kami hai, patients ko bahar se khareedni padti hai", "high"),
    ("Titabor health centre mein doctor hafte mein sirf 2 din aate hain, emergency mein problem hoti hai", "critical"),

    # --- Water/sanitation: Mariani ---
    ("Mariani mein peene ke paani ki supply bahut irregular hai, kabhi kabhi 2-3 din tak paani nahi aata", "high"),
    ("Mariani area mein drainage system kharab hai, baarish mein sadkein paani se bhar jaati hain", "medium"),

    # --- Vocational centre: Cinnamara ---
    ("Cinnamara ke yuvaon ke liye koi vocational training centre nahi hai, employment milna mushkil hai", "low"),

    # --- Road: Teok ---
    ("Teok mein bridge bahut purana ho gaya hai aur crack aa gaye hain, jaldi hi replace karna chahiye", "critical"),

    # --- School: near St. Mary's ---
    ("St. Mary's school ke paas area mein transportation ki suvidha nahi hai, bachchon ko dur paidal jaana padta hai", "low"),

    # --- Health: Dergaon ---
    ("Dergaon mein CHC mein bed ki bahut kami hai, patients ko floor par lita ke rakhna padta hai", "critical"),
]


def seed():
    print(f"Seeding {len(SEED_SUBMISSIONS)} realistic submissions via {API_BASE}/submit ...")
    print("(Paced at ~5s apart to stay safely under Gemini's free-tier rate limit)\n")

    success_count = 0
    for i, (text, expected_urgency) in enumerate(SEED_SUBMISSIONS, 1):
        for attempt in range(3):  # retry up to 3 times if rate-limited
            try:
                resp = requests.post(
                    f"{API_BASE}/submit",
                    json={"text": text, "channel": "text"},
                    timeout=20,
                )

                if resp.status_code == 503:
                    # Rate limited or transient error — back off and retry
                    wait = 8 * (attempt + 1)
                    print(f"[{i:2d}/{len(SEED_SUBMISSIONS)}] ⏳ rate-limited, waiting {wait}s and retrying...")
                    time.sleep(wait)
                    continue

                data = resp.json()

                if resp.status_code == 201:
                    ext = data["extracted"]
                    print(f"[{i:2d}/{len(SEED_SUBMISSIONS)}] ✅ {ext['category']:20s} "
                          f"| urgency={ext['urgency']:8s} | loc={ext['location_name'] or '(none)'}")
                    success_count += 1
                elif resp.status_code == 202:
                    print(f"[{i:2d}/{len(SEED_SUBMISSIONS)}] ⚠️  flagged for review: {data.get('warning')}")
                else:
                    print(f"[{i:2d}/{len(SEED_SUBMISSIONS)}] ❌ error: {data}")
                break  # success or non-retryable error, move to next submission

            except requests.exceptions.ConnectionError:
                print(f"\n❌ Could not reach {API_BASE}. Is main.py running in another terminal tab?")
                return
            except Exception as e:
                print(f"[{i:2d}/{len(SEED_SUBMISSIONS)}] ❌ unexpected error: {e}")
                break

        time.sleep(5)  # ~12/min, safely under the 15/min free-tier limit

    print(f"\nDone: {success_count}/{len(SEED_SUBMISSIONS)} submissions seeded successfully.")
    print(f"Open frontend/dashboard.html now to see the full ranked list and map.")


if __name__ == "__main__":
    seed()
