import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Bot credentials
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    
    # User bot credentials
    API_ID = int(os.getenv("API_ID", "0"))
    API_HASH = os.getenv("API_HASH")
    
    # Admin user IDs - FIXED: Handle empty string case
    ADMIN_IDS = []
    admin_ids_str = os.getenv("ADMIN_IDS", "")
    if admin_ids_str:
        ADMIN_IDS = [int(x.strip()) for x in admin_ids_str.split(",") if x.strip()]
    
    # Support channel
    SUPPORT_CHANNEL = os.getenv("SUPPORT_CHANNEL", "https://t.me/hectorbotsfiles")
    
    # Video guide channel (login tutorial)
    VIDEO_GUIDE_URL = os.getenv("VIDEO_GUIDE_URL", "https://t.me/hectorbotsfiles")
    
    # Rate limiting
    MAX_DOWNLOADS_PER_USER = int(os.getenv("MAX_DOWNLOADS_PER_USER", "5"))
    MAX_DOWNLOADS_PREMIUM = int(os.getenv("MAX_DOWNLOADS_PREMIUM", "50"))
    MAX_DOWNLOADS_PRO = int(os.getenv("MAX_DOWNLOADS_PRO", "200"))
    
    MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", "500")) * 1024 * 1024
    PREMIUM_FILE_SIZE = int(os.getenv("PREMIUM_FILE_SIZE", "2048")) * 1024 * 1024
    PRO_FILE_SIZE = int(os.getenv("PRO_FILE_SIZE", "5120")) * 1024 * 1024
    
    # Database path
    DB_PATH = os.path.join(os.getcwd(), os.getenv("DB_PATH", "users.db"))
    
    # Session settings
    SESSION_DIR = os.path.join(os.getcwd(), "sessions")
    DOWNLOAD_DIR = os.path.join(os.getcwd(), "downloads")
    
    # Payment methods - SIMPLIFIED
    PAYMENT_METHODS = {
        "mtn": os.getenv("MTN_NUMBER", ""),
        "vodafone": os.getenv("VODA_NUMBER", ""),
        "bitcoin": os.getenv("BTC", ""),
        "usdt": os.getenv("USDT", ""),
        "selar": os.getenv("SELAR", "")
    }
    
    # Cooldown settings
    DOWNLOAD_COOLDOWN = int(os.getenv("DOWNLOAD_COOLDOWN", "20"))  # seconds
    
    @classmethod
    def validate_config(cls):
        required = ['BOT_TOKEN', 'API_ID', 'API_HASH']
        missing = [var for var in required if not getattr(cls, var)]
        
        if missing:
            raise ValueError(f"Missing: {', '.join(missing)}")
        
        # Create directories with full paths
        os.makedirs(cls.SESSION_DIR, exist_ok=True)
        os.makedirs(cls.DOWNLOAD_DIR, exist_ok=True)
        
        print(f"✅ Configuration validated!")
        print(f"📁 Sessions: {cls.SESSION_DIR}")
        print(f"📁 Downloads: {cls.DOWNLOAD_DIR}")
        print(f"📁 Database: {cls.DB_PATH}")
        print(f"👑 Admin IDs: {cls.ADMIN_IDS}")
        print(f"💰 Payment Methods: {[k for k, v in cls.PAYMENT_METHODS.items() if v]}")
        print(f"📢 Support Channel: {cls.SUPPORT_CHANNEL}")