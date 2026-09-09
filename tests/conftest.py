import os
import sys

# Permite "import main" sin importar cómo se invoque pytest (bare `pytest`,
# `python -m pytest`, o desde otro directorio).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
