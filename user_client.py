import os
import asyncio
from pyrogram import Client
from pyrogram.types import Message, Chat
from pyrogram.errors import (
    SessionPasswordNeeded, PhoneCodeInvalid,
    PhoneNumberInvalid, FloodWait, ChannelPrivate,
    UserNotParticipant, ChatAdminRequired
)

from config import Config
from utils import FileManager

class UserBotClient:
    def __init__(self):
        self.client = None
        self.is_connected = False
        self.joined_channels = []
    
    async def start(self):
        """Start user bot with automatic authentication"""
        try:
            print("🔐 Starting user bot authentication...")
            
            self.client = Client(
                Config.USER_SESSION,
                api_id=Config.API_ID,
                api_hash=Config.API_HASH,
                workdir="sessions"
            )
            
            await self.client.start()
            self.is_connected = True
            
            me = await self.client.get_me()
            print(f"✅ User bot authenticated as: {me.first_name}")
            
            # Load joined channels
            await self.load_joined_channels()
            
            return True
            
        except Exception as e:
            print(f"❌ User bot failed: {e}")
            return False
    
    async def load_joined_channels(self):
        """Load all channels and groups the user is member of"""
        try:
            print("📋 Loading your channels and groups...")
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
            
            print(f"✅ Loaded {len(self.joined_channels)} channels/groups")
            
        except Exception as e:
            print(f"❌ Failed to load channels: {e}")
    
    async def get_joined_channels(self):
        """Get list of joined channels"""
        return self.joined_channels
    
    async def search_channels(self, query: str):
        """Search channels by title or username"""
        results = []
        for channel in self.joined_channels:
            if (query.lower() in channel['title'].lower() or 
                (channel['username'] and query.lower() in channel['username'].lower())):
                results.append(channel)
        return results
    
    async def download_file(self, chat_id: str, message_id: int) -> str:
        """Download file from Telegram with proper filename handling"""
        if not self.is_connected:
            raise Exception("User bot not connected")
        
        try:
            # Get the message
            message = await self.client.get_messages(chat_id, message_id)
            if not message or getattr(message, 'empty', False):
                raise Exception("Message not found or inaccessible")
            
            # Check if message has media
            if not any([message.video, message.document, message.audio, message.photo, message.sticker, message.animation, message.voice]):
                raise Exception("No media found in message")
            
            # Generate proper filename with correct extension
            filename = await self._generate_filename(message)
            file_path = os.path.join("downloads", filename)
            
            # Download file
            print(f"📥 Downloading: {filename}")
            download_path = await message.download(file_name=file_path)
            
            # Verify the file was downloaded and has correct extension
            if download_path and os.path.exists(download_path):
                actual_filename = os.path.basename(download_path)
                print(f"✅ Download completed: {actual_filename}")
                return download_path
            else:
                raise Exception("Download failed - file not found after download")
            
        except ChannelPrivate:
            raise Exception("This channel is private and I cannot access it. Please make sure you're a member.")
        except UserNotParticipant:
            raise Exception("You are not a member of this channel. Join the channel first.")
        except ChatAdminRequired:
            raise Exception("Admin rights required to access this content.")
        except Exception as e:
            raise Exception(f"Download failed: {str(e)}")
    
    async def upload_file(self, user_id: int, file_path: str, caption: str = "") -> Message:
        """Upload file to user with proper file type detection"""
        if not self.is_connected:
            raise Exception("User bot not connected")
        
        if not os.path.exists(file_path):
            raise Exception("File not found")
        
        filename = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        print(f"📤 Uploading: {filename} ({file_size/1024/1024:.1f}MB)")
        
        file_ext = os.path.splitext(file_path)[1].lower()
        upload_kwargs = {'caption': caption} if caption else {}
        
        try:
            # Determine file type and upload accordingly
            if file_ext in ['.mp4', '.avi', '.mov', '.mkv', '.webm']:
                # Send as video
                message = await self.client.send_video(
                    user_id, 
                    file_path,
                    **upload_kwargs
                )
            elif file_ext in ['.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff']:
                # Send as photo
                message = await self.client.send_photo(
                    user_id,
                    file_path,
                    **upload_kwargs
                )
            elif file_ext in ['.mp3', '.ogg', '.m4a', '.wav', '.flac', '.aac']:
                # Send as audio
                message = await self.client.send_audio(
                    user_id,
                    file_path,
                    **upload_kwargs
                )
            elif file_ext in ['.apk']:
                # Send APK as document but with proper thumbnail
                message = await self.client.send_document(
                    user_id,
                    file_path,
                    **upload_kwargs
                )
            else:
                # Send as document with original filename
                message = await self.client.send_document(
                    user_id,
                    file_path,
                    **upload_kwargs
                )
            
            print(f"✅ Upload completed: {filename}")
            return message
            
        except Exception as e:
            print(f"❌ Upload failed: {e}")
            # Fallback: send as document
            try:
                message = await self.client.send_document(
                    user_id,
                    file_path,
                    **upload_kwargs
                )
                print(f"✅ Upload completed (fallback): {filename}")
                return message
            except Exception as fallback_error:
                print(f"❌ Fallback upload also failed: {fallback_error}")
                raise
    
    async def get_message(self, chat_id: str, message_id: int) -> Message:
        """Get message from Telegram - works with both usernames and chat IDs"""
        if not self.is_connected:
            raise Exception("User bot not connected")
        
        try:
            message = await self.client.get_messages(chat_id, message_id)
            if not message or getattr(message, 'empty', False):
                raise Exception("Message not found or inaccessible")
            return message
            
        except ChannelPrivate:
            raise Exception("❌ Channel is private. Make sure you're a member and have access.")
        except UserNotParticipant:
            raise Exception("❌ You're not a member of this channel. Join the channel first.")
        except Exception as e:
            raise Exception(f"❌ Cannot access message: {str(e)}")
    
    async def _generate_filename(self, message: Message) -> str:
        """Generate proper filename with correct extension"""
        if message.video:
            media = message.video
            file_type = "video"
            default_ext = "mp4"
        elif message.document:
            media = message.document
            file_type = "document"
            default_ext = media.mime_type.split('/')[-1] if media.mime_type else "bin"
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
            default_ext = "mp4"
        elif message.voice:
            media = message.voice
            file_type = "voice"
            default_ext = "ogg"
        else:
            return f"file_{message.id}.bin"
        
        # If file has original filename, use it
        if hasattr(media, 'file_name') and media.file_name:
            return FileManager.clean_filename(media.file_name)
        
        # Otherwise generate filename with proper extension
        file_ext = self._get_file_extension(media, file_type)
        if file_ext == 'bin':
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
    
    async def stop(self):
        """Stop the user bot"""
        if self.client and self.is_connected:
            await self.client.stop()
        self.is_connected = False