#!/usr/bin/env python3
"""
Test runner for GUI tests.
Runs all GUI-related tests and provides a summary.
"""

import unittest
import sys

def run_all_gui_tests():
    """Run all GUI tests."""
    # Discover and run all GUI tests
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add all GUI test modules
    test_modules = [
        'test.gui.test_gui',
        'test.gui.test_gui_playthrough',
        'test.gui.test_gui_stress',
        'test.gui.test_gui_automated_play',
        'test.gui.test_gui_comprehensive'
    ]

    for module_name in test_modules:
        try:
            module = __import__(module_name)
            tests = loader.loadTestsFromModule(module)
            suite.addTests(tests)
            print(f"Loaded tests from {module_name}")
        except ImportError as e:
            print(f"Warning: Could not import {module_name}: {e}")

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Print summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Success rate: {(result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100:.1f}%")

    if result.failures:
        print("\nFAILURES:")
        for test, traceback in result.failures:
            print(f"  - {test}")
            print(f"    {traceback.split(chr(10))[-2]}")

    if result.errors:
        print("\nERRORS:")
        for test, traceback in result.errors:
            print(f"  - {test}")
            print(f"    {traceback.split(chr(10))[-2]}")

    return len(result.failures) == 0 and len(result.errors) == 0

if __name__ == '__main__':
    success = run_all_gui_tests()
    sys.exit(0 if success else 1)

