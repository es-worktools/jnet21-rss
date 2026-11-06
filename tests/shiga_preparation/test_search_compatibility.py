"""Run vol.2's unchanged failure cases against the production parser too."""
import importlib.util
from pathlib import Path
from support_shiga import search

path = Path(__file__).resolve().parents[2] / 'validation/test_shiga_candidate.py'
spec = importlib.util.spec_from_file_location('inherited_shiga_tests', path)
module = importlib.util.module_from_spec(spec)
# The original test imports its sibling; provide only the module during loading.
import sys
from unittest.mock import patch
with patch.dict(sys.modules, {'shiga_candidate': search}):
    spec.loader.exec_module(module)
Safety = module.Safety
