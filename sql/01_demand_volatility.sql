USE supply_chain_db;

WITH MonthlyDemand AS (
    SELECT 
        category_name,
        DATE_FORMAT(STR_TO_DATE(order_date_dateorders, '%m/%d/%Y %H:%i'), '%Y-%m') AS month,
        SUM(order_item_quantity) AS monthly_units
    FROM orders
    WHERE order_status NOT IN ('CANCELED', 'SUSPECTED_FRAUD')
    GROUP BY category_name, month
),
Stats AS (
    SELECT 
        category_name,
        AVG(monthly_units) AS avg_monthly_demand,
        STDDEV(monthly_units) AS std_monthly_demand
    FROM MonthlyDemand
    GROUP BY category_name
)
SELECT 
    category_name,
    ROUND(avg_monthly_demand, 2) AS avg_demand,
    ROUND(std_monthly_demand, 2) AS volatility_std,
    ROUND(std_monthly_demand / avg_monthly_demand, 4) AS cv_score
FROM Stats
WHERE avg_monthly_demand > 0
ORDER BY cv_score DESC;