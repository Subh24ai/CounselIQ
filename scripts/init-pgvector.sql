-- Enable the pgvector extension on database initialisation.
-- This runs once, the first time the postgres data volume is created.
CREATE EXTENSION IF NOT EXISTS vector;
