-- ============================================================================
-- Intellexa Memory System - Simplified Setup (Run First)
-- Run this in Supabase SQL Editor
-- ============================================================================

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================================
-- 1. TABLES
-- ============================================================================

-- User documents table
CREATE TABLE IF NOT EXISTS user_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    file_type TEXT NOT NULL,
    file_size BIGINT NOT NULL,
    storage_path TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    error_message TEXT,
    chunk_count INTEGER DEFAULT 0,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Document chunks table
CREATE TABLE IF NOT EXISTS document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES user_documents(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    content_summary TEXT,
    page_number INTEGER,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Document embeddings table
CREATE TABLE IF NOT EXISTS document_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chunk_id UUID NOT NULL REFERENCES document_chunks(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES user_documents(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,
    embedding vector(768),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_user_documents_user_id ON user_documents(user_id);
CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id ON document_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_document_chunks_user_id ON document_chunks(user_id);
CREATE INDEX IF NOT EXISTS idx_document_embeddings_user_id ON document_embeddings(user_id);
CREATE INDEX IF NOT EXISTS idx_document_embeddings_document_id ON document_embeddings(document_id);

-- Vector similarity index
CREATE INDEX IF NOT EXISTS idx_document_embeddings_vector 
ON document_embeddings 
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- ============================================================================
-- 2. ENABLE RLS
-- ============================================================================

ALTER TABLE user_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_embeddings ENABLE ROW LEVEL SECURITY;

-- ============================================================================
-- 3. SERVICE ROLE POLICIES (Bypasses RLS - for backend)
-- ============================================================================

-- Drop existing policies if they exist
DROP POLICY IF EXISTS "Service role full access on user_documents" ON user_documents;
DROP POLICY IF EXISTS "Service role full access on document_chunks" ON document_chunks;
DROP POLICY IF EXISTS "Service role full access on document_embeddings" ON document_embeddings;

CREATE POLICY "Service role full access on user_documents"
ON user_documents FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "Service role full access on document_chunks"
ON document_chunks FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "Service role full access on document_embeddings"
ON document_embeddings FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ============================================================================
-- 4. SIMILARITY SEARCH FUNCTION
-- ============================================================================

-- Drop existing function if it exists (to avoid signature mismatch)
DROP FUNCTION IF EXISTS match_document_embeddings(vector, text, integer);
DROP FUNCTION IF EXISTS match_document_embeddings(vector, text);

CREATE OR REPLACE FUNCTION match_document_embeddings(
    query_embedding vector(768),
    match_user_id text,
    match_count int DEFAULT 5
)
RETURNS TABLE (
    chunk_id uuid,
    document_id uuid,
    content text,
    filename text,
    file_type text,
    page_number int,
    similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        dc.id as chunk_id,
        ud.id as document_id,
        dc.content,
        ud.filename,
        ud.file_type,
        dc.page_number,
        1 - (de.embedding <=> query_embedding) as similarity
    FROM document_embeddings de
    JOIN document_chunks dc ON de.chunk_id = dc.id
    JOIN user_documents ud ON de.document_id = ud.id
    WHERE de.user_id = match_user_id
    AND ud.status = 'ready'
    ORDER BY de.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- ============================================================================
-- 5. STORAGE BUCKET
-- ============================================================================

INSERT INTO storage.buckets (id, name, public)
VALUES ('user-uploads', 'user-uploads', false)
ON CONFLICT (id) DO NOTHING;

-- Drop existing storage policy if exists
DROP POLICY IF EXISTS "Service role full access on storage" ON storage.objects;

CREATE POLICY "Service role full access on storage"
ON storage.objects FOR ALL TO service_role
USING (bucket_id = 'user-uploads')
WITH CHECK (bucket_id = 'user-uploads');

-- ============================================================================
-- DONE! 
-- Since you're using service_role key in backend, RLS is bypassed.
-- ============================================================================
