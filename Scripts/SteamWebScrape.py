import time
import random
from pathlib import Path

import pandas as pd
import httpx
from bs4 import BeautifulSoup


# =========================
# CONFIGURATION
# =========================

CSV_PATH = Path("steam_games.csv")

# Change these to match your CSV's actual column names.
APPID_COLUMN = "appid"
STATUS_COLUMN = "ai_disclosure_status"
TEXT_COLUMN = "ai_disclosure_text"

# Delay between requests to avoid hammering Steam.
MIN_DELAY = 0.5
MAX_DELAY = 0.8

TIMEOUT = 30
MAX_RETRIES = 3


# =========================
# SCRAPING
# =========================

def get_ai_disclosure(client: httpx.Client, appid: int) -> dict:
    """Fetch a Steam game's AI disclosure."""

    url = f"https://store.steampowered.com/app/{appid}/"

    response = client.get(
        url,
        params={"l": "english"},
        timeout=TIMEOUT,
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    # Find the heading by its complete text.
    heading = soup.find(
        lambda tag: (
            tag.name == "h2"
            and tag.get_text(" ", strip=True)
            == "AI Generated Content Disclosure"
        )
    )

    if heading is None:
        # A successful HTTP response alone does not prove that we
        # received a valid game page.
        is_game_page = (
                soup.find("h1", id="appHubAppName") is not None
                or soup.find("div", class_="game_page_background") is not None
                or soup.find("div", id="game_area_description") is not None
        )

        if not is_game_page:
            raise ValueError(
                f"Could not identify a valid Steam game page. "
                f"HTTP status: {response.status_code}; "
                f"page title: {soup.title.get_text(strip=True) if soup.title else 'None'}"
            )

        return {
            "status": "not_found",
            "text": None,
        }

    section = heading.find_parent(
        "div",
        class_="game_area_description",
    )

    if section is None:
        raise ValueError("Disclosure heading found, but section is missing")

    paragraphs = section.find_all("p")

    # The first paragraph is explanatory text.
    # The last paragraph contains the developer's disclosure.
    if len(paragraphs) < 2:
        raise ValueError("Disclosure text could not be extracted")

    disclosure_text = paragraphs[-1].get_text(
        separator=" ",
        strip=True,
    )

    if not disclosure_text:
        raise ValueError("Disclosure text is empty")

    return {
        "status": "found",
        "text": disclosure_text,
    }


def scrape_with_retries(client: httpx.Client, appid: int) -> dict:
    """Retry failed requests, identifying likely age-restricted pages."""

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return get_ai_disclosure(client, appid)

        except Exception as exc:
            error_message = str(exc)

            # Steam may redirect age-restricted pages to a sign-in page.
            if "page title: Sign In" in error_message:
                print(f"  Likely adult page: {appid}")
                return {
                    "status": "likely adult page",
                    "text": None,
                }

            print(
                f"  Attempt {attempt}/{MAX_RETRIES} failed for "
                f"{appid}: {type(exc).__name__}: {exc}"
            )

            if attempt < MAX_RETRIES:
                time.sleep(2 ** attempt)

    return {
        "status": "error",
        "text": None,
    }


# =========================
# MAIN PROCESS
# =========================

def main():
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"CSV not found: {CSV_PATH.resolve()}")

    df = pd.read_csv(CSV_PATH, dtype={APPID_COLUMN: "string"})

    df[STATUS_COLUMN] = df[STATUS_COLUMN].astype("string")
    df[TEXT_COLUMN] = df[TEXT_COLUMN].astype("string")

    # Validate the expected columns.
    required_columns = [APPID_COLUMN, STATUS_COLUMN, TEXT_COLUMN]
    missing_columns = [col for col in required_columns if col not in df.columns]

    if missing_columns:
        raise ValueError(
            f"Missing CSV columns: {missing_columns}\n"
            f"Available columns: {list(df.columns)}"
        )

    # Process rows with empty statuses or "error".
    status = df[STATUS_COLUMN].astype("string").str.strip().str.lower()

    unchecked = (
            status.isna()
            | (status == "")
            | (status == "error")
    )

    total = int(unchecked.sum())
    print(f"Total games: {len(df)}")
    print(f"Already checked: {len(df) - total}")
    print(f"Remaining: {total}")

    if total == 0:
        print("All rows have already been checked.")
        return

    # Reuse one HTTP client for connection pooling.
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/130.0.0.0 Safari/537.36"
        )
    }

    with httpx.Client(
            headers=headers,
            follow_redirects=True,
            cookies={
                "birthtime": "631152001",
                "lastagecheckage": "1-January-1990",
                "wants_mature_content": "1",
            },
    ) as client:

        processed = 0

        for index in df.index[unchecked]:
            raw_appid = df.at[index, APPID_COLUMN]

            try:
                if pd.isna(raw_appid) or not str(raw_appid).strip():
                    raise ValueError("Missing appid")

                # Handles IDs stored as numbers such as "9801.0".
                appid = int(float(str(raw_appid).strip()))

                print(
                    f"[{processed + 1}/{total}] "
                    f"Checking appid {appid}..."
                )

                result = scrape_with_retries(client, appid)

                df.at[index, STATUS_COLUMN] = result["status"]
                df.at[index, TEXT_COLUMN] = result["text"]

                print(f"  Result: {result['status']}")

            except Exception as exc:
                # Invalid IDs or other row-specific errors.
                df.at[index, STATUS_COLUMN] = "error"
                df.at[index, TEXT_COLUMN] = None

                print(f"  Could not process row: {exc}")

            # Save after every row so progress survives interruptions.
            df.to_csv(CSV_PATH, index=False)
            processed += 1

            if processed < total:
                time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))

    print(f"\nFinished. Updated CSV: {CSV_PATH.resolve()}")


if __name__ == "__main__":
    main()
