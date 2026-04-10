import logging
from supabase import create_client, Client
from app.core.config import settings

logger = logging.getLogger(__name__)

# Initialize Supabase client lazily or safely
supabase: Client = None

try:
    if settings.SUPABASE_URL and settings.SUPABASE_URL.startswith("http"):
        supabase = create_client(
            settings.SUPABASE_URL, 
            settings.SUPABASE_KEY
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
