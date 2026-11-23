-- HyFleet: all SQL queries used in the project
-- Database: data/fleet.db (SQLite), built in section 4 of notebooks/hyfleet_analysis.ipynb.
-- Open it in DB Browser for SQLite, or run: sqlite3 data/fleet.db < sql/queries.sql


-- SELECT, WHERE, ORDER BY, LIMIT
SELECT duty_id, vehicle_id, duty_date, distance_km, fuel_litres
FROM duties
WHERE distance_km > 600
ORDER BY distance_km DESC
LIMIT 5;

-- GROUP BY and HAVING
SELECT vehicle_id,
       COUNT(*)                   AS duties,
       ROUND(SUM(distance_km))    AS annual_km,
       ROUND(AVG(distance_km), 1) AS avg_daily_km
FROM duties
GROUP BY vehicle_id
HAVING SUM(distance_km) > 100000
ORDER BY annual_km DESC;

-- JOIN tables together
SELECT dp.depot_name,
       v.vehicle_type,
       COUNT(DISTINCT v.vehicle_id)                         AS vehicles,
       ROUND(SUM(d.distance_km))                            AS total_km,
       ROUND(100.0 * SUM(d.fuel_litres) / SUM(d.distance_km), 1) AS l_per_100km
FROM duties d
JOIN vehicles v  ON d.vehicle_id = v.vehicle_id
JOIN depots   dp ON v.depot_id   = dp.depot_id
GROUP BY dp.depot_name, v.vehicle_type
ORDER BY dp.depot_name, v.vehicle_type;

-- CASE WHEN: create categories
SELECT CASE
         WHEN distance_km <= 200 THEN '1: up to 200 km'
         WHEN distance_km <= 400 THEN '2: 201 to 400 km'
         ELSE '3: over 400 km'
       END AS range_band,
       COUNT(*) AS duties,
       ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM duties), 1) AS pct_of_duties
FROM duties
GROUP BY range_band
ORDER BY range_band;

-- CTEs and window functions
WITH vehicle_km AS (
    SELECT v.depot_id, d.vehicle_id, SUM(d.distance_km) AS annual_km
    FROM duties d
    JOIN vehicles v USING (vehicle_id)
    GROUP BY v.depot_id, d.vehicle_id
),
ranked AS (
    SELECT depot_id, vehicle_id, ROUND(annual_km) AS annual_km,
           RANK() OVER (PARTITION BY depot_id ORDER BY annual_km DESC) AS rank_in_depot,
           ROUND(100.0 * annual_km / SUM(annual_km) OVER (PARTITION BY depot_id), 1) AS pct_of_depot_km
    FROM vehicle_km
)
SELECT * FROM ranked
WHERE rank_in_depot <= 3
ORDER BY depot_id, rank_in_depot;

-- Dates in SQL: join each duty to its weekly diesel price
WITH duty_week AS (
    SELECT d.*, date(d.duty_date, '-6 days', 'weekday 1') AS week_start
    FROM duties d
)
SELECT strftime('%Y-%m', dw.duty_date)                        AS month,
       ROUND(SUM(dw.fuel_litres))                             AS litres,
       ROUND(AVG(p.pump_ppl), 1)                              AS avg_pump_ppl,
       ROUND(SUM(dw.fuel_litres * p.pump_ppl / 100 / 1.2))    AS fuel_cost_gbp
FROM duty_week dw
JOIN diesel_prices p ON dw.week_start = p.week_start
GROUP BY month
ORDER BY month;

-- Check: no duties lost in the price join
SELECT (SELECT COUNT(*) FROM duties) AS duties_total,
       COUNT(*) AS duties_matched_to_a_price
FROM duties d
JOIN diesel_prices p ON date(d.duty_date, '-6 days', 'weekday 1') = p.week_start;
