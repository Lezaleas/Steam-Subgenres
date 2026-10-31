# Technical Methodology

# 1. Objective

A core objective of this study was to determine whether breakout hits serve as causal pioneers that establish new subgenres, or if they act as catalytic inflection points capitalizing on pre-existing latent demand within the market.
With the data indicating that breakout hits capitalize on existing demand rather than creating it, the analysis shifted to systematically identifying high-grossing subgenres across the platform.

linktothesubredditthreadhere
Indie and solo developers have expressed skepticism regarding generative AI integration, citing as concerns player backlash and brand risk. Consequently, an empirical study was conducted to examine the presence of AI disclosures on Steam storefronts and assess its correlation with title profitability and sales performance.

# 2. Data Collection

Publisher-level attributes were retrieved using the Gamalytic API via an automated collection script.
This dataset includes primary publisher identifiers, standardized tier classifications (AAA, Indie, Hobbyist), base pricing, and estimated unit sales.

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

---

# 6. Final Data Preparations



# 7. Statistics and Possible Biases

A minimum sample-size threshold was established to determine when a category's repurchase rate can be considered statistically precise enough for interpretation. The target was a 95% confidence range of approximately ±1 percentage point around the expected 3% repurchase rate.

At a 3% repurchase rate, the standard error for 100 observations is approximately 1.7 percentage points. At 95% confidence, this produces an expected range of approximately ±3.3 percentage points. Since the margin of error decreases with the square root of the sample size, approximately 1,100 observations are required to reduce the 95% margin of error to ±1 percentage point.

**A practical threshold of 1,100 observations** was therefore adopted. Categories below this threshold were not excluded, but their results should be interpreted with greater caution due to their lower statistical precision.

The following table is the result of calculating the p-value of each resulting category against the hypothesis of 2.99% repurchase rate displayed by the general population:

```sql
WITH category_stats AS (
    SELECT
        pos_message,
        COUNT(*) AS sample_size,
        COUNT(*) FILTER (
            WHERE had_subsequent_order = TRUE
        ) AS repurchases
    FROM analysis.all
    WHERE pos_message IS NOT NULL
    GROUP BY pos_message
),

calculations AS (
    SELECT
        pos_message,
        sample_size,
        repurchases,
        repurchases::numeric / sample_size AS repurchase_rate,

        SQRT(
            (repurchases::numeric / sample_size)
            * (1 - repurchases::numeric / sample_size)
            / sample_size
        ) AS standard_error,

        (
            (repurchases::numeric / sample_size) - 0.0299
        )
        / SQRT(
            0.0299 * (1 - 0.0299) / sample_size
        ) AS z_score

    FROM category_stats
)

SELECT
    pos_message,

    ROUND(repurchase_rate * 100, 2) AS repurchase_rate_pct,

    sample_size AS count,

    ROUND(
        (repurchase_rate - 1.96 * standard_error) * 100,
        2
    ) AS error_lower_pct,

    ROUND(
        (repurchase_rate + 1.96 * standard_error) * 100,
        2
    ) AS error_upper_pct,

ROUND(
    (
        2 * (
            1 - (
                0.5 * (
                    1 + erf(ABS(z_score) / SQRT(2))
                )
            )
        )
    )::numeric,
    2
) AS p_value_vs_baseline

FROM calculations
ORDER BY p_value_vs_baseline DESC;
```

| Category          | Repurchase Rate |  Count | Low 95% Range | High 95% Range | P-value vs 2.99% Baseline |
| ----------------- | --------------: | -----: | ------------: | -------------: | ---------------------: |
| Good Delivery     |           2.98% |  4,695 |         2.50% |          3.47% |                   0.94 |
| Value/Price       |           4.24% |    283 |         1.89% |          6.59% |                   0.22 |
| Easy/Good Service |           3.82% |  1,127 |         2.70% |          4.93% |                   0.11 |
| Unspecified       |           3.23% | 32,438 |         3.04% |          3.42% |                   0.02 |
| Product Quality   |           3.98% |  6,132 |         3.49% |          4.47% |                  <0.01 |
| Unsatisfied       |           2.54% | 34,406 |         2.38% |          2.71% |                  <0.01 |

