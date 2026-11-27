"""`python -m lifeos` runs the same command line as the `lifeos` script (useful before the script is on the PATH)."""
import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
