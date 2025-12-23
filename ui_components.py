from pyrogram.types import (
    InlineKeyboardMarkup, 
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton
)

from config import Config  # ADDED IMPORT

class UIComponents:
    @staticmethod
    def get_main_menu(user_data=None):
        """Main menu with user status"""
        if not user_data:
            return InlineKeyboardMarkup([
                [InlineKeyboardButton("🔐 Login", callback_data="login")],
                [InlineKeyboardButton("ℹ️ Help", callback_data="help"),
                 InlineKeyboardButton("💎 Premium", callback_data="premium_info")],
                [InlineKeyboardButton("📊 Stats", callback_data="stats"),
                 InlineKeyboardButton("📢 Support", url=Config.SUPPORT_CHANNEL)]
            ])
        
        buttons = []
        
        # Check if user is admin
        is_admin = user_data.get('is_admin', False)
        
        if is_admin:
            buttons.append([InlineKeyboardButton("👑 Admin Panel", callback_data="admin_menu")])
        
        # Add download and forward buttons
        buttons.append([
            InlineKeyboardButton("📥 Download", callback_data="download_media"),
            InlineKeyboardButton("⚡ Forward", callback_data="forward_media")
        ])
        
        # Add batch download for premium users or admins
        if user_data.get('is_premium', False) or user_data.get('is_pro', False) or is_admin:
            buttons.append([InlineKeyboardButton("📦 Batch Download", callback_data="batch_download")])
        
        # Add premium button if not premium
        if not user_data.get('is_premium', False) and not is_admin:
            buttons.append([InlineKeyboardButton("💎 Upgrade to Premium", callback_data="premium_info")])
        
        # Add other buttons
        buttons.extend([
            [InlineKeyboardButton("📊 My Stats", callback_data="stats"),
             InlineKeyboardButton("ℹ️ Help", callback_data="help")],
            [InlineKeyboardButton("📢 Support", url=Config.SUPPORT_CHANNEL)],
            [InlineKeyboardButton("🔐 Logout", callback_data="logout")]
        ])
        
        return InlineKeyboardMarkup(buttons)
    
    @staticmethod
    def get_login_keyboard():
        """Login keyboard with phone sharing"""
        return ReplyKeyboardMarkup([
            [KeyboardButton("📱 Share My Number", request_contact=True)],
            [KeyboardButton("❌ Cancel")]
        ], resize_keyboard=True, one_time_keyboard=True)
    
    @staticmethod
    def get_premium_plans_keyboard():
        """Premium plans selection - REMOVED ALL PAYMENTS BUTTON"""
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("💎 Premium - $5/month", callback_data="premium_plan")],
            [InlineKeyboardButton("🚀 Pro - $15/month", callback_data="pro_plan")],
            [InlineKeyboardButton("📊 Compare Plans", callback_data="compare_plans")],
            [InlineKeyboardButton("📢 Support", url=Config.SUPPORT_CHANNEL)],
            [InlineKeyboardButton("🔙 Back to Main", callback_data="main_menu")]
        ])
    
    @staticmethod
    def get_payment_methods_keyboard(plan_type):
        """Payment methods for premium - REMOVED ALL PAYMENTS BUTTON"""
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📱 MTN Mobile Money", callback_data=f"pay_mtn_{plan_type}")],
            [InlineKeyboardButton("📱 Vodafone Cash", callback_data=f"pay_vodafone_{plan_type}")],
            [InlineKeyboardButton("₿ Bitcoin", callback_data=f"pay_bitcoin_{plan_type}")],
            [InlineKeyboardButton("💎 USDT", callback_data=f"pay_usdt_{plan_type}")],
            [InlineKeyboardButton("🌍 Selar (International)", callback_data=f"pay_selar_{plan_type}")],
            [InlineKeyboardButton("📢 Support", url=Config.SUPPORT_CHANNEL)],
            [InlineKeyboardButton("🔙 Back to Plans", callback_data="premium_info")]
        ])
    
    @staticmethod
    def get_all_payments_keyboard():
        """Back to plans from all payments view - REMOVED THIS FUNCTIONALITY"""
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("💎 Choose Plan", callback_data="premium_info")],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]
        ])
    
    @staticmethod
    def get_admin_menu():
        """Admin menu"""
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 System Stats", callback_data="admin_stats")],
            [InlineKeyboardButton("💎 Premium Management", callback_data="admin_premium")],
            [InlineKeyboardButton("📢 Broadcast Message", callback_data="admin_broadcast")],
            [InlineKeyboardButton("📢 Support Channel", url=Config.SUPPORT_CHANNEL)],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]
        ])
    
    @staticmethod
    def get_premium_management_keyboard():
        """Premium management for admins"""
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Pending Payments", callback_data="admin_pending_payments")],
            [InlineKeyboardButton("➕ Add Premium User", callback_data="admin_add_premium")],
            [InlineKeyboardButton("➕ Add Pro User", callback_data="admin_add_pro")],
            [InlineKeyboardButton("➖ Remove Premium/Pro", callback_data="admin_remove_premium")],
            [InlineKeyboardButton("📢 Support", url=Config.SUPPORT_CHANNEL)],
            [InlineKeyboardButton("🔙 Admin Menu", callback_data="admin_menu")]
        ])
    
    @staticmethod
    def get_payment_verification_keyboard(payment_id):
        """Payment verification buttons for admins"""
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Verify Premium", callback_data=f"verify_payment_{payment_id}_premium"),
                InlineKeyboardButton("🚀 Verify Pro", callback_data=f"verify_payment_{payment_id}_pro")
            ],
            [InlineKeyboardButton("❌ Reject Payment", callback_data=f"reject_payment_{payment_id}")],
            [InlineKeyboardButton("📢 Support", url=Config.SUPPORT_CHANNEL)],
            [InlineKeyboardButton("🔙 Back to Payments", callback_data="admin_pending_payments")]
        ])
    
    @staticmethod
    def get_cancel_keyboard():
        """Cancel button"""
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="main_menu")]
        ])
    
    @staticmethod
    def get_back_keyboard(target="main_menu"):
        """Back button"""
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data=target)]
        ])
    
    @staticmethod
    def get_batch_download_keyboard():
        """Batch download options"""
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 Download 10 Recent", callback_data="batch_10")],
            [InlineKeyboardButton("📥 Download 20 Recent", callback_data="batch_20")],
            [InlineKeyboardButton("📥 Download 30 Recent", callback_data="batch_30")],
            [InlineKeyboardButton("📢 Support", url=Config.SUPPORT_CHANNEL)],
            [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
        ])
    
    @staticmethod
    def get_contact_admin_keyboard():
        """Contact admin buttons"""
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📞 Contact Admin", url="https://t.me/admin")],
            [InlineKeyboardButton("🆘 Support Group", url=Config.SUPPORT_CHANNEL)],
            [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
        ])
    
    @staticmethod
    def get_simple_download_keyboard():
        """Simple download button for after completion"""
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 Download", callback_data="download_media"),
             InlineKeyboardButton("⚡ Forward", callback_data="forward_media")],
            [InlineKeyboardButton("📊 My Stats", callback_data="stats"),
             InlineKeyboardButton("📢 Support", url=Config.SUPPORT_CHANNEL)],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]
        ])
    
    @staticmethod
    def get_stats_keyboard():
        """Stats menu buttons"""
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 Download Media", callback_data="download_media")],
            [InlineKeyboardButton("📢 Support", url=Config.SUPPORT_CHANNEL)],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]
        ])

