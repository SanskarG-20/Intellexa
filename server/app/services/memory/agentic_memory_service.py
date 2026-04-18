"""
agentic_memory_service.py - Structured Agentic Memory Engine
Builds evolving, linked memory nodes on top of vector retrieval.
"""

import json
import re
from collections import Counter
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.db.supabase import supabase
from app.services.llama_service import llama_service
from app.services.memory.embedding_service import embedding_service


class AgenticMemoryService:
    """
    Manages structured, evolving memories with graph relationships.

    Memory node shape:
      {
        id,
        user_id,
        content,
        summary,
        tags,
        keywords,
        embedding,
        related_memories,
        created_at
      }
    """

    SUPPORTED_SOURCE_TYPES = {"docs", "images", "videos", "code", "chat", "other"}
    STOPWORDS = {
        "about", "after", "again", "also", "been", "being", "because", "between", "could",
        "from", "have", "into", "just", "like", "only", "other", "should", "some", "than",
        "that", "their", "there", "these", "they", "this", "those", "through", "under", "were",
        "what", "when", "where", "which", "while", "with", "would", "your", "you", "them",
    }

    @staticmethod
    def _normalize_text(value: str) -> str:
        return " ".join(str(value or "").split()).strip()

    @staticmethod
    def _dedupe_keep_order(values: List[str], max_items: int) -> List[str]:
        unique: List[str] = []
        seen = set()
        for value in values:
            text = " ".join(str(value or "").lower().split())
            if not text or text in seen:
                continue
            seen.add(text)
            unique.append(text)
            if len(unique) >= max_items:
                break
        return unique

    @classmethod
    def _fallback_enrichment(cls, content: str) -> Dict[str, Any]:
        sentences = re.split(r"(?<=[.!?])\s+", content)
        summary = content[:240]
        if sentences:
            first_sentence = sentences[0].strip()
            if first_sentence:
                summary = first_sentence[:240]

        tokens = re.findall(r"[a-zA-Z0-9]{4,}", content.lower())
        tokens = [token for token in tokens if token not in cls.STOPWORDS]
        token_counts = Counter(tokens)
        keywords = [token for token, _ in token_counts.most_common(10)]
        tags = keywords[:5]

        return {
            "summary": summary,
            "tags": tags,
            "keywords": keywords,
        }

    @staticmethod
    def _extract_json(text: str) -> Optional[Dict[str, Any]]:
        if not text:
            return None

        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return None

        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return None

        return None

    async def _generate_enrichment(self, content: str) -> Dict[str, Any]:
        fallback = self._fallback_enrichment(content)

        system_prompt = (
            "You extract concise structured memory metadata. "
            "Return valid JSON only with keys: summary, tags, keywords. "
            "summary must be <= 220 chars. tags 3-6 short labels. keywords 5-12 terms."
        )
        user_prompt = (
            "Create structured memory metadata from this content:\n\n"
            f"{content[:3000]}\n\n"
            "Return JSON now."
        )

        try:
            llm_response = await llama_service.get_ai_response(user_prompt, system_prompt=system_prompt)
            parsed = self._extract_json(llm_response)
            if not parsed:
                return fallback

            summary = self._normalize_text(parsed.get("summary", ""))[:220] or fallback["summary"]
            tags = self._dedupe_keep_order([str(item) for item in parsed.get("tags", [])], 8)
            keywords = self._dedupe_keep_order([str(item) for item in parsed.get("keywords", [])], 16)

            if not tags:
                tags = fallback["tags"]
            if not keywords:
                keywords = fallback["keywords"]

            return {
                "summary": summary,
                "tags": tags,
                "keywords": keywords,
            }
        except Exception:
            return fallback

    async def find_similar_memories(
        self,
        user_id: str,
        embedding: List[float],
        top_k: int = 6,
        similarity_threshold: float = 0.55,
        exclude_memory_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Find similar memory nodes via vector search RPC."""
        if not supabase or not embedding:
            return []

        try:
            response = supabase.rpc(
                "match_agent_memories",
                {
                    "query_embedding": embedding,
                    "match_user_id": user_id,
                    "match_count": max(top_k * 2, top_k),
                },
            ).execute()
        except Exception as exc:
            print(f"[AgenticMemory] match_agent_memories unavailable or failed: {exc}")
            return []

        rows = response.data or []
        results: List[Dict[str, Any]] = []
        for row in rows:
            memory_id = str(row.get("id", ""))
            if not memory_id:
                continue
            if exclude_memory_id and memory_id == exclude_memory_id:
                continue

            similarity = float(row.get("similarity") or 0.0)
            if similarity < similarity_threshold:
                continue

            row["id"] = memory_id
            row["similarity"] = max(0.0, min(1.0, similarity))
            row["tags"] = row.get("tags") or []
            row["keywords"] = row.get("keywords") or []
            row["related_memories"] = row.get("related_memories") or []
            results.append(row)

        results.sort(key=lambda item: float(item.get("similarity") or 0.0), reverse=True)
        return results[:top_k]

    async def _create_bidirectional_links(
        self,
        user_id: str,
        memory_id: str,
        related_memories: List[Dict[str, Any]],
    ) -> None:
        """Create graph edges in both directions."""
        if not supabase or not related_memories:
            return

        link_rows: List[Dict[str, Any]] = []
        for related in related_memories:
            related_id = str(related.get("id", "")).strip()
            if not related_id or related_id == memory_id:
                continue

            weight = max(0.0, min(1.0, float(related.get("similarity") or 0.0)))
            link_rows.append(
                {
                    "user_id": user_id,
                    "from_memory_id": memory_id,
                    "to_memory_id": related_id,
                    "relation_type": "semantic_similarity",
                    "weight": weight,
                }
            )
            link_rows.append(
                {
                    "user_id": user_id,
                    "from_memory_id": related_id,
                    "to_memory_id": memory_id,
                    "relation_type": "semantic_similarity",
                    "weight": weight,
                }
            )

        if not link_rows:
            return

        try:
            supabase.table("memory_relationships").upsert(
                link_rows,
                on_conflict="user_id,from_memory_id,to_memory_id,relation_type",
            ).execute()
        except Exception as exc:
            print(f"[AgenticMemory] Failed to upsert memory relationships: {exc}")

    async def _update_related_memory_list(
        self,
        user_id: str,
        memory_id: str,
        related_ids: List[str],
    ) -> None:
        """Persist related memory IDs on node for fast adjacency lookups."""
        if not supabase:
            return

        if not related_ids:
            return

        try:
            existing = supabase.table("agent_memories").select("related_memories").eq(
                "id", memory_id
            ).eq("user_id", user_id).execute()
            current = []
            if existing.data:
                current = existing.data[0].get("related_memories") or []

            merged = self._dedupe_keep_order(current + related_ids, 50)
            supabase.table("agent_memories").update(
                {"related_memories": merged, "updated_at": datetime.utcnow().isoformat()}
            ).eq("id", memory_id).eq("user_id", user_id).execute()
        except Exception as exc:
            print(f"[AgenticMemory] Failed to update related list for {memory_id}: {exc}")

    async def _evolve_related_memories(
        self,
        user_id: str,
        new_memory: Dict[str, Any],
        related_memories: List[Dict[str, Any]],
    ) -> None:
        """
        Evolve existing memory nodes by merging context from newly added related memory.
        """
        if not supabase:
            return

        new_summary = self._normalize_text(new_memory.get("summary", ""))
        new_tags = [str(item) for item in (new_memory.get("tags") or [])]
        new_keywords = [str(item) for item in (new_memory.get("keywords") or [])]
        new_id = str(new_memory.get("id", ""))

        for related in related_memories:
            related_id = str(related.get("id", "")).strip()
            if not related_id or related_id == new_id:
                continue

            existing_summary = self._normalize_text(related.get("summary", ""))
            evolved_summary = existing_summary
            if new_summary and new_summary.lower() not in existing_summary.lower():
                if evolved_summary:
                    evolved_summary = f"{evolved_summary} | Related: {new_summary}"
                else:
                    evolved_summary = new_summary
                evolved_summary = evolved_summary[:320]

            merged_tags = self._dedupe_keep_order((related.get("tags") or []) + new_tags, 12)
            merged_keywords = self._dedupe_keep_order((related.get("keywords") or []) + new_keywords, 20)
            merged_related = self._dedupe_keep_order((related.get("related_memories") or []) + [new_id], 50)

            try:
                supabase.table("agent_memories").update(
                    {
                        "summary": evolved_summary or existing_summary,
                        "tags": merged_tags,
                        "keywords": merged_keywords,
                        "related_memories": merged_related,
                        "updated_at": datetime.utcnow().isoformat(),
                    }
                ).eq("id", related_id).eq("user_id", user_id).execute()
            except Exception as exc:
                print(f"[AgenticMemory] Failed to evolve memory {related_id}: {exc}")

    async def create_memory(
        self,
        user_id: str,
        content: str,
        source_type: str = "other",
        source_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Create a structured memory node with enrichment, embedding, linking, and evolution.
        """
        if not supabase:
            return None

        normalized_content = self._normalize_text(content)
        if not normalized_content:
            return None

        normalized_source = source_type if source_type in self.SUPPORTED_SOURCE_TYPES else "other"
        enrichment = await self._generate_enrichment(normalized_content)
        embedding = await embedding_service.embed_text(normalized_content, skip_on_error=False)

        insert_payload = {
            "user_id": user_id,
            "content": normalized_content,
            "summary": enrichment.get("summary", "") or normalized_content[:220],
            "tags": enrichment.get("tags") or [],
            "keywords": enrichment.get("keywords") or [],
            "embedding": embedding,
            "related_memories": [],
            "source_type": normalized_source,
            "source_id": source_id,
            "metadata": metadata or {},
        }

        try:
            insert_res = supabase.table("agent_memories").insert(insert_payload).execute()
            if not insert_res.data:
                return None
            created = insert_res.data[0]
        except Exception as exc:
            print(f"[AgenticMemory] Failed to create memory: {exc}")
            return None

        memory_id = str(created.get("id", "")).strip()
        if not memory_id:
            return created

        similar = await self.find_similar_memories(
            user_id=user_id,
            embedding=embedding or [],
            top_k=6,
            similarity_threshold=0.5,
            exclude_memory_id=memory_id,
        )

        similar_ids = [str(item.get("id", "")).strip() for item in similar if item.get("id")]
        if similar_ids:
            await self._create_bidirectional_links(user_id, memory_id, similar)
            await self._update_related_memory_list(user_id, memory_id, similar_ids)
            await self._evolve_related_memories(user_id, created, similar)
            created["related_memories"] = self._dedupe_keep_order(similar_ids, 50)

        return created

    async def ingest_contents(
        self,
        user_id: str,
        contents: List[str],
        source_type: str,
        source_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        max_items: int = 25,
    ) -> int:
        """
        Ingest a list of content blocks into agentic memory nodes.
        Returns number of successfully created nodes.
        """
        if not contents:
            return 0

        created_count = 0
        for idx, content in enumerate(contents[:max_items]):
            text = self._normalize_text(content)
            if len(text) < 40:
                continue

            record = await self.create_memory(
                user_id=user_id,
                content=text,
                source_type=source_type,
                source_id=source_id,
                metadata={**(metadata or {}), "ingest_index": idx},
            )
            if record:
                created_count += 1

        return created_count

    async def _fetch_linked_memories(
        self,
        user_id: str,
        memory_ids: List[str],
        limit: int = 16,
    ) -> List[Dict[str, Any]]:
        if not supabase or not memory_ids:
            return []

        try:
            relation_res = supabase.table("memory_relationships").select(
                "to_memory_id, weight"
            ).eq("user_id", user_id).in_("from_memory_id", memory_ids).order(
                "weight", desc=True
            ).limit(limit).execute()
        except Exception as exc:
            print(f"[AgenticMemory] Failed reading memory relationships: {exc}")
            return []

        relation_rows = relation_res.data or []
        if not relation_rows:
            return []

        relation_weight: Dict[str, float] = {}
        for row in relation_rows:
            to_id = str(row.get("to_memory_id", "")).strip()
            if not to_id:
                continue
            relation_weight[to_id] = max(relation_weight.get(to_id, 0.0), float(row.get("weight") or 0.0))

        linked_ids = list(relation_weight.keys())
        if not linked_ids:
            return []

        try:
            memory_res = supabase.table("agent_memories").select(
                "id, user_id, content, summary, tags, keywords, related_memories, source_type, source_id, created_at"
            ).eq("user_id", user_id).in_("id", linked_ids).execute()
        except Exception as exc:
            print(f"[AgenticMemory] Failed reading linked memories: {exc}")
            return []

        linked_memories: List[Dict[str, Any]] = []
        for row in memory_res.data or []:
            row_id = str(row.get("id", "")).strip()
            if not row_id:
                continue
            row["similarity"] = max(0.0, min(1.0, 0.4 + (relation_weight.get(row_id, 0.0) * 0.6)))
            row["tags"] = row.get("tags") or []
            row["keywords"] = row.get("keywords") or []
            row["related_memories"] = row.get("related_memories") or []
            linked_memories.append(row)

        linked_memories.sort(key=lambda item: float(item.get("similarity") or 0.0), reverse=True)
        return linked_memories

    async def retrieve_context(
        self,
        query: str,
        user_id: str,
        top_k: int = 8,
        query_embedding: Optional[List[float]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Graph-aware retrieval:
        1) top semantic memory nodes
        2) linked neighbors from the memory graph
        3) merged deduplicated results
        """
        normalized_query = self._normalize_text(query)
        if not normalized_query:
            return []

        embedding = query_embedding or await embedding_service.embed_query(normalized_query)
        anchors = await self.find_similar_memories(
            user_id=user_id,
            embedding=embedding,
            top_k=max(top_k, 4),
            similarity_threshold=0.3,
        )

        if not anchors:
            return []

        anchor_ids = [str(item.get("id", "")).strip() for item in anchors if item.get("id")]
        linked = await self._fetch_linked_memories(
            user_id=user_id,
            memory_ids=anchor_ids,
            limit=max(top_k * 2, 10),
        )

        merged: Dict[str, Dict[str, Any]] = {}
        for item in anchors + linked:
            memory_id = str(item.get("id", "")).strip()
            if not memory_id:
                continue

            existing = merged.get(memory_id)
            if not existing or float(item.get("similarity") or 0.0) > float(existing.get("similarity") or 0.0):
                normalized_item = dict(item)
                normalized_item["id"] = memory_id
                normalized_item["tags"] = normalized_item.get("tags") or []
                normalized_item["keywords"] = normalized_item.get("keywords") or []
                normalized_item["related_memories"] = normalized_item.get("related_memories") or []
                merged[memory_id] = normalized_item

        merged_list = list(merged.values())
        merged_list.sort(
            key=lambda item: (float(item.get("similarity") or 0.0), str(item.get("created_at") or "")),
            reverse=True,
        )
        return merged_list[:top_k]


agentic_memory_service = AgenticMemoryService()
