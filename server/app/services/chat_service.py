import re
from typing import Dict, List

from app.db.supabase import supabase
from app.services.autopsy_service import autopsy_service
from app.services.context_service import context_service
from app.services.ethics_service import ethics_service
from app.services.explanation_service import explanation_service
from app.services.llama_service import llama_service
from app.services.perspective_service import perspective_service
from app.services.rag_service import rag_service
from app.services.reframe_service import reframe_service
from app.services.trust_service import trust_service
from app.services.memory.retrieval_service import retrieval_service


class ChatService:
    """
    Business logic layer orchestrating the full response pipeline:
    1) autopsy, 2) optional query reframe, 3) context, 4) answer generation,
    5) multi-perspective answer, 6) ethical check, 7) explanation,
    8) trust score.
    """

    REALTIME_FALLBACK_MESSAGE = "I couldn't find the latest update right now, but here's what I know."
    VOICE_REALTIME_FALLBACK_MESSAGE = "I couldn't find the latest update right now, but here's what I know."
    GROUNDING_STOPWORDS = {
        "about",
        "above",
        "after",
        "again",
        "also",
        "been",
        "being",
        "from",
        "have",
        "into",
        "only",
        "that",
        "their",
        "there",
        "these",
        "this",
        "those",
        "what",
        "when",
        "where",
        "which",
        "while",
        "with",
        "would",
        "your",
    }

    @classmethod
    def _build_main_system_prompt(
        cls,
        context: str,
        rag_context: str = "",
        memory_context: str = "",
        force_web_grounded: bool = False,
    ) -> str:
        system_prompt = (
            "You are Intellexa Core, a sophisticated AI assistant designed "
            "to provide ethical, context-aware, and helpful responses.\n"
            "For any question about current facts, you MUST rely on search results. "
            "If search results are available, do NOT use your own knowledge.\n\n"
        )

        if memory_context:
            system_prompt += f"{memory_context}\n\n"
            system_prompt += (
                "Memory rules (CRITICAL - HIGHEST PRIORITY):\n"
                "- The USER'S PERSONAL CONTEXT contains information from documents they've uploaded.\n"
                "- This is TRUSTED information from the user's own knowledge base.\n"
                "- You MUST use this information to answer questions about topics in the documents.\n"
                "- When the question relates to anything in the personal context, answer using ONLY that information.\n"
                "- DO NOT say 'insufficient information' if the answer exists in the personal context.\n"
                "- Cite the source filename when using information (e.g., 'According to your document [filename]...').\n"
                "- If the personal context contains relevant information, prioritize it over your general knowledge.\n"
                "- Extract ALL relevant details from the context - be thorough and comprehensive.\n\n"
            )

        if context:
            system_prompt += f"Here is the recent conversation history for context:\n{context}\n\n"

        if rag_context:
            system_prompt += f"{rag_context}\n\n"
            system_prompt += (
                "Retrieval rules:\n"
                "- You MUST answer ONLY using the provided search results.\n"
                "- If relevant information exists in those results, do NOT claim there is no information available.\n"
                "- If results are insufficient or irrelevant, explicitly say information is insufficient.\n\n"
            )

        if force_web_grounded and rag_context:
            system_prompt += (
                "Answering rules for this request:\n"
                "- Use only the latest verified information provided above.\n"
                "- Do not invent or assume facts not present in that information.\n"
                "- If information is sufficient, provide a direct answer and cite evidence from the results.\n"
                "- If information is insufficient, explicitly say what is missing.\n\n"
            )

        return system_prompt

    @classmethod
    def _content_tokens(cls, text: str) -> List[str]:
        tokens = re.findall(r"[a-z0-9]{3,}", str(text or "").lower())
        return [token for token in tokens if token not in cls.GROUNDING_STOPWORDS]

    @classmethod
    def _is_answer_grounded(cls, answer: str, web_data: List[Dict[str, str]]) -> bool:
        if not answer or not str(answer).strip() or not web_data:
            return False

        web_corpus = " ".join(
            f"{item.get('title', '')} {item.get('snippet', '')}" for item in web_data
        )
        web_tokens = set(cls._content_tokens(web_corpus))
        answer_tokens = set(cls._content_tokens(answer))

        if not web_tokens or not answer_tokens:
            return False

        overlap = sum(1 for token in answer_tokens if token in web_tokens)
        overlap_ratio = overlap / max(1, len(answer_tokens))
        return overlap >= 3 and overlap_ratio >= 0.10

    @staticmethod
    def _looks_like_no_info_answer(answer: str) -> bool:
        text = " ".join(str(answer or "").lower().split())
        if not text:
            return True

        no_info_markers = (
            "no information available",
            "don't have enough information",
            "do not have enough information",
            "cannot determine",
            "can't determine",
            "insufficient information",
            "not enough information",
            "unable to find",
        )
        return any(marker in text for marker in no_info_markers)

    @staticmethod
    def _build_source_backed_answer(query: str, web_data: List[Dict[str, str]]) -> str:
        if not web_data:
            return ChatService.REALTIME_FALLBACK_MESSAGE

        key_points = []
        for item in web_data[:2]:
            snippet = " ".join(str(item.get("snippet", "")).split())
            if not snippet:
                continue
            key_points.append(snippet)

        if not key_points:
            return (
                f"I found recent updates for '{query}', but there is not enough detail yet "
                "to provide a reliable direct answer."
            )

        summary = " ".join(key_points)
        return f"Here's the latest update on '{query}': {summary}"

    @staticmethod
    def _build_short_answer(full_answer: str) -> str:
        text = str(full_answer or "").strip()
        if not text:
            return ChatService.REALTIME_FALLBACK_MESSAGE

        cleaned = (
            text.replace("\n", " ")
            .replace("[", " ")
            .replace("]", " ")
        )
        cleaned = re.sub(r"https?://\S+", "", cleaned)
        cleaned = re.sub(r"\bbased on recent sources?\s*:?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(
            r"\bsource\s*\d+\s*(says|said|confirms|reported)?\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"\bsources?\s*:\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\b(the same update|same update)\b\.?", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bfallback\b[^.]*\.?", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        if not cleaned:
            return ChatService.REALTIME_FALLBACK_MESSAGE

        cleaned = re.sub(r"^based on [^:]+:\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"^according to [^,]+,\s*", "", cleaned, flags=re.IGNORECASE)

        sentences = [
            sentence.strip()
            for sentence in re.split(r"(?<=[.!?])\s+", cleaned)
            if sentence.strip()
        ]

        sentences = [
            sentence
            for sentence in sentences
            if sentence.lower().strip(" .!?") not in {"same update", "the same update", "update"}
        ]

        short = " ".join(sentences[:2]) if sentences else cleaned
        short = " ".join(short.split())

        if len(short) > 240:
            words = short.split()
            short = " ".join(words[:34]).strip()
            if short and not short.endswith((".", "!", "?")):
                short += "..."

        if not short:
            return ChatService.REALTIME_FALLBACK_MESSAGE

        if not short.endswith((".", "!", "?")):
            short += "."

        return short

    @classmethod
    def _estimate_context_relevance(cls, message: str, context: str) -> float:
        query_terms = [
            token.lower()
            for token in str(message or "").replace("\n", " ").split()
            if len(token.strip(".,!?;:\"'()[]{}")) >= 4
        ]
        context_lower = str(context or "").lower()

        if not context_lower.strip():
            return 0.0

        if not query_terms:
            return 1.0

        normalized_terms = []
        for term in query_terms:
            cleaned = term.strip(".,!?;:\"'()[]{}")
            if cleaned:
                normalized_terms.append(cleaned)

        if not normalized_terms:
            return 1.0

        unique_terms = set(normalized_terms)
        matches = sum(1 for term in unique_terms if term in context_lower)
        return max(0.0, min(1.0, matches / len(unique_terms)))

    @classmethod
    def _derive_confidence(cls, trust_score: int) -> str:
        if trust_score >= 80:
            return "high"
        if trust_score >= 55:
            return "medium"
        return "low"

    @staticmethod
    async def process_chat(user_id: str, message: str, voice_mode: bool = False) -> dict:
        """
        Main workflow for processing a chat message.
        Now includes memory context retrieval for personalized responses.
        """
        # 1. Perspective Autopsy (Gemini)
        autopsy_res = await autopsy_service.perform_autopsy(message)

        # 2. Conditional Query Reframing (Wow Mode)
        reframe_payload = await reframe_service.reframe_query(message, autopsy_res)
        reframed_query = str((reframe_payload or {}).get("reframed_query", "")).strip()
        query_for_reasoning = reframed_query or message

        # 3. Context retrieval (conversation history)
        context = await context_service.get_user_context(user_id, limit=5)

        # 3b. Memory context retrieval (user's personal documents)
        memory_results = await retrieval_service.retrieve_context(
            query=query_for_reasoning,
            user_id=user_id,
            top_k=10,
            similarity_threshold=0.25  # Lower threshold to get more context
        )
        memory_context = retrieval_service.format_context_for_prompt(memory_results)
        memory_used = bool(memory_results)
        
        if memory_used:
            print(f"[ChatService] ✓ Memory context used: {len(memory_results)} chunks from user documents")

        # 4. Real-time detection + forced search (critical path)
        autopsy_needs_search = bool((autopsy_res or {}).get("needs_search", False))
        realtime_needs_search = rag_service.is_realtime_query(query_for_reasoning)
        voice_realtime_strict = bool(voice_mode and realtime_needs_search)
        force_search = autopsy_needs_search or realtime_needs_search or voice_realtime_strict

        web_data: List[Dict[str, str]] = []
        search_used = False
        main_answer = ""

        if force_search:
            web_data = await rag_service.search_web(query_for_reasoning)
            web_data = [
                {
                    "title": str(item.get("title", "")),
                    "snippet": str(item.get("snippet", "")),
                    "url": str(item.get("url", "")),
                }
                for item in (web_data or [])
                if isinstance(item, dict)
            ]
            search_used = bool(web_data)

            if not web_data:
                if voice_realtime_strict:
                    main_answer = ChatService.VOICE_REALTIME_FALLBACK_MESSAGE

        if not main_answer:
            rag_context = rag_service.construct_rag_context(web_data) if web_data else ""
            system_prompt = ChatService._build_main_system_prompt(
                context=context,
                rag_context=rag_context,
                memory_context=memory_context,
                force_web_grounded=force_search and bool(web_data),
            )
            main_answer = await llama_service.get_ai_response(
                query_for_reasoning,
                system_prompt=system_prompt,
            )

            if force_search and web_data and ChatService._looks_like_no_info_answer(main_answer):
                no_info_recovery_prompt = (
                    ChatService._build_main_system_prompt(
                        context=context,
                        rag_context=rag_context,
                        memory_context=memory_context,
                        force_web_grounded=True,
                    )
                    + "IMPORTANT: Relevant search results are already provided. "
                    + "Give a direct answer using those results. Do not reply with no information available."
                )
                main_answer = await llama_service.get_ai_response(
                    query_for_reasoning,
                    system_prompt=no_info_recovery_prompt,
                )

            if force_search and web_data:
                is_grounded = ChatService._is_answer_grounded(main_answer, web_data)

                if not is_grounded:
                    stricter_prompt = (
                        ChatService._build_main_system_prompt(
                            context=context,
                            rag_context=rag_context,
                            memory_context=memory_context,
                            force_web_grounded=True,
                        )
                        + "STRICT VALIDATION MODE: Previous answer did not align with the provided "
                        + "information. Regenerate using only the latest verified information. "
                        + "Do not use prior knowledge."
                    )
                    main_answer = await llama_service.get_ai_response(
                        query_for_reasoning,
                        system_prompt=stricter_prompt,
                    )
                    is_grounded = ChatService._is_answer_grounded(main_answer, web_data)

                    if not is_grounded:
                        main_answer = ChatService._build_source_backed_answer(
                            query_for_reasoning,
                            web_data,
                        )

            if force_search and web_data and ChatService._looks_like_no_info_answer(main_answer):
                main_answer = ChatService._build_source_backed_answer(
                    query_for_reasoning,
                    web_data,
                )
        short_answer = ChatService._build_short_answer(main_answer)

        # 5. Multi-perspective generation
        answer = await perspective_service.generate_perspectives(
            user_query=query_for_reasoning,
            context=context,
            base_answer=main_answer,
        )

        # 6. Ethical check
        ethical_check = await ethics_service.get_ethical_perspectives(main_answer, query_for_reasoning)

        # 7. Explanation generation
        explanation = await explanation_service.generate_explanation(
            user_query=query_for_reasoning,
            perspective_answer=answer,
            ethical_check=ethical_check,
            perspective_autopsy=autopsy_res,
            context=context,
        )

        # 8. Trust score calculation
        context_relevance = ChatService._estimate_context_relevance(query_for_reasoning, context)
        trust_payload = trust_service.calculate_trust_score(
            context_relevance=context_relevance,
            bias_detected=bool(ethical_check.get("bias_detected", False)),
            response_text=main_answer,
            explanation=explanation,
        )
        trust_score = int(trust_payload.get("trust_score", 0))
        confidence = ChatService._derive_confidence(trust_score)

        # Persist only the main answer for conversation history continuity.
        if supabase:
            try:
                supabase.table("conversations").insert(
                    {
                        "user_id": user_id,
                        "message": message,
                        "response": main_answer,
                    }
                ).execute()
            except Exception as e:
                print(f"Failed to save conversation: {str(e)}")

        # New contract fields + legacy compatibility fields.
        return {
            "perspective_autopsy": autopsy_res,
            "reframed_query": reframed_query or None,
            "answer": answer,
            "explanation": explanation,
            "ethical_check": ethical_check,
            "trust_score": trust_score,
            "confidence": confidence,
            "search_used": search_used,
            "memory_used": memory_used,
            "sources": web_data,
            "full_answer": main_answer,
            "short_answer": short_answer,
            "trust_evaluation": {
                "trust_score": trust_score,
                "confidence": confidence,
            },
            "neutral_reframe": ({"reframed_query": reframed_query} if reframed_query else None),
            "response": main_answer,
            "ethical_perspectives": answer,
            "audit_results": ethical_check,
        }


chat_service = ChatService()
