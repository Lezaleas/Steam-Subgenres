import csv
import os
import tempfile
import time
import ollama

# -----------------------------
# Configuration
# -----------------------------
INPUT_CSV = "ai.csv"
MODEL = "mistral:7b"
INPUT_TEXT_COLUMN = "ai_disclosure_text"
OUTPUT_COLUMN = "ai_code"
RETRY_SECONDS = 10
SAVE_EVERY = 1000  # Save/flush to temp file every N rows

# -----------------------------
# Prompt
# -----------------------------
SYSTEM_PROMPT = """
You are a classification assistant for Steam game AI disclosures.
Determine if generative AI was used to CREATE or MODIFY DEVELOPMENT CODE, SCRIPTS, or PROGRAMMING LOGIC that appears OR IS COMPILED IN THE GAME ITSELF.

Return true if generative AI was used for:
Generating or modifying source code, algorithms, scripts, physics systems, or game logic used in the running application.
Creating shader code, database queries, build scripts, or engine integration code that functions as part of the game.
Generating or modifying code assets used during runtime, automated tooling embedded in development builds, or modding/scripting backends.
Generating or modifying existing codebases using AI, even if human software engineers or programmers subsequently reviewed, refactored, or edited them.
Using generative AI to synthesize, refactor, or translate code logic for the game.

Return false if:
AI was used exclusively for audio, artwork, visual assets, translation, localization, or other non-coding tasks.
AI was used exclusively for text generation, dialogue writing, storytelling, or narrative design.
AI was used exclusively to create promotional scripts, marketing code, website backends, or tools outside the game build.
AI was used exclusively for standard IDE features, linters, or general production assistance (like standard autocomplete or syntax highlighting) without generating or modifying functional game code logic.
The disclosure mentions AI programming tools but does not establish that they were actually used to create or modify code in the game.
The text does not clearly establish that generative AI was used to create or modify in-game code.

IMPORTANT:
Classify based on the actual use of generative AI, not merely the mention of AI tools.
Human review, refactoring, or editing does not negate AI use.
If AI was used for both in-game code and other purposes, return true.
Do not assume that AI was used for coding simply because a game functions.
Dialogue writing and text localization are classified separately and should not count here.

Output strictly one word: true or false.

"""

VALID_CATEGORIES = {
    "true",
    "false"
}

# ----------------------------

def classify_text(text):
    """Sends text to Ollama and retries indefinitely on failure."""
    if not text or not str(text).strip():
        return "false"

    text_str = str(text).strip()

    while True:
        try:
            response = ollama.chat(
                model=MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT.strip()},
                    {"role": "user", "content": text_str}
                ],
                options={
                    "temperature": 0.0,
                    "num_ctx": 1024  # Reduces RAM usage and speeds up CPU processing
                }
            )
            result = response['message']['content'].strip().lower()

            # Clean potential backticks or extra formatting
            result = result.replace("`", "").strip()

            if result in VALID_CATEGORIES:
                return result

            # Fallback text parsing if the model adds conversational filler
            if "true" in result and "false" not in result:
                return "true"
            elif "false" in result and "true" not in result:
                return "false"

            return "false"

        except Exception as e:
            print(f"[Error] Ollama request failed: {e}. Retrying in {RETRY_SECONDS} seconds...")
            time.sleep(RETRY_SECONDS)


def main():
    if not os.path.exists(INPUT_CSV):
        print(f"Error: Input file '{INPUT_CSV}' not found.")
        return

    input_dir = os.path.dirname(os.path.abspath(INPUT_CSV)) or "."

    # 1. Read input CSV
    print(f"Loading '{INPUT_CSV}'...")
    with open(INPUT_CSV, mode="r", encoding="utf-8", newline="") as infile:
        reader = csv.DictReader(infile)
        fieldnames = reader.fieldnames
        if not fieldnames:
            print("Error: CSV file is empty or missing headers.")
            return

        # Ensure output column exists in schema
        if OUTPUT_COLUMN not in fieldnames:
            fieldnames = list(fieldnames) + [OUTPUT_COLUMN]

        rows = list(reader)

    print(f"Loaded {len(rows)} rows. Starting classification with model '{MODEL}'...")

    temp_file_path = None
    try:
        # 2. Write to a temporary file first (prevents corruption of original file)
        with tempfile.NamedTemporaryFile(mode="w", delete=False, dir=input_dir, encoding="utf-8",
                                         newline="") as temp_file:
            temp_file_path = temp_file.name
            writer = csv.DictWriter(temp_file, fieldnames=fieldnames)
            writer.writeheader()

            for i, row in enumerate(rows, 1):
                raw_current = row.get(OUTPUT_COLUMN)
                current_value = str(raw_current).strip().lower() if raw_current is not None else ""

                # Check if already classified (allows resuming if script is stopped)
                if current_value in VALID_CATEGORIES:
                    print(f"[{i}/{len(rows)}] Skipping already classified row.")
                else:
                    text_to_classify = row.get(INPUT_TEXT_COLUMN, "")
                    print(f"[{i}/{len(rows)}] Classifying text...")
                    classification = classify_text(text_to_classify)
                    row[OUTPUT_COLUMN] = classification

                writer.writerow(row)

                # Periodically flush every SAVE_EVERY row to commit data to disk
                if i % SAVE_EVERY == 0:
                    temp_file.flush()
                    os.fsync(temp_file.fileno())


                    print(f"--- Progress checkpoint: Saved {i} rows to temporary file ---")

        # 3. Atomically replace the original CSV with the completed temp file
        os.replace(temp_file_path, INPUT_CSV)
        print(f"\nSuccess! All rows processed and saved safely to '{INPUT_CSV}'.")

    except Exception as e:
        print(f"\nCritical Error during execution: {e}")
        # Clean up temp file if something went wrong
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        raise


if __name__ == "__main__":
    main()