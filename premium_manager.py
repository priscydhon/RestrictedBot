import asyncio
from datetime import datetime, timedelta
from config import Config

class PremiumManager:
    def __init__(self, db):
        self.db = db
    
    def get_user_tier(self, user_data):
        """Get user tier level"""
        # Admins have highest priority
        if user_data.get('is_admin', False) or user_data['user_id'] in Config.ADMIN_IDS:
            return "admin"
        elif user_data.get('is_pro', False):
            return "pro"
        elif user_data.get('is_premium', False):
            return "premium"
        else:
            return "free"
    
    def get_download_limit(self, user_data):
        """Get user's daily download limit - ADMINS HAVE UNLIMITED"""
        # Admins have unlimited downloads
        if user_data.get('is_admin', False) or user_data['user_id'] in Config.ADMIN_IDS:
            return 999999  # Effectively unlimited
        
        tier = self.get_user_tier(user_data)
        limits = {
            "free": Config.MAX_DOWNLOADS_PER_USER,
            "premium": Config.MAX_DOWNLOADS_PREMIUM,
            "pro": Config.MAX_DOWNLOADS_PRO
        }
        return limits.get(tier, Config.MAX_DOWNLOADS_PER_USER)
    
    def get_file_size_limit(self, user_data):
        """Get user's file size limit in bytes - ADMINS HAVE UNLIMITED"""
        # Admins have unlimited file size
        if user_data.get('is_admin', False) or user_data['user_id'] in Config.ADMIN_IDS:
            return 50 * 1024 * 1024 * 1024  # 50GB for admins
        
        tier = self.get_user_tier(user_data)
        limits = {
            "free": Config.MAX_FILE_SIZE,
            "premium": Config.PREMIUM_FILE_SIZE,
            "pro": Config.PRO_FILE_SIZE
        }
        return limits.get(tier, Config.MAX_FILE_SIZE)
    
    def can_download(self, user_data):
        """Check if user can download - ADMINS HAVE NO LIMITS"""
        if not user_data:
            return False, "User not found"
        
        # Admins have unlimited downloads - NO LIMITS AT ALL
        if user_data.get('is_admin', False) or user_data['user_id'] in Config.ADMIN_IDS:
            return True, "Admin unlimited access"
        
        # Check daily limit for non-admins
        max_downloads = self.get_download_limit(user_data)
        used_downloads = user_data.get('download_count', 0)
        
        if used_downloads >= max_downloads:
            return False, f"Daily limit reached ({used_downloads}/{max_downloads})"
        
        return True, "OK"
    
    def get_cooldown_time(self, user_data):
        """Get cooldown time between downloads - ADMINS HAVE NO COOLDOWN"""
        if user_data.get('is_admin', False) or user_data['user_id'] in Config.ADMIN_IDS:
            return 0  # No cooldown for admins
        if self.get_user_tier(user_data) != "free":
            return 0  # No cooldown for premium users
        return Config.DOWNLOAD_COOLDOWN
    
    async def process_payment(self, user_id, payment_method, plan_type, transaction_id):
        """Process payment and add to pending"""
        amount = 5 if plan_type == "premium" else 15
        
        success = self.db.add_payment(user_id, payment_method, amount, transaction_id)
        if success:
            return True, "Payment recorded! Waiting for verification."
        else:
            return False, "Failed to record payment. Please try again."
    
    def get_premium_benefits(self, tier):
        """Get benefits for each tier"""
        benefits = {
            "admin": {
                "downloads": "Unlimited",
                "file_size": "Unlimited",
                "features": ["All features", "No restrictions", "Admin privileges"],
                "cooldown": "None"
            },
            "free": {
                "downloads": "5/day",
                "file_size": "500MB",
                "features": ["Basic downloads", "Standard support"],
                "cooldown": "20 seconds"
            },
            "premium": {
                "downloads": "50/day", 
                "file_size": "2GB",
                "features": ["Priority downloads", "Batch downloads", "No cooldown", "Priority support"],
                "cooldown": "None"
            },
            "pro": {
                "downloads": "200/day",
                "file_size": "5GB", 
                "features": ["Unlimited downloads", "Batch processing", "VIP support", "Custom requests"],
                "cooldown": "None"
            }
        }
        return benefits.get(tier, benefits["free"])