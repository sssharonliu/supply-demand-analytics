USE supply_chain_db;

SELECT 
    shipping_mode,
    COUNT(*) AS total_orders,
    -- Calculate the average delay
    ROUND(AVG(days_for_shipping_real - days_for_shipment_scheduled), 2) AS avg_days_late,
    -- Calculate the percentage of orders that were late
    ROUND(SUM(CASE WHEN days_for_shipping_real > days_for_shipment_scheduled THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS late_delivery_rate_pct
FROM orders
WHERE order_status = 'COMPLETE' -- Only look at finished deliveries
GROUP BY shipping_mode
ORDER BY late_delivery_rate_pct DESC;