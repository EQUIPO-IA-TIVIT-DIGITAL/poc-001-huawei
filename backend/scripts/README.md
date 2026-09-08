# Utility Scripts

This directory contains utility scripts, debugging tools, and migrations that should not be executed in production.

## Files

### tmp_query.py
Temporary script for ad-hoc Firestore queries. Useful for debugging and data analysis.

**Usage:**
```bash
python scripts/tmp_query.py
```

**Note:** Requires Firebase credentials to be configured directly in the script.

### refactor_gcp.py
Migration script used to refactor GCP credential configuration in adapters.

**Usage:**
```bash
python scripts/refactor_gcp.py
```

**Note:** Already executed. Kept for historical reference only.

## Warning

**These scripts MUST NOT be included in production deployment.** They are development and debugging tools only.

## Adding New Scripts

If you need to create a new utility script:

1. Place it in this directory
2. Document it in this README
3. Ensure it is not included in the production Dockerfile
4. Include clear comments about its purpose
