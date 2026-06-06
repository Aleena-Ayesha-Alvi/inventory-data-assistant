import streamlit as st
import pandas as pd
import os
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel, Field

# Import our secure backend logic
from secure_agent import query_dataset, set_dataframe

# 1. Page Configuration
st.set_page_config(page_title="Data Query Agent", page_icon="📊", layout="wide")
st.title("📊 Inventory Data Assistant")

# 2. Robust Data Loading
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
        
        # Clean up phantom columns
        clean_df = clean_df.dropna(how='all', axis=1) 
        clean_df = clean_df.loc[:, ~clean_df.columns.str.contains('^Unnamed')] 
        
        # THE ULTIMATE CLEANER: Strip edges, remove newlines, AND crush multiple/weird spaces into one
        clean_df.columns = clean_df.columns.str.replace('\n', '', regex=False).str.replace(r'\s+', ' ', regex=True).str.strip()
        
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

# 3. Pydantic Schema for Call 1 (Structured Planning)
class AgentPlan(BaseModel):
    definition_answer: str = Field(description="The definition of any terms requested by the user. Leave empty if none requested.")
    pandas_code: str = Field(description="The pandas code to execute to answer the data question. Must start with 'result = ...'. Leave empty if no math/data needed.")

# 4. Initialize Chat Memory
if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# 5. The Optimized Two-Call Pipeline
if prompt := st.chat_input("Ask a question about the inventory data..."):
    if df is None:
        st.warning("Data source is missing. Cannot query.")
        st.stop()

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Analyzing and Computing..."):
            try:
                # Setup Groq for lightning-fast, unlimited testing
                llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0)
                
                # --- API CALL 1: Planning & Coding ---
                # Dynamically extract the cleaned columns
                columns = ", ".join(df.columns.tolist())
                
                system_instruction = f"""You are a precise data assistant. 
                Available DataFrame 'df' columns: [{columns}]
                
                CRITICAL RULES:
                1. Answer definition questions in 'definition_answer'.
                2. Write pandas code into 'pandas_code' based ONLY on the exact columns provided above.
                3. Your code MUST start with 'result = '.
                4. Use standard pandas methods (e.g., result = df['Product ID'].nunique()).
                5. DO NOT use markdown, backticks (```), or any formatting. Pure text code only."""
                
                structured_llm = llm.with_structured_output(AgentPlan)
                plan = structured_llm.invoke([SystemMessage(content=system_instruction), HumanMessage(content=prompt)])
                
                # --- LOCAL EXECUTION: Sandbox ---
                data_result = ""
                if plan.pandas_code and plan.pandas_code.strip():
                    # TELEMETRY: Print exactly what Groq wrote
                    st.info(f"💻 Agent generated code: `{plan.pandas_code}`")
                    
                    tool_output = query_dataset.invoke({"pandas_code": plan.pandas_code})
                    data_result = str(tool_output)
                    
                    # TELEMETRY: Print exactly what the Sandbox returned
                    if "Error" in data_result:
                        st.error(f"🛡️ Sandbox rejected execution: {data_result}")
                    else:
                        st.success(f"🛡️ Sandbox execution successful: {data_result}")
                
                # --- API CALL 2: Synthesis ---
                synthesis_prompt = f"""User asked: {prompt}
                Definition context found: {plan.definition_answer}
                Data computation result: {data_result}
                
                Combine this information into a clean, direct, human-readable final answer. Do not show the pandas code."""
                
                final_response = llm.invoke([HumanMessage(content=synthesis_prompt)])
                final_answer = final_response.content

                # Render and save
                st.markdown(final_answer)
                st.session_state.messages.append({"role": "assistant", "content": final_answer})
                
            except Exception as e:
                st.error(f"Execution Error: {str(e)}")