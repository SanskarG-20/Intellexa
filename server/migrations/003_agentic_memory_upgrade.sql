-- ============================================================================
-- Agentic Memory System Upgrade
-- Adds structured, evolving, interconnected memory nodes and graph links.
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS vector;

-- --------------------------------------------------------------------------
-- 1) Structured memory nodes
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent_memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    content TEXT NOT NULL,
    summary TEXT NOT NULL,
    tags TEXT[] NOT NULL DEFAULT '{}',
    keywords TEXT[] NOT NULL DEFAULT '{}',
    embedding vector(768),
    related_memories UUID[] NOT NULL DEFAULT '{}',
    source_type TEXT NOT NULL DEFAULT 'other'
        CHECK (source_type IN ('docs', 'images', 'videos', 'code', 'chat', 'other')),
    source_id TEXT,
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_memories_user_id ON agent_memories(user_id);
CREATE INDEX IF NOT EXISTS idx_agent_memories_created_at ON agent_memories(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_memories_source_type ON agent_memories(source_type);
CREATE INDEX IF NOT EXISTS idx_agent_memories_tags_gin ON agent_memories USING gin(tags);
CREATE INDEX IF NOT EXISTS idx_agent_memories_keywords_gin ON agent_memories USING gin(keywords);
CREATE INDEX IF NOT EXISTS idx_agent_memories_vector ON agent_memories
    USING hnsw (embedding vector_cosine_ops);

-- --------------------------------------------------------------------------
-- 2) Knowledge graph edges between memory nodes
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS memory_relationships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    from_memory_id UUID NOT NULL REFERENCES agent_memories(id) ON DELETE CASCADE,
    to_memory_id UUID NOT NULL REFERENCES agent_memories(id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL DEFAULT 'semantic_similarity',
    weight DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_memory_relationship_not_self CHECK (from_memory_id <> to_memory_id),
    CONSTRAINT uq_memory_relationship UNIQUE (user_id, from_memory_id, to_memory_id, relation_type)
);

CREATE INDEX IF NOT EXISTS idx_memory_relationships_user_id ON memory_relationships(user_id);
CREATE INDEX IF NOT EXISTS idx_memory_relationships_from ON memory_relationships(from_memory_id);
CREATE INDEX IF NOT EXISTS idx_memory_relationships_to ON memory_relationships(to_memory_id);
CREATE INDEX IF NOT EXISTS idx_memory_relationships_weight ON memory_relationships(weight DESC);

-- --------------------------------------------------------------------------
-- 3) Trigger to auto-update updated_at
-- --------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION update_agent_memory_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_update_agent_memory_updated_at ON agent_memories;
CREATE TRIGGER trg_update_agent_memory_updated_at
    BEFORE UPDATE ON agent_memories
    FOR EACH ROW
    EXECUTE FUNCTION update_agent_memory_updated_at();

-- --------------------------------------------------------------------------
-- 4) RPC for semantic memory matching
-- --------------------------------------------------------------------------
DROP FUNCTION IF EXISTS match_agent_memories(vector, text, integer);
CREATE OR REPLACE FUNCTION match_agent_memories(
    query_embedding vector(768),
    match_user_id text,
    match_count int DEFAULT 10
)
RETURNS TABLE (
    id uuid,
    user_id text,
    content text,
    summary text,
    tags text[],
    keywords text[],
    related_memories uuid[],
    source_type text,
    source_id text,
    created_at timestamptz,
    similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        am.id,
        am.user_id,
        am.content,
        am.summary,
        am.tags,
        am.keywords,
        am.related_memories,
        am.source_type,
        am.source_id,
        am.created_at,
        1 - (am.embedding <=> query_embedding) as similarity
    FROM agent_memories am
    WHERE am.user_id = match_user_id
    ORDER BY am.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- --------------------------------------------------------------------------
-- 5) RLS and service role policies
-- --------------------------------------------------------------------------
ALTER TABLE agent_memories ENABLE ROW LEVEL SECURITY;
ALTER TABLE memory_relationships ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Service role full access on agent_memories" ON agent_memories;
CREATE POLICY "Service role full access on agent_memories"
ON agent_memories FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Service role full access on memory_relationships" ON memory_relationships;
CREATE POLICY "Service role full access on memory_relationships"
ON memory_relationships FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Optional user policies for direct authenticated access
DROP POLICY IF EXISTS "Users can read own agent memories" ON agent_memories;
CREATE POLICY "Users can read own agent memories"
ON agent_memories FOR SELECT USING (user_id = auth.uid()::text);

DROP POLICY IF EXISTS "Users can read own memory relationships" ON memory_relationships;
CREATE POLICY "Users can read own memory relationships"
ON memory_relationships FOR SELECT USING (user_id = auth.uid()::text);
