import psycopg2
import psycopg2.extras
import os
import time
from datetime import datetime, timedelta
import threading
from dotenv import load_dotenv

load_dotenv()

class DatabaseManager:
    def __init__(self):
        self.db_url = os.getenv("DATABASE_URL")
        if not self.db_url:
            raise ValueError("DATABASE_URL environment variable not set")
        
        self.lock = threading.Lock()
        self.init_database()
    
    def get_connection(self):
        """Get a database connection"""
        try:
            conn = psycopg2.connect(self.db_url)
            return conn
        except Exception as e:
            print(f"❌ Database connection failed: {e}")
            raise
    
    def init_database(self):
        """Initialize database with required tables"""
        try:
            with self.lock:
                conn = self.get_connection()
                cursor = conn.cursor()
                
                # Users table with premium fields
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        user_id BIGINT PRIMARY KEY,
                        phone_number TEXT,
                        session_file TEXT,
                        is_active BOOLEAN DEFAULT true,
                        is_admin BOOLEAN DEFAULT false,
                        is_premium BOOLEAN DEFAULT false,
                        is_pro BOOLEAN DEFAULT false,
                        download_count INTEGER DEFAULT 0,
                        daily_reset TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        channels_verified BOOLEAN DEFAULT false,
                        last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        subscription_expiry TIMESTAMP
                    )
                ''')
                
                # Download stats table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS download_stats (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT REFERENCES users(user_id),
                        file_name TEXT,
                        file_size BIGINT,
                        downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Premium payments table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS premium_payments (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT REFERENCES users(user_id),
                        payment_method TEXT,
                        amount REAL,
                        transaction_id TEXT,
                        status TEXT DEFAULT 'pending',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        verified_at TIMESTAMP
                    )
                ''')
                
                conn.commit()
                conn.close()
                print(f"✅ PostgreSQL Database initialized!")
                
        except Exception as e:
            print(f"❌ Database initialization failed: {e}")
            raise
    
    def add_user(self, user_id, phone_number, session_file, is_admin=False):
        """Add a new user to database - FIXED: Preserve daily_reset for existing users"""
        try:
            with self.lock:
                conn = self.get_connection()
                cursor = conn.cursor()
                
                # Check if user already exists
                cursor.execute('SELECT user_id FROM users WHERE user_id = %s', (user_id,))
                user_exists = cursor.fetchone()
                
                if user_exists:
                    # User exists - UPDATE without resetting daily_reset
                    cursor.execute('''
                        UPDATE users SET 
                        phone_number = %s,
                        session_file = %s,
                        is_admin = %s,
                        last_used = %s
                        WHERE user_id = %s
                    ''', (phone_number, session_file, is_admin, datetime.now(), user_id))
                    print(f"✅ Updated user session: {user_id} (daily limit preserved)")
                else:
                    # New user - INSERT with initial daily_reset
                    cursor.execute('''
                        INSERT INTO users 
                        (user_id, phone_number, session_file, is_admin, last_used, daily_reset)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    ''', (user_id, phone_number, session_file, is_admin, datetime.now(), datetime.now()))
                    print(f"✅ Added new user to database: {user_id} (Admin: {is_admin})")
                
                conn.commit()
                conn.close()
                return True
                
        except Exception as e:
            print(f"❌ Failed to add user {user_id}: {e}")
            return False
    
    def get_user(self, user_id):
        """Get user by ID - with daily reset check AND subscription check"""
        try:
            with self.lock:
                conn = self.get_connection()
                cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
                
                cursor.execute('''
                    SELECT * FROM users WHERE user_id = %s
                ''', (user_id,))
                
                user = cursor.fetchone()
                
                if user:
                    # Check if daily reset is needed (more than 24 hours since last reset)
                    last_reset = user['daily_reset']
                    current_time = datetime.now()
                    
                    if (current_time - last_reset) > timedelta(hours=24):
                        # Reset daily download count
                        cursor.execute('''
                            UPDATE users SET download_count = 0, daily_reset = %s 
                            WHERE user_id = %s
                        ''', (current_time, user_id))
                        conn.commit()
                        print(f"🔄 Reset daily download count for user {user_id}")
                    
                    # Check if subscription has expired
                    if user['subscription_expiry']:
                        expiry_date = user['subscription_expiry']
                        if current_time > expiry_date:
                            # Subscription expired, downgrade to free
                            cursor.execute('''
                                UPDATE users SET is_premium = false, is_pro = false, subscription_expiry = NULL 
                                WHERE user_id = %s
                            ''', (user_id,))
                            conn.commit()
                            print(f"⚠️ Subscription expired for user {user_id}, downgraded to free")
                
                # Update last used time
                cursor.execute('''
                    UPDATE users SET last_used = %s WHERE user_id = %s
                ''', (datetime.now(), user_id))
                
                conn.commit()
                conn.close()
                
                if user:
                    return dict(user)
                return None
                
        except Exception as e:
            print(f"❌ Failed to get user {user_id}: {e}")
            return None
    
    def update_user_session(self, user_id, session_file):
        """Update user's session file"""
        try:
            with self.lock:
                conn = self.get_connection()
                cursor = conn.cursor()
                
                cursor.execute('''
                    UPDATE users SET session_file = %s, last_used = %s 
                    WHERE user_id = %s
                ''', (session_file, datetime.now(), user_id))
                
                conn.commit()
                conn.close()
                return True
                
        except Exception as e:
            print(f"❌ Failed to update user session {user_id}: {e}")
            return False
    
    def increment_download_count(self, user_id):
        """Increment user's download count"""
        try:
            with self.lock:
                conn = self.get_connection()
                cursor = conn.cursor()
                
                cursor.execute('''
                    UPDATE users SET download_count = download_count + 1, last_used = %s
                    WHERE user_id = %s
                ''', (datetime.now(), user_id))
                
                conn.commit()
                conn.close()
                return True
                
        except Exception as e:
            print(f"❌ Failed to increment download count for user {user_id}: {e}")
            return False
    
    def set_premium_status(self, user_id, premium_type):
        """Set user premium status (premium or pro)"""
        try:
            with self.lock:
                conn = self.get_connection()
                cursor = conn.cursor()
                
                # Calculate subscription expiry (30 days from now)
                expiry_date = datetime.now() + timedelta(days=30)
                
                if premium_type == "premium":
                    cursor.execute('''
                        UPDATE users SET is_premium = true, is_pro = false, subscription_expiry = %s WHERE user_id = %s
                    ''', (expiry_date, user_id))
                elif premium_type == "pro":
                    cursor.execute('''
                        UPDATE users SET is_premium = true, is_pro = true, subscription_expiry = %s WHERE user_id = %s
                    ''', (expiry_date, user_id))
                else:
                    cursor.execute('''
                        UPDATE users SET is_premium = false, is_pro = false, subscription_expiry = NULL WHERE user_id = %s
                    ''', (user_id,))
                
                conn.commit()
                conn.close()
                return True
                
        except Exception as e:
            print(f"❌ Failed to set premium status for user {user_id}: {e}")
            return False
    
    def set_channels_verified(self, user_id, verified=True):
        """Set channel verification status"""
        try:
            with self.lock:
                conn = self.get_connection()
                cursor = conn.cursor()
                
                cursor.execute('''
                    UPDATE users SET channels_verified = %s WHERE user_id = %s
                ''', (verified, user_id))
                
                conn.commit()
                conn.close()
                return True
                
        except Exception as e:
            print(f"❌ Failed to set channel verification for user {user_id}: {e}")
            return False
    
    def add_payment(self, user_id, payment_method, amount, transaction_id):
        """Add payment record"""
        try:
            with self.lock:
                conn = self.get_connection()
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT INTO premium_payments (user_id, payment_method, amount, transaction_id)
                    VALUES (%s, %s, %s, %s)
                ''', (user_id, payment_method, amount, transaction_id))
                
                conn.commit()
                conn.close()
                return True
                
        except Exception as e:
            print(f"❌ Failed to add payment for user {user_id}: {e}")
            return False
    
    def get_pending_payments(self):
        """Get all pending payments"""
        try:
            with self.lock:
                conn = self.get_connection()
                cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
                
                cursor.execute('''
                    SELECT * FROM premium_payments WHERE status = 'pending'
                ''')
                
                payments = [dict(p) for p in cursor.fetchall()]
                conn.close()
                return payments
                
        except Exception as e:
            print(f"❌ Failed to get pending payments: {e}")
            return []
    
    def verify_payment(self, payment_id, premium_type):
        """Verify a payment and upgrade user"""
        try:
            with self.lock:
                conn = self.get_connection()
                cursor = conn.cursor()
                
                # Get payment info
                cursor.execute('SELECT user_id FROM premium_payments WHERE id = %s', (payment_id,))
                payment = cursor.fetchone()
                
                if not payment:
                    return False
                
                user_id = payment[0]
                
                # Update payment status
                cursor.execute('''
                    UPDATE premium_payments SET status = 'verified', verified_at = %s
                    WHERE id = %s
                ''', (datetime.now(), payment_id))
                
                # Upgrade user with subscription expiry
                self.set_premium_status(user_id, premium_type)
                
                conn.commit()
                conn.close()
                return True
                
        except Exception as e:
            print(f"❌ Failed to verify payment {payment_id}: {e}")
            return False
    
    def add_download_stat(self, user_id, file_name, file_size):
        """Add download statistics"""
        try:
            with self.lock:
                conn = self.get_connection()
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT INTO download_stats (user_id, file_name, file_size)
                    VALUES (%s, %s, %s)
                ''', (user_id, file_name, file_size))
                
                conn.commit()
                conn.close()
                return True
                
        except Exception as e:
            print(f"❌ Failed to add download stat for user {user_id}: {e}")
            return False
    
    def get_all_users(self):
        """Get all users"""
        try:
            with self.lock:
                conn = self.get_connection()
                cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
                
                cursor.execute('''
                    SELECT * FROM users ORDER BY created_at DESC
                ''')
                
                users = [dict(u) for u in cursor.fetchall()]
                conn.close()
                return users
                
        except Exception as e:
            print(f"❌ Failed to get all users: {e}")
            return []
    
    def get_user_stats(self, user_id):
        """Get user download statistics"""
        try:
            with self.lock:
                conn = self.get_connection()
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT COUNT(*), SUM(file_size) FROM download_stats 
                    WHERE user_id = %s
                ''', (user_id,))
                
                result = cursor.fetchone()
                conn.close()
                
                return {
                    'total_downloads': result[0] or 0,
                    'total_size': result[1] or 0
                }
                
        except Exception as e:
            print(f"❌ Failed to get user stats {user_id}: {e}")
            return {'total_downloads': 0, 'total_size': 0}
    
    def get_system_stats(self):
        """Get system-wide statistics"""
        try:
            with self.lock:
                conn = self.get_connection()
                cursor = conn.cursor()
                
                # Total users
                cursor.execute('SELECT COUNT(*) FROM users')
                total_users = cursor.fetchone()[0]
                
                # Active users (used in last 30 days)
                thirty_days_ago = datetime.now() - timedelta(days=30)
                cursor.execute('SELECT COUNT(*) FROM users WHERE last_used > %s', (thirty_days_ago,))
                active_users = cursor.fetchone()[0]
                
                # Premium users
                cursor.execute('SELECT COUNT(*) FROM users WHERE is_premium = true')
                premium_users = cursor.fetchone()[0]
                
                # Pro users
                cursor.execute('SELECT COUNT(*) FROM users WHERE is_pro = true')
                pro_users = cursor.fetchone()[0]
                
                # Admin users
                cursor.execute('SELECT COUNT(*) FROM users WHERE is_admin = true')
                admin_users = cursor.fetchone()[0]
                
                # Total downloads
                cursor.execute('SELECT COUNT(*) FROM download_stats')
                total_downloads = cursor.fetchone()[0]
                
                # Total size
                cursor.execute('SELECT SUM(file_size) FROM download_stats')
                total_size = cursor.fetchone()[0] or 0
                
                # Pending payments
                cursor.execute('SELECT COUNT(*) FROM premium_payments WHERE status = %s', ('pending',))
                pending_payments = cursor.fetchone()[0]
                
                conn.close()
                
                return {
                    'total_users': total_users,
                    'active_users': active_users,
                    'premium_users': premium_users,
                    'pro_users': pro_users,
                    'admin_users': admin_users,
                    'total_downloads': total_downloads,
                    'total_size': total_size,
                    'pending_payments': pending_payments
                }
                
        except Exception as e:
            print(f"❌ Failed to get system stats: {e}")
            return {
                'total_users': 0,
                'active_users': 0,
                'premium_users': 0,
                'pro_users': 0,
                'admin_users': 0,
                'total_downloads': 0,
                'total_size': 0,
                'pending_payments': 0
            }
    
    def reset_daily_limits(self):
        """Reset daily download limits for all users"""
        try:
            with self.lock:
                conn = self.get_connection()
                cursor = conn.cursor()
                
                cursor.execute('''
                    UPDATE users SET download_count = 0, daily_reset = %s
                ''', (datetime.now(),))
                
                conn.commit()
                conn.close()
                print("✅ Reset daily download limits for all users")
                return True
                
        except Exception as e:
            print(f"❌ Failed to reset daily limits: {e}")
            return False
    
    def delete_user(self, user_id):
        """Delete user and all associated data"""
        try:
            with self.lock:
                conn = self.get_connection()
                cursor = conn.cursor()
                
                # Delete user's download stats
                cursor.execute('DELETE FROM download_stats WHERE user_id = %s', (user_id,))
                
                # Delete user's payments
                cursor.execute('DELETE FROM premium_payments WHERE user_id = %s', (user_id,))
                
                # Delete user
                cursor.execute('DELETE FROM users WHERE user_id = %s', (user_id,))
                
                conn.commit()
                conn.close()
                print(f"✅ Deleted user and all associated data: {user_id}")
                return True
                
        except Exception as e:
            print(f"❌ Failed to delete user {user_id}: {e}")
            return False
    
    def get_user_download_history(self, user_id, limit=10):
        """Get user's download history"""
        try:
            with self.lock:
                conn = self.get_connection()
                cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
                
                cursor.execute('''
                    SELECT file_name, file_size, downloaded_at 
                    FROM download_stats 
                    WHERE user_id = %s 
                    ORDER BY downloaded_at DESC 
                    LIMIT %s
                ''', (user_id, limit))
                
                history = [dict(h) for h in cursor.fetchall()]
                conn.close()
                return history
                
        except Exception as e:
            print(f"❌ Failed to get download history for user {user_id}: {e}")
            return []
    
    def get_recent_payments(self, limit=10):
        """Get recent payments (all statuses)"""
        try:
            with self.lock:
                conn = self.get_connection()
                cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
                
                cursor.execute('''
                    SELECT * FROM premium_payments 
                    ORDER BY created_at DESC 
                    LIMIT %s
                ''', (limit,))
                
                payments = [dict(p) for p in cursor.fetchall()]
                conn.close()
                return payments
                
        except Exception as e:
            print(f"❌ Failed to get recent payments: {e}")
            return []
    
    def update_user_admin_status(self, user_id, is_admin):
        """Update user admin status"""
        try:
            with self.lock:
                conn = self.get_connection()
                cursor = conn.cursor()
                
                cursor.execute('''
                    UPDATE users SET is_admin = %s WHERE user_id = %s
                ''', (is_admin, user_id))
                
                conn.commit()
                conn.close()
                print(f"✅ Updated admin status for user {user_id}: {is_admin}")
                return True
                
        except Exception as e:
            print(f"❌ Failed to update admin status for user {user_id}: {e}")
            return False
    
    def get_top_downloaders(self, limit=10):
        """Get top downloaders"""
        try:
            with self.lock:
                conn = self.get_connection()
                cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
                
                cursor.execute('''
                    SELECT u.user_id, u.phone_number, COUNT(ds.id) as download_count, SUM(ds.file_size) as total_size
                    FROM users u
                    LEFT JOIN download_stats ds ON u.user_id = ds.user_id
                    GROUP BY u.user_id, u.phone_number
                    ORDER BY download_count DESC
                    LIMIT %s
                ''', (limit,))
                
                downloaders = [dict(d) for d in cursor.fetchall()]
                conn.close()
                return downloaders
                
        except Exception as e:
            print(f"❌ Failed to get top downloaders: {e}")
            return []
