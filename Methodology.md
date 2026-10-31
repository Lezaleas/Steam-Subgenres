# Technical Methodology

# 1. Exploratory Pre-Analysis and Goal Setting

A core objective of this study was to determine whether breakout hits serve as causal pioneers that establish new subgenres, or if they act as catalytic inflection points capitalizing on pre-existing latent demand within the market.
With the data indicating that breakout hits capitalize on existing demand rather than creating it, the analysis shifted to systematically identifying high-grossing subgenres across the platform.

linktothesubredditthreadhere
On the other hand, indie and solo developers have expressed widespread skepticism regarding generative AI integration, citing concerns around store compliance penalties, player backlash, and brand risk. Consequently, an empirical study was conducted to examine the presence of AI disclosures on Steam storefronts and assess its correlation with title profitability and sales performance.

# 2. Data Gathering

Publisher-level attributes were retrieved using the Gamalytic API via an automated collection script.
This dataset includes primary publisher identifiers, standardized tier classifications (AAA, Indie, Hobbyist), base pricing, and estimated unit sales.

pythongscriptlinkhere
To document developer disclosures regarding artificial intelligence, target HTML elements were extracted from individual Steam store pages using custom web scraping scripts.
The raw text of each disclosure was preserved to perform NLP classification and semantic categorization via Large Language Models..

datasetlinkhere
Game-level genre taxonomies were integrated from a continuously updated Steam games dataset.
This dataset captures daily snapshots of crowdsourced community tags and subgenre classifications associated with each title.

![Data Structure](pictures/data_structure.webp)

# 3. Data Cleaning & Preparation

In the steam games dataset, titles with a price of $0 were excluded from the dataset, as free-to-play games utilize fundamentally distinct monetization models.

The column for subgenres 

# 5. Review Categorization Using an LLM in Python

**Ollama:** About 30,000 reviews contained messages written in Brazilian Portuguese. A locally hosted LLM, accessed through Ollama, was used to classify these messages into 12 distinct categories, such as delivery not received and easy service, allowing qualitative review text to be transformed into structured data for quantitative analysis.

The category taxonomy was developed manually through iterative trial runs. Initial classifications were manually inspected and the categories were progressively refined until they provided a useful balance between specificity and consistency.

The initial model selected for classification produced accurate results, but its computational requirements would have resulted in an estimated processing time of approximately 20 days. A compromise was found with **Qwen2.5:3B**, which provided sufficiently high classification precision while being substantially faster and clearing the task in 2 days. Classification quality was manually checked on trial outputs before processing the full dataset.

**Python:** Because positive and negative reviews required different classification taxonomies, two filtered copies of the reviews table were created in PostgreSQL, containing only reviews within the respective score ranges. These tables were then exported to CSV and processed in Python. The script handled prompting the LLM with each review message, extracting the resulting category, and periodically saving checkpoints so that processing could be resumed without losing completed classifications.

The Python script initially also validated the model's output against the predefined category list, since the model occasionally generated categories outside the intended taxonomy. This validation step was ultimately removed after it became apparent that these occasional category variations could be more effectively consolidated into the final taxonomy in SQL.

The resulting classified datasets were saved as two CSV files, containing the review messages alongside their assigned categories. These files were then imported back into PostgreSQL using pgAdmin.

**[View the complete Python script](./pictures/review_categorization.py)**

---

# 6. Final Data Preparations

For brevity, the following chapters focus on the processing and analysis of positive messages. The negative messages underwent the same general processing pipeline.

The positive messages were joined to the main orders table using order_id as the linking key. Integrity checks were performed after the joins to verify that the relationships behaved as expected and that no orders were left without an assigned message category:
```sql
UPDATE public.orders o
SET pos_message = p.issue_category
FROM public.pos_messages p
WHERE p.order_id = o.order_id;
```

The original message categories were consolidated into broader analytical categories to reduce fragmentation and improve interpretability. The mapping was performed in SQL as follows:
```sql
UPDATE public.orders
SET pos_message = CASE
    WHEN issue_category LIKE 'RECOMMEN%' THEN 'Unspecified'
    WHEN issue_category LIKE 'SKIPPED' THEN 'Unspecified'
    WHEN issue_category LIKE 'OTHER' THEN 'Unspecified'
    WHEN issue_category LIKE '%PRICE%' THEN 'Value/Price'
    WHEN issue_category LIKE '%VALUE%' THEN 'Value/Price'
    WHEN issue_category LIKE '%SERVICE%' THEN 'Easy/Good Service'
    WHEN issue_category LIKE '%PURCHASE%' THEN 'Easy/Good Service'
    WHEN issue_category LIKE '%PRODUCT%' THEN 'Product Quality'
    WHEN issue_category LIKE '%PACKAGE%' THEN 'Product Quality'
    WHEN issue_category LIKE '%DELIVERY%' THEN 'Good Delivery'
    ELSE pos_message
END;

```

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
