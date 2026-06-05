# Task 1: Edge Cases & Engineering Decisions

### 1. Dirty Data Handling (The "Phantom Column" Bug)
**Issue:** The raw `inventory_data.csv` contained leading commas, causing Pandas to load an empty, unnamed first column (`Unnamed: 0`).
**Solution:** Built a dynamic scrubber in the `load_data()` function that bypasses junk header rows and uses `.dropna(how='all', axis=1)` alongside regex column matching to strip phantom columns before the LLM ever sees the data.

### 2. Rate Limiting & Multi-Agent Loops
**Issue:** Free-tier LLM API keys restrict requests per minute. The ReAct (Reason + Act) loop makes 3-4 micro-requests per user query (Thought -> Tool Call -> Observation -> Final Answer), instantly triggering `429 RESOURCE_EXHAUSTED` errors.
**Solution:** Configured LangChain's `max_retries=6` parameter to gracefully catch rate limits and throttle the execution loop rather than crashing the Streamlit UI.

### 3. Upstream API Outages (503 Service Unavailable)
**Issue:** During load testing, the upstream LLM provider returned a `503 UNAVAILABLE` error due to high global demand.
**Future Production Fix:** A hard 503 outage requires a multi-model fallback strategy. In a production environment, I would wrap the initialization function in a `try/except` block to automatically route failed primary calls to a backup provider (e.g., falling back from Gemini to Groq/Llama 3) to ensure zero downtime.