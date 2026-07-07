"""
Targeted top-up — adds submissions for categories/locations you're
currently missing (health, water, vocational), without re-submitting
what you already have. Paced conservatively (8s apart, no aggressive
retries) to avoid the rate-limit cascade from the full seed_data.py run.

Run this with your server already running (with GEMINI_API_KEY and
GOOGLE_MAPS_API_KEY still exported in that terminal):

    python3 seed_topup.py

If it still hits 503s, the printed 'detail' field will show the exact
Gemini error this time (not just a generic "rate-limited" guess), so we
can diagnose precisely rather than assume.
"""

import time
import requests

API_BASE = "http://localhost:8080"

TOPUP_SUBMISSIONS = [
    "Titabor PHC mein dawaiyon ki bahut kami hai, patients ko bahar se khareedni padti hai, bahut zaroori hai",
    "Titabor health centre mein doctor hafte mein sirf 2 din aate hain, emergency mein bahut problem hoti hai",
    "Mariani mein peene ke paani ki supply bahut irregular hai, 2-3 din tak paani nahi aata kabhi kabhi",
    "Mariani area mein drainage system bilkul kharab hai, baarish mein sadkein paani se bhar jaati hain",
    "Cinnamara ke yuvaon ke liye koi vocational training centre nahi hai, employment milna bahut mushkil hai",
    "Dergaon mein CHC mein bed ki bahut kami hai, patients ko floor par lita ke rakhna padta hai, urgent hai",
]


def topup():
    print(f"Topping up {len(TOPUP_SUBMISSIONS)} submissions (missing categories) via {API_BASE}/submit ...")
    print("(Paced at 8s apart — conservative, to avoid the earlier rate-limit cascade)\n")

    success_count = 0
    for i, text in enumerate(TOPUP_SUBMISSIONS, 1):
        try:
            resp = requests.post(
                f"{API_BASE}/submit",
                json={"text": text, "channel": "text"},
                timeout=20,
            )
            data = resp.json()

            if resp.status_code == 201:
                ext = data["extracted"]
                print(f"[{i}/{len(TOPUP_SUBMISSIONS)}] ✅ {ext['category']:20s} "
                      f"| urgency={ext['urgency']:8s} | loc={ext['location_name'] or '(none)'}")
                success_count += 1
            elif resp.status_code == 202:
                print(f"[{i}/{len(TOPUP_SUBMISSIONS)}] ⚠️  flagged: {data.get('warning')}")
            else:
                # Print the REAL error detail this time, not a guess
                print(f"[{i}/{len(TOPUP_SUBMISSIONS)}] ❌ status={resp.status_code} "
                      f"detail={data.get('detail', data)}")

        except requests.exceptions.ConnectionError:
            print(f"\n❌ Could not reach {API_BASE}. Is main.py running?")
            return
        except Exception as e:
            print(f"[{i}/{len(TOPUP_SUBMISSIONS)}] ❌ unexpected error: {e}")

        time.sleep(8)  # conservative pacing, no rapid retries this time

    print(f"\nDone: {success_count}/{len(TOPUP_SUBMISSIONS)} top-up submissions added.")
    print("Refresh dashboard.html to see the fuller picture.")


if __name__ == "__main__":
    topup()
