import os
import sys
import subprocess
import time
import webbrowser

def main():
    print("=" * 60)
    print("      RecipeLab: Multi-Agent Culinary Assistant Setup")
    print("=" * 60)
    
    # Check if virtual env exists
    base_dir = os.path.dirname(os.path.abspath(__file__))
    venv_dir = os.path.join(base_dir, ".venv")
    
    if not os.path.exists(venv_dir):
        print("Virtual environment not found. Please create it and install requirements.")
        sys.exit(1)
        
    python_bin = os.path.join(venv_dir, "bin", "python")
    if not os.path.exists(python_bin):
        python_bin = sys.executable # Fallback
        
    print(f"Using python executable: {python_bin}")
    print("Starting FastAPI Uvicorn Server on http://127.0.0.1:8000 ...")
    
    # Try to import webbrowser and open the page after a short delay
    def open_browser():
        time.sleep(2)
        print("Opening web interface in your browser...")
        webbrowser.open("http://127.0.0.1:8000")

    # Start browser opener in a separate thread
    import threading
    threading.Thread(target=open_browser, daemon=True).start()

    # Run the server
    try:
        subprocess.run([
            python_bin, "-m", "uvicorn", "backend:app", 
            "--host", "127.0.0.1", 
            "--port", "8000",
            "--reload"
        ], cwd=base_dir)
    except KeyboardInterrupt:
        print("\nRecipeLab server stopped.")
    except Exception as e:
        print(f"Error running server: {e}")

if __name__ == "__main__":
    main()
