# Requirements Document

## Introduction

This document specifies the requirements for upgrading Intellexa's existing memory system to an Agentic Memory System. The current system provides basic document upload, text extraction, chunking, embedding generation, and vector similarity search. The upgraded system will transform this into a structured, evolving, interconnected memory system inspired by agent-mem, where memories have rich metadata (summaries, tags, keywords), bidirectional relationships, and evolve over time as new related content is added.

## Glossary

- **Memory**: A structured unit of stored information containing content, summary, tags, keywords, embedding, and relationships to other memories
- **Memory_System**: The upgraded agentic memory system that manages structured, interconnected memories
- **Embedding_Service**: The service that generates vector embeddings using Sentence Transformers (BAAI/bge-base-en-v1.5)
- **LLM_Service**: The Gemini service used for generating summaries, tags, and keywords
- **Memory_Link**: A bidirectional relationship between two related memories
- **Memory_Graph**: The network of interconnected memories and their relationships
- **Legacy_System**: The existing memory system (document upload, chunking, embeddings, retrieval)
- **RAG_Pipeline**: Retrieval-Augmented Generation pipeline that uses memory context for chat responses
- **Similarity_Threshold**: The minimum cosine similarity score (0-1) required to create a memory link
- **Memory_Evolution**: The process of updating existing memories when new related memories are added

## Requirements

### Requirement 1: Memory Structure

**User Story:** As a developer, I want each memory to have rich metadata and structure, so that memories are more than just text chunks with embeddings.

#### Acceptance Criteria

1. THE Memory_System SHALL store memories with id, user_id, content, summary, tags, keywords, embedding, created_at, and updated_at fields
2. THE Memory_System SHALL store related_memories as an array of memory IDs for each memory
3. WHEN a memory is created, THE Memory_System SHALL generate a summary using LLM_Service
4. WHEN a memory is created, THE Memory_System SHALL generate semantic tags using LLM_Service
5. WHEN a memory is created, THE Memory_System SHALL generate keywords using LLM_Service
6. WHEN a memory is created, THE Memory_System SHALL generate an embedding using Embedding_Service
7. THE Memory_System SHALL store all memory metadata in the memories table

### Requirement 2: Memory Creation Pipeline

**User Story:** As a user, I want uploaded documents to be automatically processed into structured memories, so that my knowledge base becomes more intelligent over time.

#### Acceptance Criteria

1. WHEN a document is uploaded, THE Memory_System SHALL extract and chunk the content using the existing chunking service
2. WHEN chunks are created, THE Memory_System SHALL generate a summary for each chunk using LLM_Service with a maximum length of 200 characters
3. WHEN chunks are created, THE Memory_System SHALL generate 3-5 semantic tags for each chunk using LLM_Service
4. WHEN chunks are created, THE Memory_System SHALL extract 5-10 keywords from each chunk using LLM_Service
5. WHEN chunks are created, THE Memory_System SHALL generate embeddings using Embedding_Service
6. WHEN embeddings are generated, THE Memory_System SHALL find similar existing memories using cosine similarity
7. WHEN similar memories are found with similarity above Similarity_Threshold, THE Memory_System SHALL create bidirectional memory links
8. THE Memory_System SHALL store all generated metadata in the memories table

### Requirement 3: Memory Linking

**User Story:** As a user, I want related memories to be automatically connected, so that I can discover connections in my knowledge base.

#### Acceptance Criteria

1. WHEN a new memory is created, THE Memory_System SHALL search for similar memories using embedding similarity
2. WHEN similar memories are found with similarity >= 0.7, THE Memory_System SHALL create a memory link
3. THE Memory_System SHALL store memory links in the memory_links table with memory_id_1, memory_id_2, similarity_score, and link_type fields
4. WHEN a memory link is created from Memory A to Memory B, THE Memory_System SHALL create the reverse link from Memory B to Memory A
5. THE Memory_System SHALL prevent duplicate links between the same two memories
6. THE Memory_System SHALL support link_type values of semantic, temporal, and explicit
7. WHEN memories are linked, THE Memory_System SHALL update the related_memories array for both memories

### Requirement 4: Memory Evolution

**User Story:** As a user, I want existing memories to be updated when new related information is added, so that my knowledge base stays current and interconnected.

#### Acceptance Criteria

1. WHEN a new memory is linked to an existing memory, THE Memory_System SHALL update the existing memory's updated_at timestamp
2. WHEN a new memory is linked to an existing memory, THE Memory_System SHALL add the new memory ID to the existing memory's related_memories array
3. WHEN multiple new memories are linked to an existing memory, THE Memory_System SHALL maintain temporal ordering in the related_memories array
4. THE Memory_System SHALL track memory access patterns in a memory_access_log table with memory_id, accessed_at, and access_type fields
5. THE Memory_System SHALL support access_type values of retrieval, creation, and update

