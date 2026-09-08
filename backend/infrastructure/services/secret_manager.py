"""
GCP Secret Manager Integration

Fetches secrets from Secret Manager and injects them as environment variables.
Falls back gracefully to existing env vars if Secret Manager is unavailable.

Usage in main.py (before any other imports that need secrets):
    from infrastructure.services.secret_manager import load_secrets
    load_secrets()
"""

import os
import logging

logger = logging.getLogger(__name__)

# Secrets to load: (env_var_name, secret_id_in_gcp)
_SECRETS_MAP = [
    ("SECRET_KEY", "tivit-cu002-secret-key"),
    ("GEMINI_API_KEY", "tivit-cu002-gemini-api-key"),
    ("REDIS_PASSWORD", "tivit-cu002-redis-password"),
]

_LOADED = False


def load_secrets():
    """
    Load secrets from GCP Secret Manager into environment variables.
    
    Only runs in production (FLASK_ENV=production).
    Only overwrites env vars that are NOT already set,
    so explicit env vars always take priority.
    """
    global _LOADED
    if _LOADED:
        return
    _LOADED = True

    is_production = os.environ.get("FLASK_ENV") == "production"
    project_id = os.environ.get("GCP_PROJECT_ID")

    if not is_production:
        logger.debug("Secret Manager: skipped (not production)")
        return

    if not project_id:
        logger.warning("Secret Manager: GCP_PROJECT_ID not set, skipping")
        return

    try:
        from google.cloud import secretmanager

        client = secretmanager.SecretManagerServiceClient()
        loaded_count = 0

        for env_var, secret_id in _SECRETS_MAP:
            # Skip if already set via env var
            if os.environ.get(env_var):
                logger.debug(f"Secret '{env_var}': already set via env, skipping")
                continue

            try:
                name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
                response = client.access_secret_version(request={"name": name})
                secret_value = response.payload.data.decode("UTF-8")
                os.environ[env_var] = secret_value
                loaded_count += 1
                logger.info(f"✅ Secret '{env_var}': loaded from Secret Manager")
            except Exception as e:
                logger.warning(f"⚠️  Secret '{env_var}' ({secret_id}): {e}")

        logger.info(f"Secret Manager: {loaded_count}/{len(_SECRETS_MAP)} secrets loaded")

    except ImportError:
        logger.warning("Secret Manager: google-cloud-secret-manager not installed")
    except Exception as e:
        logger.error(f"Secret Manager: init failed: {e}")


def get_secret(secret_id: str, project_id: str | None = None) -> str | None:
    """
    Fetch a single secret value from Secret Manager.
    
    Args:
        secret_id: The secret ID in GCP
        project_id: GCP project ID (defaults to GCP_PROJECT_ID env var)
    
    Returns:
        Secret value as string, or None if unavailable
    """
    project_id = project_id or os.environ.get("GCP_PROJECT_ID")
    if not project_id:
        return None

    try:
        from google.cloud import secretmanager

        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        return response.payload.data.decode("UTF-8")
    except Exception as e:
        logger.warning(f"Failed to fetch secret '{secret_id}': {e}")
        return None
