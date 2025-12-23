import os
import asyncio
from pyrogram import Client
from pyrogram.types import Message
from pyrogram.errors import (
    ChannelPrivate, UserNotParticipant, ChatAdminRequired,
    InviteHashInvalid, InviteHashExpired, UsernameNotOccupied,
    AuthKeyUnregistered, SessionExpired, SessionRevoked,
    PeerIdInvalid
)
from pyrogram import raw

from database import DatabaseManager
from utils import FileManager

# PATCH: Fix Pyrogram's outdated MIN_CHANNEL_ID for newer Telegram channels
# This fixes PEER_ID_INVALID errors for channels created after 2023
try:
    import pyrogram.utils as pyrogram_utils
    # Update the MIN values to support newer channel IDs
    if hasattr(pyrogram_utils, 'MIN_CHANNEL_ID'):
        pyrogram_utils.MIN_CHANNEL_ID = -1009999999999
    if hasattr(pyrogram_utils, 'MIN_CHAT_ID'):
        pyrogram_utils.MIN_CHAT_ID = -999999999999
    print("✅ Pyrogram MIN_CHANNEL_ID patched for newer channels")
except Exception as e:
    print(f"⚠️ Could not patch Pyrogram constants: {e}")

class UserSession:
    def __init__(self, auth_manager, user_id, bot_client=None):
        self.auth_manager = auth_manager
        self.user_id = user_id
        self.db = DatabaseManager()
        self.bot_client = bot_client  # For sending progress updates
        self.client = None
        self.is_connected = False
        self.joined_channels = []
    
    async def connect(self):
        """Connect user session with better error handling - FASTER CONNECTION"""
        if not self.auth_manager.is_user_authenticated(self.user_id):
            raise Exception("User not authenticated. Please /login first.")
        
        self.client = self.auth_manager.get_user_session(self.user_id)
        if not self.client:
            raise Exception("Failed to create session client. Please /login again.")
        
        try:
            # FASTER: Connect without full startup sequence
            await self.client.connect()
            
            # Quick test without full get_me if possible
            try:
                me = await self.client.get_me()
                print(f"✅ User session connected: {me.first_name} (ID: {me.id})")
            except:
                print(f"✅ User session connected: {self.user_id}")
            
            self.is_connected = True
            
            # Skip loading channels to save time - we'll load on demand
            # await self.load_joined_channels()
            
            # Update last used time
            self.db.get_user(self.user_id)
            
        except (AuthKeyUnregistered, SessionExpired, SessionRevoked) as e:
            # Session is invalid, clean up
            print(f"❌ Session invalid for user {self.user_id}: {e}")
            await self.cleanup_invalid_session()
            raise Exception("Session expired or invalid. Please /login again.")
        except Exception as e:
            print(f"❌ Failed to connect user session {self.user_id}: {e}")
            raise Exception(f"Failed to connect: {str(e)}")
    
    async def load_joined_channels(self):
        """Load all channels and groups the user is member of"""
        try:
            print(f"📋 Loading channels and groups for user {self.user_id}...")
            self.joined_channels = []
            
            async for dialog in self.client.get_dialogs():
                if dialog.chat.type in ["channel", "group", "supergroup"]:
                    channel_info = {
                        'id': dialog.chat.id,
                        'title': dialog.chat.title,
                        'username': getattr(dialog.chat, 'username', None),
                        'type': dialog.chat.type,
                        'is_restricted': getattr(dialog.chat, 'is_restricted', False)
                    }
                    self.joined_channels.append(channel_info)
            
            print(f"✅ Loaded {len(self.joined_channels)} channels/groups for user {self.user_id}")
            
        except Exception as e:
            print(f"❌ Failed to load channels for user {self.user_id}: {e}")
    
    async def download_file(self, chat_id: str, message_id: int, progress_callback=None) -> str:
        """Download file using user's session with progress tracking"""
        if not self.is_connected:
            raise Exception("User session not connected")
        
        try:
            # Resolve peer first to ensure it's in cache
            await self.resolve_peer(chat_id)
            
            # Get the message
            message = await self.client.get_messages(chat_id, message_id)
            if not message:
                raise Exception("Message not found")
            
            # Check if message has media
            if not any([message.video, message.document, message.audio, message.photo, message.sticker, message.animation, message.voice]):
                raise Exception("No media found in message")
            
            # Generate proper filename with correct extension
            filename = await self._generate_filename(message)
            file_path = os.path.join("downloads", filename)
            
            # Download file with progress
            print(f"📥 User {self.user_id} downloading: {filename}")
            
            # Custom download function with progress
            download_path = await self._download_with_progress(message, file_path, progress_callback)
            
            # Update download stats
            file_size = os.path.getsize(download_path) if os.path.exists(download_path) else 0
            self.db.increment_download_count(self.user_id)
            self.db.add_download_stat(self.user_id, filename, file_size)
            
            print(f"✅ Download completed: {filename}")
            return download_path
            
        except ChannelPrivate:
            raise Exception("This channel is private and you cannot access it. Please make sure you're a member and have joined the channel.")
        except UserNotParticipant:
            raise Exception("You are not a member of this channel. Please join the channel first to access its content.")
        except ChatAdminRequired:
            raise Exception("Admin rights required to access this content.")
        except PeerIdInvalid:
            raise Exception("Cannot find this channel. Please make sure you're a member. Try opening the channel in your Telegram app first, then try again.")
        except Exception as e:
            raise Exception(f"Download failed: {str(e)}")
    
    async def _download_with_progress(self, message, file_path, progress_callback=None):
        """Download file with progress tracking"""
        def progress(current, total):
            if progress_callback and total > 0:
                percentage = (current / total) * 100
                progress_callback(percentage, current, total)
        
        download_path = await message.download(file_name=file_path, progress=progress)
        return download_path
    
    # REMOVED upload_file method - files will be uploaded through the bot instead
    
    async def batch_download(self, chat_id: str, message_ids: list, progress_callback=None):
        """Download multiple files (premium feature) - FIXED FOR ADMINS"""
        if not self.is_connected:
            raise Exception("User session not connected")
        
        downloaded_files = []
        
        for i, message_id in enumerate(message_ids):
            try:
                if progress_callback:
                    progress_callback(f"Downloading {i+1}/{len(message_ids)}...", i+1, len(message_ids))
                
                file_path = await self.download_file(chat_id, message_id)
                downloaded_files.append(file_path)
                
                # Add cooldown between downloads
                await asyncio.sleep(1)  # Reduced from 2 to 1 second
                
            except Exception as e:
                print(f"❌ Failed to download message {message_id}: {e}")
                continue
        
        return downloaded_files

    async def resolve_peer(self, chat_id: str):
        """Resolve peer to ensure it's in the session cache - IMPROVED FOR PRIVATE CHANNELS"""
        try:
            chat_id_int = int(chat_id) if isinstance(chat_id, str) and chat_id.lstrip('-').isdigit() else None
            
            # First, try direct resolution
            try:
                if chat_id_int:
                    chat = await self.client.get_chat(chat_id_int)
                else:
                    chat = await self.client.get_chat(chat_id)
                print(f"✅ Resolved peer: {chat.title if hasattr(chat, 'title') else chat_id}")
                return True
            except PeerIdInvalid:
                print(f"🔍 Direct resolution failed, loading dialogs...")
            except Exception as e:
                print(f"⚠️ Direct resolution error: {e}")
            
            # If direct resolution failed for numeric ID, load dialogs to populate cache
            if chat_id_int:
                print(f"🔍 Searching dialogs for channel {chat_id}...")
                
                # Load all dialogs - this populates the peer cache with access_hash
                dialog_count = 0
                found_chat = None
                
                try:
                    async for dialog in self.client.get_dialogs():
                        dialog_count += 1
                        if dialog.chat.id == chat_id_int:
                            print(f"✅ Found channel in dialogs: {dialog.chat.title}")
                            found_chat = dialog.chat
                            # Continue loading to fully populate cache
                except Exception as e:
                    print(f"⚠️ Error loading dialogs: {e}")
                
                print(f"📊 Loaded {dialog_count} dialogs")
                
                if found_chat:
                    # Successfully found in dialogs - the peer cache should now have the access_hash
                    return True
                    
                # If still not found in dialogs, try using raw API to get channel info
                print(f"🔍 Trying raw API resolution for {chat_id}...")
                try:
                    # For channels with -100 prefix, extract the actual channel ID
                    if str(chat_id_int).startswith('-100'):
                        actual_channel_id = int(str(chat_id_int)[4:])
                    else:
                        actual_channel_id = abs(chat_id_int)
                    
                    # Try to resolve using get_messages which sometimes works
                    # when direct get_chat doesn't
                    peer = await self.client.resolve_peer(chat_id_int)
                    print(f"✅ Resolved peer via raw API: {peer}")
                    return True
                except Exception as e:
                    print(f"⚠️ Raw API resolution failed: {e}")
                
                print(f"❌ Channel {chat_id} not found. User must be a member and have the channel in their chat list.")
                return False
            
            return False
            
        except Exception as e:
            print(f"⚠️ Failed to resolve peer {chat_id}: {e}")
            return False

    async def get_message(self, chat_id: str, message_id: int) -> Message:
        """Get message using user's session - WITH PEER RESOLUTION"""
        if not self.is_connected:
            raise Exception("User session not connected")
        
        try:
            # First try to resolve the peer
            resolved = await self.resolve_peer(chat_id)
            
            if not resolved:
                raise PeerIdInvalid(f"Could not resolve channel {chat_id}")
            
            # Now try to get the message
            message = await self.client.get_messages(chat_id, message_id)
            if not message:
                raise Exception("Message not found")
            return message
            
        except ChannelPrivate:
            raise Exception("❌ This channel is private. Please make sure you're a member and have joined the channel to access its content.")
        except UserNotParticipant:
            raise Exception("❌ You're not a member of this channel. Please join the channel first to download content from it.")
        except PeerIdInvalid:
            raise Exception("❌ Channel not found in your Telegram account. Make sure:\n1. You are a member of this channel\n2. Open the channel in your Telegram app\n3. Send any message in the channel (if allowed)\n4. Then try downloading again")
        except Exception as e:
            raise Exception(f"❌ Cannot access message: {str(e)}")
    
    async def join_channel(self, channel_username: str) -> bool:
        """Join a channel using user's session"""
        if not self.is_connected:
            raise Exception("User session not connected")
        
        try:
            print(f"🚀 User {self.user_id} attempting to join channel: {channel_username}")
            
            joined_chat = await self.client.join_chat(channel_username)
            
            if joined_chat:
                print(f"✅ Successfully joined: {joined_chat.title}")
                # Reload channels after joining
                await self.load_joined_channels()
                return True
            else:
                print("❌ Failed to join channel")
                return False
                
        except InviteHashInvalid:
            raise Exception("❌ Invalid invite link. The link may be expired or incorrect.")
        except InviteHashExpired:
            raise Exception("❌ Invite link has expired.")
        except UsernameNotOccupied:
            raise Exception("❌ Channel username not found. The channel may not exist.")
        except Exception as e:
            raise Exception(f"❌ Failed to join channel: {str(e)}")
    
    async def cleanup_invalid_session(self):
        """Clean up invalid session"""
        session_file = self.auth_manager.get_user_session_file(self.user_id)
        if os.path.exists(session_file):
            try:
                os.remove(session_file)
                print(f"✅ Removed invalid session file: {session_file}")
            except Exception as e:
                print(f"⚠️ Failed to remove session file: {e}")
    
    async def copy_message_to_user(self, from_chat_id: str, message_id: int, to_user_id: int) -> bool:
        """Copy message directly from source channel to user's chat with the bot - FAST FORWARD"""
        if not self.is_connected:
            raise Exception("User session not connected")
        
        try:
            # First resolve the source peer
            await self.resolve_peer(from_chat_id)
            
            # Copy the message directly to the user
            copied = await self.client.copy_message(
                chat_id=to_user_id,
                from_chat_id=from_chat_id,
                message_id=message_id
            )
            
            if copied:
                # Update download stats
                self.db.increment_download_count(self.user_id)
                self.db.add_download_stat(self.user_id, f"forward_{message_id}", 0)
                print(f"✅ Forwarded message {message_id} to user {to_user_id}")
                return True
            return False
            
        except ChannelPrivate:
            raise Exception("This channel is private and you cannot access it. Please make sure you're a member.")
        except UserNotParticipant:
            raise Exception("You are not a member of this channel. Please join first.")
        except PeerIdInvalid:
            raise Exception("Cannot find this channel. Please make sure you're a member.")
        except Exception as e:
            raise Exception(f"Forward failed: {str(e)}")
    
    async def batch_copy_messages(self, from_chat_id: str, start_message_id: int, count: int, to_user_id: int, progress_callback=None) -> int:
        """Copy multiple messages directly - FAST BATCH FORWARD"""
        if not self.is_connected:
            raise Exception("User session not connected")
        
        success_count = 0
        
        try:
            # Resolve peer first
            await self.resolve_peer(from_chat_id)
            
            # Get messages in range
            message_ids = list(range(start_message_id, start_message_id + count))
            
            for i, msg_id in enumerate(message_ids):
                try:
                    if progress_callback:
                        progress_callback(f"Forwarding {i+1}/{count}...", i+1, count)
                    
                    # Try to copy this message
                    copied = await self.client.copy_message(
                        chat_id=to_user_id,
                        from_chat_id=from_chat_id,
                        message_id=msg_id
                    )
                    
                    if copied:
                        success_count += 1
                        self.db.increment_download_count(self.user_id)
                    
                    # Small delay to avoid flood
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    print(f"⚠️ Could not forward message {msg_id}: {e}")
                    continue
            
            return success_count
            
        except Exception as e:
            raise Exception(f"Batch forward failed: {str(e)}")

    async def disconnect(self):
        """Disconnect user session"""
        if self.client and self.is_connected:
            try:
                await self.client.disconnect()  # Faster than stop()
                self.is_connected = False
                print(f"✅ User session disconnected: {self.user_id}")
            except Exception as e:
                print(f"⚠️ Error disconnecting user session {self.user_id}: {e}")
    
    async def _generate_filename(self, message: Message) -> str:
        """Generate proper filename with correct extension - FIXED"""
        if message.video:
            media = message.video
            file_type = "video"
            default_ext = "mp4"
        elif message.document:
            media = message.document
            file_type = "document"
            # Get extension from mime_type for documents
            if media.mime_type:
                mime_ext = media.mime_type.split('/')[-1]
                # Map common mime types to proper extensions
                mime_to_ext = {
                    'mp4': 'mp4', 'mpeg': 'mp3', 'x-m4a': 'm4a', 'ogg': 'ogg',
                    'webm': 'webm', 'x-matroska': 'mkv', 'quicktime': 'mov',
                    'x-msvideo': 'avi', 'x-flv': 'flv', '3gpp': '3gp',
                    'jpeg': 'jpg', 'png': 'png', 'gif': 'gif', 'webp': 'webp',
                    'pdf': 'pdf', 'zip': 'zip', 'x-rar': 'rar', 'x-7z-compressed': '7z'
                }
                default_ext = mime_to_ext.get(mime_ext, mime_ext)
            else:
                default_ext = "bin"
        elif message.audio:
            media = message.audio
            file_type = "audio"
            default_ext = "mp3"
        elif message.photo:
            media = message.photo
            file_type = "photo"
            default_ext = "jpg"
        elif message.sticker:
            media = message.sticker
            file_type = "sticker"
            default_ext = "webp"
        elif message.animation:
            media = message.animation
            file_type = "animation"
            default_ext = "gif" if message.animation.mime_type == "image/gif" else "mp4"
        elif message.voice:
            media = message.voice
            file_type = "voice"
            default_ext = "ogg"
        elif message.video_note:
            media = message.video_note
            file_type = "video_note"
            default_ext = "mp4"
        else:
            return f"file_{message.id}.bin"
        
        # Check if file has original filename WITH valid extension
        if hasattr(media, 'file_name') and media.file_name:
            original_name = FileManager.clean_filename(media.file_name)
            # Check if filename has a valid extension
            if '.' in original_name:
                ext = original_name.rsplit('.', 1)[-1].lower()
                if len(ext) <= 5 and ext.isalnum():
                    return original_name
            # Filename has no valid extension, add the default one
            return f"{original_name}.{default_ext}"
        
        # Generate filename with proper extension
        file_ext = self._get_file_extension(media, file_type)
        if file_ext == 'bin' or not file_ext:
            file_ext = default_ext
        
        return f"{file_type}_{message.id}.{file_ext}"
    
    def _get_file_extension(self, media_obj, media_type: str) -> str:
        """Get proper file extension based on media type and mime type"""
        # Try to get extension from mime type first
        if hasattr(media_obj, 'mime_type') and media_obj.mime_type:
            mime_parts = media_obj.mime_type.split('/')
            if len(mime_parts) == 2:
                ext = mime_parts[1]
                # Clean up common mime type to extension mappings
                ext_mapping = {
                    'vnd.android.package-archive': 'apk',
                    'octet-stream': 'bin',
                    'zip': 'zip',
                    'pdf': 'pdf',
                    'msword': 'doc',
                    'vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
                    'vnd.ms-excel': 'xls',
                    'vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'xlsx',
                    'vnd.ms-powerpoint': 'ppt',
                    'vnd.openxmlformats-officedocument.presentationml.presentation': 'pptx'
                }
                return ext_mapping.get(ext, ext)
        
        # Fallback to type-based extensions
        extensions = {
            'video': 'mp4',
            'audio': 'mp3',
            'photo': 'jpg',
            'sticker': 'webp',
            'animation': 'mp4',
            'voice': 'ogg',
            'video_note': 'mp4'
        }
        
        return extensions.get(media_type, 'bin')