### Requirement 5: Enhanced Retrieval

**User Story:** As a user, I want search results to include linked memories, so that I get richer context for my queries.

#### Acceptance Criteria

1. WHEN a context query is executed, THE Memory_System SHALL retrieve top-k memories using embedding similarity
2. WHEN top-k memories are retrieved, THE Memory_System SHALL fetch all linked memories for each result
3. WHEN linked memories are fetched, THE Memory_System SHALL include them in the retrieval results with a linked indicator
4. THE Memory_System SHALL rank all results (direct matches and linked memories) by relevance score
5. THE Memory_System SHALL return results with memory_id, content, summary, tags, keywords, similarity, is_linked, and source_memory_id fields
6. WHEN formatting context for LLM prompts, THE Memory_System SHALL include both direct matches and linked memories
7. THE Memory_System SHALL limit total retrieved memories to a maximum of 20 to prevent context overflow

### Requirement 6: Knowledge Graph

**User Story:** As a developer, I want to maintain a knowledge graph of memory relationships, so that I can support graph traversal and visualization in the future.

#### Acceptance Criteria

1. THE Memory_System SHALL maintain a graph structure where memories are nodes and links are edges
2. THE Memory_System SHALL support querying all memories linked to a specific memory
3. THE Memory_System SHALL support querying memories within N hops of a specific memory
4. THE Memory_System SHALL provide a function to get the subgraph for a specific memory with depth parameter
5. THE Memory_System SHALL return subgraph results with nodes (memories) and edges (links) in a structured format
6. THE Memory_System SHALL calculate and store graph metrics including degree (number of links) for each memory

### Requirement 7: Backward Compatibility

**User Story:** As a developer, I want the upgraded system to work with existing documents and code, so that the migration is seamless.

#### Acceptance Criteria

1. THE Memory_System SHALL continue to support the existing document upload API endpoints
2. THE Memory_System SHALL continue to support the existing document_chunks and document_embeddings tables
3. WHEN existing documents are present, THE Memory_System SHALL provide a migration function to convert them to the new memory structure
4. THE Memory_System SHALL maintain compatibility with the existing RAG_Pipeline integration in chat_service.py
5. THE Memory_System SHALL support both legacy retrieval (chunks only) and enhanced retrieval (memories with links)
6. WHEN the retrieval_service is called, THE Memory_System SHALL use enhanced retrieval by default
7. THE Memory_System SHALL provide a configuration flag to enable or disable memory linking features

### Requirement 8: Database Schema

**User Story:** As a developer, I want a well-designed database schema for the agentic memory system, so that data is stored efficiently and queries are fast.

#### Acceptance Criteria

1. THE Memory_System SHALL create a memories table with columns: id, user_id, document_id, chunk_id, content, summary, tags, keywords, embedding, related_memories, created_at, updated_at
2. THE Memory_System SHALL create a memory_links table with columns: id, user_id, memory_id_1, memory_id_2, similarity_score, link_type, created_at
3. THE Memory_System SHALL create a memory_tags table with columns: id, memory_id, tag, created_at
4. THE Memory_System SHALL create a memory_access_log table with columns: id, memory_id, user_id, accessed_at, access_type
5. THE Memory_System SHALL create indexes on user_id, document_id, chunk_id, and embedding columns in the memories table
6. THE Memory_System SHALL create indexes on user_id, memory_id_1, and memory_id_2 columns in the memory_links table
7. THE Memory_System SHALL create a unique constraint on (memory_id_1, memory_id_2) in the memory_links table to prevent duplicates
8. THE Memory_System SHALL create a vector index on the embedding column in the memories table for fast similarity search

### Requirement 9: Memory Service Implementation

**User Story:** As a developer, I want a dedicated memory service to handle all memory operations, so that the code is modular and maintainable.

#### Acceptance Criteria

1. THE Memory_System SHALL provide a memory_service.py module in server/app/services/memory/
2. THE Memory_Service SHALL provide a create_memory function that accepts content, user_id, document_id, and chunk_id parameters
3. THE Memory_Service SHALL provide a find_similar_memories function that accepts embedding, user_id, and top_k parameters
4. THE Memory_Service SHALL provide a link_memories function that accepts memory_id_1, memory_id_2, similarity_score, and link_type parameters
5. THE Memory_Service SHALL provide a get_linked_memories function that accepts memory_id and user_id parameters
6. THE Memory_Service SHALL provide an evolve_memory function that accepts memory_id and new_related_memory_id parameters
7. THE Memory_Service SHALL provide a retrieve_with_links function that accepts query, user_id, and top_k parameters

