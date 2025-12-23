import asyncio
from pyrogram import Client
from pyrogram.errors import UserNotParticipant, ChannelPrivate
from config import Config  # ADDED MISSING IMPORT

class ChannelVerification:
    def __init__(self, auth_manager, db):
        self.auth_manager = auth_manager
        self.db = db
    
    async def check_channel_membership(self, user_id, channel_username):
        """Check if user is member of a channel - FIXED VERSION"""
        if not self.auth_manager.is_user_authenticated(user_id):
            return False, "User not authenticated"
        
        user_session = self.auth_manager.get_user_session(user_id)
        if not user_session:
            return False, "Session not found"
        
        try:
            await user_session.connect()
            
            # Try multiple methods to check membership
            try:
                # Method 1: Try to get chat member info
                member = await user_session.get_chat_member(channel_username, "me")
                is_member = member.status in ['creator', 'administrator', 'member']
                await user_session.disconnect()
                return is_member, "Checked via member status"
                
            except UserNotParticipant:
                await user_session.disconnect()
                return False, "Not a member (UserNotParticipant)"
            except ChannelPrivate:
                await user_session.disconnect()
                return False, "Channel is private"
            except Exception as e:
                # Method 2: Try to access the chat directly
                try:
                    chat = await user_session.get_chat(channel_username)
                    # If we can access the chat without error, assume we're a member
                    await user_session.disconnect()
                    return True, "Access granted to chat"
                except Exception as e2:
                    await user_session.disconnect()
                    return False, f"Cannot access: {str(e2)}"
                
        except Exception as e:
            return False, f"Connection error: {str(e)}"
    
    async def verify_all_channels(self, user_id, channels):
        """Verify user is member of all required channels - FIXED VERSION"""
        if not channels:
            return True, "No channels to verify"
        
        results = []
        for channel in channels:
            print(f"🔍 Checking channel {channel} for user {user_id}")
            is_member, message = await self.check_channel_membership(user_id, channel)
            results.append((channel, is_member, message))
            print(f"📊 Channel {channel}: {is_member} - {message}")
        
        # Check if all channels are joined
        all_joined = all(result[1] for result in results)
        
        if all_joined:
            # Update database
            self.db.set_channels_verified(user_id, True)
            return True, "All channels verified successfully!"
        else:
            # Get list of missing channels
            missing = [result[0] for result in results if not result[1]]
            return False, f"Please join these channels: {', '.join(missing)}"
    
    def get_required_channels(self):
        """Get list of required channels from config"""
        return Config.REQUIRED_CHANNELS