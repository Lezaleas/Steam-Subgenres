import requests
import pandas as pd
import json
import time
from pathlib import Path


# ============================================================
# Configuration
# ============================================================

URL = "https://api.gamalytic.com/publishers/"
MAX_RETRIES = 5
RETRY_DELAY = 3
REQUEST_TIMEOUT = 30
CHECKPOINT_DIR = Path("gamalytic_checkpoints")
RAW_DIR = CHECKPOINT_DIR / "raw"
PROCESSED_DIR = CHECKPOINT_DIR / "processed"

CHECKPOINT_DIR.mkdir(exist_ok=True)
RAW_DIR.mkdir(exist_ok=True)
PROCESSED_DIR.mkdir(exist_ok=True)

# ============================================================
# HTTP helper
# ============================================================

session = requests.Session()

def download_page(page):
    """ Download one page with retries. Returns JSON or None if all retries fail. """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"  Requesting page {page} "
                  f"(attempt {attempt}/{MAX_RETRIES})...")
            response = session.get(URL, params={"page": page}, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            data = response.json()
            if "result" not in data:            # Basic sanity check
                raise ValueError("Response does not contain 'result'")
            return data

        except Exception as e:
            print(f"  ERROR on page {page}: {e}")
            if attempt < MAX_RETRIES:
                print(f"  Retrying in {RETRY_DELAY} seconds...")
                time.sleep(RETRY_DELAY)

    print(f"  FAILED page {page} after "
          f"{MAX_RETRIES} attempts.")
    return None

# ============================================================
# Process publisher data
# ============================================================

def process_page(data):
    """ Convert one API page into publisher and game rows. """
    publishers = []
    games = []

    for publisher in data["result"]:
        publishers.append({
            "publisher": publisher.get("name"),
            "id": publisher.get("id"),
            "number_of_games": publisher.get("numberOfGames"),
            "first_game_date": publisher.get("firstGameDate"),
            "last_game_date": publisher.get("lastGameDate"),
            "average_revenue": publisher.get("averageRevenue"),
            "median_revenue": publisher.get("medianRevenue"),
            "in_house": publisher.get("inHouse"),
            "class": publisher.get("class"),
            "total_revenue": publisher.get("totalRevenue"),
        })

        for game in publisher.get("games", []):
            games.append({
                "publisher": publisher.get("name"),
                "publisher_id": publisher.get("id"),
                "steam_id": game.get("steamId"),
                "game": game.get("name"),
                "copies_sold": game.get("copiesSold"),
                "price": game.get("price"),
                "developers": ", ".join(game.get("developers", [])),
                "publishers": ", ".join(game.get("publishers", [])),
                "publisher_class": game.get("publisherClass"),
                "review_score": game.get("reviewScore"),
                "genres": ", ".join(game.get("genres", [])),
                "unreleased": game.get("unreleased"),
                "early_access": game.get("earlyAccess"),
                "release_date": game.get("releaseDate"),
            })

        for game in publisher.get("unreleasedGames", []):
            games.append({
                "publisher": publisher.get("name"),
                "publisher_id": publisher.get("id"),
                "steam_id": game.get("steamId"),
                "game": game.get("name"),
                "copies_sold": game.get("copiesSold"),
                "price": game.get("price"),
                "developers": ", ".join(game.get("developers", [])),
                "publishers": ", ".join(game.get("publishers", [])),
                "publisher_class": game.get("publisherClass"),
                "review_score": game.get("reviewScore"),
                "genres": ", ".join(game.get("genres", [])),
                "unreleased": game.get("unreleased"),
                "early_access": game.get("earlyAccess"),
                "release_date": game.get("releaseDate"),
            })

    return publishers, games

# ============================================================
# Main scraper
# ============================================================

def scrape():

    # --------------------------------------------------------
    # Get first page to determine number of pages
    # --------------------------------------------------------

    first_checkpoint = RAW_DIR / "page_0.json"
    if first_checkpoint.exists():
        print("Page 0 already downloaded.")
        with open(first_checkpoint, "r", encoding="utf-8") as f:
            first_data = json.load(f)
    else:
        print("Downloading page 0...")
        first_data = download_page(0)
        if first_data is None:
            raise RuntimeError("Could not download page 0.")

        # Save immediately
        with open(first_checkpoint, "w", encoding="utf-8") as f:
            json.dump(first_data, f, ensure_ascii=False)

    total_pages = first_data["pages"]

    print()
    print(f"Total pages: {total_pages}")
    print()


    # --------------------------------------------------------
    # Download all pages
    # --------------------------------------------------------

    for page in range(0, total_pages + 1):
        raw_file = RAW_DIR / f"page_{page}.json"

        if raw_file.exists():        # Already downloaded?
            print(f"[{page}/{total_pages}] "
                  f"Already downloaded — skipping.")
            continue

        print(f"[{page}/{total_pages}] "
              f"Downloading...")

        data = download_page(page)

        if data is None:
            print(f"Page {page} FAILED.")
            print("Stopping here so the problem can be investigated.")
            break

        # ----------------------------------------------------
        # Save raw response BEFORE doing anything else.
        # ----------------------------------------------------

        temp_file = RAW_DIR / f"page_{page}.tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

        temp_file.replace(raw_file)        # checkpoint, rename only after writing succeeds.
        print(f"  Saved page {page}.")
        time.sleep(0.2)        # honor the api

    print()
    print("Download phase complete.")
    print()

# ============================================================
# Build CSVs from checkpoints
# ============================================================

def build_csvs():

    publishers = []
    games = []

    raw_files = sorted(
        RAW_DIR.glob("page_*.json"),
        key=lambda x: int(
            x.stem.split("_")[1]
        )
    )

    print(f"Found {len(raw_files)} downloaded pages.")

    for raw_file in raw_files:
        print(f"Processing {raw_file.name}")

        with open(raw_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        page_publishers, page_games = process_page(data)

        publishers.extend(page_publishers)
        games.extend(page_games)

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    publishers_df = pd.DataFrame(publishers)
    games_df = pd.DataFrame(games)

    publishers_df.to_csv("gamalytic_publishers.csv", index=False)
    games_df.to_csv("gamalytic_publisher_games.csv", index=False)

    print()
    print(f"Publishers: {len(publishers_df):,}")
    print(f"Games:      {len(games_df):,}")

    print()
    print("CSV files created.")


# ============================================================
# Run
# ============================================================

if __name__ == "__main__":
    scrape()
    build_csvs()