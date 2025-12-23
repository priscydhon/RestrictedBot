import os
import asyncio
from pyrogram import Client
from pyrogram.errors import (
    SessionPasswordNeeded, PhoneCodeInvalid,
    PhoneNumberInvalid, FloodWait
)

from database import DatabaseManager

class AuthManager:
    def __init__(self, api_id, api_hash, workdir="sessions"):
        self.api_id = api_id
        self.api_hash = api_hash
        self.workdir = workdir
        self.db = DatabaseManager()
        os.makedirs(workdir, exist_ok=True)
        self.active_clients = {}  # Track active clients during auth
    
    def get_user_session_file(self, user_id):
        """Get session file path for user"""
        return os.path.join(self.workdir, f"user_{user_id}.session")
    
    async def start_user_auth(self, user_id, phone_number):
        """Start authentication process for user"""
        session_file = self.get_user_session_file(user_id)
        
        try:
            # Clean up any existing client for this user
            if user_id in self.active_clients:
                try:
                    await self.active_clients[user_id].disconnect()
                except:
                    pass
                del self.active_clients[user_id]
            
            client = Client(
                f"user_{user_id}",
                api_id=self.api_id,
                api_hash=self.api_hash,
                workdir=self.workdir
            )
            
            await client.connect()
            
            # Send verification code
            sent_code = await client.send_code(phone_number)
            
            # Store the active client for later use
            self.active_clients[user_id] = client
            
            return {
                'success': True,
                'phone_code_hash': sent_code.phone_code_hash,
                'client': client
            }
            
        except PhoneNumberInvalid:
            return {'success': False, 'error': 'Invalid phone number'}
        except FloodWait as e:
            return {'success': False, 'error': f'Flood wait: {e.value} seconds'}
        except Exception as e:
            return {'success': False, 'error': f'Authentication failed: {str(e)}'}
    
    async def verify_user_code(self, user_id, phone_number, phone_code_hash, code):
        """Verify user's code and complete authentication"""
        try:
            # Get the active client for this user
            if user_id not in self.active_clients:
                return {'success': False, 'error': 'Authentication session expired. Please start over with /login.'}
            
            client = self.active_clients[user_id]
            
            # Check if client is still connected
            if not client.is_connected:
                return {'success': False, 'error': 'Connection lost. Please start over with /login.'}
            
            # Try to sign in with the code
            try:
                # FIXED: Add delay before sign-in to prevent code expiration
                await asyncio.sleep(0.2)
                await client.sign_in(phone_number, phone_code_hash, code)
            except SessionPasswordNeeded:
                # Client is still active for 2FA
                return {'success': False, 'error': '2FA_REQUIRED'}
            except PhoneCodeInvalid:
                return {'success': False, 'error': 'Invalid verification code'}
            except Exception as e:
                error_msg = str(e)
                # Handle specific timing errors
                if 'PHONE_CODE_EXPIRED' in error_msg:
                    return {'success': False, 'error': 'Code expired. Please request a new code and try again.'}
                return {'success': False, 'error': f'Sign in failed: {error_msg}'}
            
            # IMPORTANT: Properly stop the client to save session
            try:
                await client.stop()
            except:
                # If stop fails, try disconnect
                try:
                    await client.disconnect()
                except:
                    pass
            
            # Save user to database
            session_file = self.get_user_session_file(user_id)
            
            # Try multiple times to save to database
            max_retries = 3
            success = False
            for attempt in range(max_retries):
                success = self.db.add_user(user_id, phone_number, session_file)
                if success:
                    break
                elif attempt < max_retries - 1:
                    await asyncio.sleep(1)
            
            if not success:
                print(f"⚠️ Database save failed but session created for user {user_id}")
            
            # Remove from active clients
            if user_id in self.active_clients:
                del self.active_clients[user_id]
            
            return {'success': True, 'message': 'Authentication successful!'}
            
        except Exception as e:
            # Clean up on error
            if user_id in self.active_clients:
                try:
                    await self.active_clients[user_id].disconnect()
                except:
                    pass
                del self.active_clients[user_id]
            
            return {'success': False, 'error': f'Verification failed: {str(e)}'}
    
    async def verify_2fa(self, user_id, phone_number, phone_code_hash, password):
        """Verify 2FA password"""
        try:
            # Get the active client for this user
            if user_id not in self.active_clients:
                return {'success': False, 'error': 'Authentication session expired. Please start over with /login.'}
            
            client = self.active_clients[user_id]
            
            # Check if client is still connected
            if not client.is_connected:
                return {'success': False, 'error': 'Connection lost. Please start over with /login.'}
            
            await client.check_password(password)
            
            # IMPORTANT: Properly stop the client to save session
            try:
                await client.stop()
            except:
                # If stop fails, try disconnect
                try:
                    await client.disconnect()
                except:
                    pass
            
            # Save user to database
            session_file = self.get_user_session_file(user_id)
            
            # Try multiple times to save to database
            max_retries = 3
            success = False
            for attempt in range(max_retries):
                success = self.db.add_user(user_id, phone_number, session_file)
                if success:
                    break
                elif attempt < max_retries - 1:
                    await asyncio.sleep(1)
            
            if not success:
                print(f"⚠️ Database save failed but session created for user {user_id}")
            
            # Remove from active clients
            if user_id in self.active_clients:
                del self.active_clients[user_id]
            
            return {'success': True, 'message': 'Authentication successful!'}
            
        except Exception as e:
            # Clean up on error
            if user_id in self.active_clients:
                try:
                    await self.active_clients[user_id].disconnect()
                except:
                    pass
                del self.active_clients[user_id]
            
            return {'success': False, 'error': f'2FA verification failed: {str(e)}'}
    
    def cleanup_client(self, user_id):
        """Clean up client for a user"""
        if user_id in self.active_clients:
            try:
                asyncio.create_task(self.active_clients[user_id].disconnect())
            except:
                pass
            del self.active_clients[user_id]
    
    def is_user_authenticated(self, user_id):
        """Check if user is authenticated - FIXED VERSION"""
        try:
            session_file = self.get_user_session_file(user_id)
            
            # Check if session file exists and has content
            if not os.path.exists(session_file):
                print(f"❌ Session file not found: {session_file}")
                return False
            
            # Check if session file has reasonable size (not empty)
            file_size = os.path.getsize(session_file)
            if file_size < 100:  # Session files are typically >1KB
                print(f"❌ Session file too small: {file_size} bytes")
                return False
            
            # Try to get user from database
            try:
                user = self.db.get_user(user_id)
                if not user:
                    print(f"❌ User not found in database: {user_id}")
                    return False
            except Exception as e:
                print(f"⚠️ Database error checking user {user_id}: {e}")
                # If database fails but session file exists and is valid, proceed
                pass
            
            print(f"✅ User {user_id} authenticated - session file exists and valid")
            return True
                
        except Exception as e:
            print(f"❌ Authentication check failed for user {user_id}: {e}")
            return False
    
    def get_user_session(self, user_id):
        """Get user's session client - FIXED VERSION"""
        if not self.is_user_authenticated(user_id):
            print(f"❌ Cannot get session for unauthenticated user: {user_id}")
            return None
        
        try:
            client = Client(
                f"user_{user_id}",
                api_id=self.api_id,
                api_hash=self.api_hash,
                workdir=self.workdir
            )
            
            print(f"✅ Session client created for user: {user_id}")
            return client
        except Exception as e:
            print(f"❌ Failed to create session client for user {user_id}: {e}")
            return None

    async def test_session(self, user_id):
        """Test if session is valid by attempting to connect"""
        client = self.get_user_session(user_id)
        if not client:
            return False
        
        try:
            await client.connect()
            me = await client.get_me()
            await client.disconnect()
            print(f"✅ Session test successful for user {user_id}: {me.first_name}")
            return True
        except Exception as e:
            print(f"❌ Session test failed for user {user_id}: {e}")
            return False