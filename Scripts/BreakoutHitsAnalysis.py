QUOTAS = {0: 0, 1: 0, 2: 20, 3: 0}  # Number of top-ranked games considered breakout hits per tier: 0 = AAA, 3 = Hobbyist
DATE_INTERVAL = 365.25 / 2          # Length of each interval in days (approximately six months)
INTERVALS = 6                       # Number of intervals: 3 before and 3 after the release-date boundary, covering 3 years on each side
CONTROL = 0                         # picks random games to establish a control group
CONTROL_TIER = 2                    # 0 = AAA, 1 = AA, 2 = Indie, 3 = Hobbyist/Solo

import pandas as pd
import math
import numpy as np

tags = pd.read_csv("tags.csv")
tags["release"] = pd.to_datetime(tags["release"], errors="coerce")

# Map average revenue by release year and tier
avg_revenue = pd.read_csv("tier_year_avgrevenue.csv")
avg_lookup = avg_revenue.set_index(["release_year", "tier"])["avg_revenue"]

if not CONTROL:
    breakouts = tags[
        (tags["revenue_rank"] <= tags["tier"].map(QUOTAS)) &
        (tags["release"].dt.year.between(2017, 2022))
    ].copy()

FILTER_TAGS = ["Sandbox", "Co-op", "Multiplayer", "Open-World", "Building", "Management", "Crafting", "Great Soundtrack"]  # Set to None to disable filtering
if CONTROL:
    filtered_tags = tags[

        (tags["release"].dt.year.between(2017, 2022)) &
        (tags["tier"] == CONTROL_TIER)
    ]
    if FILTER_TAGS is not None:
        filtered_tags = filtered_tags[
            filtered_tags["tag"].isin(FILTER_TAGS)
        ]
    breakouts = (
        filtered_tags
        #.sample(frac=1, random_state=42)
        #.drop_duplicates(subset="steam_id")
        #.sample(n=1000, random_state=42)
        .copy()
    )
# the control groups were obtained from the previous commented out block using tier 2.
# the effect is twice as strong for AA, and dissapears for Hobbyist
CONTROL_COUNTS = [5027816, 5460950, 5749543, 6026595, 6175903, 6224356]
CONTROL_AVGS = [np.float64(1.1), np.float64(1.06), np.float64(1.04), np.float64(1.02), np.float64(1.01), np.float64(1.0)]


def calculate_adjusted_averages(breakouts):
    interval_sums = np.zeros(INTERVALS, dtype=float)
    interval_counts = np.zeros(INTERVALS, dtype=np.int64)

    for breakout in breakouts.itertuples(index=False):
        games = tags[
            (tags["tier"] == breakout.tier) &
            (tags["tag"] == breakout.tag) &
            (tags["release"] >=
             breakout.release - pd.Timedelta(days=INTERVALS / 2 * DATE_INTERVAL)) &
            (tags["release"] <=
             breakout.release + pd.Timedelta(days=INTERVALS / 2 * DATE_INTERVAL))
        ]

        for game in games.itertuples(index=False):
            if game.steam_id == breakout.steam_id or pd.isna(game.release):
                continue

            year = game.release.year
            key = (year, game.tier)

            if key not in avg_lookup.index:
                continue

            average = avg_lookup.loc[key]

            if pd.isna(average) or average == 0:
                continue

            distance = (game.release - breakout.release).days / DATE_INTERVAL
            index = math.floor(distance) + INTERVALS // 2

            if 0 <= index < INTERVALS:
                interval_sums[index] += game.revenue / average
                interval_counts[index] += 1

    interval_averages = np.divide(
        interval_sums,
        interval_counts,
        out=np.full(INTERVALS, np.nan),
        where=interval_counts > 0
    )

    adjusted_averages = interval_averages - np.asarray(CONTROL_AVGS)

    return adjusted_averages


print(f"Total breakouts: {len(breakouts)}")
observed_adjusted = calculate_adjusted_averages(breakouts)
print("Adjusted averages:", np.round(observed_adjusted, 2))