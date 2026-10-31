# Technical Methodology

# 1. Objective

A core objective of this study was to determine whether breakout hits serve as causal pioneers that establish new subgenres, or if they act as catalytic inflection points capitalizing on pre-existing latent demand within the market.

With the data indicating that breakout hits capitalize on existing demand rather than creating it, the analysis shifted to systematically identifying high-grossing subgenres across the platform.

linktothesubredditthreadhere
Indie and solo developers have expressed skepticism regarding generative AI integration, citing as concerns player backlash and brand risk. Consequently, an empirical study was conducted to examine the presence of AI disclosures on Steam storefronts and assess its correlation with title profitability and sales performance.

# 2. Data Collection

Publisher-level attributes were retrieved using the Gamalytic API via an automated collection script.
This dataset includes primary publisher identifiers and standardized tier classifications (AAA, Indie, Hobbyist).

pythongscriptlinkhere
To document developer disclosures regarding artificial intelligence, target HTML elements were extracted from individual Steam store pages using custom web scraping scripts.
The raw text of each disclosure was preserved to perform NLP classification via Large Language Models.

datasetlinkhere
Game-level genre taxonomies were integrated from a continuously updated Steam games dataset.
This dataset captures daily snapshots of crowdsourced community tags and subgenre classifications associated with each title.

![Data Structure](pictures/data_structure.webp)

# 3. Data Cleaning & Preprocessing

In the steam games dataset, titles with a price of $0 were excluded from the dataset, as free-to-play games utilize fundamentally distinct monetization models.

Due to inconsistent data types within the subgenre column—comprising both comma-separated values and JSON strings—all entries were standardized into uniform strings through the following query:

```sql
-- json to stringified array
UPDATE game.steam
SET tags = (
    SELECT jsonb_agg(key ORDER BY ordinal)
    FROM (
        SELECT key, row_number() OVER () AS ordinal
        FROM jsonb_object_keys(tags::jsonb) AS t(key)
    ) AS keys
)::text
WHERE tags IS NOT NULL
  AND jsonb_typeof(tags::jsonb) = 'object';
```

```sql
-- stringified array to string
UPDATE game.steam
SET tags = (
    SELECT string_agg(tag, ', ')
    FROM jsonb_array_elements_text(tags::jsonb) AS t(tag)
)
WHERE tags IS NOT NULL
  AND TRIM(tags) <> '';
```

The Gamalytic dataset contained multiple entries for multi-publisher titles, thus records were filtered to preserve a single unique publisher per game.
The dataset natively lists publishers in descending order of importance, the first-listed entity was retained as the primary publisher during deduplication:

```sql
DELETE FROM game.games
WHERE ctid IN (
    SELECT ctid
    FROM (
        SELECT
            ctid,
            ROW_NUMBER() OVER (
                PARTITION BY steam_id
                ORDER BY POSITION(publisher IN publishers)
            ) AS rn
        FROM game.gamalytic
    ) x
    WHERE rn > 1
);
```

Because string-matching via POSITION() occasionally introduced collision errors when a publisher name was entirely contained within another string, a secondary audit was performed. Ten affected edge cases were manually  corrected to guarantee the accuracy of the primary publisher assignment using the following inspection query:

```sql
SELECT steam_id, publisher, publishers FROM game.gamalytic
WHERE NOT ( publishers = publisher OR LEFT(publishers, LENGTH(publisher) + 1) = publisher || ',')
LIMIT 100;
```

# 4. Exploratory Data Analysis

Games were partitioned and ranked by tier and release year, establishing relative performance benchmarks to identify outlier titles in subsequent analyses.

```sql
WITH unique_games AS (
    SELECT DISTINCT
        steam_id,
        EXTRACT(YEAR FROM release)::INTEGER AS release_year,
        tier,
        revenue
    FROM game.tags
    WHERE release IS NOT NULL
      AND revenue IS NOT NULL
),
ranked_games AS (
    SELECT
        steam_id,
        release_year,
        tier,
        RANK() OVER (
            PARTITION BY release_year, tier
            ORDER BY revenue DESC
        ) AS game_rank
    FROM unique_games
)
UPDATE game.tags AS t
SET revenue_rank = r.game_rank
FROM ranked_games AS r
WHERE t.steam_id = r.steam_id
  AND EXTRACT(YEAR FROM t.release)::INTEGER = r.release_year
  AND t.tier = r.tier;
```

Additionally, a summary reference table containing mean revenue per tier and release year was compiled to facilitate revenue normalization during exploratory analysis.

```sql
WITH unique_games AS (
    SELECT DISTINCT
        steam_id,
        release,
        tier,
        revenue
    FROM game.tags
    WHERE release IS NOT NULL
      AND revenue IS NOT NULL
)
SELECT
    EXTRACT(YEAR FROM release)::INTEGER AS release_year,
    tier,
    round(AVG(revenue)) AS avg_revenue,
    COUNT(*) AS game_count
FROM unique_games
where EXTRACT(YEAR FROM release) >= 2014
GROUP BY
    EXTRACT(YEAR FROM release),
    tier
ORDER by
	tier,
    release_year;
```

