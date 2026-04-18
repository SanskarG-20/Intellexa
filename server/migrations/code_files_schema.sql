-- ============================================================================
-- Code Space SQL Schema
-- Creates tables for storing user code files
-- Run this in Supabase SQL Editor
-- ============================================================================

-- Create code_files table
CREATE TABLE IF NOT EXISTS code_files (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    path TEXT NOT NULL DEFAULT '/',
    content TEXT,
    language TEXT DEFAULT 'javascript',
    is_folder BOOLEAN DEFAULT FALSE,
    parent_id UUID REFERENCES code_files(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes for faster queries
CREATE INDEX IF NOT EXISTS idx_code_files_user_id ON code_files(user_id);
CREATE INDEX IF NOT EXISTS idx_code_files_path ON code_files(path);
CREATE INDEX IF NOT EXISTS idx_code_files_parent_id ON code_files(parent_id);

-- Create unique constraint for filename per user per path
CREATE UNIQUE INDEX IF NOT EXISTS idx_code_files_unique_name 
ON code_files(user_id, path, filename) 
WHERE is_folder = FALSE;

-- Create updated_at trigger
CREATE OR REPLACE FUNCTION update_code_file_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_code_files_updated_at ON code_files;
CREATE TRIGGER trigger_code_files_updated_at
    BEFORE UPDATE ON code_files
    FOR EACH ROW
    EXECUTE FUNCTION update_code_file_timestamp();

-- Enable RLS (Row Level Security)
ALTER TABLE code_files ENABLE ROW LEVEL SECURITY;

-- Drop existing policies if they exist (for re-runs)
DROP POLICY IF EXISTS "Users can view their own code files" ON code_files;
DROP POLICY IF EXISTS "Users can insert their own code files" ON code_files;
DROP POLICY IF EXISTS "Users can update their own code files" ON code_files;
DROP POLICY IF EXISTS "Users can delete their own code files" ON code_files;
DROP POLICY IF EXISTS "Service role has full access" ON code_files;
DROP POLICY IF EXISTS "Allow all for service_role" ON code_files;

-- Simple service role policy (backend uses service role key to bypass RLS)
CREATE POLICY "Allow all for service_role" ON code_files
    FOR ALL USING (true);

-- Grant permissions
GRANT ALL ON code_files TO authenticated;
GRANT ALL ON code_files TO service_role;
GRANT USAGE ON SCHEMA public TO authenticated;
GRANT USAGE ON SCHEMA public TO service_role;

