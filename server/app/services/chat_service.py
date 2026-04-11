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


class ChatService:
    """
    Business logic layer orchestrating the full response pipeline:
    1) autopsy, 2) optional query reframe, 3) context, 4) answer generation,
    5) multi-perspective answer, 6) ethical check, 7) explanation,
    8) trust score.
    """

    REALTIME_FALLBACK_MESSAGE = "I couldn't fetch real-time data right now, please try again."
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
        force_web_grounded: bool = False,
    ) -> str:
        system_prompt = (
            "You are Intellexa Core, a sophisticated AI assistant designed "
            "to provide ethical, context-aware, and helpful responses.\n"
            "For any question about current facts, you MUST rely on search results. "
            "If search results are available, do NOT use your own knowledge.\n\n"
        )

        if context:
            system_prompt += f"Here is the recent conversation history for context:\n{context}\n\n"

        if rag_context:
            system_prompt += f"{rag_context}\n\n"

        if force_web_grounded and rag_context:
            system_prompt += (
                "Answering rules for this request:\n"
                "- Use only the latest verified information provided above.\n"
                "- Do not invent or assume facts not present in that information.\n"
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
    async def process_chat(user_id: str, message: str) -> dict:
        """
        Main workflow for processing a chat message.
        """
        # 1. Perspective Autopsy (Gemini)
        autopsy_res = await autopsy_service.perform_autopsy(message)

        # 2. Conditional Query Reframing (Wow Mode)
        reframe_payload = await reframe_service.reframe_query(message, autopsy_res)
        reframed_query = str((reframe_payload or {}).get("reframed_query", "")).strip()
        print(f"REFRAMED: {reframed_query or '<none>'}")
        query_for_reasoning = reframed_query or message

        # 3. Context retrieval
        context = await context_service.get_user_context(user_id, limit=5)

        # 4. Real-time detection + forced search (critical path)
        autopsy_needs_search = bool((autopsy_res or {}).get("needs_search", False))
        realtime_needs_search = rag_service.is_realtime_query(query_for_reasoning)
        force_search = autopsy_needs_search or realtime_needs_search
        print(
            "[RAG][RealtimeGate] "
            f"triggered={force_search} "
            f"autopsy_needs_search={autopsy_needs_search} "
            f"realtime_detected={realtime_needs_search}"
        )

        web_data: List[Dict[str, str]] = []
        search_used = False
        main_answer = ""

        if force_search:
            print(f"[RAG][Search] Triggered for query: '{query_for_reasoning}'")
            web_data = await rag_service.search_web(query_for_reasoning)
            search_used = bool(web_data)
            print(f"[RAG][Search] Result count: {len(web_data)}")

            for index, item in enumerate(web_data[:4], start=1):
                title = " ".join(str(item.get("title", "")).split())
                snippet = " ".join(str(item.get("snippet", "")).split())
                print(f"[RAG][Search][{index}] {title} :: {snippet[:220]}")

            if not web_data:
                print("[RAG][Search] Forced search failed; returning safe fallback response.")
                main_answer = ChatService.REALTIME_FALLBACK_MESSAGE

        if not main_answer:
            rag_context = rag_service.construct_rag_context(web_data) if web_data else ""
            system_prompt = ChatService._build_main_system_prompt(
                context=context,
                rag_context=rag_context,
                force_web_grounded=force_search and bool(web_data),
            )
            main_answer = await llama_service.get_ai_response(
                query_for_reasoning,
                system_prompt=system_prompt,
            )

            if force_search and web_data:
                is_grounded = ChatService._is_answer_grounded(main_answer, web_data)
                print(f"[RAG][Validation] grounded={is_grounded}")

                if not is_grounded:
                    stricter_prompt = (
                        ChatService._build_main_system_prompt(
                            context=context,
                            rag_context=rag_context,
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
                    print(f"[RAG][Validation] grounded_after_retry={is_grounded}")

                    if not is_grounded:
                        print("[RAG][Validation] Retry mismatch; returning safe fallback response.")
                        main_answer = ChatService.REALTIME_FALLBACK_MESSAGE

        print(f"[RAG][FinalAnswer] {str(main_answer)[:260]}")

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
            "sources": web_data,
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
