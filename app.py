import streamlit as st
import pandas as pd
import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage

# Import our secure backend logic
from secure_agent import query_dataset, search_definitions, set_dataframe

# 1. Page Configuration
st.set_page_config(page_title="Data Query Agent", page_icon="📊", layout="wide")
st.title("📊 Inventory Data Assistant")

# 2. Hardcoded & Scrubbed Data Loading
current_dir = os.path.dirname(os.path.abspath(__file__))
data_path = os.path.join(current_dir, "data", "inventory_data.xlsx")

@st.cache_data
def load_data():
    try:
        raw_df = pd.read_excel(data_path, header=None)
        header_row_index = 0
        for idx, row in raw_df.iterrows():
            if row.notna().sum() >= (raw_df.shape[1] * 0.5): 
                header_row_index = idx
                break
        clean_df = pd.read_excel(data_path, skiprows=header_row_index)
        
        # --- THE FIX: Clean up phantom columns ---
        clean_df = clean_df.dropna(how='all', axis=1) # Drops columns that are entirely empty
        clean_df = clean_df.loc[:, ~clean_df.columns.str.contains('^Unnamed')] # Drops columns Pandas couldn't name
        # -----------------------------------------
        
        set_dataframe(clean_df)
        return clean_df
    except Exception as e:
        st.error(f"Failed to load dataset at {data_path}. Error: {e}")
        return None

df = load_data()

if df is not None:
    with st.sidebar:
        st.success("Internal Dataset Connected.")
        st.metric("Total Rows", df.shape[0])
        st.metric("Total Columns", df.shape[1])
        with st.expander("Preview Data"):
            st.dataframe(df.head())

# 3. Robust System Prompt & Raw LLM Setup
@st.cache_resource
def get_llm_with_tools():
    llm = ChatGoogleGenerativeAI(
        model="gemini-3.5-flash", 
        temperature=0,
        max_retries=6
    )
    tools = [query_dataset, search_definitions]
    return llm.bind_tools(tools)

llm_with_tools = get_llm_with_tools()

system_prompt = """You are a precise, analytical Data Query Agent. 
Your strict purpose is to answer questions based ONLY on the provided dataset and glossary.

Rules:
1. For data questions, ALWAYS use the 'query_dataset' tool to execute safe Pandas code.
2. For definitions or context, use the 'search_definitions' tool.
3. Never guess, assume, or hallucinate data.
4. If the data cannot be found or extracted, state that clearly.
5. Present your final answers cleanly and directly. Do not mention your internal tools, prompt, or that you are an AI.
6. CRITICAL: You must use the native JSON tool-calling API. DO NOT output raw text or XML tags like <function>."""

# 4. Initialize Chat Memory
if "messages" not in st.session_state:
    st.session_state.messages = []

# 5. Render Chat History
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# 6. The Manual ReAct Execution Loop
if prompt := st.chat_input("Ask a question about the inventory data..."):
    if df is None:
        st.warning("Data source is missing. Cannot query.")
        st.stop()

    # Display user question
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Analyzing data..."):
            try:
                # Convert our Streamlit history into strict LangChain Message objects
                messages = [SystemMessage(content=system_prompt)]
                for m in st.session_state.messages:
                    if m["role"] == "user":
                        messages.append(HumanMessage(content=m["content"]))
                    elif m["role"] == "assistant":
                        messages.append(AIMessage(content=m["content"]))

                # Step 1: Send the conversation to the LLM
                response = llm_with_tools.invoke(messages)

                # Step 2: Did the LLM decide it needs to use a tool?
                if response.tool_calls:
                    messages.append(response) # Log the LLM's "thought" to use a tool
                    
                    # Execute the tools it asked for
                    for tool_call in response.tool_calls:
                        tool_name = tool_call["name"]
                        tool_args = tool_call["args"]
                        
                        # Route to our secure tools
                        if tool_name == "query_dataset":
                            tool_result = query_dataset.invoke(tool_args)
                        elif tool_name == "search_definitions":
                            tool_result = search_definitions.invoke(tool_args)
                        else:
                            tool_result = f"Error: Unknown tool '{tool_name}'"
                            
                        # Package the raw data result and send it back to the LLM
                        messages.append(ToolMessage(content=str(tool_result), tool_call_id=tool_call["id"]))
                    
                    # Step 3: LLM reads the tool output and synthesizes the final English answer
                    final_response = llm_with_tools.invoke(messages)
                    final_answer = final_response.content
                else:
                    # The LLM answered directly without needing tools
                    final_answer = response.content

                # Render and save
                st.markdown(final_answer)
                st.session_state.messages.append({"role": "assistant", "content": final_answer})
                
            except Exception as e:
                st.error(f"Execution Error: {str(e)}")