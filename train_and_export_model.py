import json
import re
import sys
import os

def run_notebook_code():
    with open("telecom_churn_analysis.ipynb.ipynb", "r", encoding="utf-8") as f:
        nb = json.load(f)
    
    code_cells = []
    for cell in nb.get('cells', []):
        if cell.get('cell_type') == 'code':
            code_cells.append("".join(cell.get('source', [])))
            
    # Combine code cells into a single execution block
    full_code = "\n\n# ==========================================\n\n".join(code_cells)
    
    # Force Agg backend to prevent figure popups blocking execution
    full_code = "import matplotlib\nmatplotlib.use('Agg')\n" + full_code
    
    # Save code to run_notebook.py
    with open("run_notebook.py", "w", encoding="utf-8") as f:
        f.write(full_code)
        
    print("Code extracted. Running execution of the full notebook code...")
    
    # Execute the python script and pipe output
    import subprocess
    result = subprocess.run(
        [sys.executable, "run_notebook.py"],
        capture_output=True,
        text=True,
        encoding="utf-8"
    )
    
    with open("notebook_execution_output.txt", "w", encoding="utf-8") as out:
        out.write("=== STDOUT ===\n")
        out.write(result.stdout)
        out.write("\n=== STDERR ===\n")
        out.write(result.stderr)
        
    print("Execution complete. Output saved to notebook_execution_output.txt")
    print(result.stdout[-1500:]) # Print the end of stdout
    if result.returncode != 0:
        print(f"Error occurred. Exit code: {result.returncode}")
        print(result.stderr[-1500:])

if __name__ == "__main__":
    run_notebook_code()
