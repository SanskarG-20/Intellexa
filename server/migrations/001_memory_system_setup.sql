-- ============================================================================
-- Intellexa Memory System - Database Setup with RLS Policies
-- Run this in Supabase SQL Editor
-- ============================================================================

-- Enable pgvector extension (if not already enabled)
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================================
-- 1. USER_DOCUMENTS TABLE
-- Stores metadata about uploaded documents
-- ============================================================================

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

-- Index for faster user queries
CREATE INDEX IF NOT EXISTS idx_user_documents_user_id ON user_documents(user_id);
CREATE INDEX IF NOT EXISTS idx_user_documents_status ON user_documents(status);

-- ============================================================================
-- 2. DOCUMENT_CHUNKS TABLE
-- Stores text chunks extracted from documents
-- ============================================================================

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

-- Index for faster document and user queries
CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id ON document_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_document_chunks_user_id ON document_chunks(user_id);

-- ============================================================================
-- 3. DOCUMENT_EMBEDDINGS TABLE
-- Stores vector embeddings for document chunks
-- ============================================================================

CREATE TABLE IF NOT EXISTS document_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chunk_id UUID NOT NULL REFERENCES document_chunks(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES user_documents(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,
    embedding vector(768),  -- Gemini embedding dimension
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for vector similarity search (using ivfflat for approximate nearest neighbor)
CREATE INDEX IF NOT EXISTS idx_document_embeddings_vector 
ON document_embeddings 
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Index for user and document queries
CREATE INDEX IF NOT EXISTS idx_document_embeddings_user_id ON document_embeddings(user_id);
CREATE INDEX IF NOT EXISTS idx_document_embeddings_document_id ON document_embeddings(document_id);

-- ============================================================================
-- 4. ROW LEVEL SECURITY (RLS) POLICIES
-- ============================================================================

-- Enable RLS on all tables
ALTER TABLE user_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_embeddings ENABLE ROW LEVEL SECURITY;

-- Helper function to get user ID from JWT claims
CREATE OR REPLACE FUNCTION auth.jwt_user_id() RETURNS text AS $$
BEGIN
    -- Try auth.uid() first (Supabase built-in)
    IF auth.uid() IS NOT NULL THEN
        RETURN auth.uid()::text;
    END IF;
    -- Fallback to JWT claims
    RETURN current_setting('request.jwt.claims', true)::jsonb ->> 'sub';
EXCEPTION WHEN OTHERS THEN
    RETURN NULL;
END;
$$ LANGUAGE plpgsql STABLE;

-- ============================================================================
-- POLICIES FOR user_documents
-- ============================================================================

-- Allow service role full access (for backend operations)
CREATE POLICY "Service role has full access"
ON user_documents
FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

-- Allow users to insert their own documents
CREATE POLICY "Users can insert own documents"
ON user_documents
FOR INSERT
WITH CHECK (user_id = auth.jwt_user_id());

-- Allow users to read their own documents
CREATE POLICY "Users can read own documents"
ON user_documents
FOR SELECT
USING (user_id = auth.jwt_user_id());

-- Allow users to update their own documents
CREATE POLICY "Users can update own documents"
ON user_documents
FOR UPDATE
USING (user_id = auth.jwt_user_id());

-- Allow users to delete their own documents
CREATE POLICY "Users can delete own documents"
ON user_documents
FOR DELETE
USING (user_id = auth.jwt_user_id());

-- ============================================================================
-- POLICIES FOR document_chunks
-- ============================================================================

-- Allow service role full access
CREATE POLICY "Service role has full access"
ON document_chunks
FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

-- Allow users to insert their own chunks
CREATE POLICY "Users can insert own chunks"
ON document_chunks
FOR INSERT
WITH CHECK (user_id = auth.jwt_user_id());

-- Allow users to read their own chunks
CREATE POLICY "Users can read own chunks"
ON document_chunks
FOR SELECT
USING (user_id = auth.jwt_user_id());

-- Allow users to delete their own chunks
CREATE POLICY "Users can delete own chunks"
ON document_chunks
FOR DELETE
USING (user_id = auth.jwt_user_id());

-- ============================================================================
-- POLICIES FOR document_embeddings
-- ============================================================================

-- Allow service role full access
CREATE POLICY "Service role has full access"
ON document_embeddings
FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

-- Allow users to insert their own embeddings
CREATE POLICY "Users can insert own embeddings"
ON document_embeddings
FOR INSERT
WITH CHECK (user_id = auth.jwt_user_id());

-- Allow users to read their own embeddings
CREATE POLICY "Users can read own embeddings"
ON document_embeddings
FOR SELECT
USING (user_id = auth.jwt_user_id());

-- Allow users to delete their own embeddings
CREATE POLICY "Users can delete own embeddings"
ON document_embeddings
FOR DELETE
USING (user_id = auth.jwt_user_id());

-- ============================================================================
-- 5. RPC FUNCTION FOR VECTOR SIMILARITY SEARCH
-- ============================================================================

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
-- 6. STORAGE BUCKET POLICIES
-- ============================================================================

-- Create storage bucket if it doesn't exist
INSERT INTO storage.buckets (id, name, public)
VALUES ('user-uploads', 'user-uploads', false)
ON CONFLICT (id) DO NOTHING;

-- Policy: Service role has full access to storage
CREATE POLICY "Service role has full access"
ON storage.objects
FOR ALL
TO service_role
USING (bucket_id = 'user-uploads')
WITH CHECK (bucket_id = 'user-uploads');

-- Policy: Users can upload files to their own folder
CREATE POLICY "Users can upload to own folder"
ON storage.objects
FOR INSERT
WITH CHECK (
    bucket_id = 'user-uploads' 
    AND (storage.foldername(name))[1] = auth.uid()::text
);

-- Policy: Users can read their own files
CREATE POLICY "Users can read own files"
ON storage.objects
FOR SELECT
USING (
    bucket_id = 'user-uploads' 
    AND (storage.foldername(name))[1] = auth.uid()::text
);

-- Policy: Users can delete their own files
CREATE POLICY "Users can delete own files"
ON storage.objects
FOR DELETE
USING (
    bucket_id = 'user-uploads' 
    AND (storage.foldername(name))[1] = auth.uid()::text
);

-- ============================================================================
-- DONE! The database is now set up with proper RLS policies.
-- IMPORTANT: Since you're using the service_role key in your backend,
-- the service_role policies allow full access, bypassing RLS.
-- ============================================================================
