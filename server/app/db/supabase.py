import logging
from supabase import create_client, Client
from app.core.config import settings

logger = logging.getLogger(__name__)

# Initialize Supabase client lazily or safely
# Use service role key for backend operations (bypasses RLS)
supabase: Client = None

try:
    if settings.SUPABASE_URL and settings.SUPABASE_URL.startswith("http"):
        # Prefer service role key for backend operations
        service_key = settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_KEY
        if not settings.SUPABASE_SERVICE_ROLE_KEY:
            logger.warning(
                "SUPABASE_SERVICE_ROLE_KEY not set. Using anon key which may fail with RLS. "
                "Set SUPABASE_SERVICE_ROLE_KEY for backend operations."
            )
        supabase = create_client(
            settings.SUPABASE_URL, 
            service_key
        )
    else:
        logger.warning("Supabase URL is missing or invalid. Database features will be disabled.")
except Exception as e:
    logger.error(f"Failed to initialize Supabase client: {str(e)}")

def get_db():
    """
    Dependency helper to provide the Supabase client.
    """
    if not supabase:
        raise RuntimeError("DATABASE_ERROR: Supabase credentials are not configured or valid.")
    return supabase
