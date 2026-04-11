from app.services.llama_service import llama_service
from app.services.autopsy_service import autopsy_service
from app.services.context_service import context_service
from app.services.ethics_service import ethics_service
from app.services.explanation_service import explanation_service
from app.services.perspective_service import perspective_service
from app.services.reframe_service import reframe_service
from app.services.trust_service import trust_service
from app.db.supabase import supabase



class ChatService:
    """
    Business logic layer orchestrating the full response pipeline:
    1) autopsy, 2) optional query reframe, 3) context, 4) main answer,
    5) multi-perspective answer, 6) ethical check, 7) explanation,
    8) trust score.
    """

    @classmethod
    def _build_main_system_prompt(cls, context: str) -> str:
        system_prompt = (
            "You are Intellexa Core, a sophisticated AI assistant designed "
            "to provide ethical, context-aware, and helpful responses.\n\n"
        )

        if context:
            system_prompt += f"Here is the recent conversation history for context:\n{context}\n"

        return system_prompt

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

        # 4. Main answer (LLaMA)
        system_prompt = ChatService._build_main_system_prompt(context)
        main_answer = await llama_service.get_ai_response(query_for_reasoning, system_prompt=system_prompt)

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
                supabase.table("conversations").insert({
                    "user_id": user_id,
                    "message": message,
                    "response": main_answer
                }).execute()
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
            "trust_evaluation": {
                "trust_score": trust_score,
                "confidence": confidence,
            },
            "neutral_reframe": (
                {"reframed_query": reframed_query}
                if reframed_query
                else None
            ),
            "response": main_answer,
            "ethical_perspectives": answer,
            "audit_results": ethical_check,
        }


chat_service = ChatService()
