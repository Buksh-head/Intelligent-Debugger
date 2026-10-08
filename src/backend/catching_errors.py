import ast
import subprocess
import sys

def capture_and_print_errors(student_code: str):
    """
    Executes student code and prints out the exact error or success output.
    """
    print("-" * 40)
    print("Code test")
    
    # Catch Syntax Errors
    try:
        ast.parse(student_code)
    except SyntaxError as e:
        print("SYNTAX ERROR")
        print(f"Error Type: {type(e).__name__}")
        print(f"Line Number: {e.lineno}")
        print(f"Message: {e.msg}")
        return

    # Catch Runtime Errors and Infinite Loops
    try:
        # Run the code in a subprocess
        process = subprocess.run(
            [sys.executable, '-c', student_code],
            capture_output=True,
            text=True,
            timeout=2.0 # Force quit after 2 seconds
        )
        
        # Check if the program crashed while running
        if process.returncode != 0:
            print("RUNTIME ERROR")
            print("Raw Traceback Text:")
            print(process.stderr.strip())
            return
            
        # Print output if no error
        print("NO ERROR")
        print("Output:")
        print(process.stdout.strip())
        
    except subprocess.TimeoutExpired:
        print("TIMEOUT (INFINITE LOOP)")
        print("The code ran longer than 2 seconds")

if __name__ == "__main__":
    
    # 1. A Syntax Error (Missing colon)
    code_syntax_error = """
if True
    print("Hello")
    """
    capture_and_print_errors(code_syntax_error)

    # 2. A Runtime Error (Adding a string and an integer)
    code_runtime_error = """
age = "twenty"
print(age + 5)
    """
    capture_and_print_errors(code_runtime_error)

    # 3. An Infinite Loop
    code_timeout = """
while True:
    pass
    """
    capture_and_print_errors(code_timeout)

    # 4. Perfect Code
    code_success = """
print("Hello, world! My code works.")
    """
    capture_and_print_errors(code_success)
