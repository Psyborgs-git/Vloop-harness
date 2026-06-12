import pytest
from harness.engine.middleware.context_cleaner import ContextCleaner

def test_context_cleaner_ansi_strip():
    cleaner = ContextCleaner()
    raw = "\x1b[31mError:\x1b[0m Something went wrong."
    cleaned = cleaner.clean(raw)
    assert cleaned == "Error: Something went wrong."

def test_context_cleaner_carriage_return_squash():
    cleaner = ContextCleaner()
    # A loading bar that updates 3 times on the same line
    raw = "Loading [1/3]...\rLoading [2/3]...\rLoading [3/3]...\nDone."
    cleaned = cleaner.clean(raw)
    assert cleaned == "Loading [3/3]...\nDone."

def test_context_cleaner_truncation():
    cleaner = ContextCleaner(max_lines=10, keep_first=2, keep_last=3)
    raw = "\n".join([f"Line {i}" for i in range(20)])
    cleaned = cleaner.clean(raw)
    
    lines = cleaned.split('\n')
    assert "Line 0" in lines[0]
    assert "Line 1" in lines[1]
    assert "15 lines truncated" in cleaned
    assert "Line 17" in lines[-3]
    assert "Line 18" in lines[-2]
    assert "Line 19" in lines[-1]
