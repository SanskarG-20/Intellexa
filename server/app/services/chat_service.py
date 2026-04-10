import asyncio
import datetime
from app.services.llama_service import llama_service
from app.services.autopsy_service import autopsy_service
from app.services.context_service import context_service
from app.services.ethics_service import ethics_service
from app.services.audit_service import audit_service
from app.services.explain_service import explain_service
from app.services.trust_service import trust_service
from app.services.rag_service import rag_service
from app.services.reframe_service import reframe_service
from app.db.supabase import supabase
from app.core.config import settings


class ChatService:
    """
    Business logic layer orchestrating:
    Cognitive Analysis → Smart RAG → LLM Generation (with live data)
    → Ethical Auditing → Trust Evaluation
    Uses an Asynchronous Parallel Pipeline for minimal latency.
    """

    @staticmethod
    async def process_chat(user_id: str, message: str) -> dict:
        """
        Main workflow optimized for minimal latency using parallel execution.
        """
        # ─── PHASE 1: Parallel Intake ────────────────────────────────────────
        # Cognitive Analysis + History Retrieval + Neutral Reframe all run at once.
        autopsy_task = autopsy_service.perform_autopsy(message)
        context_task = context_service.get_user_context(user_id, limit=5)
        reframe_task = reframe_service.reframe_query(message)

        autopsy_res, context, reframe_res = await asyncio.gather(
            autopsy_task, context_task, reframe_task
        )

        # ─── PHASE 2: Conditional Smart RAG ─────────────────────────────────
        # The Perspective Autopsy semantically decides if a web search is needed.
        # No keywords — purely intent-based routing.
        rag_context = ""
        if autopsy_res.get("needs_search"):
            print(f"[ChatService] RAG triggered — fetching live data for: '{message[:40]}'")
            web_data = await rag_service.search_web(message)
            if web_data:
                rag_context = rag_service.construct_rag_context(web_data)
                print(f"[ChatService] RAG context injected: {len(web_data)} source(s) found.")
            else:
                print("[ChatService] RAG fetch returned no results. Answering from model knowledge.")

        # ─── PHASE 3: Context-Aware Generation ───────────────────────────────
        # Build the full system prompt with: current datetime + history + live data.
        now = datetime.datetime.now().strftime("%A, %d %B %Y, %I:%M %p IST")
        system_prompt = (
            "You are Intellexa Core, an intelligent, ethical, and context-aware AI assistant.\n"
            f"Current date and time: {now}\n"
            "Your training knowledge cutoff is December 2023.\n"
            "If the user asks about events after December 2023, "
            "use the LIVE WEB DATA section below (if provided) to answer accurately.\n"
            "If no live data is provided and the question requires it, "
            "clearly state your knowledge cutoff and suggest the user verify online.\n\n"
        )

        if context:
            system_prompt += f"### CONVERSATION HISTORY (last 5 turns):\n{context}\n\n"

        if rag_context:
            system_prompt += rag_context  # Already formatted with timestamp by rag_service

        # Call the primary LLM (Llama 3.1) with the enriched prompt
        ai_response = await llama_service.get_ai_response(message, system_prompt=system_prompt)

        # ─── PHASE 4: Parallel Intelligence ─────────────────────────────────
        # Ethics, Bias Audit, and Explanation run simultaneously.
        ethics_task = ethics_service.get_ethical_perspectives(ai_response)
        audit_task = audit_service.audit_response(ai_response)
        explain_task = explain_service.explain_answer(message, ai_response)

        ethical_p, audit_res, reasoning_steps = await asyncio.gather(
            ethics_task, audit_task, explain_task
        )

        # ─── PHASE 5: Final Synthesis ─────────────────────────────────────────
        trust_eval = await trust_service.evaluate_trust(autopsy_res, audit_res)

        # Persist conversation to Supabase
        if supabase:
            try:
                supabase.table("conversations").insert({
                    "user_id": user_id,
                    "message": message,
                    "response": ai_response
                }).execute()
            except Exception as e:
                print(f"[ChatService] DB save failed: {str(e)}")

        return {
            "response": ai_response,
            "ethical_perspectives": ethical_p,
            "audit_results": audit_res,
            "perspective_autopsy": autopsy_res,
            "explanation": reasoning_steps,
            "trust_evaluation": trust_eval,
            "neutral_reframe": reframe_res,
        }


chat_service = ChatService()
