"""python -m gradebook ..."""

import os
import sys

from gradebook.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:], dict(os.environ)))
