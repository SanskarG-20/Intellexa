# Design Document: Agentic Memory System

## Overview

This document describes the technical design for upgrading Intellexa's memory system from simple vector storage to a structured, evolving, interconnected agentic memory engine. The design is inspired by agent-mem and builds on the existing Supabase + Sentence Transformers + Gemini stack.

---

## Architecture

### High-Level Component Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        DOCUMENT UPLOAD FLOW                         │
│                                                                     │
│  Upload API → Storage → Chunking → Memory Creation Pipeline         │
│                                    ↓                                │
│                          ┌─────────────────┐                        │
│                          │  memory_service  │                        │
│                          └────────┬────────┘                        │
│                    ┌──────────────┼──────────────┐                  │
│                    ↓              ↓              ↓                  │
│             LLM Metadata    Embedding      Similarity               │
│             (summary,       Generation     Search                   │
│              tags,                         ↓                        │
│              keywords)               Memory Linking                 │
│                    └──────────────┼──────────────┘                  │
│                                   ↓                                 │
│                          memories + memory_links                    │
│                          (Supabase tables)                          │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                        RETRIEVAL FLOW                               │
│                                                                     │
│  Chat Query → embed_query → similarity_search                       │
│                                    ↓                                │
│                          Top-K direct matches                       │
│                                    ↓                                │
│                          Fetch linked memories                      │
│                                    ↓                                │
│                          Merge + rank results                       │
│                                    ↓                                │
│                          Format enriched context                    │
│                                    ↓                                │
│                          chat_service.py (LLM prompt)               │
└─────────────────────────────────────────────────────────────────────┘
```

### Service Layer

```
server/app/services/memory/
├── embedding_service.py        (existing — unchanged)
├── chunking_service.py         (existing — unchanged)
├── storage_service.py          (existing — unchanged)
├── pdf_service.py              (existing — unchanged)
├── image_service.py            (existing — unchanged)
├── video_service.py            (existing — unchanged)
├── retrieval_service.py        (existing — upgraded)
├── memory_service.py           (NEW — core memory CRUD + pipeline)
├── memory_linking_service.py   (NEW — bidirectional link management)
├── memory_evolution_service.py (NEW — memory updates on new links)
├── memory_graph_service.py     (NEW — graph traversal + subgraph)
└── __init__.py                 (existing)
```

---

## Database Schema

### New Tables

#### `memories`
The central table replacing the direct chunk→embedding pattern with rich structured memories.

```sql
CREATE TABLE memories (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         TEXT NOT NULL,
    document_id     UUID REFERENCES user_documents(id) ON DELETE CASCADE,
    chunk_id        UUID REFERENCES document_chunks(id) ON DELETE CASCADE,
    content         TEXT NOT NULL,
    summary         TEXT,
    tags            TEXT[] DEFAULT '{}',
    keywords        TEXT[] DEFAULT '{}',
    embedding       vector(768),
    related_memories UUID[] DEFAULT '{}',
    source_type     TEXT DEFAULT 'document',  -- 'document' | 'code' | 'chat'
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_memories_user_id       ON memories(user_id);
CREATE INDEX idx_memories_document_id   ON memories(document_id);
CREATE INDEX idx_memories_chunk_id      ON memories(chunk_id);
CREATE INDEX idx_memories_tags          ON memories USING GIN(tags);
CREATE INDEX idx_memories_keywords      ON memories USING GIN(keywords);
CREATE INDEX idx_memories_embedding     ON memories
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

#### `memory_links`
Stores bidirectional relationships between memories.

```sql
CREATE TABLE memory_links (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         TEXT NOT NULL,
    memory_id_1     UUID NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    memory_id_2     UUID NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    similarity_score FLOAT NOT NULL,
    link_type       TEXT DEFAULT 'semantic',  -- 'semantic' | 'temporal' | 'explicit'
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(memory_id_1, memory_id_2)
);

CREATE INDEX idx_memory_links_user_id    ON memory_links(user_id);
CREATE INDEX idx_memory_links_memory_1   ON memory_links(memory_id_1);
CREATE INDEX idx_memory_links_memory_2   ON memory_links(memory_id_2);
```

#### `memory_tags`
Denormalized tag index for fast tag-based search.

```sql
CREATE TABLE memory_tags (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    memory_id   UUID NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    user_id     TEXT NOT NULL,
    tag         TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_memory_tags_user_tag ON memory_tags(user_id, tag);
CREATE INDEX idx_memory_tags_memory   ON memory_tags(memory_id);
```

#### `memory_access_log`
Tracks access patterns for future relevance scoring.

```sql
CREATE TABLE memory_access_log (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    memory_id   UUID NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    user_id     TEXT NOT NULL,
    accessed_at TIMESTAMPTZ DEFAULT NOW(),
    access_type TEXT DEFAULT 'retrieval'  -- 'retrieval' | 'creation' | 'update'
);

CREATE INDEX idx_memory_access_memory ON memory_access_log(memory_id);
CREATE INDEX idx_memory_access_user   ON memory_access_log(user_id);
```

### Updated RPC Function

```sql
-- Enhanced similarity search that returns memory metadata
CREATE OR REPLACE FUNCTION match_memories(
    query_embedding vector(768),
    match_user_id   text,
    match_count     int DEFAULT 10,
    similarity_threshold float DEFAULT 0.3
)
RETURNS TABLE (
    memory_id        uuid,
    content          text,
    summary          text,
    tags             text[],
    keywords         text[],
    related_memories uuid[],
    document_id      uuid,
    filename         text,
    similarity       float
)
LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    SELECT
        m.id,
        m.content,
        m.summary,
        m.tags,
        m.keywords,
        m.related_memories,
        m.document_id,
        ud.filename,
        1 - (m.embedding <=> query_embedding) AS similarity
    FROM memories m
    LEFT JOIN user_documents ud ON m.document_id = ud.id
    WHERE m.user_id = match_user_id
      AND 1 - (m.embedding <=> query_embedding) >= similarity_threshold
    ORDER BY m.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;
```

---

## Memory Creation Pipeline

When a document chunk is processed, the pipeline runs:

```
chunk.content
    │
    ├─► Gemini: generate_memory_metadata(content)
    │       → { summary, tags: [], keywords: [] }
    │
    ├─► EmbeddingService: embed_text(content)
    │       → vector[768]
    │
    ├─► DB INSERT into memories
    │       → memory_id
    │
    ├─► find_similar_memories(embedding, user_id, top_k=10, threshold=0.7)
    │       → [candidate_memory_ids]
    │
    └─► for each candidate:
            link_memories(new_id, candidate_id, similarity, 'semantic')
            evolve_memory(candidate_id, new_id)
```

### LLM Metadata Generation

A single Gemini call per chunk generates all metadata:

**Prompt template:**
```
Given the following text, generate:
1. A concise 1-2 sentence summary
2. 3-5 semantic category tags (e.g. "machine learning", "finance")
3. 5-10 key concepts or named entities

Text: {content}

Respond in JSON:
{
  "summary": "...",
  "tags": ["...", "..."],
  "keywords": ["...", "..."]
}
```

**Fallback** (when Gemini fails): extract first 200 chars as summary, use TF-IDF-style word frequency for keywords, empty tags.

---

## Memory Linking

### Algorithm

```python
SIMILARITY_THRESHOLD = 0.7
MAX_LINKS_PER_MEMORY = 10

async def link_new_memory(memory_id, embedding, user_id):
    candidates = await find_similar_memories(
        embedding, user_id, top_k=20, threshold=SIMILARITY_THRESHOLD
    )
    # Exclude self, limit to top MAX_LINKS_PER_MEMORY
    for candidate in candidates[:MAX_LINKS_PER_MEMORY]:
        await create_bidirectional_link(
            memory_id, candidate.id, candidate.similarity
        )
```

### Bidirectional Link Creation

```python
async def create_bidirectional_link(id_a, id_b, score):
    # Insert both directions (UNIQUE constraint prevents duplicates)
    upsert(memory_links, {memory_id_1: id_a, memory_id_2: id_b, similarity_score: score})
    upsert(memory_links, {memory_id_1: id_b, memory_id_2: id_a, similarity_score: score})
    # Update related_memories arrays on both memories
    append_to_array(memories, id_a, 'related_memories', id_b)
    append_to_array(memories, id_b, 'related_memories', id_a)
```

---

## Memory Evolution

When memory B is linked to existing memory A:

```python
async def evolve_memory(memory_id, new_related_id):
    # 1. Update timestamp
    update(memories, memory_id, { updated_at: now() })
    # 2. Append to related_memories (already done by link creation)
    # 3. Log access
    insert(memory_access_log, { memory_id, access_type: 'update' })
```

Evolution is intentionally lightweight — the memory's content is not rewritten. The `related_memories` array and `updated_at` timestamp capture the evolution.

---

## Enhanced Retrieval

### `retrieve_with_links(query, user_id, top_k=10)`

```
1. embed query → vector
2. match_memories RPC → top_k direct matches (with similarity scores)
3. for each direct match:
     fetch all linked memory IDs from memory_links
     load linked memory content (batch fetch)
4. merge: direct_matches + linked_memories (deduplicated)
5. rank: direct matches by similarity desc, linked by parent similarity * 0.8
6. cap at 20 total results
7. log access for all returned memories
8. format_context_for_prompt(results)
```

### Result Schema

```python
@dataclass
class AgenticRetrievedContext:
    memory_id: str
    content: str
    summary: str
    tags: List[str]
    keywords: List[str]
    similarity: float
    is_linked: bool          # True if fetched via link, not direct match
    source_memory_id: str    # ID of the direct match that linked to this
    filename: str
    document_id: str
```

### Context Formatting

```
--- USER'S KNOWLEDGE BASE ---

[MEMORY: resume.pdf | Tags: career, skills | Relevance: 92%]
John has 5 years of experience in Python and machine learning...

  ↳ [LINKED: resume.pdf | Tags: career, education]
    John completed his MS in Computer Science at Stanford...

[MEMORY: cover_letter.pdf | Tags: career, goals | Relevance: 85%]
...

--- END OF KNOWLEDGE BASE ---
```

---

## Knowledge Graph

### `memory_graph_service.py`

```python
async def get_subgraph(memory_id, user_id, depth=2):
    """BFS traversal up to `depth` hops from memory_id."""
    visited = set()
    queue = [(memory_id, 0)]
    nodes = []
    edges = []

    while queue:
        current_id, current_depth = queue.pop(0)
        if current_id in visited or current_depth > depth:
            continue
        visited.add(current_id)
        memory = await get_memory(current_id)
        nodes.append(memory)
        links = await get_links(current_id, user_id)
        for link in links:
            edges.append(link)
            if link.memory_id_2 not in visited:
                queue.append((link.memory_id_2, current_depth + 1))

    return { "nodes": nodes, "edges": edges }
```

---

## API Endpoints

All new endpoints are added to `server/app/api/v1/memory.py` under the existing `/api/v1/memory` prefix.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/memories` | List all memories for user (paginated) |
| GET | `/memories/{id}` | Get memory with its links |
| GET | `/memories/{id}/graph` | Get subgraph (BFS, depth=2) |
| POST | `/memories/{id}/link` | Manually link two memories |
| DELETE | `/memories/{id}/link/{linked_id}` | Remove a link |
| GET | `/tags` | List all unique tags for user |
| GET | `/search` | Search memories by tag or keyword |
| POST | `/migrate` | Migrate existing document chunks to memories |

---

## Integration with RAG Pipeline

`chat_service.py` change — replace the existing retrieval call:

```python
# BEFORE
memory_results = await retrieval_service.retrieve_context(
    query=query_for_reasoning, user_id=user_id, top_k=10
)
memory_context = retrieval_service.format_context_for_prompt(memory_results)

# AFTER
from app.services.memory.memory_service import memory_service as agentic_memory

memory_results = await agentic_memory.retrieve_with_links(
    query=query_for_reasoning, user_id=user_id, top_k=10
)
memory_context = agentic_memory.format_context_for_prompt(memory_results)
```

The `format_context_for_prompt` output is backward compatible — same string format, just richer content.

---

## Backward Compatibility

- Existing `document_chunks` and `document_embeddings` tables are **not dropped**
- The old `match_document_embeddings` RPC is **kept** alongside the new `match_memories`
- `retrieval_service.py` keeps its existing interface; the new `memory_service.py` is additive
- `chat_service.py` switches to the new service but falls back to legacy if `memories` table is empty
- A `/api/v1/memory/migrate` endpoint converts existing chunks to the new memory structure

---

## Migration Strategy

```
POST /api/v1/memory/migrate
→ for each document_chunk (user_id):
    1. Check if memory already exists for this chunk_id (skip if yes)
    2. Generate metadata via Gemini (summary, tags, keywords)
    3. Fetch existing embedding from document_embeddings
    4. INSERT into memories
    5. Run linking pass for this new memory
→ Return { processed, successful, failed, skipped }
```

---

## Performance Considerations

- **Batch LLM calls**: Process up to 5 chunks per Gemini request using a batch prompt
- **Batch embeddings**: Use existing `embed_batch()` — already optimized
- **Async linking**: Memory linking runs as a background task after the memory is stored
- **In-memory cache**: Cache last 100 retrieved memories for 5 minutes (TTL dict)
- **Link cap**: Max 10 links per memory to prevent graph explosion
- **Retrieval cap**: Max 20 total results (10 direct + 10 linked) to prevent context overflow

---

## Correctness Properties (PBT)

1. **Bidirectionality**: For every link (A→B), a link (B→A) must exist with the same similarity score
2. **No self-links**: A memory must never be linked to itself
3. **No duplicate links**: The `UNIQUE(memory_id_1, memory_id_2)` constraint enforces this at DB level
4. **related_memories consistency**: The `related_memories` array on a memory must match the set of IDs in `memory_links` for that memory
5. **Retrieval completeness**: `retrieve_with_links` must return at least as many results as `retrieve_context` for the same query (linked memories only add, never remove)
6. **Threshold enforcement**: No link is created with similarity < `SIMILARITY_THRESHOLD` (0.7)
