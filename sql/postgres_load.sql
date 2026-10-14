-- PostgreSQL loading (psql, from the project root). Run 01_schema.sql first.
\copy customers FROM 'data/customers.csv' WITH (FORMAT csv, HEADER true)
\copy customer_months FROM 'data/customer_months.csv' WITH (FORMAT csv, HEADER true)
ANALYZE customers;
ANALYZE customer_months;

-- The queries in 02-05 use standard SQL (CTEs, window functions, CASE). Known differences to adapt
-- for PostgreSQL: named parameters ":snap" become $1 or psql variables, and ROUND(x, n) needs a
-- NUMERIC cast (ROUND(CAST(x AS NUMERIC), n)). The Python runner executes the SQLite dialect.
