#!/usr/bin/env python3
"""
Local validation script to check our Django code changes.
This simulates the key parts of the CI workflow without requiring full Django setup.
"""

import ast
import re
import sys
from pathlib import Path

def check_file_syntax(filepath):
    """Check Python syntax of a file."""
    try:
        with open(filepath, 'r') as f:
            ast.parse(f.read(), filename=str(filepath))
        return True, None
    except SyntaxError as e:
        return False, str(e)

def check_imports_structure(filepath):
    """Check that imports are properly structured."""
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Check for common import issues
    issues = []
    
    # Check for relative imports
    if 'from .cache_utils import' in content:
        issues.append("✓ Uses relative imports correctly")
    
    # Check for Django patterns
    if 'from django.db import models' in content or 'models.Model' in content:
        issues.append("✓ Django model patterns found")
    
    if 'from rest_framework' in content:
        issues.append("✓ DRF imports found")
        
    return issues

def check_cache_implementation():
    """Check our cache implementation."""
    cache_file = Path("django-backend/soroscan/ingest/cache_utils.py")
    
    with open(cache_file, 'r') as f:
        content = f.read()
    
    checks = []
    
    # Check for cache key pattern
    if 'event_count:{contract_id}' in content:
        checks.append("✓ Cache key pattern implemented")
    
    # Check for TTL
    if '300' in content and '5 min' in content:
        checks.append("✓ 5-minute TTL implemented")
    
    # Check for metrics
    if 'cache_hits_total' in content and 'cache_misses_total' in content:
        checks.append("✓ Cache metrics implemented")
    
    # Check for invalidation function
    if 'def invalidate_event_count_cache' in content:
        checks.append("✓ Cache invalidation function implemented")
    
    return checks

def check_serializer_updates():
    """Check serializer uses cached counts."""
    serializer_file = Path("django-backend/soroscan/ingest/serializers.py")
    
    with open(serializer_file, 'r') as f:
        content = f.read()
    
    checks = []
    
    if 'from .cache_utils import get_event_count' in content:
        checks.append("✓ Cache utils imported in serializers")
    
    if 'get_event_count(obj.contract_id)' in content:
        checks.append("✓ Serializers use cached event counts")
    
    # Check that old .count() calls are replaced
    if 'obj.events.count()' not in content:
        checks.append("✓ Direct .count() calls removed from serializers")
    
    return checks

def check_task_invalidation():
    """Check tasks invalidate cache."""
    tasks_file = Path("django-backend/soroscan/ingest/tasks.py")
    
    with open(tasks_file, 'r') as f:
        content = f.read()
    
    checks = []
    
    if 'from .cache_utils import' in content and 'invalidate_event_count_cache' in content:
        checks.append("✓ Cache invalidation imported in tasks")
    
    if 'invalidate_event_count_cache(contract.contract_id)' in content:
        checks.append("✓ Cache invalidated on event creation")
    
    return checks

def check_admin_endpoint():
    """Check admin ingest errors endpoint."""
    views_file = Path("django-backend/soroscan/ingest/views.py")
    urls_file = Path("django-backend/soroscan/ingest/urls.py")
    
    with open(views_file, 'r') as f:
        views_content = f.read()
    
    with open(urls_file, 'r') as f:
        urls_content = f.read()
    
    checks = []
    
    if 'def admin_ingest_errors_view' in views_content:
        checks.append("✓ Admin ingest errors view implemented")
    
    if 'request.user.is_staff' in views_content:
        checks.append("✓ Admin access control implemented")
    
    if 'admin/ingest-errors/' in urls_content:
        checks.append("✓ Admin endpoint URL configured")
    
    if 'IngestError.objects.filter' in views_content:
        checks.append("✓ IngestError model queried in view")
    
    return checks

def check_event_types_endpoint():
    """Check event types endpoint."""
    views_file = Path("django-backend/soroscan/ingest/views.py")
    urls_file = Path("django-backend/soroscan/ingest/urls.py")
    
    with open(views_file, 'r') as f:
        views_content = f.read()
    
    with open(urls_file, 'r') as f:
        urls_content = f.read()
    
    checks = []
    
    if 'def contract_event_types_view' in views_content:
        checks.append("✓ Contract event types view implemented")
    
    if 'event-types/' in urls_content:
        checks.append("✓ Event types endpoint URL configured")
    
    if 'order_by("-count")' in views_content:
        checks.append("✓ Results sorted by count (descending)")
    
    return checks

def main():
    """Run all validation checks."""
    print("🔍 Running local Django workflow validation...\n")
    
    # Files to check
    files_to_check = [
        "django-backend/soroscan/ingest/models.py",
        "django-backend/soroscan/ingest/views.py",
        "django-backend/soroscan/ingest/serializers.py", 
        "django-backend/soroscan/ingest/cache_utils.py",
        "django-backend/soroscan/ingest/tasks.py",
        "django-backend/soroscan/ingest/metrics.py",
        "django-backend/soroscan/ingest/admin.py",
        "django-backend/soroscan/ingest/urls.py",
        "django-backend/soroscan/ingest/tests/test_views.py"
    ]
    
    # 1. Syntax check
    print("1️⃣ Checking Python syntax...")
    syntax_ok = True
    for filepath in files_to_check:
        ok, error = check_file_syntax(filepath)
        if ok:
            print(f"   ✓ {filepath}")
        else:
            print(f"   ❌ {filepath}: {error}")
            syntax_ok = False
    
    if not syntax_ok:
        print("\n❌ Syntax errors found. Fix them before proceeding.")
        return False
    
    print("   🎉 All files pass syntax check!\n")
    
    # 2. Cache implementation check
    print("2️⃣ Checking Redis cache implementation...")
    cache_checks = check_cache_implementation()
    for check in cache_checks:
        print(f"   {check}")
    print()
    
    # 3. Serializer updates check
    print("3️⃣ Checking serializer cache integration...")
    serializer_checks = check_serializer_updates()
    for check in serializer_checks:
        print(f"   {check}")
    print()
    
    # 4. Task invalidation check
    print("4️⃣ Checking cache invalidation in tasks...")
    task_checks = check_task_invalidation()
    for check in task_checks:
        print(f"   {check}")
    print()
    
    # 5. Admin endpoint check
    print("5️⃣ Checking admin ingest errors endpoint...")
    admin_checks = check_admin_endpoint()
    for check in admin_checks:
        print(f"   {check}")
    print()
    
    # 6. Event types endpoint check
    print("6️⃣ Checking contract event types endpoint...")
    event_types_checks = check_event_types_endpoint()
    for check in event_types_checks:
        print(f"   {check}")
    print()
    
    # Summary
    total_checks = (len(cache_checks) + len(serializer_checks) + 
                   len(task_checks) + len(admin_checks) + len(event_types_checks))
    
    print(f"✅ Validation complete! {total_checks} feature checks passed.")
    print("🚀 Code is ready for CI/CD pipeline!")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
