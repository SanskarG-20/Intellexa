"""
Direct test of the RAG pipeline — no API server needed.
Tests: DDG search, context building, and injection into the system prompt.
"""
import asyncio
import datetime
from app.services.rag_service import rag_service
from app.services.autopsy_service import autopsy_service


async def test():
    query = "Who won IPL 2024?"
    print(f"\n{'='*55}")
    print(f"  RAG Pipeline End-to-End Test")
    print(f"{'='*55}")
    print(f"Query: {query}")
    print(f"Time:  {datetime.datetime.now().strftime('%d %B %Y %I:%M %p')}\n")

    # Step 1: Autopsy (should set needs_search=True)
    print("[1] Running Perspective Autopsy...")
    autopsy = await autopsy_service.perform_autopsy(query)
    print(f"    needs_search = {autopsy.get('needs_search')}")
    print(f"    bias_detected = {autopsy.get('bias_detected')}")

    # Step 2: Live Search
    print("\n[2] Triggering web search...")
    results = await rag_service.search_web(query)
    print(f"    Sources found: {len(results)}")
    for i, r in enumerate(results, 1):
        print(f"    [{i}] {r['title'][:60]}")
        print(f"        {r['snippet'][:100]}...")

    # Step 3: Build RAG context
    print("\n[3] Building RAG context for LLM...")
    ctx = rag_service.construct_rag_context(results)
    if ctx:
        print(ctx[:500])
    else:
        print("    [!] No context built — search returned nothing.")

    print(f"\n{'='*55}")
    print("  Test Complete")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    asyncio.run(test())