### Requirement 10: LLM Integration for Metadata Generation

**User Story:** As a user, I want the system to automatically generate meaningful summaries, tags, and keywords, so that my memories are well-organized and searchable.

#### Acceptance Criteria

1. THE Memory_System SHALL use Gemini_Service to generate summaries with a prompt that requests concise 1-2 sentence summaries
2. THE Memory_System SHALL use Gemini_Service to generate 3-5 semantic tags with a prompt that requests categorical labels
3. THE Memory_System SHALL use Gemini_Service to extract 5-10 keywords with a prompt that requests key concepts and entities
4. WHEN LLM_Service fails to generate metadata, THE Memory_System SHALL use fallback extraction methods
5. THE Memory_System SHALL cache LLM responses for identical content to reduce API calls
6. THE Memory_System SHALL batch process multiple chunks in a single LLM request when possible
7. THE Memory_System SHALL handle LLM rate limits with exponential backoff retry logic

### Requirement 11: API Endpoints

**User Story:** As a frontend developer, I want API endpoints for memory operations, so that I can build user interfaces for memory management.

#### Acceptance Criteria

1. THE Memory_System SHALL provide a GET /api/v1/memory/memories endpoint to list all memories for a user
2. THE Memory_System SHALL provide a GET /api/v1/memory/memories/{memory_id} endpoint to get a specific memory with its links
3. THE Memory_System SHALL provide a GET /api/v1/memory/memories/{memory_id}/graph endpoint to get the memory subgraph
4. THE Memory_System SHALL provide a POST /api/v1/memory/memories/{memory_id}/link endpoint to manually create a link between memories
5. THE Memory_System SHALL provide a DELETE /api/v1/memory/memories/{memory_id}/link/{linked_memory_id} endpoint to remove a link
6. THE Memory_System SHALL provide a GET /api/v1/memory/tags endpoint to list all unique tags for a user
7. THE Memory_System SHALL provide a GET /api/v1/memory/search endpoint to search memories by tags or keywords

### Requirement 12: Migration Support

**User Story:** As a system administrator, I want a migration script to convert existing documents to the new memory structure, so that existing data is not lost.

#### Acceptance Criteria

1. THE Memory_System SHALL provide a migrate_existing_documents function in memory_service.py
2. WHEN migrate_existing_documents is called, THE Memory_System SHALL iterate through all existing document_chunks for a user
3. WHEN processing each chunk, THE Memory_System SHALL create a new memory with generated metadata
4. WHEN processing each chunk, THE Memory_System SHALL preserve the link to the original document_id and chunk_id
5. THE Memory_System SHALL provide a POST /api/v1/memory/migrate endpoint to trigger migration for a user
6. THE Memory_System SHALL return migration progress with counts of processed, successful, and failed chunks
7. WHEN migration is complete, THE Memory_System SHALL mark documents as migrated to prevent duplicate processing

### Requirement 13: Performance Optimization

**User Story:** As a user, I want the memory system to be fast and efficient, so that my experience is smooth even with large knowledge bases.

#### Acceptance Criteria

1. THE Memory_System SHALL batch process embeddings for multiple memories in a single call to Embedding_Service
2. THE Memory_System SHALL batch process LLM requests for multiple chunks when generating metadata
3. THE Memory_System SHALL use database connection pooling for all database operations
4. THE Memory_System SHALL cache frequently accessed memories in memory for 5 minutes
5. THE Memory_System SHALL limit similarity search to top 100 candidates before applying Similarity_Threshold
6. THE Memory_System SHALL use asynchronous processing for memory linking to avoid blocking document upload
7. THE Memory_System SHALL provide configuration options for batch sizes and cache TTL

### Requirement 14: Testing and Validation

**User Story:** As a developer, I want comprehensive tests for the memory system, so that I can ensure reliability and catch bugs early.

#### Acceptance Criteria

1. THE Memory_System SHALL provide unit tests for all memory_service functions
2. THE Memory_System SHALL provide integration tests for the complete memory creation pipeline
3. THE Memory_System SHALL provide tests for bidirectional link creation and validation
4. THE Memory_System SHALL provide tests for memory evolution when new links are added
5. THE Memory_System SHALL provide tests for enhanced retrieval with linked memories
6. THE Memory_System SHALL provide tests for backward compatibility with legacy retrieval
7. THE Memory_System SHALL provide performance tests for large-scale memory operations (1000+ memories)

