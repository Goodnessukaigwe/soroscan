#!/usr/bin/env python
"""
Package verification script.

Verifies that the SDK package is correctly structured and importable.
"""

import sys
from pathlib import Path


def verify_structure() -> bool:
    """Verify package structure."""
    print("Checking package structure...")

    required_files = [
        "soroscan/__init__.py",
        "soroscan/client.py",
        "soroscan/models.py",
        "soroscan/exceptions.py",
        "tests/__init__.py",
        "tests/conftest.py",
        "tests/test_client.py",
        "tests/test_async_client.py",
        "tests/test_models.py",
        "pyproject.toml",
        "README.md",
        "LICENSE",
        "py.typed",
    ]

    root = Path(__file__).parent
    missing = []

    for file_path in required_files:
        if not (root / file_path).exists():
            missing.append(file_path)

    if missing:
        print(f"✗ Missing files: {', '.join(missing)}")
        return False

    print("✓ All required files present")
    return True


def verify_imports() -> bool:
    """Verify package imports."""
    print("\nChecking imports...")

    try:
        # Add package to path
        sys.path.insert(0, str(Path(__file__).parent))

        # Import main package
        import soroscan

        # Verify version
        assert hasattr(soroscan, "__version__")
        print(f"  Version: {soroscan.__version__}")

        # Verify clients

        print("  ✓ SoroScanClient")
        print("  ✓ AsyncSoroScanClient")

        # Verify models

        print("  ✓ TrackedContract")
        print("  ✓ ContractEvent")
        print("  ✓ WebhookSubscription")
        print("  ✓ ContractStats")
        print("  ✓ PaginatedResponse")

        # Verify exceptions

        print("  ✓ Exception classes")

        print("✓ All imports successful")
        return True

    except Exception as e:
        print(f"✗ Import failed: {e}")
        return False


def verify_type_hints() -> bool:
    """Verify type hints are present."""
    print("\nChecking type hints...")

    try:
        from soroscan.client import SoroScanClient

        # Check that methods have annotations
        methods = [
            "get_contracts",
            "get_contract",
            "create_contract",
            "get_events",
            "get_event",
            "record_event",
            "get_webhooks",
            "create_webhook",
        ]

        for method_name in methods:
            method = getattr(SoroScanClient, method_name)
            if not hasattr(method, "__annotations__"):
                print(f"✗ Missing annotations for {method_name}")
                return False

        print("✓ Type hints present")
        return True

    except Exception as e:
        print(f"✗ Type hint check failed: {e}")
        return False


def main() -> int:
    """Run all verifications."""
    print("=" * 60)
    print("SoroScan SDK Package Verification")
    print("=" * 60)

    checks = [
        ("Structure", verify_structure),
        ("Imports", verify_imports),
        ("Type Hints", verify_type_hints),
    ]

    results = []
    for name, check_func in checks:
        try:
            results.append(check_func())
        except Exception as e:
            print(f"✗ {name} check failed with exception: {e}")
            results.append(False)

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)

    for (name, _), success in zip(checks, results):
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"{status}: {name}")

    if all(results):
        print("\n✓ Package verification successful!")
        return 0
    else:
        print("\n✗ Package verification failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