Most categories display statistically significant differences in repurchase rate compared to the 2.99% baseline. The main exception is the "Good Delivery" category, which has a large sample size of 4,695 but a high p-value of 0.94. This indicates that its 2.98% repurchase rate is effectively indistinguishable from the 2.99% general rate, likely because the true repurchase rate for this category is genuinely very close to the baseline. A similar analysis with similar results was made for the negative message categories.

 Potential Biases
- **Review reporting bias:** Customers are more likely to report issues that are easy to identify or describe, or that have a strong emotional impact. This may cause some issues to be over/underrepresented relative to their actual frequency or impact.
- **Review-selection bias:** The customers who choose to leave reviews may differ systematically from those who do not. As a result, the analyzed reviews may not fully represent the experiences or behavior of the entire customer population.
- **Correlation vs. causation:** The review itself is not necessarily causing the lower repurchase rate. Rather, the review category serves as an observable indicator of an underlying customer experience. Therefore, the analysis demonstrates correlation between reported issues and repurchase behavior, rather than causality.
- **LLM classification bias:** The review categorization process introduced potential classification errors. In particular, due to computational resource limitations, each review was assigned only one category, even when a review could reasonably describe multiple issues. This may cause some categories to be overrepresented at the expense of others.
- **Dataset timing:** The Olist database represents a relatively early period in the company's lifetime, when brand recognition was likely lower and customers had had less time to establish purchasing habits. Repurchase rates may therefore be lower than what would be expected from a more established marketplace, limiting the generalizability of the findings to later stages of the company's growth.

# 8. Dashboard Creation

The following DAX measure was created to provide a reusable repurchase rate metric throughout the dashboard:

```text
Repurchase = 
DIVIDE(
    CALCULATE(
        COUNT('analysis all'[customer_unique_id]),
        'analysis all'[had_subsequent_order] = TRUE()),
    COUNT('analysis all'[customer_unique_id]))
```

It was also important to estimate the number of customers potentially lost within each category, including customers who did not leave a review. Under the assumption that customers who left reviews and those who did not are drawn from the same underlying distribution, the following measure was used to extrapolate the observed repurchase behavior of reviewers to the broader customer population:

```text
Good Review Coverage = 
DIVIDE(
    CALCULATE(
        COUNTROWS('analysis all'),
        REMOVEFILTERS('analysis all'),
        'analysis all'[review_score] = 5),
    CALCULATE(
        COUNTROWS('analysis all'),
        REMOVEFILTERS('analysis all'),
        'analysis all'[review_score] = 5,
        'analysis all'[pos_message] <> "Unspecified"))
```

```text
Estimated Repurchases Gained = 
VAR BaselineRate =
    CALCULATE(
        [Repurchase],
        'analysis all'[review_score] = 5,
        REMOVEFILTERS('analysis all'[pos_message]))

VAR HighlightRate =
    [Repurchase]

VAR AffectedCustomers =
    DISTINCTCOUNT(
        'analysis all'[customer_unique_id])

RETURN
    MAX(
        0,
        (HighlightRate - BaselineRate)
            * AffectedCustomers
            * [Good Review Coverage])
```

Since certain categories can be grouped into opposing positive and negative customer experiences (e.g., good delivery vs. delivery delay), the following measure was of many implemented to quantify the difference in repurchase rates between positive and negative feedback within the same category:

```text
Delta Product = 
VAR GoodProduct =
    CALCULATE(
        [Repurchase],
        'analysis all'[pos_message] = "Product Quality")

VAR NegativeProduct =
    CALCULATE(
        [Repurchase],
        'analysis all'[neg_message] IN {
            "Product Damage",
            "Product Quality",
            "Product Mismatch",
            "Product Missing"})

RETURN
    GoodProduct - NegativeProduct
```

Sliders were added to allow users to filter out categories below the recommended sampling threshold, accompanied by an explanatory message indicating the threshold used.

A repurchase-rate-by-time table was considered but ultimately omitted. Because repurchases are attributed to the customer's initial purchase for the purposes of this analysis, subsequent repurchases are associated with the date of the original order. As a result, a temporal visualization would produce an apparent decline in repurchase rates that is largely an artifact of the methodology rather than a genuine trend.

Analysis of additional relationships, such as repurchase rate by state or product, was outside the scope of this project. However, these dimensions could be incorporated in future analyses if they provide meaningful additional insight into the factors associated with customer retention.

[← View Results](README.md)
