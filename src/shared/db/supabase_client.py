from supabase import Client, create_client

from src.shared.config.env import SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL
from src.shared.logger import logger

_client: Client | None = None


def get_client() -> Client:
    global _client
    if _client is None:
        logger.debug("Initialising Supabase client | url={}", SUPABASE_URL)
        _client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
        logger.debug("Supabase client ready")
    return _client
