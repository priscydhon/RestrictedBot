import re
import os

class LinkParser:
    @staticmethod
    def parse_telegram_link(link: str):
        """
        Parse Telegram links to extract chat info and message ID
        Supports:
        - Public: https://t.me/username/123
        - Private: https://t.me/c/123456789/2
        - Short: @username/123
        """
        if not link:
            return None
            
        # Private chat links: t.me/c/123456789/2
        private_match = re.match(r'(?:https?://)?t\.me/c/(\d+)/(\d+)', link.strip())
        if private_match:
            channel_id = int(private_match.group(1))
            message_id = int(private_match.group(2))
            proper_chat_id = f"-100{channel_id}"
            return proper_chat_id, message_id, "private"
        
        # Public channel links: t.me/username/123
        public_match = re.match(r'(?:https?://)?(?:t\.me|telegram\.me)/([a-zA-Z0-9_]+)/(\d+)', link.strip())
        if public_match:
            username = public_match.group(1)
            message_id = int(public_match.group(2))
            return username, message_id, "public"
        
        # Short format: @username/123
        short_match = re.match(r'@([a-zA-Z0-9_]+)/(\d+)', link.strip())
        if short_match:
            username = short_match.group(1)
            message_id = int(short_match.group(2))
            return username, message_id, "public"
        
        return None

class FileManager:
    @staticmethod
    def clean_filename(filename: str) -> str:
        """Clean filename to remove invalid characters"""
        cleaned = re.sub(r'[<>:"/\\|?*]', '_', filename)
        return cleaned.strip()
    
    @staticmethod
    def cleanup_file(path: str):
        """Remove temporary file"""
        try:
            if os.path.exists(path):
                os.remove(path)
                print(f"🧹 Cleaned up file: {path}")
        except Exception as e:
            print(f"⚠️ Failed to cleanup file {path}: {e}")

class UserManager:
    """Manage user states for authentication"""
    
    def __init__(self):
        self.auth_states = {}  # {user_id: {'state': 'awaiting_phone', 'data': {}}}
        self.processing_users = set()
    
    def set_auth_state(self, user_id, state, data=None):
        """Set user authentication state"""
        if data is None:
            data = {}
        self.auth_states[user_id] = {'state': state, 'data': data}
    
    def get_auth_state(self, user_id):
        """Get user authentication state"""
        return self.auth_states.get(user_id)
    
    def clear_auth_state(self, user_id):
        """Clear user authentication state"""
        if user_id in self.auth_states:
            del self.auth_states[user_id]
    
    def add_processing_user(self, user_id):
        """Add user to processing set"""
        self.processing_users.add(user_id)
    
    def remove_processing_user(self, user_id):
        """Remove user from processing set"""
        self.processing_users.discard(user_id)
    
    def is_user_processing(self, user_id):
        """Check if user is processing"""
        return user_id in self.processing_users