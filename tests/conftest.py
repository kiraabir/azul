"""Pytest configuration for AZUL test suite."""
import os
import sys

# Ensure the project root is on sys.path so `client` and `app` can be imported
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))