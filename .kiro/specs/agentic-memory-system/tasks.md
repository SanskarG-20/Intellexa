# Implementation Tasks: Agentic Memory System

## Tasks

- [ ] 1. Database Schema Migration
  - [ ] 1.1 Create `server/migrations/002_agentic_memory_schema.sql` with `memories`, `memory_links`, `memory_tags`, `memory_access_log` tables, all indexes, RLS policies, and the `match_memories` RPC function
  - [ ] 1.2 Keep existing tables (`document_chunks`, `document_embeddings`) and the `match_document_embeddings` RPC intact for backward compatibility

- [ ] 2. Memory Service Core (`server/app/services/memory/memory_service.py`)
  - [ ] 2.1 Implement `generate_memory_metadata(content)` — calls Gemini with a single JSON prompt to return `{ summary, tags, keywords }` with a fallback for API failures
  - [ ] 2.2 Implement `create_memory(content, user_id, document_id, chunk_id, source_type)` — runs the full pipeline: metadata generation → embedding → DB insert → async linking
  - [ ] 2.3 Implement `find_similar_memories(embedding, user_id, top_k, threshold)` — calls the `match_memories` RPC
  - [ ] 2.4 Implement `retrieve_with_links(query, user_id, top_k)` — embeds query, fetches direct matches, fetches linked memories, merges and ranks, caps at 20 results
  - [ ] 2.5 Implement `format_context_for_prompt(results)` — formats `AgenticRetrievedContext` list into the enriched context string for LLM injection
  - [ ] 2.6 Implement `migrate_existing_documents(user_id)` — iterates existing `document_chunks`, creates memories for each, skips already-migrated chunks

- [ ] 3. Memory Linking Service (`server/app/services/memory/memory_linking_service.py`)
  - [ ] 3.1 Implement `create_bidirectional_link(memory_id_1, memory_id_2, similarity_score, link_type)` — upserts both directions in `memory_links` and updates `related_memories` arrays on both memories
  - [ ] 3.2 Implement `get_linked_memories(memory_id, user_id)` — fetches all memories linked to a given memory
  - [ ] 3.3 Implement `remove_link(memory_id_1, memory_id_2, user_id)` — deletes both directions of a link and updates `related_memories` arrays
  - [ ] 3.4 Implement `run_linking_pass(memory_id, embedding, user_id)` — finds similar memories above threshold and creates bidirectional links (max 10 links per memory)

- [ ] 4. Memory Evolution Service (`server/app/services/memory/memory_evolution_service.py`)
  - [ ] 4.1 Implement `evolve_memory(memory_id, new_related_id)` — updates `updated_at` timestamp and logs an `update` access event in `memory_access_log`
  - [ ] 4.2 Implement `log_access(memory_id, user_id, access_type)` — inserts a row into `memory_access_log`

- [ ] 5. Memory Graph Service (`server/app/services/memory/memory_graph_service.py`)
  - [ ] 5.1 Implement `get_subgraph(memory_id, user_id, depth=2)` — BFS traversal returning `{ nodes: [memory], edges: [link] }` up to `depth` hops
  - [ ] 5.2 Implement `get_memory_degree(memory_id, user_id)` — returns the number of links for a memory

- [ ] 6. Pydantic Schemas (`server/app/schemas/memory.py`)
  - [ ] 6.1 Add `MemoryInfo`, `MemoryDetailResponse`, `MemoryListResponse` schemas
  - [ ] 6.2 Add `MemoryLinkRequest`, `MemoryLinkResponse`, `MemoryGraphResponse` schemas
  - [ ] 6.3 Add `MemorySearchRequest`, `MemorySearchResponse`, `MigrationResponse` schemas

- [ ] 7. API Endpoints (`server/app/api/v1/memory.py`)
  - [ ] 7.1 Add `GET /api/v1/memory/memories` — list all memories for user with pagination
  - [ ] 7.2 Add `GET /api/v1/memory/memories/{memory_id}` — get a single memory with its linked memories
  - [ ] 7.3 Add `GET /api/v1/memory/memories/{memory_id}/graph` — get subgraph (BFS depth=2)
  - [ ] 7.4 Add `POST /api/v1/memory/memories/{memory_id}/link` — manually create a link between two memories
  - [ ] 7.5 Add `DELETE /api/v1/memory/memories/{memory_id}/link/{linked_memory_id}` — remove a link
  - [ ] 7.6 Add `GET /api/v1/memory/tags` — list all unique tags for user
  - [ ] 7.7 Add `GET /api/v1/memory/search` — search memories by tag or keyword query param
  - [ ] 7.8 Add `POST /api/v1/memory/migrate` — trigger migration of existing document chunks to memories

- [ ] 8. Integrate Memory Creation into Document Upload Pipeline (`server/app/api/v1/memory.py`)
  - [ ] 8.1 In `process_document_background`, after `_store_chunks` and `_store_embeddings`, call `memory_service.create_memory` for each chunk to populate the `memories` table
  - [ ] 8.2 Run the linking pass as a background task after all memories for a document are created (batch linking)

- [ ] 9. Upgrade Chat Service Integration (`server/app/services/chat_service.py`)
  - [ ] 9.1 Replace the `retrieval_service.retrieve_context` call with `memory_service.retrieve_with_links`
  - [ ] 9.2 Add fallback: if `memories` table is empty for the user, fall back to legacy `retrieval_service.retrieve_context`
  - [ ] 9.3 Update the `format_context_for_prompt` call to use the new enriched format

- [ ] 10. Upgrade Retrieval Service (`server/app/services/memory/retrieval_service.py`)
  - [ ] 10.1 Add `retrieve_with_links` method that delegates to `memory_service` when the memories table has data, otherwise falls back to the existing chunk-based search

- [ ] 11. Tests
  - [ ] 11.1 Write unit tests for `memory_service.generate_memory_metadata` — test Gemini success path and fallback path
  - [ ] 11.2 Write unit tests for `memory_linking_service.create_bidirectional_link` — verify both directions are created and `related_memories` arrays are updated
  - [ ] 11.3 Write property-based test for bidirectionality invariant: for any two linked memories A and B, `(A→B) ∈ memory_links` iff `(B→A) ∈ memory_links`
  - [ ] 11.4 Write unit tests for `memory_service.retrieve_with_links` — verify linked memories are included and results are capped at 20
  - [ ] 11.5 Write integration test for the full document upload → memory creation → retrieval pipeline
