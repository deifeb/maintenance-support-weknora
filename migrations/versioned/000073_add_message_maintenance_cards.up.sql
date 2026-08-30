ALTER TABLE messages ADD COLUMN IF NOT EXISTS maintenance_cards JSONB NOT NULL DEFAULT '[]'::jsonb;
