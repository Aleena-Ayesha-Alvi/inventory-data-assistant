import pandas as pd
from langchain_core.tools import tool
import ast

# Global variable to hold the dataframe once loaded in the app
_df_context = None

FORBIDDEN_CALLS = {
    "__import__", "open", "eval", "exec", "compile", "exit", "quit",
    "getattr", "setattr", "delattr", "globals", "locals", "vars", "input", "breakpoint"
}

# Pandas methods/objects that read or write files, or evaluate strings as code
FORBIDDEN_ATTRIBUTES = {
    "to_csv", "to_excel", "to_pickle", "to_parquet", "to_json", "to_hdf", "to_sql",
    "to_feather", "to_stata", "to_html", "to_latex", "to_clipboard", "to_xml",
    "to_markdown", "to_orc", "ExcelWriter", "HDFStore", "io", "eval"
}

SAFE_BUILTINS = {
    "print": print, "len": len, "max": max, "min": min, "sum": sum, "abs": abs,
    "round": round, "sorted": sorted, "int": int, "float": float, "str": str,
    "bool": bool, "list": list, "dict": dict, "tuple": tuple, "set": set,
    "range": range, "zip": zip, "enumerate": enumerate, "any": any, "all": all
}

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
                if node.func.id in FORBIDDEN_CALLS:
                    return f"Security Exception: Call to forbidden function '{node.func.id}'."
            # Dunder access (e.g. ().__class__.__subclasses__()) is the classic sandbox escape
            if isinstance(node, ast.Name) and node.id.startswith("__"):
                return f"Security Exception: Access to '{node.id}' is prohibited."
            if isinstance(node, ast.Attribute):
                if node.attr.startswith("_"):
                    return f"Security Exception: Access to private attribute '{node.attr}' is prohibited."
                # Pandas I/O (pd.read_csv, df.to_csv, ...) would give file system access
                if node.attr.startswith("read_") or node.attr in FORBIDDEN_ATTRIBUTES:
                    return f"Security Exception: File/system operation '{node.attr}' is prohibited."

        # Compile and execute within a highly restricted context.
        # The dataframe is copied so generated code can never mutate the source data.
        local_vars = {"df": _df_context.copy(), "pd": pd}
        global_vars = {"__builtins__": SAFE_BUILTINS}
        
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