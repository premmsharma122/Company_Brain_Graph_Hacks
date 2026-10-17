"""CLI: python -m app.seed [--reset]   (run from backend/, after python ../data/generate_data.py)"""
import sys
from . import graph

if __name__ == "__main__":
    if "--reset" in sys.argv:
        graph.reset_graph()
    print(graph.load_seed())
