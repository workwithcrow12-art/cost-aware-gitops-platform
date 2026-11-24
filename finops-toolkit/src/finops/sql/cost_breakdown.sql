-- The table uses the legacy CUR Athena integration schema.
WITH usage AS (
    SELECT
        CASE WHEN line_item_usage_start_date >= TIMESTAMP '$midpoint 00:00:00'
            THEN 'current' ELSE 'previous' END AS period,
        CAST(line_item_usage_start_date AS DATE) AS usage_date,
        $env_expr AS environment,
        $team_expr AS team,
        COALESCE(NULLIF(TRIM(line_item_product_code), ''), 'unallocated') AS service,
        CAST(line_item_unblended_cost AS DECIMAL(38, 12)) AS cost
    FROM "$table"
    WHERE $partition_filter
        line_item_usage_start_date >= TIMESTAMP '$start 00:00:00'
        AND line_item_usage_start_date < TIMESTAMP '$end 00:00:00'
        AND COALESCE(line_item_line_item_type, 'Usage') IN (
            'Usage', 'DiscountedUsage', 'SavingsPlanCoveredUsage'
        )
), coverage AS (
    SELECT period, COUNT(DISTINCT usage_date) AS usage_days
    FROM usage
    GROUP BY period
)
SELECT u.period, u.environment, u.team, u.service, SUM(u.cost) AS cost, c.usage_days
FROM usage u
JOIN coverage c ON u.period = c.period
GROUP BY u.period, u.environment, u.team, u.service, c.usage_days
