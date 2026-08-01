-- DuckDB example. Keep raw event time UTC; local sessions are derived dimensions.
-- Replace the glob root with the mounted Silver release path.

CREATE OR REPLACE VIEW silver_klines AS
SELECT
    exchange,
    market_path,
    dataset,
    dataset_kind,
    symbol,
    interval,
    CAST(open_time_us AS BIGINT) AS open_time_us,
    CAST(close_time_exclusive_us AS BIGINT) AS close_time_exclusive_us,
    CAST(available_time_us AS BIGINT) AS available_time_us,
    to_timestamp(CAST(open_time_us AS DOUBLE) / 1000000.0) AS open_time_utc,
    to_timestamp(CAST(available_time_us AS DOUBLE) / 1000000.0) AS available_time_utc,
    CAST(open AS DECIMAL(38, 18)) AS open,
    CAST(high AS DECIMAL(38, 18)) AS high,
    CAST(low AS DECIMAL(38, 18)) AS low,
    CAST(close AS DECIMAL(38, 18)) AS close,
    TRY_CAST(base_volume AS DECIMAL(38, 18)) AS base_volume,
    TRY_CAST(quote_volume AS DECIMAL(38, 18)) AS quote_volume,
    TRY_CAST(trade_count AS BIGINT) AS trade_count,
    source_sha256,
    archive_id,
    pipeline_version
FROM read_csv_auto(
    '02_NORMALIZED_SILVER/**/*.csv.gz',
    header = true,
    union_by_name = true,
    all_varchar = true
);

-- Availability-safe research input. A caller supplies the simulated decision time.
-- SELECT * FROM silver_klines WHERE available_time_us <= :decision_time_us;

-- Example venue/source comparison; do not collapse these into one close column.
CREATE OR REPLACE VIEW aligned_price_sources AS
SELECT
    symbol,
    open_time_us,
    max(close) FILTER (WHERE market_path = 'spot' AND dataset = 'klines') AS spot_close,
    max(close) FILTER (WHERE market_path = 'futures/um' AND dataset = 'klines') AS um_trade_close,
    max(close) FILTER (WHERE dataset = 'markPriceKlines') AS mark_close,
    max(close) FILTER (WHERE dataset = 'indexPriceKlines') AS index_close,
    max(close) FILTER (WHERE dataset = 'premiumIndexKlines') AS premium_close
FROM silver_klines
GROUP BY symbol, open_time_us;