class Messages:
    @staticmethod
    def get_welcome_message():
        return """
🤖 **Welcome to Premium Downloader Bot!**

✨ **Features:**
• Download from private channels
• High-speed downloads  
• Multiple file formats
• Premium benefits available

📥 **Free Tier:** 5 downloads/day
💎 **Premium:** 50 downloads/day  
🚀 **Pro:** 200 downloads/day

Click **🔐 Login** to get started!
        """
    
    @staticmethod
    def get_premium_info_message():
        return """
💎 **Premium Plans**

**Free Tier:**
• 5 downloads per day
• Files up to 500MB
• Basic support
• 20-second cooldown

**💎 Premium Plan - $5/month**
• 50 downloads per day  
• Files up to 2GB
• Priority support
• Batch downloads
• No cooldown

**🚀 Pro Plan - $15/month**  
• 200 downloads per day
• Files up to 5GB
• VIP support
• All premium features
• Custom requests

Choose a plan to continue:
        """
    
    @staticmethod
    def get_all_payment_methods_message():
        """All payment methods in one message - UPDATED TO REDIRECT"""
        return """
💰 **Payment Methods**

Please choose your preferred payment method from the previous menu.

If you need assistance with payments, please contact @official_kango directly.

**Available Methods:**
• 📱 MTN Mobile Money
• 📱 Vodafone Cash  
• ₿ Bitcoin
• 💎 USDT
• 🌍 Selar (International)

Contact @official_kango for any payment issues.
        """
    
    @staticmethod
    def get_payment_instructions(method, plan_type, payment_info):
        plan_name = "Premium" if plan_type == "premium" else "Pro"
        amount = "$5" if plan_type == "premium" else "$15"
        downloads = "50" if plan_type == "premium" else "200"
        size = "2GB" if plan_type == "premium" else "5GB"
        
        instructions = f"""
💳 **Payment Instructions - {plan_name} Plan**

**Plan:** {plan_name}
**Amount:** {amount}
**Downloads:** {downloads} per day
**File Size:** Up to {size}

**Payment Method:** {method.upper()}
        """
        
        if method == "mtn":
            instructions += f"""
📱 **MTN Mobile Money:**
Send {amount} to:
`{payment_info}`

**Reference:** Your User ID

**After payment:**
1. Take a screenshot
2. Contact @official_kango with your screenshot
3. Wait for verification (1-6 hours)
            """
        elif method == "vodafone":
            instructions += f"""
📱 **Vodafone Cash:**
Send {amount} to:
`{payment_info}`

**Reference:** Your User ID

**After payment:**
1. Take a screenshot
2. Contact @official_kango with your screenshot
3. Wait for verification (1-6 hours)
            """
        elif method == "bitcoin":
            instructions += f"""
₿ **Bitcoin:**
Send {amount} worth of BTC to:
`{payment_info}`

**Memo:** Include your User ID

**After payment:**
1. Take a screenshot of transaction
2. Contact @official_kango with your screenshot
3. Wait for verification (1-6 hours)
            """
        elif method == "usdt":
            instructions += f"""
💎 **USDT (TRC20):**
Send {amount} worth of USDT to:
`{payment_info}`

**Memo:** Include your User ID

**After payment:**
1. Take a screenshot of transaction
2. Contact @official_kango with your screenshot
3. Wait for verification (1-6 hours)
            """
        elif method == "selar":
            instructions += f"""
🌍 **International Payments:**
Pay via Selar: {payment_info}

**Note:** Selar payments are automated and usually verified within minutes.

**After payment:**
1. Take a screenshot
2. Contact @official_kango with your screenshot
3. Wait for verification
            """
        
        instructions += f"""

**Contact Admin:** @official_kango
**Verification Time:** 1-6 hours

Thank you for your purchase!
        """
        
        return instructions
    
    @staticmethod
    def get_download_limits_message(user_data):
        max_downloads = 5
        max_size = "500MB"
        user_type = "🆓 Free User"
        cooldown = "20 seconds"
        
        if user_data.get('is_admin', False) or user_data['user_id'] in Config.ADMIN_IDS:
            max_downloads = "Unlimited"
            max_size = "Unlimited"
            user_type = "👑 Admin User"
            cooldown = "None"
        elif user_data.get('is_pro', False):
            max_downloads = 200
            max_size = "5GB"
            user_type = "🚀 Pro User"
            cooldown = "None"
        elif user_data.get('is_premium', False):
            max_downloads = 50
            max_size = "2GB" 
            user_type = "💎 Premium User"
            cooldown = "None"
        
        used = user_data.get('download_count', 0)
        
        if max_downloads == "Unlimited":
            remaining = "Unlimited"
        else:
            remaining = max(0, max_downloads - used)
        
        return f"""
📊 **Your Download Limits**

**Account Type:** {user_type}
**Downloads Today:** {used}/{max_downloads}
**Remaining Today:** {remaining}
**Max File Size:** {max_size}
**Cooldown:** {cooldown}

{'💎 **Upgrade to Premium for more benefits!**' if user_type == "🆓 Free User" else '✅ **You have premium benefits!**'}
        """
    
    @staticmethod
    def get_help_message():
        return """
ℹ️ **Help Center**

**How to Use:**
1. Click **🔐 Login** and share your phone number
2. Click **📥 Download** or **⚡ Forward**
3. Send any Telegram link

**Download vs Forward:**
• **📥 Download** - Downloads file to server, then sends to you
• **⚡ Forward** - Copies content directly (faster, no size limits)

**Supported Links:**
• `t.me/username/123` - Public channels
• `t.me/c/123456789/2` - Private channels  
• `@username/123` - Short format

**Commands:**
• `/start` - Start the bot
• `/forward` - Fast forward content
• `/batch` - Batch download (Premium/Pro only)
• `/addprem` - Add premium user (Admin only)
• `/addpro` - Add pro user (Admin only)
• `/deleteprem` - Remove premium/pro (Admin only)
• `/broadcast` - Broadcast message (Admin only)

**Need Help?**
Join our support channel for updates and assistance.
        """
    
    @staticmethod
    def get_admin_welcome_message():
        return """
👑 **Admin Panel**

**Available Commands:**
• `/addprem [user_id]` - Add premium user
• `/addpro [user_id]` - Add pro user
• `/deleteprem [user_id]` - Remove premium/pro
• `/broadcast [message]` - Broadcast to all users
• `/batch [link]` - Batch download (for testing)

**Quick Actions:**
        """
    
    @staticmethod
    def get_batch_instructions():
        return """
📦 **Batch Download**

**Usage:** `/batch [telegram_link]`

**Examples:**
• `/batch https://t.me/channel/123`
• `/batch @channel 123`

**Features:**
• Downloads multiple recent posts
• Available for Premium/Pro users only
• Maintains original quality
• Automatic file organization

**Note:** This may take several minutes depending on the number of files.
        """
    
    @staticmethod
    def get_premium_added_message(plan_type="premium"):
        plan_name = "Premium" if plan_type == "premium" else "Pro"
        downloads = "50" if plan_type == "premium" else "200"
        size = "2GB" if plan_type == "premium" else "5GB"
        
        return f"""
🎉 **Congratulations!**

✅ **You've been upgraded to {plan_name}!**

**Your new benefits:**
• {downloads} downloads per day
• Files up to {size}
• Batch downloads
• No cooldown
• Priority support

**Thank you for choosing our service!**

Start downloading with your new {plan_name.lower()} benefits!
        """
    
    @staticmethod
    def get_login_instructions():
        return """
🔐 **Login Process**

To use this bot, you need to login with your Telegram account. This allows the bot to access channels you're a member of and download content on your behalf.

**Your privacy is protected:**
• We don't store your messages
• Only you can access your account
• Your session is stored securely

Click **📱 Share My Number** below to start the login process.
        """