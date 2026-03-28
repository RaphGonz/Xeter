"""Entry point for the Embedding Worker Docker container.
Delegates to xeter.services.worker.main.main().
"""
from xeter.services.worker.main import main

if __name__ == "__main__":
    main()
