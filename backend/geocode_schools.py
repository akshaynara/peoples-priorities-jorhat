"""
One-time script: geocodes the real school names in benchmark_data.py using
your live GOOGLE_MAPS_API_KEY, and rewrites the file with real lat/lon
values in place of the placeholder coordinates.

Run this once, from the backend/ folder, with your Maps key exported:

    export GOOGLE_MAPS_API_KEY=your_key_here
    python3 geocode_schools.py

It will print each school's old (placeholder) vs new (real) coordinates,
then ask for confirmation before overwriting benchmark_data.py. A backup
of the original file is saved as benchmark_data.py.bak just in case.
"""

import os
import re
import shutil
import sys

try:
    import googlemaps
except ImportError:
    print("Missing dependency. Run: pip3 install googlemaps")
    sys.exit(1)

API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")
if not API_KEY:
    print("GOOGLE_MAPS_API_KEY is not set in this terminal session.")
    print("Run: export GOOGLE_MAPS_API_KEY=your_key_here")
    sys.exit(1)

from benchmark_data import SEED_SCHOOLS  # noqa: E402  (import after key check)

gmaps = googlemaps.Client(key=API_KEY)


def geocode_school(name: str, block: str) -> tuple[float, float] | None:
    """Geocode a school by name + block, biased to Jorhat, Assam."""
    query = f"{name}, {block}, Jorhat, Assam, India"
    try:
        result = gmaps.geocode(query)
    except Exception as e:
        print(f"  ERROR geocoding '{query}': {e}")
        return None

    if not result:
        # Retry with just the block + district, dropping the specific name,
        # in case the exact school isn't in Google's index
        fallback_query = f"{block}, Jorhat, Assam, India"
        try:
            result = gmaps.geocode(fallback_query)
        except Exception:
            return None
        if result:
            print(f"  (exact school not found, used block-level location for '{name}')")

    if not result:
        return None

    loc = result[0]["geometry"]["location"]
    return loc["lat"], loc["lng"]


def main():
    print(f"Geocoding {len(SEED_SCHOOLS)} schools using live Google Maps API...\n")

    updates = []  # (udise_code, name, old_lat, old_lon, new_lat, new_lon)
    for school in SEED_SCHOOLS:
        print(f"Geocoding: {school.name} ({school.block})...")
        coords = geocode_school(school.name, school.block)
        if coords:
            new_lat, new_lon = coords
            print(f"  Old (placeholder): {school.latitude:.4f}, {school.longitude:.4f}")
            print(f"  New (real):        {new_lat:.4f}, {new_lon:.4f}\n")
            updates.append((school.udise_code, school.name, new_lat, new_lon))
        else:
            print(f"  Could not geocode — keeping placeholder coordinates.\n")

    if not updates:
        print("No schools were successfully geocoded. Nothing to update.")
        return

    print(f"\n{len(updates)}/{len(SEED_SCHOOLS)} schools geocoded successfully.")
    confirm = input("Overwrite benchmark_data.py with these real coordinates? [y/N]: ")
    if confirm.strip().lower() != "y":
        print("Cancelled. No changes made.")
        return

    # Backup original file first
    shutil.copy("benchmark_data.py", "benchmark_data.py.bak")
    print("Backed up original to benchmark_data.py.bak")

    with open("benchmark_data.py", "r") as f:
        content = f.read()

    for udise_code, name, new_lat, new_lon in updates:
        # Find this school's block in the file by UDISE code, then replace
        # its latitude/longitude lines within that block only.
        pattern = re.compile(
            r'(udise_code="' + re.escape(udise_code) + r'".*?latitude=)[^,]+(,\s*longitude=)[^,]+,',
            re.DOTALL,
        )
        replacement = rf'\g<1>{new_lat}\g<2>{new_lon},'
        new_content, count = pattern.subn(replacement, content)
        if count == 1:
            content = new_content
            print(f"Updated coordinates for {name}")
        else:
            print(f"WARNING: could not locate unique block for {name} (udise {udise_code}) — skipped")

    with open("benchmark_data.py", "w") as f:
        f.write(content)

    print("\nDone. benchmark_data.py updated with real geocoded coordinates.")
    print("Original saved as benchmark_data.py.bak if you need to revert.")


if __name__ == "__main__":
    main()
