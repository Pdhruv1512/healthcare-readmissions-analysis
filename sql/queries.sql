-- =========================================================
-- U.S. Hospital Readmissions Analysis: SQL Queries
-- Database: hospitals.db (SQLite), built by build_database.py
-- Tables: hospitals, readmissions, footnotes
--
-- Key metric: Excess Readmission Ratio (ERR) = predicted / expected
-- readmission rate. ERR > 1 means more 30-day readmissions than expected
-- for a hospital with similar patients; ERR < 1 means fewer.
-- =========================================================

-- 1. DATA COVERAGE AND SUPPRESSION
-- Business question: How much of the data is usable, and why is the rest missing?
SELECT
    COALESCE(r.footnote, '-') AS footnote,
    COALESCE(f.description, 'Reported (no footnote)') AS meaning,
    COUNT(*) AS hospital_condition_rows,
    SUM(CASE WHEN r.excess_readmission_ratio IS NOT NULL THEN 1 ELSE 0 END) AS rows_with_err,
    ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM readmissions), 1) AS pct_of_rows
FROM readmissions r
LEFT JOIN footnotes f ON f.footnote = r.footnote
GROUP BY r.footnote, f.description
ORDER BY hospital_condition_rows DESC;


-- 2. READMISSION PERFORMANCE BY CONDITION
-- Business question: Which conditions have the highest readmission rates,
-- and for which do the most hospitals do worse than expected?
SELECT
    condition,
    COUNT(*) AS hospitals_reported,
    ROUND(AVG(predicted_readmission_rate), 2) AS avg_predicted_rate_pct,
    ROUND(AVG(expected_readmission_rate), 2) AS avg_expected_rate_pct,
    ROUND(AVG(excess_readmission_ratio), 4) AS avg_err,
    SUM(CASE WHEN excess_readmission_ratio > 1 THEN 1 ELSE 0 END) AS hospitals_worse_than_expected,
    ROUND(100.0 * SUM(CASE WHEN excess_readmission_ratio > 1 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_worse_than_expected
FROM readmissions
WHERE excess_readmission_ratio IS NOT NULL
GROUP BY condition
ORDER BY avg_predicted_rate_pct DESC;


-- 3. HOSPITALS ABOVE EXPECTED IN AT LEAST ONE CONDITION
-- Business question: How many hospitals have more readmissions than expected
-- (ERR > 1) for at least one condition?
-- Note: CMS's actual payment reduction compares each hospital to the median
-- ERR of its peer group, so ERR > 1 is a signal of risk, not the exact penalty rule.
WITH per_hospital AS (
    SELECT
        facility_id,
        COUNT(*) AS conditions_reported,
        SUM(CASE WHEN excess_readmission_ratio > 1 THEN 1 ELSE 0 END) AS conditions_over_1
    FROM readmissions
    WHERE excess_readmission_ratio IS NOT NULL
    GROUP BY facility_id
)
SELECT
    COUNT(*) AS hospitals_with_any_err,
    SUM(CASE WHEN conditions_over_1 >= 1 THEN 1 ELSE 0 END) AS hospitals_over_1_any_condition,
    ROUND(100.0 * SUM(CASE WHEN conditions_over_1 >= 1 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_over_1_any_condition,
    SUM(CASE WHEN conditions_over_1 >= 3 THEN 1 ELSE 0 END) AS hospitals_over_1_three_plus_conditions,
    ROUND(AVG(conditions_reported), 2) AS avg_conditions_reported
FROM per_hospital;


-- 4. STAR RATING VS. READMISSIONS
-- Business question: Do hospitals with higher CMS star ratings also have
-- fewer excess readmissions?
-- Note: readmissions are one of the five measure groups in the star rating,
-- so part of this relationship is built in. Hospitals missing from the
-- hospitals table (20 facilities, 120 rows) are excluded by the JOIN.
SELECT
    COALESCE(CAST(h.star_rating AS TEXT), 'Not rated') AS star_rating,
    COUNT(DISTINCT r.facility_id) AS hospitals,
    COUNT(*) AS hospital_condition_rows,
    ROUND(AVG(r.excess_readmission_ratio), 4) AS avg_err,
    ROUND(100.0 * SUM(CASE WHEN r.excess_readmission_ratio > 1 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_rows_worse_than_expected
FROM readmissions r
JOIN hospitals h ON h.facility_id = r.facility_id
WHERE r.excess_readmission_ratio IS NOT NULL
GROUP BY h.star_rating
ORDER BY h.star_rating IS NULL, h.star_rating;


-- 5. OWNERSHIP TYPE VS. READMISSIONS
-- Business question: Do for-profit, non-profit, and government hospitals differ?
-- Note: the 'Other' group has very few hospitals in this program; read it with caution.
SELECT
    CASE
        WHEN h.ownership LIKE 'Voluntary non-profit%' THEN 'Non-profit'
        WHEN h.ownership IN ('Proprietary', 'Physician') THEN 'For-profit'
        WHEN h.ownership LIKE 'Government%' THEN 'Government'
        ELSE 'Other (VA, DoD, Tribal)'
    END AS ownership_group,
    COUNT(DISTINCT r.facility_id) AS hospitals,
    ROUND(AVG(r.excess_readmission_ratio), 4) AS avg_err,
    ROUND(100.0 * SUM(CASE WHEN r.excess_readmission_ratio > 1 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_rows_worse_than_expected
FROM readmissions r
JOIN hospitals h ON h.facility_id = r.facility_id
WHERE r.excess_readmission_ratio IS NOT NULL
GROUP BY ownership_group
ORDER BY avg_err DESC;


-- 6. STATE RANKING
-- Business question: Which states perform best and worst on readmissions?
-- Only states with at least 20 reporting hospitals are ranked.
-- Note: Maryland hospitals appear in the data but are waived from HRRP payment
-- adjustments under the state's own payment model.
WITH state_stats AS (
    SELECT
        state,
        COUNT(DISTINCT facility_id) AS hospitals,
        ROUND(AVG(excess_readmission_ratio), 4) AS avg_err,
        ROUND(100.0 * SUM(CASE WHEN excess_readmission_ratio > 1 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_rows_worse_than_expected
    FROM readmissions
    WHERE excess_readmission_ratio IS NOT NULL
    GROUP BY state
    HAVING COUNT(DISTINCT facility_id) >= 20
)
SELECT
    RANK() OVER (ORDER BY avg_err ASC) AS rank_best_to_worst,
    state,
    hospitals,
    avg_err,
    pct_rows_worse_than_expected
FROM state_stats
ORDER BY rank_best_to_worst;


-- 7. HOSPITAL VOLUME VS. READMISSIONS (HEART FAILURE)
-- Business question: Do hospitals that treat more heart failure patients
-- have better readmission results? Hospitals are split into 4 equal-sized
-- groups by number of discharges (rows with a reported discharge count only).
WITH hf AS (
    SELECT
        facility_id,
        discharges,
        excess_readmission_ratio,
        NTILE(4) OVER (ORDER BY discharges) AS volume_quartile
    FROM readmissions
    WHERE condition = 'Heart failure'
      AND excess_readmission_ratio IS NOT NULL
      AND discharges IS NOT NULL
)
SELECT
    volume_quartile,
    COUNT(*) AS hospitals,
    MIN(discharges) AS min_discharges,
    MAX(discharges) AS max_discharges,
    ROUND(AVG(excess_readmission_ratio), 4) AS avg_err,
    ROUND(100.0 * SUM(CASE WHEN excess_readmission_ratio > 1 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_worse_than_expected
FROM hf
GROUP BY volume_quartile
ORDER BY volume_quartile;


-- 8. LOWEST AND HIGHEST HEART FAILURE EXCESS READMISSION RATIOS
-- Business question: Which larger hospitals stand out? Only hospitals with
-- at least 300 heart failure discharges are included, so results are stable.
WITH ranked AS (
    SELECT
        r.facility_name,
        r.state,
        h.star_rating,
        r.discharges,
        r.excess_readmission_ratio,
        r.predicted_readmission_rate,
        RANK() OVER (ORDER BY r.excess_readmission_ratio ASC) AS best_rank,
        RANK() OVER (ORDER BY r.excess_readmission_ratio DESC) AS worst_rank
    FROM readmissions r
    LEFT JOIN hospitals h ON h.facility_id = r.facility_id
    WHERE r.condition = 'Heart failure'
      AND r.excess_readmission_ratio IS NOT NULL
      AND r.discharges >= 300
)
SELECT
    CASE WHEN best_rank <= 5 THEN 'Lowest ERR' ELSE 'Highest ERR' END AS group_label,
    facility_name,
    state,
    star_rating,
    discharges,
    excess_readmission_ratio,
    predicted_readmission_rate
FROM ranked
WHERE best_rank <= 5 OR worst_rank <= 5
ORDER BY excess_readmission_ratio;


-- 9. NEW JERSEY HEART FAILURE RANKING
-- Business question: New Jersey ranked 2nd worst in the country. Which NJ
-- hospitals do best and worst on heart failure readmissions?
SELECT
    r.facility_name,
    h.city,
    r.discharges,
    r.excess_readmission_ratio AS err,
    RANK() OVER (ORDER BY r.excess_readmission_ratio) AS rank_in_nj
FROM readmissions r
LEFT JOIN hospitals h ON h.facility_id = r.facility_id
WHERE r.state = 'NJ'
  AND r.condition = 'Heart failure'
  AND r.excess_readmission_ratio IS NOT NULL
ORDER BY err;