To evaluate whether breakout hits catalyze subgenre expansion or lead to market saturation, a temporal impact analysis was conducted across high-performing titles:
* Cohort Identification: A top-performing cohort of K games was selected based on tier-normalized revenue rankings.
* Temporal Windowing: For each breakout title, associated subgenre entries within a multi-year temporal window relative to the breakout release date (t = 0) were aggregated. Revenues and temporal distances were tallied to calculate trajectory averages.
* Control Group Baseline: To isolate genuine subgenre trajectory shifts from broader platform expansion, a randomized baseline control group was subtracted from the aggregate results.

This approach encounters potential selection bias, as top-performing titles naturally concentrate within established, high-revenue subgenres. However, because Steam games feature up to 20 community tags per title, the inclusion of lower-density secondary tags introduces sufficient variation to reduce systemic bias and limit aggregate margin of error.

# 5. Feature Engineering

Due to extreme right-skewness in revenue distributions, values were winsorized to prevent outlier distortion. This transformation was applied separately for each publisher tier to preserve relative scale differences across AAA, Indie, and Hobbyist titles.

```sql
UPDATE game.tags AS t
SET winsorized_revenue = LEAST(
    t.revenue,
    p.p95_revenue
)
FROM (
    SELECT
        tier,
        PERCENTILE_CONT(0.95)
            WITHIN GROUP (ORDER BY revenue) AS p95_revenue
    FROM (
        SELECT DISTINCT
            tier,
            steam_id,
            revenue
        FROM game.tags
        WHERE revenue IS NOT NULL
    ) games
    GROUP BY tier
) p
WHERE t.tier = p.tier
  AND t.revenue IS NOT NULL;
```

Additionally, winsorized revenue was normalized within its respective tier to establish balanced comparative metrics across market segments.

```sql
WITH game_data AS (
    SELECT DISTINCT
        steam_id,
        tier,
        winsorized_revenue
    FROM game.tags
    WHERE winsorized_revenue IS NOT NULL
),
tier_avg AS (
    SELECT
        tier,
        AVG(winsorized_revenue) AS avg_revenue
    FROM game_data
    GROUP BY tier
)
UPDATE game.tags t
SET normalized_revenue =
    round(t.winsorized_revenue::NUMERIC / a.avg_revenue, 4)
FROM tier_avg a
WHERE t.tier = a.tier
  AND t.winsorized_revenue IS NOT NULL;
```

# 6. AI disclosure Categorization Using an LLM in Python

Using a local instance of Mistral 7B via Python and Ollama, the scraped AI disclosure texts were categorized to evaluate whether generative AI was utilized across four distinct vectors: visuals, localization, code, and audio.

The resulting classification schema generated a binary boolean feature set mapped to each game's steam_id. This table was subsequently integrated into the primary analytical model within Power BI via a relational join on the steam_id key.

**[View the complete Python script](./pictures/review_categorization.py)**

# 7. Statistics and Possible Biases

The primary data bias arises from Steam’s community-driven tagging mechanism. Highly visible titles benefit from higher tag density and accuracy, whereas lesser-known games suffer from sparse tagging. Furthermore, crowdsourced inputs introduce non-systematic tagging errors and subjective misclassifications across the dataset.

To control for production scale and financial backing, comparative analyses were restricted within identical publisher tiers. However, publisher tier functions as an imperfect proxy for actual investment; the correlation between tier classification and capital expenditure is non-absolute. Furthermore, because the taxonomy is limited to four discrete tiers, residual within-tier heterogeneity remains—meaning considerable variance in development budgets persists among games grouped within the same category.

Due to the remaining variance after winsorization and normalization (μ = 1.0, σ = 2.08), sample size thresholds were established to ensure statistical validity across subgenre cohorts. Based on a 95% confidence level and an acceptable margin of error of E = 0.5, a minimum sample size of 66 games per cohort was required for comparative evaluations. Columns below this sample are therefore dynamically greyed out in dashboards

# 8. Dashboard Creation

Review counts were normalized within their respective release years and publisher tiers to control for macro-market expansion and facilitate direct year-over-year genre comparisons. To smooth temporal volatility and mitigate annual noise in longitudinal charts, 3-year rolling averages were applied. Equivalent DAX measures were utilized for revenue and copies sold metrics.

```
N Review Score = 
DIVIDE(
    [W Review Score],
    CALCULATE(
        [W Review Score],
        REMOVEFILTERS('game tags'[steam_id]),
        REMOVEFILTERS('game tags'[tag]),
        REMOVEFILTERS('game ai'[ai_disclosure_status]),
        REMOVEFILTERS('game ai'[ai_art]),
        REMOVEFILTERS('game ai'[ai_localization]),
        REMOVEFILTERS('game ai'[ai_code]),
        REMOVEFILTERS('game ai'[ai_audio])
    )
)
```

```
3YR Review Score = 
AVERAGEX(
    DATESINPERIOD(
        'game tags'[release],
        MAX('game tags'[release]),
        -3,
        YEAR
    ),
    [N Review Score]
)
```

[← View Results](README.md)
