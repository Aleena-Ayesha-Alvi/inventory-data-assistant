# Task 1: Edge Cases & Engineering Decisions

### 1. Bulletproofing Excel Ingestion (Phantom Columns & Hidden Whitespace)
**Issue:** The raw `inventory_data.xlsx` was messy. Not only did it load empty "phantom columns" (`Unnamed: 0`), but the headers contained hidden newlines and non-breaking spaces (e.g., `"Hand-In-\nStock"`). This caused Pandas `KeyError` crashes when the LLM generated exact-string matching queries.
**Solution:** Built a dynamic, regex-powered scrubber in the `load_data()` function. It bypasses junk rows, drops empty axes, and aggressively crushes all hidden whitespace and newlines into standard spaces. The clean column names are then dynamically injected into the LLM prompt to guarantee perfect mapping.

### 2. The 429 Quota Death & The Sequential Pipeline Pivot
**Issue:** The initial ReAct (Reason + Act) loop architecture made 3-5 micro-requests per query. This instantly exhausted the free-tier API rate limits (`429 RESOURCE_EXHAUSTED`) during basic testing.
**Solution:** Scrapped the ReAct loop entirely to optimize token and API usage. Architected a two-call Sequential Pipeline using LangChain's Pydantic Structured Outputs. Call 1 acts as the Planner/Coder, and Call 2 acts as the Synthesizer. Switched the execution engine to Groq (Llama 3.3) to completely bypass rate limits and ensure lightning-fast, predictable execution.

### 3. The Security Sandbox AST Trap (Assignment Syntax)
**Issue:** The backend `secure_agent.py` vault uses strict parsing to evaluate code safely. When the LLM was prompted to write complex pandas aggregations, conflicts between the Pydantic schema constraints and the system prompt caused it to generate invalid multi-assignment syntax (e.g., `result = x, result = y`), instantly crashing the sandbox.
**Solution:** Synced the Pydantic schema and the system prompt to enforce strict, single-list assignment for multi-variable outputs. The LLM now reliably generates perfectly formatted, sandbox-compliant Python code.