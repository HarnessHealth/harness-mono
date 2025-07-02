-- Harness Database Initialization Script

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Create schemas
CREATE SCHEMA IF NOT EXISTS harness;

-- Set search path
SET search_path TO harness, public;

-- Create user roles
CREATE ROLE harness_read;
CREATE ROLE harness_write;

-- Grant permissions
GRANT USAGE ON SCHEMA harness TO harness_read, harness_write;
GRANT SELECT ON ALL TABLES IN SCHEMA harness TO harness_read;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA harness TO harness_write;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA harness TO harness_write;

-- Create audit trigger function
CREATE OR REPLACE FUNCTION harness.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Log completed initialization
DO $$
BEGIN
    RAISE NOTICE 'Harness database initialization completed successfully';
END $$;