import os
import pandas as pd
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain.agents import tool
from langchain_core.prompts import ChatPromptTemplate
import ast

load_dotenv()

# Global variable to hold the dataframe once loaded in the app
_df_context = None

def set_dataframe(df):
    global _df_context
    _df_context = df

def safe_pandas_eval(code_str: str) -> str:
    """
    Secures arbitrary code execution by checking the Abstract Syntax Tree (AST)
    and evaluating the expression in an isolated, restricted environment.
    """
    global _df_context
    if _df_context is None:
         return "Error: No dataset has been uploaded yet."
         
    try:
        # Clean up code blocks if LLM wraps it in markdown
        if "```" in code_str:
            code_str = code_str.split("```python")[-1].split("```")[0].strip()
        
        # Parse the code into an AST to verify safety
        tree = ast.parse(code_str, mode='exec')
        
        # Walk through nodes to block dangerous operations (like builtins, imports, or file access)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                return "Security Exception: Imports are prohibited in this sandbox."
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in ['__import__', 'open', 'eval', 'exec', 'exit', 'quit']:
                    return f"Security Exception: Call to forbidden function '{node.func.id}'."

        # Compile and execute within a highly restricted context
        local_vars = {"df": _df_context, "pd": pd}
        global_vars = {"__builtins__": {
            "print": print, "len": len, "max": max, "min": min, "int": int, 
            "float": float, "str": str, "list": list, "dict": dict, "range": range
        }}
        
        # Divert stdout to capture execution outputs if any, or evaluate expression
        exec(compile(tree, filename="<llm_sandbox>", mode="exec"), global_vars, local_vars)
        
        # Look for a result variable or return a description of the state
        if "result" in local_vars:
            return str(local_vars["result"])
        
        return "Code executed successfully, but no 'result' variable was assigned."
        
    except Exception as e:
        return f"Execution Error: {str(e)}. Please check your query syntax and try again."

@tool
def query_dataset(pandas_code: str) -> str:
    """
    Executes safe Python/Pandas operations on the active dataset 'df'.
    Always assign your final answer to a variable named 'result'.
    Example: result = df['Quantity'].sum()
    """
    return safe_pandas_eval(pandas_code)

@tool
def search_definitions(term: str) -> str:
    """
    Searches the corporate metadata and glossary for definitions of specific inventory terms.
    """
    # Placeholder definitions for inventory context; can be expanded or hooked to duckduckgo
    glossary = {
        "sku": "Stock Keeping Unit - a unique identifier for each distinct product.",
        "reorder point": "The minimum inventory level at which new stock must be ordered.",
        "safety stock": "Surplus inventory held to protect against supply chain shortages."
    }
    return glossary.get(term.lower(), f"No direct glossary match found for '{term}'. Processing general lookup...")

def get_data_agent():
    # Bind our secure tools to the model
    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    tools = [query_dataset, search_definitions]
    return llm.bind_tools(tools)