import re
import asyncio
import os
import signal
import sys
import time
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import Message, ReplyKeyboardRemove

from config import Config
from database import DatabaseManager
from auth_manager import AuthManager
from user_session import UserSession
from utils import LinkParser, FileManager
from ui_components import UIComponents, Messages
from premium_manager import PremiumManager

class TelegramDownloader:
    def __init__(self):
        self.config = Config
        self.config.validate_config()
        
        # Initialize database and managers
        self.db = DatabaseManager()
        self.auth_manager = AuthManager(Config.API_ID, Config.API_HASH, Config.SESSION_DIR)
        self.premium_manager = PremiumManager(self.db)
        
        # User state management
        self.user_states = {}  # Track user states for various operations
        self.processing_users = set()  # Users currently processing downloads
        self.last_download_time = {}  # Track last download time for cooldown
        
        # Initialize bot client
        self.bot = Client(
            "downloader_bot",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            bot_token=Config.BOT_TOKEN,
            workdir="sessions"
        )
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        print(f"\n🛑 Shutting down...")
        asyncio.create_task(self.shutdown())
    
    async def _check_access(self, message: Message) -> bool:
        """Check if user can access the bot - FIXED ADMIN ACCESS"""
        user_id = message.from_user.id
        
        # Check if user is authenticated
        if not self.auth_manager.is_user_authenticated(user_id):
            await message.reply_text(
                "🔐 **Please login first!**\n\n"
                "Use the login button below to authenticate with your Telegram account.",
                reply_markup=UIComponents.get_main_menu()
            )
            return False
        
        # Get user data
        user_data = self.db.get_user(user_id)
        if not user_data:
            await message.reply_text(
                "❌ User account not found. Please login again.",
                reply_markup=UIComponents.get_main_menu()
            )
            return False
        
        # FIXED: Check if user is admin (from database OR from config)
        is_admin = user_data.get('is_admin', False) or user_id in Config.ADMIN_IDS
        
        # Check download limits (skip for admins - THEY HAVE UNLIMITED ACCESS)
        if not is_admin:
            can_download, reason = self.premium_manager.can_download(user_data)
            if not can_download:
                await message.reply_text(
                    f"❌ **{reason}**\n\n"
                    f"💎 Upgrade to Premium for more downloads!",
                    reply_markup=UIComponents.get_main_menu(user_data)
                )
                return False
            
            # Check cooldown for free users - SHOW WAIT TIME
            cooldown = self.premium_manager.get_cooldown_time(user_data)
            if cooldown > 0 and user_id in self.last_download_time:
                time_since_last = time.time() - self.last_download_time[user_id]
                if time_since_last < cooldown:
                    wait_time = cooldown - int(time_since_last)
                    await message.reply_text(
                        f"⏳ **Please wait {wait_time} seconds** before next download.\n\n"
                        f"Free users have {cooldown} second cooldown between downloads.\n"
                        f"💎 Premium users have no cooldown!",
                        reply_markup=UIComponents.get_main_menu(user_data)
                    )
                    return False
        
        return True

    async def handle_start(self, client, message: Message):
        """Handle /start command - FIXED ADMIN ACCESS"""
        user_id = message.from_user.id
        
        # FIXED: Check if user is admin from config
        is_config_admin = user_id in Config.ADMIN_IDS
        
        user_data = self.db.get_user(user_id)
        
        # If user is admin in config but not in database, update database
        if is_config_admin and user_data and not user_data.get('is_admin', False):
            self.db.update_user_admin_status(user_id, True)
            user_data['is_admin'] = True
        
        # Check if user is authenticated AND has valid session
        is_authenticated = self.auth_manager.is_user_authenticated(user_id)
        
        if is_authenticated and user_data:
            # User is logged in, show main menu directly
            await message.reply_text(
                Messages.get_welcome_message(),
                reply_markup=UIComponents.get_main_menu(user_data)
            )
        else:
            # New user or not authenticated, show welcome with login
            await message.reply_text(
                Messages.get_welcome_message(),
                reply_markup=UIComponents.get_main_menu()
            )
    
    async def handle_callback_query(self, client, callback_query):
        """Handle all callback queries - FIXED CONFIG IMPORT"""
        user_id = callback_query.from_user.id
        data = callback_query.data
        
        try:
            # Main menu actions
            if data == "main_menu":
                # FIXED: Clear any payment states when going to main menu
                if user_id in self.user_states:
                    if self.user_states[user_id].get('awaiting_payment'):
                        del self.user_states[user_id]['awaiting_payment']
                
                user_data = self.db.get_user(user_id)
                await callback_query.message.edit_text(
                    Messages.get_welcome_message(),
                    reply_markup=UIComponents.get_main_menu(user_data)
                )
            
            elif data == "login":
                await self.handle_login_callback(client, callback_query)
            
            elif data == "download_media":
                await self.handle_download_media(client, callback_query)
            
            elif data == "forward_media":
                await self.handle_forward_media_callback(client, callback_query)
            
            elif data == "stats":
                await self.handle_stats_callback(client, callback_query)
            
            elif data == "help":
                await self.handle_help_callback(client, callback_query)
            
            elif data == "premium_info":
                await self.handle_premium_info(client, callback_query)
            
            elif data == "compare_plans":
                await self.handle_compare_plans(client, callback_query)
            
            elif data == "all_payments":
                # REDIRECT TO PREMIUM INFO INSTEAD
                await self.handle_premium_info(client, callback_query)
            
            elif data.startswith("premium_plan") or data.startswith("pro_plan"):
                plan_type = "premium" if "premium" in data else "pro"
                await self.handle_plan_selection(client, callback_query, plan_type)
            
            elif data.startswith("pay_"):
                await self.handle_payment_method(client, callback_query, data)
            
            elif data == "logout":
                await self.handle_logout_callback(client, callback_query)
            
            elif data == "batch_download":
                await self.handle_batch_download_callback(client, callback_query)
            
            # Batch download buttons - FIXED TO WORK PROPERLY
            elif data.startswith("batch_"):
                await self.handle_batch_selection(client, callback_query, data)
            
            # Admin actions
            elif data == "admin_menu":
                await self.handle_admin_menu(client, callback_query)
            
            elif data == "admin_stats":
                await self.handle_admin_stats(client, callback_query)
            
            elif data == "admin_premium":
                await self.handle_admin_premium(client, callback_query)
            
            elif data == "admin_broadcast":
                await self.handle_admin_broadcast_callback(client, callback_query)
            
            elif data == "admin_pending_payments":
                await self.handle_admin_pending_payments(client, callback_query)
            
            elif data == "admin_add_premium":
                await self.handle_admin_add_premium_callback(client, callback_query)
            
            elif data == "admin_add_pro":
                await self.handle_admin_add_pro_callback(client, callback_query)
            
            elif data == "admin_remove_premium":
                await self.handle_admin_remove_premium_callback(client, callback_query)
            
            elif data.startswith("verify_payment_"):
                payment_id = int(data.split("_")[2])
                plan_type = data.split("_")[3]
                await self.handle_verify_payment(client, callback_query, payment_id, plan_type)
            
            elif data == "cancel":
                # FIXED: Clear payment states when canceling
                if user_id in self.user_states:
                    if self.user_states[user_id].get('awaiting_payment'):
                        del self.user_states[user_id]['awaiting_payment']
                
                user_data = self.db.get_user(user_id)
                await callback_query.message.edit_text(
                    "❌ Operation cancelled.",
                    reply_markup=UIComponents.get_main_menu(user_data)
                )
            
            await callback_query.answer()
            
        except Exception as e:
            print(f"❌ Callback error: {e}")
            await callback_query.answer("❌ An error occurred", show_alert=True)
    
    async def handle_batch_selection(self, client, callback_query, data):
        """Handle batch download selection - FIXED FOR ADMINS"""
        user_id = callback_query.from_user.id
        user_data = self.db.get_user(user_id)
        
        # Check if user has premium OR is admin
        is_admin = user_data.get('is_admin', False) or user_id in Config.ADMIN_IDS
        has_premium = user_data.get('is_premium', False) or user_data.get('is_pro', False)
        
        if not has_premium and not is_admin:
            await callback_query.answer("❌ Premium feature only", show_alert=True)
            return
        
        # Get batch count from data (batch_10, batch_20, batch_30)
        count = int(data.replace("batch_", ""))
        
        # Set user state for batch link
        self.user_states[user_id] = {
            'awaiting_batch_link': True,
            'batch_count': count
        }
        
        await callback_query.message.edit_text(
            f"📦 **Batch Download - {count} Files**\n\n"
            f"Please send the Telegram link to start batch download from.\n\n"
            f"**Supported formats:**\n"
            f"• `t.me/username/123`\n"
            f"• `t.me/c/123456789/2`\n"
            f"• `@username/123`\n\n"
            f"The bot will download {count} recent files starting from this message.",
            reply_markup=UIComponents.get_cancel_keyboard()
        )
    
    async def handle_login_callback(self, client, callback_query):
        """Handle login callback"""
        user_id = callback_query.from_user.id
        
        print(f"🔍 LOGIN CALLBACK: User {user_id}")
        
        if self.auth_manager.is_user_authenticated(user_id):
            user_data = self.db.get_user(user_id)
            await callback_query.message.edit_text(
                "✅ You are already logged in!",
                reply_markup=UIComponents.get_main_menu(user_data)
            )
            return
        
        # Set user state for phone number
        self.user_states[user_id] = {'awaiting_phone': True}
        
        # Send the login message with share button
        await callback_query.message.delete()  # Delete the original message
        
        await callback_query.message.reply_text(
            Messages.get_login_instructions(),
            reply_markup=UIComponents.get_login_keyboard()
        )
    
    async def handle_contact(self, client, message: Message):
        """Handle phone number sharing"""
        user_id = message.from_user.id
        
        if user_id not in self.user_states or not self.user_states[user_id].get('awaiting_phone'):
            return
        
        if not message.contact:
            await message.reply_text("❌ Please share your phone number using the button.")
            return
        
        phone_number = message.contact.phone_number
        if not phone_number.startswith('+'):
            phone_number = '+' + phone_number
        
        # Clear the keyboard immediately
        await message.reply_text(
            "📱 Processing your phone number...",
            reply_markup=ReplyKeyboardRemove()
        )
        
        # Start authentication process
        status_msg = await message.reply_text("📱 Sending verification code...")
        
        auth_result = await self.auth_manager.start_user_auth(user_id, phone_number)
        
        if auth_result['success']:
            self.user_states[user_id] = {
                'awaiting_code': True,
                'phone_number': phone_number,
                'phone_code_hash': auth_result['phone_code_hash']
            }
            
            await status_msg.edit_text(
                "✅ **Verification code sent!**\n\n"
                "Please check your Telegram app and send the 5-digit verification code you received.\n\n"
                "**Format:** Send code WITH SPACES for faster processing (e.g., 123 45)\n\n"
                f"[📹 Watch Login Guide]({Config.VIDEO_GUIDE_URL})"
            )
        else:
            await status_msg.edit_text(f"❌ {auth_result['error']}")
            if user_id in self.user_states:
                del self.user_states[user_id]
    
    async def handle_verification_code(self, client, message: Message):
        """Handle verification code input - FIXED: Better code extraction"""
        user_id = message.from_user.id
        
        if user_id not in self.user_states or not self.user_states[user_id].get('awaiting_code'):
            return
        
        # Clean the code - remove ALL whitespace and special chars, keep only digits
        text = message.text.strip() if message.text else ""
        # Remove spaces, dashes, underscores, etc - keep only digits
        code = ''.join(c for c in text if c.isdigit())
        
        if len(code) != 5:
            await message.reply_text("❌ Please enter a valid 5-digit verification code.\n\nYou can type it with or without spaces (e.g., 12345 or 123 45)")
            return
        
        user_state = self.user_states[user_id]
        status_msg = await message.reply_text("🔐 Verifying code...")
        
        # FIXED: Add a small delay to prevent code expiration (Telegram timing issue)
        await asyncio.sleep(0.5)
        
        verify_result = await self.auth_manager.verify_user_code(
            user_id,
            user_state['phone_number'],
            user_state['phone_code_hash'],
            code
        )
        
        if verify_result['success']:
            # Clear user state first
            if user_id in self.user_states:
                del self.user_states[user_id]
            
            # Handle successful login
            await self.handle_login_success(user_id)
            
        elif verify_result['error'] == '2FA_REQUIRED':
            self.user_states[user_id]['awaiting_2fa'] = True
            await status_msg.edit_text("🔒 **Two-Factor Authentication Required**\n\nPlease send your 2FA password:")
        else:
            await status_msg.edit_text(f"❌ {verify_result['error']}")
            if user_id in self.user_states:
                del self.user_states[user_id]
    
    async def handle_login_success(self, user_id):
        """Handle successful login"""
        user_data = self.db.get_user(user_id)
        
        # Send success message with main menu
        await self.bot.send_message(
            user_id,
            "✅ **Login successful!**\n\n"
            "Your Telegram account has been connected successfully.\n\n"
            "You can now download content from channels you're a member of.",
            reply_markup=UIComponents.get_main_menu(user_data)
        )
    
    async def handle_2fa_password(self, client, message: Message):
        """Handle 2FA password"""
        user_id = message.from_user.id
        
        if user_id not in self.user_states or not self.user_states[user_id].get('awaiting_2fa'):
            return
        
        password = message.text.strip()
        user_state = self.user_states[user_id]
        status_msg = await message.reply_text("🔐 Verifying 2FA password...")
        
        verify_result = await self.auth_manager.verify_2fa(
            user_id,
            user_state['phone_number'],
            user_state['phone_code_hash'],
            password
        )
        
        if verify_result['success']:
            # Clear user state first
            if user_id in self.user_states:
                del self.user_states[user_id]
            
            # Handle successful login
            await self.handle_login_success(user_id)
        else:
            await status_msg.edit_text(f"❌ {verify_result['error']}")
            if user_id in self.user_states:
                del self.user_states[user_id]
    
    async def handle_logout_callback(self, client, callback_query):
        """Handle logout callback - FIXED: KEEP SUBSCRIPTION"""
        user_id = callback_query.from_user.id
        
        # Remove session file but KEEP subscription data in database
        session_file = self.auth_manager.get_user_session_file(user_id)
        if os.path.exists(session_file):
            os.remove(session_file)
        
        # Clear auth state but don't touch premium status
        if user_id in self.user_states:
            del self.user_states[user_id]
        
        await callback_query.message.edit_text(
            "✅ **Logged out successfully!**\n\n"
            "Your session has been removed but your subscription remains active.\n\n"
            "Use /start to login again with the same account.",
            reply_markup=UIComponents.get_main_menu()
        )
    
    async def handle_links(self, client, message: Message):
        """Handle Telegram links - FASTER PROCESSING"""
        user_id = message.from_user.id
        
        # FIXED: Check if user is in payment state and clear it if they send a link
        if user_id in self.user_states and self.user_states[user_id].get('awaiting_payment'):
            del self.user_states[user_id]['awaiting_payment']
        
        if not await self._check_access(message):
            return
        
        if user_id in self.processing_users:
            await message.reply_text("⏳ Please wait, another download is in progress...")
            return
        
        try:
            self.processing_users.add(user_id)
            text = message.text or message.caption
            
            # Parse link
            link_data = LinkParser.parse_telegram_link(text)
            if not link_data:
                await message.reply_text(
                    "❌ **Invalid link format.**\n\n"
                    "**Supported formats:**\n"
                    "• `t.me/username/123` - Public channels\n"
                    "• `t.me/c/123456789/2` - Private channels\n"
                    "• `@username/123` - Short format\n\n"
                    "Please check the link and try again.",
                    reply_markup=UIComponents.get_main_menu(self.db.get_user(user_id))
                )
                return
            
            chat_id, message_id, link_type = link_data
            user_data = self.db.get_user(user_id)
            
            # FASTER: Create progress message and start immediately
            status_msg = await message.reply_text("🔗 Processing link...")
            
            # Create user session - FASTER CONNECTION
            user_session = UserSession(self.auth_manager, user_id, self.bot)
            await user_session.connect()
            
            try:
                # FASTER: Skip extra status updates, go straight to download
                # Get message
                try:
                    target_message = await user_session.get_message(chat_id, message_id)
                except Exception as access_error:
                    error_msg = str(access_error)
                    if "not a member" in error_msg.lower() or "private" in error_msg.lower():
                        await status_msg.edit_text(
                            "❌ **Channel Access Required**\n\n"
                            "You need to join this channel first to download its content.\n\n"
                            "**How to fix:**\n"
                            "1. Join the channel manually\n"
                            "2. Make sure you're a member\n"
                            "3. Try the download again\n\n"
                            "If you've already joined, wait a few minutes and try again.",
                            reply_markup=UIComponents.get_main_menu(user_data)
                        )
                    else:
                        await status_msg.edit_text(
                            f"❌ **Access Error**\n\n{error_msg}",
                            reply_markup=UIComponents.get_main_menu(user_data)
                        )
                    return
                
                # Process download with progress - COOL PROGRESS BARS
                await self._process_download_with_progress(message, status_msg, user_session, chat_id, message_id, target_message, user_data)
                
            finally:
                # FIXED: Better session cleanup to prevent connection errors
                try:
                    await user_session.disconnect()
                except Exception as e:
                    print(f"⚠️ Session disconnect warning: {e}")
            
        except Exception as e:
            await message.reply_text(
                f"❌ **Download Failed**\n\n{str(e)}",
                reply_markup=UIComponents.get_main_menu(self.db.get_user(user_id))
            )
        finally:
            self.processing_users.discard(user_id)
    
    async def _process_download_with_progress(self, message: Message, status_msg: Message, user_session: UserSession, 
                                           chat_id: str, message_id: int, target_message: Message, user_data: dict):
        """Process download with progress updates - COOL PROGRESS BARS"""
        user_id = message.from_user.id
        
        # Check media
        if not any([target_message.video, target_message.document, target_message.audio, target_message.photo]):
            await status_msg.edit_text("❌ No downloadable media found in this message.")
            return
        
        # Check file size
        file_size = await self._get_media_size(target_message)
        max_size = self.premium_manager.get_file_size_limit(user_data)
        
        if file_size and file_size > max_size:
            size_mb = file_size / 1024 / 1024
            max_mb = max_size / 1024 / 1024
            await status_msg.edit_text(
                f"❌ **File Too Large**\n\n"
                f"File size: {size_mb:.1f}MB\n"
                f"Your limit: {max_mb:.0f}MB\n\n"
                f"💎 Upgrade to Premium for larger files!",
                reply_markup=UIComponents.get_main_menu(user_data)
            )
            return
        
        # Download with progress - COOL PROGRESS BAR
        await status_msg.edit_text("📥 Starting download...")
        
        # Progress tracking with COOL progress bars
        last_update_time = 0
        animation_frames = ["🔄", "⚡", "🔷", "🔶", "💠", "🌀"]
        frame_index = 0
        start_time = time.time()
        
        async def download_progress(percentage, current, total):
            nonlocal last_update_time, frame_index
            current_time = time.time()
            
            # Update more frequently for better animation (every 0.5 seconds or 5% change)
            if current_time - last_update_time > 0.5 or percentage % 5 == 0 or percentage == 100:
                mb_current = current / 1024 / 1024
                mb_total = total / 1024 / 1024
                progress_bar = self._create_cool_progress_bar(percentage)
                animation = animation_frames[frame_index % len(animation_frames)]
                frame_index += 1
                
                elapsed = current_time - start_time
                speed = (current / 1024 / 1024) / elapsed if elapsed > 0 else 0
                eta = (total - current) / (current / elapsed) if current > 0 else 0
                
                status_text = (
                    f"**📥 DOWNLOADING** {animation}\n\n"
                    f"{progress_bar} **{percentage:.1f}%**\n\n"
                    f"**Size:** {mb_current:.1f}MB / {mb_total:.1f}MB\n"
                    f"**Speed:** {speed:.1f} MB/s\n"
                    f"**ETA:** {self._format_time(eta)}"
                )
                
                try:
                    await status_msg.edit_text(status_text)
                    last_update_time = current_time
                except:
                    pass  # Ignore edit errors
        
        try:
            downloaded_path = await user_session.download_file(chat_id, message_id, download_progress)
        except Exception as download_error:
            await status_msg.edit_text(f"❌ **Download Failed**\n\n{str(download_error)}")
            return
        
        # Upload with progress - COOL PROGRESS BAR
        await status_msg.edit_text("📤 Starting upload...")
        
        last_upload_time = 0
        upload_frame_index = 0
        upload_start_time = time.time()
        
        async def upload_progress(percentage, current, total):
            nonlocal last_upload_time, upload_frame_index
            current_time = time.time()
            
            # Update more frequently for better animation
            if current_time - last_upload_time > 0.5 or percentage % 5 == 0 or percentage == 100:
                mb_current = current / 1024 / 1024
                mb_total = total / 1024 / 1024
                progress_bar = self._create_cool_progress_bar(percentage, "🟢", "⚫")
                animation = animation_frames[upload_frame_index % len(animation_frames)]
                upload_frame_index += 1
                
                elapsed = current_time - upload_start_time
                speed = (current / 1024 / 1024) / elapsed if elapsed > 0 else 0
                eta = (total - current) / (current / elapsed) if current > 0 else 0
                
                status_text = (
                    f"**📤 UPLOADING** {animation}\n\n"
                    f"{progress_bar} **{percentage:.1f}%**\n\n"
                    f"**Progress:** {mb_current:.1f}MB / {mb_total:.1f}MB\n"
                    f"**Speed:** {speed:.1f} MB/s\n"
                    f"**ETA:** {self._format_time(eta)}"
                )
                
                try:
                    await status_msg.edit_text(status_text)
                    last_upload_time = current_time
                except:
                    pass  # Ignore edit errors
        
        try:
            # Detect media type from original message
            media_type = None
            if target_message.video:
                media_type = "video"
            elif target_message.photo:
                media_type = "photo"
            elif target_message.audio:
                media_type = "audio"
            elif target_message.voice:
                media_type = "voice"
            elif target_message.video_note:
                media_type = "video_note"
            elif target_message.animation:
                media_type = "animation"
            elif target_message.sticker:
                media_type = "sticker"
            elif target_message.document:
                media_type = "document"
            
            # Upload file through the bot with correct media type
            await self._upload_file_through_bot(user_id, downloaded_path, target_message.caption or "Downloaded via Premium Downloader Bot", upload_progress, media_type)
        except Exception as upload_error:
            await status_msg.edit_text(f"❌ **Upload Failed**\n\n{str(upload_error)}")
            return
        
        # Cleanup and success
        FileManager.cleanup_file(downloaded_path)
        
        # Update last download time for cooldown
        self.last_download_time[user_id] = time.time()
        
        # Success message - SEND AS NEW MESSAGE
        user_data = self.db.get_user(user_id)  # Refresh data
        max_downloads = self.premium_manager.get_download_limit(user_data)
        used = user_data.get('download_count', 0)
        remaining = max(0, max_downloads - used) if max_downloads != "Unlimited" else "Unlimited"
        
        success_text = f"✅ **Download Completed!**\n\n📊 Remaining downloads today: {remaining}/{max_downloads}"
        
        if remaining == 0 and max_downloads != "Unlimited":
            success_text += "\n\n💎 Upgrade to Premium for more downloads!"
        
        # FIXED: Send as new message instead of editing status
        await message.reply_text(
            success_text,
            reply_markup=UIComponents.get_simple_download_keyboard()
        )
        
        # Delete the status message
        try:
            await status_msg.delete()
        except:
            pass
    
    def _create_cool_progress_bar(self, percentage, filled_char="🔵", empty_char="⚪", length=10):
        """Create a cool visual progress bar with emojis"""
        filled = int(length * percentage / 100)
        empty = length - filled
        
        # Create gradient effect
        if percentage < 30:
            filled_char = "🔴"  # Red for low progress
        elif percentage < 70:
            filled_char = "🟡"  # Yellow for medium progress
        else:
            filled_char = "🟢"  # Green for high progress
            
        return filled_char * filled + empty_char * empty
    
    def _format_time(self, seconds):
        """Format seconds into human readable time"""
        if seconds <= 0:
            return "00:00"
        
        minutes = int(seconds // 60)
        seconds = int(seconds % 60)
        return f"{minutes:02d}:{seconds:02d}"
    
    def _calculate_speed(self, current, total, start_time):
        """Calculate download/upload speed"""
        elapsed = time.time() - start_time
        if elapsed > 0:
            return (current / 1024 / 1024) / elapsed
        return 0
    
    async def _upload_file_through_bot(self, user_id: int, file_path: str, caption: str = "", progress_callback=None, media_type: str = None):
        """Upload file through the bot directly - SENDS IN ORIGINAL FORMAT"""
        if not os.path.exists(file_path):
            raise Exception("File not found")
        
        filename = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        print(f"📤 Bot uploading: {filename} ({file_size/1024/1024:.1f}MB) as {media_type or 'auto-detect'}")
        
        file_ext = os.path.splitext(file_path)[1].lower()
        
        # Video extensions
        video_exts = ['.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.3gp', '.wmv', '.m4v']
        # Photo extensions
        photo_exts = ['.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff', '.gif']
        # Audio extensions  
        audio_exts = ['.mp3', '.ogg', '.m4a', '.wav', '.flac', '.aac', '.wma', '.opus']
        # Voice extensions
        voice_exts = ['.oga']
        # Animation extensions
        animation_exts = ['.gif']
        
        try:
            # Use media_type if provided, otherwise detect from extension
            if media_type == "video" or (media_type is None and file_ext in video_exts):
                # Send as video with supports_streaming for better playback
                await self.bot.send_video(
                    user_id, 
                    file_path,
                    caption=caption,
                    supports_streaming=True
                )
                print(f"✅ Sent as VIDEO: {filename}")
                
            elif media_type == "photo" or (media_type is None and file_ext in photo_exts and file_ext != '.gif'):
                # Send as photo
                await self.bot.send_photo(
                    user_id,
                    file_path,
                    caption=caption
                )
                print(f"✅ Sent as PHOTO: {filename}")
                
            elif media_type == "animation" or (media_type is None and file_ext == '.gif'):
                # Send as animation (GIF)
                await self.bot.send_animation(
                    user_id,
                    file_path,
                    caption=caption
                )
                print(f"✅ Sent as ANIMATION: {filename}")
                
            elif media_type == "audio" or (media_type is None and file_ext in audio_exts):
                # Send as audio
                await self.bot.send_audio(
                    user_id,
                    file_path,
                    caption=caption
                )
                print(f"✅ Sent as AUDIO: {filename}")
                
            elif media_type == "voice" or (media_type is None and file_ext in voice_exts):
                # Send as voice
                await self.bot.send_voice(
                    user_id,
                    file_path,
                    caption=caption
                )
                print(f"✅ Sent as VOICE: {filename}")
                
            elif media_type == "video_note":
                # Send as video note (round video)
                await self.bot.send_video_note(
                    user_id,
                    file_path
                )
                print(f"✅ Sent as VIDEO NOTE: {filename}")
                
            elif media_type == "sticker":
                # Send as sticker
                await self.bot.send_sticker(
                    user_id,
                    file_path
                )
                print(f"✅ Sent as STICKER: {filename}")
                
            else:
                # Send as document with original filename
                await self.bot.send_document(
                    user_id,
                    file_path,
                    caption=caption
                )
                print(f"✅ Sent as DOCUMENT: {filename}")
            
        except Exception as e:
            print(f"❌ Bot upload failed ({media_type}): {e}")
            # Fallback: send as document
            try:
                await self.bot.send_document(
                    user_id,
                    file_path,
                    caption=caption
                )
                print(f"✅ Bot upload completed (fallback as document): {filename}")
            except Exception as fallback_error:
                print(f"❌ Bot fallback upload also failed: {fallback_error}")
                raise
    
    def _create_progress_bar(self, percentage, length=10):
        """Create a visual progress bar"""
        filled = int(length * percentage / 100)
        empty = length - filled
        return "█" * filled + "░" * empty
    
    async def handle_premium_info(self, client, callback_query):
        """Show premium information"""
        await callback_query.message.edit_text(
            Messages.get_premium_info_message(),
            reply_markup=UIComponents.get_premium_plans_keyboard()
        )
    
    async def handle_compare_plans(self, client, callback_query):
        """Show plan comparison"""
        premium_manager = PremiumManager(self.db)
        
        free_benefits = premium_manager.get_premium_benefits("free")
        premium_benefits = premium_manager.get_premium_benefits("premium")
        pro_benefits = premium_manager.get_premium_benefits("pro")
        admin_benefits = premium_manager.get_premium_benefits("admin")
        
        comparison_text = """
📊 **Plan Comparison**

**🆓 Free Tier:**
• Downloads: {free_downloads}
• File Size: {free_size}
• Features: {free_features}
• Cooldown: {free_cooldown}

**💎 Premium - $5/month:**
• Downloads: {premium_downloads}
• File Size: {premium_size}  
• Features: {premium_features}
• Cooldown: {premium_cooldown}

**🚀 Pro - $15/month:**
• Downloads: {pro_downloads}
• File Size: {pro_size}
• Features: {pro_features}
• Cooldown: {pro_cooldown}

**👑 Admin:**
• Downloads: {admin_downloads}
• File Size: {admin_size}
• Features: {admin_features}
• Cooldown: {admin_cooldown}
        """.format(
            free_downloads=free_benefits['downloads'],
            free_size=free_benefits['file_size'],
            free_features=", ".join(free_benefits['features']),
            free_cooldown=free_benefits['cooldown'],
            premium_downloads=premium_benefits['downloads'],
            premium_size=premium_benefits['file_size'],
            premium_features=", ".join(premium_benefits['features']),
            premium_cooldown=premium_benefits['cooldown'],
            pro_downloads=pro_benefits['downloads'],
            pro_size=pro_benefits['file_size'],
            pro_features=", ".join(pro_benefits['features']),
            pro_cooldown=pro_benefits['cooldown'],
            admin_downloads=admin_benefits['downloads'],
            admin_size=admin_benefits['file_size'],
            admin_features=", ".join(admin_benefits['features']),
            admin_cooldown=admin_benefits['cooldown']
        )
        
        await callback_query.message.edit_text(
            comparison_text,
            reply_markup=UIComponents.get_premium_plans_keyboard()
        )
    
    async def handle_plan_selection(self, client, callback_query, plan_type):
        """Handle plan selection"""
        await callback_query.message.edit_text(
            f"💳 **Payment Method - {plan_type.title()} Plan**\n\n"
            f"Choose your payment method:",
            reply_markup=UIComponents.get_payment_methods_keyboard(plan_type)
        )
    
    async def handle_payment_method(self, client, callback_query, data):
        """Handle payment method selection - FIXED"""
        parts = data.split('_')
        payment_method = parts[1]
        plan_type = parts[2]
        
        payment_info = Config.PAYMENT_METHODS.get(payment_method)
        
        # FIXED: Proper payment method check
        if not payment_info or payment_info.strip() == "":
            await callback_query.message.edit_text(
                f"❌ **{payment_method.upper()} payment method is not configured.**\n\n"
                f"Please contact the admin or choose another payment method.",
                reply_markup=UIComponents.get_back_keyboard("premium_info")
            )
            return
        
        instructions = Messages.get_payment_instructions(payment_method, plan_type, payment_info)
        
        # Set user state for payment
        user_id = callback_query.from_user.id
        self.user_states[user_id] = {
            'awaiting_payment': True,
            'payment_method': payment_method,
            'plan_type': plan_type
        }
        
        await callback_query.message.edit_text(
            instructions,
            reply_markup=UIComponents.get_back_keyboard(f"{plan_type}_plan")
        )
    
    async def handle_payment_confirmation(self, client, message: Message):
        """Handle payment transaction ID"""
        user_id = message.from_user.id
        
        # FIXED: Only process if user is actually in payment state
        if user_id not in self.user_states or not self.user_states[user_id].get('awaiting_payment'):
            # If not in payment state, treat as normal link
            if re.match(r'(https://t\.me/|@[a-zA-Z0-9_]+/\d+)', message.text or ''):
                await self.handle_links(client, message)
            return
        
        transaction_id = message.text.strip()
        if not transaction_id:
            await message.reply_text("❌ Please provide a valid transaction ID.")
            return
        
        user_state = self.user_states[user_id]
        
        # Process payment
        success, result_message = await self.premium_manager.process_payment(
            user_id,
            user_state['payment_method'],
            user_state['plan_type'],
            transaction_id
        )
        
        if success:
            await message.reply_text(
                f"✅ {result_message}\n\n"
                f"📞 **Contact Admin:** @official_kango\n"
                f"⏰ **Verification Time:** 1-6 hours\n\n"
                "Thank you for your purchase!",
                reply_markup=UIComponents.get_main_menu(self.db.get_user(user_id))
            )
        else:
            await message.reply_text(
                f"❌ {result_message}\n\nPlease try again or contact @official_kango for help.",
                reply_markup=UIComponents.get_main_menu(self.db.get_user(user_id))
            )
        
        # Clear payment state after processing
        if user_id in self.user_states:
            del self.user_states[user_id]['awaiting_payment']
    
    async def handle_stats_callback(self, client, callback_query):
        """Handle stats callback - FIXED FOR ALL USERS"""
        user_id = callback_query.from_user.id
        
        # FIXED: Check login status first
        if not self.auth_manager.is_user_authenticated(user_id):
            await callback_query.answer("❌ Please login first!", show_alert=True)
            return
        
        user_data = self.db.get_user(user_id)
        
        if not user_data:
            await callback_query.answer("❌ User not found", show_alert=True)
            return
        
        stats = self.db.get_user_stats(user_id)
        limits_message = Messages.get_download_limits_message(user_data)
        
        stats_text = f"""
📊 **Your Statistics**

{limits_message}

**Total Downloads:** {stats['total_downloads']}
**Total Data Downloaded:** {stats['total_size'] / 1024 / 1024:.1f} MB
**Account Created:** {user_data['created_at']}
**Last Activity:** {user_data['last_used']}
        """
        
        await callback_query.message.edit_text(
            stats_text,
            reply_markup=UIComponents.get_stats_keyboard()
        )
    
    async def handle_help_callback(self, client, callback_query):
        """Handle help callback"""
        await callback_query.message.edit_text(
            Messages.get_help_message(),
            reply_markup=UIComponents.get_back_keyboard("main_menu")
        )
    
    async def handle_download_media(self, client, callback_query):
        """Handle download media callback"""
        user_id = callback_query.from_user.id
        user_data = self.db.get_user(user_id)
        
        await callback_query.message.edit_text(
            "📥 **Download Media**\n\n"
            "Simply send any Telegram message link to download its media.\n\n"
            "**Supported formats:**\n"
            "• `t.me/username/123`\n"
            "• `t.me/c/123456789/2`\n"
            "• `@username/123`\n\n"
            "**Note:** You must be a member of private channels to download their content.",
            reply_markup=UIComponents.get_main_menu(user_data)
        )
    
    async def handle_all_payments(self, client, callback_query):
        """Show all payment methods in one message - REDIRECTED"""
        await callback_query.message.edit_text(
            Messages.get_all_payment_methods_message(),
            reply_markup=UIComponents.get_back_keyboard("premium_info")
        )
    
    async def handle_batch_download_callback(self, client, callback_query):
        """Handle batch download callback - FIXED FOR ADMINS"""
        user_id = callback_query.from_user.id
        user_data = self.db.get_user(user_id)
        
        # Check if user has premium OR is admin
        is_admin = user_data.get('is_admin', False) or user_id in Config.ADMIN_IDS
        has_premium = user_data.get('is_premium', False) or user_data.get('is_pro', False)
        
        if not has_premium and not is_admin:
            await callback_query.answer("❌ Premium feature only", show_alert=True)
            return
        
        await callback_query.message.edit_text(
            Messages.get_batch_instructions(),
            reply_markup=UIComponents.get_batch_download_keyboard()
        )
    
    # Admin handlers
    async def handle_admin_menu(self, client, callback_query):
        """Show admin menu - FIXED ADMIN ACCESS"""
        user_id = callback_query.from_user.id
        
        # FIXED: Check login status first
        if not self.auth_manager.is_user_authenticated(user_id):
            await callback_query.answer("❌ Please login first!", show_alert=True)
            return
        
        # FIXED: Check admin access from both database and config
        user_data = self.db.get_user(user_id)
        is_admin = (user_data and user_data.get('is_admin', False)) or user_id in Config.ADMIN_IDS
        
        if not is_admin:
            await callback_query.answer("❌ Admin only", show_alert=True)
            return
        
        await callback_query.message.edit_text(
            Messages.get_admin_welcome_message(),
            reply_markup=UIComponents.get_admin_menu()
        )
    
    async def handle_admin_stats(self, client, callback_query):
        """Show admin statistics - FIXED ADMIN ACCESS"""
        user_id = callback_query.from_user.id
        
        # FIXED: Check admin access from both database and config
        user_data = self.db.get_user(user_id)
        is_admin = (user_data and user_data.get('is_admin', False)) or user_id in Config.ADMIN_IDS
        
        if not is_admin:
            await callback_query.answer("❌ Admin only", show_alert=True)
            return
        
        stats = self.db.get_system_stats()
        
        stats_text = f"""
👑 **Admin Statistics**

**Users:**
• Total: {stats['total_users']}
• Active: {stats['active_users']}
• Premium: {stats['premium_users']}
• Pro: {stats['pro_users']}
• Admin: {stats['admin_users']}

**Downloads:**
• Total: {stats['total_downloads']}
• Data: {stats['total_size'] / 1024 / 1024:.1f} MB

**Payments:**
• Pending: {stats['pending_payments']}

**System:**
• Database: {Config.DB_PATH}
• Sessions: {len([f for f in os.listdir('sessions') if f.endswith('.session')])}
        """
        
        await callback_query.message.edit_text(
            stats_text,
            reply_markup=UIComponents.get_admin_menu()
        )
    
    async def handle_admin_premium(self, client, callback_query):
        """Show premium management - FIXED ADMIN ACCESS"""
        user_id = callback_query.from_user.id
        
        # FIXED: Check admin access from both database and config
        user_data = self.db.get_user(user_id)
        is_admin = (user_data and user_data.get('is_admin', False)) or user_id in Config.ADMIN_IDS
        
        if not is_admin:
            await callback_query.answer("❌ Admin only", show_alert=True)
            return
        
        await callback_query.message.edit_text(
            "💎 **Premium Management**\n\n"
            "Manage premium users and payments.",
            reply_markup=UIComponents.get_premium_management_keyboard()
        )
    
    async def handle_admin_pending_payments(self, client, callback_query):
        """Show pending payments - FIXED ADMIN ACCESS"""
        user_id = callback_query.from_user.id
        
        # FIXED: Check admin access from both database and config
        user_data = self.db.get_user(user_id)
        is_admin = (user_data and user_data.get('is_admin', False)) or user_id in Config.ADMIN_IDS
        
        if not is_admin:
            await callback_query.answer("❌ Admin only", show_alert=True)
            return
        
        pending_payments = self.db.get_pending_payments()
        
        if not pending_payments:
            await callback_query.message.edit_text(
                "✅ No pending payments.",
                reply_markup=UIComponents.get_premium_management_keyboard()
            )
            return
        
        payments_text = "📋 **Pending Payments**\n\n"
        
        for payment in pending_payments[:10]:  # Show first 10
            payments_text += f"**ID:** {payment['id']}\n"
            payments_text += f"**User:** {payment['user_id']}\n"
            payments_text += f"**Method:** {payment['payment_method']}\n"
            payments_text += f"**Amount:** ${payment['amount']}\n"
            payments_text += f"**TX ID:** {payment['transaction_id']}\n"
            payments_text += f"**Date:** {payment['created_at']}\n"
            
            # Add verify buttons
            keyboard = UIComponents.get_payment_verification_keyboard(payment['id'])
            await callback_query.message.edit_text(payments_text, reply_markup=keyboard)
            return
        
        await callback_query.message.edit_text(
            payments_text,
            reply_markup=UIComponents.get_premium_management_keyboard()
        )
    
    async def handle_admin_add_premium_callback(self, client, callback_query):
        """Handle admin add premium callback"""
        user_id = callback_query.from_user.id
        
        # Check admin access
        user_data = self.db.get_user(user_id)
        is_admin = (user_data and user_data.get('is_admin', False)) or user_id in Config.ADMIN_IDS
        
        if not is_admin:
            await callback_query.answer("❌ Admin only", show_alert=True)
            return
        
        self.user_states[user_id] = {'awaiting_add_premium': True}
        
        await callback_query.message.edit_text(
            "👑 **Add Premium User**\n\n"
            "Please send the user ID to add as premium user:\n\n"
            "**Format:** `/addprem 123456789`\n"
            "Or just send the user ID number",
            reply_markup=UIComponents.get_cancel_keyboard()
        )
    
    async def handle_admin_add_pro_callback(self, client, callback_query):
        """Handle admin add pro callback"""
        user_id = callback_query.from_user.id
        
        # Check admin access
        user_data = self.db.get_user(user_id)
        is_admin = (user_data and user_data.get('is_admin', False)) or user_id in Config.ADMIN_IDS
        
        if not is_admin:
            await callback_query.answer("❌ Admin only", show_alert=True)
            return
        
        self.user_states[user_id] = {'awaiting_add_pro': True}
        
        await callback_query.message.edit_text(
            "👑 **Add Pro User**\n\n"
            "Please send the user ID to add as pro user:\n\n"
            "**Format:** `/addpro 123456789`\n"
            "Or just send the user ID number",
            reply_markup=UIComponents.get_cancel_keyboard()
        )
    
    async def handle_admin_remove_premium_callback(self, client, callback_query):
        """Handle admin remove premium callback"""
        user_id = callback_query.from_user.id
        
        # Check admin access
        user_data = self.db.get_user(user_id)
        is_admin = (user_data and user_data.get('is_admin', False)) or user_id in Config.ADMIN_IDS
        
        if not is_admin:
            await callback_query.answer("❌ Admin only", show_alert=True)
            return
        
        self.user_states[user_id] = {'awaiting_remove_premium': True}
        
        await callback_query.message.edit_text(
            "👑 **Remove Premium/Pro User**\n\n"
            "Please send the user ID to remove from premium/pro:\n\n"
            "**Format:** `/deleteprem 123456789`\n"
            "Or just send the user ID number",
            reply_markup=UIComponents.get_cancel_keyboard()
        )
    
    async def handle_admin_broadcast_callback(self, client, callback_query):
        """Handle admin broadcast callback - FIXED ADMIN ACCESS"""
        user_id = callback_query.from_user.id
        
        # FIXED: Check admin access from both database and config
        user_data = self.db.get_user(user_id)
        is_admin = (user_data and user_data.get('is_admin', False)) or user_id in Config.ADMIN_IDS
        
        if not is_admin:
            await callback_query.answer("❌ Admin only", show_alert=True)
            return
        
        self.user_states[user_id] = {'awaiting_broadcast': True}
        
        await callback_query.message.edit_text(
            "📢 **Admin Broadcast**\n\n"
            "Please send the message you want to broadcast to all users:",
            reply_markup=UIComponents.get_cancel_keyboard()
        )
    
    async def handle_admin_broadcast_message(self, client, message: Message):
        """Handle admin broadcast message - FIXED ADMIN ACCESS"""
        user_id = message.from_user.id
        
        # FIXED: Check admin access from both database and config
        user_data = self.db.get_user(user_id)
        is_admin = (user_data and user_data.get('is_admin', False)) or user_id in Config.ADMIN_IDS
        
        if not is_admin:
            return
        
        if user_id not in self.user_states or not self.user_states[user_id].get('awaiting_broadcast'):
            return
        
        broadcast_text = message.text
        all_users = self.db.get_all_users()
        
        status_msg = await message.reply_text(f"📢 Broadcasting to {len(all_users)} users...")
        
        success_count = 0
        fail_count = 0
        
        for user in all_users:
            try:
                await self.bot.send_message(
                    user['user_id'], 
                    f"📢 **Admin Broadcast**\n\n{broadcast_text}"
                )
                success_count += 1
            except:
                fail_count += 1
            await asyncio.sleep(0.1)  # Rate limiting
        
        await status_msg.edit_text(
            f"✅ **Broadcast Completed!**\n\n"
            f"• ✅ Successful: {success_count}\n"
            f"• ❌ Failed: {fail_count}",
            reply_markup=UIComponents.get_admin_menu()
        )
        
        if user_id in self.user_states:
            del self.user_states[user_id]
    
    async def handle_verify_payment(self, client, callback_query, payment_id, plan_type):
        """Verify a payment - FIXED ADMIN ACCESS"""
        user_id = callback_query.from_user.id
        
        # FIXED: Check admin access from both database and config
        user_data = self.db.get_user(user_id)
        is_admin = (user_data and user_data.get('is_admin', False)) or user_id in Config.ADMIN_IDS
        
        if not is_admin:
            await callback_query.answer("❌ Admin only", show_alert=True)
            return
        
        success = self.db.verify_payment(payment_id, plan_type)
        
        if success:
            await callback_query.answer("✅ Payment verified!", show_alert=True)
            await self.handle_admin_pending_payments(client, callback_query)
        else:
            await callback_query.answer("❌ Failed to verify payment", show_alert=True)
    
    async def _get_media_size(self, message: Message) -> int:
        """Get media file size"""
        if message.video:
            return message.video.file_size
        elif message.document:
            return message.document.file_size
        elif message.audio:
            return message.audio.file_size
        return None
    
    # Command handlers
    async def handle_batch_command(self, client, message: Message):
        """Handle /batch command for premium users AND ADMINS"""
        user_id = message.from_user.id
        
        if not await self._check_access(message):
            return
        
        user_data = self.db.get_user(user_id)
        
        # Check if user has premium OR is admin
        is_admin = user_data.get('is_admin', False) or user_id in Config.ADMIN_IDS
        has_premium = user_data.get('is_premium', False) or user_data.get('is_pro', False)
        
        if not has_premium and not is_admin:
            await message.reply_text(
                "❌ **Batch download is a premium feature!**\n\n"
                "💎 Upgrade to Premium to use batch downloads.",
                reply_markup=UIComponents.get_main_menu(user_data)
            )
            return
        
        # Parse the link from command
        text = message.text.strip()
        if text == "/batch":
            await message.reply_text(
                Messages.get_batch_instructions(),
                reply_markup=UIComponents.get_batch_download_keyboard()
            )
            return
        
        # Extract link from command
        link = text.replace("/batch", "").strip()
        if not link:
            await message.reply_text(
                "❌ Please provide a Telegram link after /batch command.\n\n"
                "**Example:** `/batch https://t.me/channel/123`",
                reply_markup=UIComponents.get_main_menu(user_data)
            )
            return
        
        # Process batch download
        await self.process_batch_download(message, link, user_data, count=10)
    
    async def process_batch_download(self, message: Message, link: str, user_data: dict, count=10):
        """Process batch download - FIXED FOR ADMINS & CORRECT ORDER"""
        user_id = message.from_user.id
        
        if user_id in self.processing_users:
            await message.reply_text("⏳ Please wait, another download is in progress...")
            return
        
        try:
            self.processing_users.add(user_id)
            
            # Parse link
            link_data = LinkParser.parse_telegram_link(link)
            if not link_data:
                await message.reply_text(
                    "❌ **Invalid link format.**\n\n"
                    "Please check the link and try again.",
                    reply_markup=UIComponents.get_main_menu(user_data)
                )
                return
            
            chat_id, start_message_id, link_type = link_data
            
            status_msg = await message.reply_text("📦 Starting batch download...")
            
            # Create user session
            user_session = UserSession(self.auth_manager, user_id, self.bot)
            await user_session.connect()
            
            try:
                # FIXED: Download messages in CORRECT ORDER (recent posts BELOW the link)
                # For recent posts, we need to download messages with HIGHER IDs (newer messages)
                downloaded_count = 0
                for i in range(count):
                    # FIXED: Get messages with HIGHER IDs for recent posts (messages after the link)
                    message_id = start_message_id + i + 1  # Start from next message
                    
                    try:
                        await status_msg.edit_text(f"📥 Downloading {i+1}/{count}...")
                        
                        # Download single file
                        downloaded_path = await user_session.download_file(chat_id, message_id)
                        if downloaded_path:
                            # Upload through bot
                            await self._upload_file_through_bot(user_id, downloaded_path, f"Batch download #{i+1}")
                            FileManager.cleanup_file(downloaded_path)
                            downloaded_count += 1
                            
                            # Update download count
                            self.db.increment_download_count(user_id)
                            
                    except Exception as e:
                        print(f"❌ Failed to download message {message_id}: {e}")
                        # If we can't download newer messages, try older ones
                        continue
                
                # FIXED: Send completion as new message
                await message.reply_text(
                    f"✅ **Batch download completed!**\n\n"
                    f"📦 Downloaded {downloaded_count} files\n"
                    f"💎 Remaining downloads: {self.premium_manager.get_download_limit(user_data) - user_data.get('download_count', 0)}",
                    reply_markup=UIComponents.get_simple_download_keyboard()
                )
                
                # Delete status message
                try:
                    await status_msg.delete()
                except:
                    pass
                
            finally:
                # FIXED: Better session cleanup
                try:
                    await user_session.disconnect()
                except Exception as e:
                    print(f"⚠️ Session disconnect warning: {e}")
            
        except Exception as e:
            await message.reply_text(
                f"❌ **Batch download failed**\n\n{str(e)}",
                reply_markup=UIComponents.get_main_menu(user_data)
            )
        finally:
            self.processing_users.discard(user_id)
    
    async def handle_addprem_command(self, client, message: Message):
        """Handle /addprem command for admins"""
        user_id = message.from_user.id
        
        # Check admin access
        user_data = self.db.get_user(user_id)
        is_admin = (user_data and user_data.get('is_admin', False)) or user_id in Config.ADMIN_IDS
        
        if not is_admin:
            await message.reply_text("❌ Admin only command.")
            return
        
        # Parse command
        text = message.text.strip()
        parts = text.split()
        
        if len(parts) < 2:
            await message.reply_text(
                "👑 **Add Premium User**\n\n"
                "**Usage:** `/addprem [user_id]`\n\n"
                "**Example:** `/addprem 123456789`",
                reply_markup=UIComponents.get_admin_menu()
            )
            return
        
        try:
            target_user_id = int(parts[1])
            success = self.db.set_premium_status(target_user_id, "premium")
            
            if success:
                # Notify target user
                try:
                    await self.bot.send_message(
                        target_user_id,
                        Messages.get_premium_added_message("premium"),
                        reply_markup=UIComponents.get_main_menu(self.db.get_user(target_user_id))
                    )
                except:
                    pass  # User might have blocked the bot
                
                await message.reply_text(
                    f"✅ **Premium added successfully!**\n\n"
                    f"User ID: `{target_user_id}`\n"
                    f"The user has been notified.",
                    reply_markup=UIComponents.get_admin_menu()
                )
            else:
                await message.reply_text(
                    f"❌ Failed to add premium for user {target_user_id}",
                    reply_markup=UIComponents.get_admin_menu()
                )
                
        except ValueError:
            await message.reply_text(
                "❌ Invalid user ID. Please provide a numeric user ID.",
                reply_markup=UIComponents.get_admin_menu()
            )
    
    async def handle_addpro_command(self, client, message: Message):
        """Handle /addpro command for admins"""
        user_id = message.from_user.id
        
        # Check admin access
        user_data = self.db.get_user(user_id)
        is_admin = (user_data and user_data.get('is_admin', False)) or user_id in Config.ADMIN_IDS
        
        if not is_admin:
            await message.reply_text("❌ Admin only command.")
            return
        
        # Parse command
        text = message.text.strip()
        parts = text.split()
        
        if len(parts) < 2:
            await message.reply_text(
                "👑 **Add Pro User**\n\n"
                "**Usage:** `/addpro [user_id]`\n\n"
                "**Example:** `/addpro 123456789`",
                reply_markup=UIComponents.get_admin_menu()
            )
            return
        
        try:
            target_user_id = int(parts[1])
            success = self.db.set_premium_status(target_user_id, "pro")
            
            if success:
                # Notify target user
                try:
                    await self.bot.send_message(
                        target_user_id,
                        Messages.get_premium_added_message("pro"),
                        reply_markup=UIComponents.get_main_menu(self.db.get_user(target_user_id))
                    )
                except:
                    pass  # User might have blocked the bot
                
                await message.reply_text(
                    f"✅ **Pro added successfully!**\n\n"
                    f"User ID: `{target_user_id}`\n"
                    f"The user has been notified.",
                    reply_markup=UIComponents.get_admin_menu()
                )
            else:
                await message.reply_text(
                    f"❌ Failed to add pro for user {target_user_id}",
                    reply_markup=UIComponents.get_admin_menu()
                )
                
        except ValueError:
            await message.reply_text(
                "❌ Invalid user ID. Please provide a numeric user ID.",
                reply_markup=UIComponents.get_admin_menu()
            )
    
    async def handle_deleteprem_command(self, client, message: Message):
        """Handle /deleteprem command for admins"""
        user_id = message.from_user.id
        
        # Check admin access
        user_data = self.db.get_user(user_id)
        is_admin = (user_data and user_data.get('is_admin', False)) or user_id in Config.ADMIN_IDS
        
        if not is_admin:
            await message.reply_text("❌ Admin only command.")
            return
        
        # Parse command
        text = message.text.strip()
        parts = text.split()
        
        if len(parts) < 2:
            await message.reply_text(
                "👑 **Remove Premium/Pro User**\n\n"
                "**Usage:** `/deleteprem [user_id]`\n\n"
                "**Example:** `/deleteprem 123456789`",
                reply_markup=UIComponents.get_admin_menu()
            )
            return
        
        try:
            target_user_id = int(parts[1])
            success = self.db.set_premium_status(target_user_id, "free")
            
            if success:
                await message.reply_text(
                    f"✅ **Premium/Pro removed successfully!**\n\n"
                    f"User ID: `{target_user_id}`",
                    reply_markup=UIComponents.get_admin_menu()
                )
            else:
                await message.reply_text(
                    f"❌ Failed to remove premium/pro for user {target_user_id}",
                    reply_markup=UIComponents.get_admin_menu()
                )
                
        except ValueError:
            await message.reply_text(
                "❌ Invalid user ID. Please provide a numeric user ID.",
                reply_markup=UIComponents.get_admin_menu()
            )
    
    async def handle_broadcast_command(self, client, message: Message):
        """Handle /broadcast command for admins"""
        user_id = message.from_user.id
        
        # Check admin access
        user_data = self.db.get_user(user_id)
        is_admin = (user_data and user_data.get('is_admin', False)) or user_id in Config.ADMIN_IDS
        
        if not is_admin:
            await message.reply_text("❌ Admin only command.")
            return
        
        # Parse command
        text = message.text.strip()
        broadcast_text = text.replace("/broadcast", "").strip()
        
        if not broadcast_text:
            await message.reply_text(
                "📢 **Admin Broadcast**\n\n"
                "**Usage:** `/broadcast [message]`\n\n"
                "**Example:** `/broadcast Hello everyone! New update available.`",
                reply_markup=UIComponents.get_admin_menu()
            )
            return
        
        all_users = self.db.get_all_users()
        
        status_msg = await message.reply_text(f"📢 Broadcasting to {len(all_users)} users...")
        
        success_count = 0
        fail_count = 0
        
        for user in all_users:
            try:
                await self.bot.send_message(
                    user['user_id'], 
                    f"📢 **Admin Broadcast**\n\n{broadcast_text}"
                )
                success_count += 1
            except:
                fail_count += 1
            await asyncio.sleep(0.1)  # Rate limiting
        
        await status_msg.edit_text(
            f"✅ **Broadcast Completed!**\n\n"
            f"• ✅ Successful: {success_count}\n"
            f"• ❌ Failed: {fail_count}",
            reply_markup=UIComponents.get_admin_menu()
        )

    async def handle_forward_command(self, client, message: Message):
        """Handle /forward command - FAST DIRECT FORWARDING"""
        user_id = message.from_user.id
        
        # Parse command for link
        text = message.text.strip()
        link_text = text.replace("/forward", "").strip()
        
        if not link_text:
            user_data = self.db.get_user(user_id)
            await message.reply_text(
                "⚡ **Fast Forward**\n\n"
                "Forward content directly without downloading!\n\n"
                "**Usage:** `/forward [telegram_link]`\n\n"
                "**Example:**\n"
                "`/forward https://t.me/channel/123`\n\n"
                "**Benefits:**\n"
                "• Much faster than downloading\n"
                "• No storage needed\n"
                "• Works with large files\n\n"
                "Or send a link directly after clicking the button below.",
                reply_markup=UIComponents.get_main_menu(user_data)
            )
            return
        
        # Process the forward
        await self._process_forward(client, message, link_text)
    
    async def _process_forward(self, client, message: Message, link_text: str):
        """Process forward request - FAST DIRECT FORWARDING"""
        user_id = message.from_user.id
        
        # Check access and limits (cooldown, daily quota)
        if not await self._check_access(message):
            return
        
        user_data = self.db.get_user(user_id)
        
        if user_id in self.processing_users:
            await message.reply_text("⏳ Please wait, another operation is in progress...")
            return
        
        try:
            self.processing_users.add(user_id)
            
            # Parse link
            link_data = LinkParser.parse_telegram_link(link_text)
            if not link_data:
                await message.reply_text(
                    "❌ **Invalid link format.**\n\n"
                    "**Supported formats:**\n"
                    "• `t.me/username/123`\n"
                    "• `t.me/c/123456789/2`\n"
                    "• `@username/123`",
                    reply_markup=UIComponents.get_main_menu(user_data)
                )
                return
            
            chat_id, message_id, link_type = link_data
            
            status_msg = await message.reply_text("⚡ Forwarding content...")
            
            # Create user session
            user_session = UserSession(self.auth_manager, user_id, self.bot)
            await user_session.connect()
            
            try:
                # Use copy_message for direct forward
                success = await user_session.copy_message_to_user(
                    from_chat_id=chat_id,
                    message_id=message_id,
                    to_user_id=user_id
                )
                
                if success:
                    # Update cooldown for free users
                    is_admin = user_data.get('is_admin', False) or user_id in Config.ADMIN_IDS
                    if not is_admin:
                        self.last_download_time[user_id] = time.time()
                    
                    await status_msg.edit_text(
                        "✅ **Content forwarded successfully!**\n\n"
                        "⚡ Fast forward completed instantly.",
                        reply_markup=UIComponents.get_simple_download_keyboard()
                    )
                else:
                    await status_msg.edit_text(
                        "❌ Could not forward this content.",
                        reply_markup=UIComponents.get_main_menu(user_data)
                    )
                    
            finally:
                try:
                    await user_session.disconnect()
                except:
                    pass
                    
        except Exception as e:
            await message.reply_text(
                f"❌ **Forward Failed**\n\n{str(e)}",
                reply_markup=UIComponents.get_main_menu(user_data)
            )
        finally:
            self.processing_users.discard(user_id)
    
    async def handle_forward_media_callback(self, client, callback_query):
        """Handle forward_media callback - Set state for forwarding"""
        user_id = callback_query.from_user.id
        user_data = self.db.get_user(user_id)
        
        if not self.auth_manager.is_user_authenticated(user_id):
            await callback_query.message.edit_text(
                "🔐 **Please login first!**",
                reply_markup=UIComponents.get_main_menu()
            )
            return
        
        # Set state for forwarding
        self.user_states[user_id] = {'awaiting_forward_link': True}
        
        await callback_query.message.edit_text(
            "⚡ **Fast Forward Mode**\n\n"
            "Send me a Telegram link to forward the content directly.\n\n"
            "**Supported formats:**\n"
            "• `t.me/username/123`\n"
            "• `t.me/c/123456789/2`\n"
            "• `@username/123`\n\n"
            "**Benefits:**\n"
            "• Much faster than downloading\n"
            "• No file size limits\n"
            "• Works instantly",
            reply_markup=UIComponents.get_cancel_keyboard()
        )

    def setup_handlers(self):
        """Setup message handlers"""
        # Commands
        @self.bot.on_message(filters.command("start"))
        async def start_handler(client, message):
            await self.handle_start(client, message)
        
        @self.bot.on_message(filters.command("admin"))
        async def admin_handler(client, message):
            user_id = message.from_user.id
            # Check admin access
            user_data = self.db.get_user(user_id)
            is_admin = (user_data and user_data.get('is_admin', False)) or user_id in Config.ADMIN_IDS
            
            if not is_admin:
                await message.reply_text("❌ Admin only command.")
                return
            
            await message.reply_text(
                Messages.get_admin_welcome_message(),
                reply_markup=UIComponents.get_admin_menu()
            )
        
        @self.bot.on_message(filters.command("batch"))
        async def batch_handler(client, message):
            await self.handle_batch_command(client, message)
        
        @self.bot.on_message(filters.command("addprem"))
        async def addprem_handler(client, message):
            await self.handle_addprem_command(client, message)
        
        @self.bot.on_message(filters.command("addpro"))
        async def addpro_handler(client, message):
            await self.handle_addpro_command(client, message)
        
        @self.bot.on_message(filters.command("deleteprem"))
        async def deleteprem_handler(client, message):
            await self.handle_deleteprem_command(client, message)
        
        @self.bot.on_message(filters.command("broadcast"))
        async def broadcast_handler(client, message):
            await self.handle_broadcast_command(client, message)
        
        @self.bot.on_message(filters.command("forward"))
        async def forward_handler(client, message):
            await self.handle_forward_command(client, message)
        
        # Callback queries
        self.bot.on_callback_query()(self.handle_callback_query)
        
        # Contact sharing
        self.bot.on_message(filters.contact)(self.handle_contact)
        
        # Text messages for various states
        @self.bot.on_message(filters.private & filters.text)
        async def handle_all_text(client, message: Message):
            user_id = message.from_user.id
            
            # Check for various states
            if user_id in self.user_states:
                if self.user_states[user_id].get('awaiting_code'):
                    await self.handle_verification_code(client, message)
                elif self.user_states[user_id].get('awaiting_2fa'):
                    await self.handle_2fa_password(client, message)
                elif self.user_states[user_id].get('awaiting_payment'):
                    await self.handle_payment_confirmation(client, message)
                elif self.user_states[user_id].get('awaiting_broadcast'):
                    await self.handle_admin_broadcast_message(client, message)
                elif self.user_states[user_id].get('awaiting_batch_link'):
                    # Handle batch link input
                    link = message.text.strip()
                    batch_count = self.user_states[user_id].get('batch_count', 10)
                    
                    if link:
                        user_data = self.db.get_user(user_id)
                        await self.process_batch_download(message, link, user_data, batch_count)
                    
                    if user_id in self.user_states:
                        del self.user_states[user_id]
                elif self.user_states[user_id].get('awaiting_forward_link'):
                    # Handle forward link input
                    link = message.text.strip()
                    
                    if user_id in self.user_states:
                        del self.user_states[user_id]
                    
                    if link:
                        await self._process_forward(client, message, link)
                elif self.user_states[user_id].get('awaiting_add_premium'):
                    # Handle add premium via text
                    try:
                        target_user_id = int(message.text.strip())
                        success = self.db.set_premium_status(target_user_id, "premium")
                        
                        if success:
                            # Notify target user
                            try:
                                await self.bot.send_message(
                                    target_user_id,
                                    Messages.get_premium_added_message("premium"),
                                    reply_markup=UIComponents.get_main_menu(self.db.get_user(target_user_id))
                                )
                            except:
                                pass
                            
                            await message.reply_text(
                                f"✅ Premium added for user {target_user_id}",
                                reply_markup=UIComponents.get_admin_menu()
                            )
                        else:
                            await message.reply_text(
                                f"❌ Failed to add premium for user {target_user_id}",
                                reply_markup=UIComponents.get_admin_menu()
                            )
                    except ValueError:
                        await message.reply_text("❌ Invalid user ID")
                    
                    if user_id in self.user_states:
                        del self.user_states[user_id]
                
                elif self.user_states[user_id].get('awaiting_add_pro'):
                    # Handle add pro via text
                    try:
                        target_user_id = int(message.text.strip())
                        success = self.db.set_premium_status(target_user_id, "pro")
                        
                        if success:
                            # Notify target user
                            try:
                                await self.bot.send_message(
                                    target_user_id,
                                    Messages.get_premium_added_message("pro"),
                                    reply_markup=UIComponents.get_main_menu(self.db.get_user(target_user_id))
                                )
                            except:
                                pass
                            
                            await message.reply_text(
                                f"✅ Pro added for user {target_user_id}",
                                reply_markup=UIComponents.get_admin_menu()
                            )
                        else:
                            await message.reply_text(
                                f"❌ Failed to add pro for user {target_user_id}",
                                reply_markup=UIComponents.get_admin_menu()
                            )
                    except ValueError:
                        await message.reply_text("❌ Invalid user ID")
                    
                    if user_id in self.user_states:
                        del self.user_states[user_id]
                        
                elif self.user_states[user_id].get('awaiting_remove_premium'):
                    # Handle remove premium via text
                    try:
                        target_user_id = int(message.text.strip())
                        success = self.db.set_premium_status(target_user_id, "free")
                        
                        if success:
                            await message.reply_text(
                                f"✅ Premium/Pro removed for user {target_user_id}",
                                reply_markup=UIComponents.get_admin_menu()
                            )
                        else:
                            await message.reply_text(
                                f"❌ Failed to remove premium/pro for user {target_user_id}",
                                reply_markup=UIComponents.get_admin_menu()
                            )
                    except ValueError:
                        await message.reply_text("❌ Invalid user ID")
                    
                    if user_id in self.user_states:
                        del self.user_states[user_id]
                else:
                    # Check if it's a link
                    if re.match(r'(https://t\.me/|@[a-zA-Z0-9_]+/\d+)', message.text or ''):
                        await self.handle_links(client, message)
            else:
                # Check if it's a link
                if re.match(r'(https://t\.me/|@[a-zA-Z0-9_]+/\d+)', message.text or ''):
                    await self.handle_links(client, message)

    async def start(self):
        """Start the system"""
        try:
            # Setup handlers first
            self.setup_handlers()
            
            # Start bot
            await self.bot.start()
            
            me = await self.bot.get_me()
            print(f"🤖 Bot started: @{me.username}")
            
            # Add admin users to database if not exists
            for admin_id in Config.ADMIN_IDS:
                user = self.db.get_user(admin_id)
                if not user:
                    success = self.db.add_user(admin_id, "admin", f"admin_{admin_id}.session", is_admin=True)
                    print(f"✅ Added admin user to database: {admin_id}")
                else:
                    # Ensure existing admin users have admin flag set
                    if not user.get('is_admin', False):
                        self.db.update_user_admin_status(admin_id, True)
            
            system_stats = self.db.get_system_stats()
            print(f"📊 System stats: {system_stats['total_users']} users, {system_stats['total_downloads']} downloads")
            print(f"👑 Admin users: {Config.ADMIN_IDS}")
            print("✅ Premium Downloader Bot ready!")
            
            # Keep running
            await asyncio.Event().wait()
            
        except Exception as e:
            print(f"❌ Failed to start: {e}")
            await self.shutdown()
    
    async def shutdown(self):
        """Clean shutdown"""
        print("👋 Shutting down...")
        await self.bot.stop()
        sys.exit(0)

async def main():
    downloader = TelegramDownloader()
    try:
        await downloader.start()
    except KeyboardInterrupt:
        await downloader.shutdown()

if __name__ == "__main__":
    # Create directories
    os.makedirs("sessions", exist_ok=True)
    os.makedirs("downloads", exist_ok=True)
    
    asyncio.run(main())