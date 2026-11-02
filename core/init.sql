CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE TABLE IF NOT EXISTS images (
  id         BIGSERIAL PRIMARY KEY,
  name       TEXT NOT NULL,
  filename   TEXT UNIQUE NOT NULL,
  member_id  INT NOT NULL,
  ai_no      INT NOT NULL,
  s3_key     TEXT NOT NULL,
  source     TEXT DEFAULT 'auto',
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS images_name_trgm ON images USING gin (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS images_created   ON images (created_at DESC);
