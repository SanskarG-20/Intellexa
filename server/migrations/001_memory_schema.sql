-- ============================================================================
-- Multimodal Context Memory System - Database Schema
-- ============================================================================
-- This migration creates the necessary tables and functions for the memory
-- system that stores and retrieves user-uploaded document context.
--
-- PREREQUISITE: Enable pgvector extension in Supabase dashboard first:
-- Go to Database > Extensions > Enable 'vector'
-- ============================================================================

-- Enable pgvector extension (if not already enabled)
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================================
-- Table: user_documents
-- Stores metadata about uploaded documents
-- ============================================================================
CREATE TABLE IF NOT EXISTS user_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    file_type TEXT NOT NULL CHECK (file_type IN ('pdf', 'image', 'video', 'text')),
    file_size BIGINT,
    storage_path TEXT NOT NULL,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'ready', 'failed')),
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for user_documents
CREATE INDEX IF NOT EXISTS idx_user_documents_user_id ON user_documents(user_id);
CREATE INDEX IF NOT EXISTS idx_user_documents_status ON user_documents(status);
CREATE INDEX IF NOT EXISTS idx_user_documents_created_at ON user_documents(created_at DESC);

-- ============================================================================
-- Table: document_chunks
-- Stores text chunks extracted from documents
-- ============================================================================
CREATE TABLE IF NOT EXISTS document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES user_documents(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    content_summary TEXT,
    page_number INTEGER,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for document_chunks
CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id ON document_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_document_chunks_user_id ON document_chunks(user_id);

-- ============================================================================
-- Table: document_embeddings
-- Stores vector embeddings for document chunks using pgvector
-- ============================================================================
CREATE TABLE IF NOT EXISTS document_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chunk_id UUID REFERENCES document_chunks(id) ON DELETE CASCADE,
    document_id UUID REFERENCES user_documents(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,
    embedding vector(768),  -- Gemini embedding dimension
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create HNSW index for fast cosine similarity search
CREATE INDEX IF NOT EXISTS idx_document_embeddings_vector ON document_embeddings 
    USING hnsw (embedding vector_cosine_ops);

-- Indexes for document_embeddings
CREATE INDEX IF NOT EXISTS idx_document_embeddings_user_id ON document_embeddings(user_id);
CREATE INDEX IF NOT EXISTS idx_document_embeddings_document_id ON document_embeddings(document_id);

-- ============================================================================
-- Function: match_document_embeddings
-- Performs similarity search to find relevant document chunks
-- ============================================================================
CREATE OR REPLACE FUNCTION match_document_embeddings(
    query_embedding vector,
    match_user_id text,
    match_count int DEFAULT 5
)
RETURNS TABLE (
    id uuid,
    chunk_id uuid,
    document_id uuid,
    content text,
    filename text,
    file_type text,
    similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        de.id,
        de.chunk_id,
        de.document_id,
        dc.content,
        ud.filename,
        ud.file_type,
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
-- Function: get_document_chunk_count
-- Returns the number of chunks for a given document
-- ============================================================================
CREATE OR REPLACE FUNCTION get_document_chunk_count(doc_id uuid)
RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    chunk_count integer;
BEGIN
    SELECT COUNT(*) INTO chunk_count
    FROM document_chunks
    WHERE document_id = doc_id;
    
    RETURN chunk_count;
END;
$$;

-- ============================================================================
-- Trigger: update_updated_at
-- Automatically updates the updated_at column on row modification
-- ============================================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_user_documents_updated_at
    BEFORE UPDATE ON user_documents
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- Row Level Security (RLS) Policies
-- Ensures users can only access their own documents
-- ============================================================================

-- Enable RLS on tables
ALTER TABLE user_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_embeddings ENABLE ROW LEVEL SECURITY;

-- Policy: Users can only see their own documents
CREATE POLICY "Users can view own documents" ON user_documents
    FOR SELECT USING (user_id = current_setting('request.jwt.claims->>sub', true));

CREATE POLICY "Users can insert own documents" ON user_documents
    FOR INSERT WITH CHECK (user_id = current_setting('request.jwt.claims->>sub', true));

CREATE POLICY "Users can delete own documents" ON user_documents
    FOR DELETE USING (user_id = current_setting('request.jwt.claims->>sub', true));

-- Policy: Users can only see their own chunks
CREATE POLICY "Users can view own chunks" ON document_chunks
    FOR SELECT USING (user_id = current_setting('request.jwt.claims->>sub', true));

-- Policy: Users can only see their own embeddings
CREATE POLICY "Users can view own embeddings" ON document_embeddings
    FOR SELECT USING (user_id = current_setting('request.jwt.claims->>sub', true));

-- ============================================================================
-- Grant necessary permissions for service role (backend)
-- ============================================================================
-- Note: In Supabase, the service_role key bypasses RLS, so these grants
-- are for authenticated users if needed.

-- ============================================================================
-- Storage Bucket Setup (Run in Supabase Dashboard SQL Editor)
-- ============================================================================
-- Create a storage bucket for user uploads:
-- INSERT INTO storage.buckets (id, name, public) VALUES ('user-uploads', 'user-uploads', false);

-- Storage policies for the bucket:
-- CREATE POLICY "Users can upload own files"
-- ON storage.objects FOR INSERT
-- WITH CHECK (bucket_id = 'user-uploads' AND auth.uid()::text = (storage.foldername(name))[1]);

-- CREATE POLICY "Users can view own files"
-- ON storage.objects FOR SELECT
-- USING (bucket_id = 'user-uploads' AND auth.uid()::text = (storage.foldername(name))[1]);

-- CREATE POLICY "Users can delete own files"
-- ON storage.objects FOR DELETE
-- USING (bucket_id = 'user-uploads' AND auth.uid()::text = (storage.foldername(name))[1]);
