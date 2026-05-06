CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Normalized FX quotes (IRR per 1 unit of quote_ccy).
-- tier: 'official' or 'market'
CREATE TABLE IF NOT EXISTS rates (
  ts          TIMESTAMPTZ NOT NULL,
  source      TEXT        NOT NULL,
  tier        TEXT        NOT NULL,
  base_ccy    TEXT        NOT NULL,
  quote_ccy   TEXT        NOT NULL,
  bid         NUMERIC,
  ask         NUMERIC,
  mid         NUMERIC,
  meta        JSONB       NOT NULL DEFAULT '{}'::jsonb,
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (ts, source, tier, base_ccy, quote_ccy)
);

SELECT create_hypertable('rates', 'ts', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS rates_lookup_idx
  ON rates (tier, base_ccy, quote_ccy, ts DESC);

-- Alerts emitted by signal detection (spikes, spread widening, etc.)
CREATE TABLE IF NOT EXISTS alerts (
  id          BIGSERIAL   PRIMARY KEY,
  ts          TIMESTAMPTZ NOT NULL,
  rule_id     TEXT        NOT NULL,
  severity    TEXT        NOT NULL,
  tier        TEXT        NOT NULL,
  source      TEXT        NOT NULL,
  base_ccy    TEXT        NOT NULL,
  quote_ccy   TEXT        NOT NULL,
  message     TEXT        NOT NULL,
  context     JSONB       NOT NULL DEFAULT '{}'::jsonb,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS alerts_dedup_idx
  ON alerts (ts, rule_id, tier, source, base_ccy, quote_ccy);
CREATE INDEX IF NOT EXISTS alerts_lookup_idx
  ON alerts (base_ccy, quote_ccy, ts DESC);

-- Per-source health (freshness + error tracking)
CREATE TABLE IF NOT EXISTS source_health (
  source        TEXT PRIMARY KEY,
  tier          TEXT NOT NULL,
  last_success  TIMESTAMPTZ,
  last_error    TIMESTAMPTZ,
  error_count   BIGINT NOT NULL DEFAULT 0,
  last_message  TEXT
);

-- Optional rollup: 1h OHLC for mid (best effort)
CREATE MATERIALIZED VIEW IF NOT EXISTS rates_1h
WITH (timescaledb.continuous) AS
SELECT
  time_bucket('1 hour', ts) AS bucket,
  tier,
  base_ccy,
  quote_ccy,
  first(mid, ts) AS open,
  max(mid) AS high,
  min(mid) AS low,
  last(mid, ts) AS close
FROM rates
WHERE mid IS NOT NULL
GROUP BY bucket, tier, base_ccy, quote_ccy;

