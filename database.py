from math import ceil
import sqlite3
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
import time
import threading

load_dotenv()
DB_PATH = 'data/subscriptions.db'
TRIAL_DAYS = int(os.getenv('TRIAL_DAYS', 5))

# Синхронизация для предотвращения `database is locked`
db_lock = threading.Lock()

def get_db_connection():
    """Создает соединение с базой данных с таймаутом и повторными попытками."""
    for attempt in range(5):
        try:
            conn = sqlite3.connect(DB_PATH, timeout=20)
            conn.execute("PRAGMA busy_timeout = 20000")  # Увеличенный таймаут
            conn.execute("PRAGMA journal_mode = WAL")  # Включаем WAL для конкурентного доступа
            return conn
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e):
                time.sleep(2 ** attempt)  # Экспоненциальная задержка
            else:
                raise e
    raise sqlite3.OperationalError("Database is locked after multiple attempts")

def init_db():
    try:
        os.makedirs('data', exist_ok=True)
        with db_lock:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                active BOOLEAN DEFAULT 1,
                subscription_end TIMESTAMP,
                trial_used BOOLEAN DEFAULT 0
            )''')
            
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS payments (
                payment_id TEXT PRIMARY KEY,
                user_id INTEGER,
                amount REAL,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'pending',
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )''')
            
            conn.commit()
            conn.close()
    except Exception as e:
        print(f"Error initializing database: {e}")

def add_user(user_id: int, username: str = None):
    try:
        with db_lock:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('''
            INSERT OR IGNORE INTO users (user_id, username, join_date, active, trial_used)
            VALUES (?, ?, datetime('now'), 1, 0)
            ''', (user_id, username))
            conn.commit()
            conn.close()
    except Exception as e:
        print(f"Error adding user {user_id}: {e}")

def check_user_access(user_id: int) -> bool:
    try:
        with db_lock:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('''
            SELECT subscription_end, trial_used, join_date, active FROM users 
            WHERE user_id = ?
            ''', (user_id,))
            result = cursor.fetchone()
            
            if result:
                subscription_end, trial_used, join_date, active = result
                if active:
                    if subscription_end and datetime.strptime(subscription_end, '%Y-%m-%d %H:%M:%S') > datetime.now():
                        conn.close()
                        return True
                    elif not trial_used:
                        trial_end = datetime.strptime(join_date, '%Y-%m-%d %H:%M:%S') + timedelta(days=TRIAL_DAYS)
                        if trial_end > datetime.now():
                            conn.close()
                            return True
            conn.close()
            return False
    except Exception as e:
        print(f"Error checking access for user {user_id}: {e}")
        return False

def update_subscription(user_id: int, payment_id: str, amount: float):
    try:
        with db_lock:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
            SELECT subscription_end, trial_used, join_date FROM users WHERE user_id = ?
            ''', (user_id,))
            result = cursor.fetchone()
            
            # Определяем новую дату окончания подписки
            if result:
                subscription_end, trial_used, join_date = result
                if subscription_end and datetime.strptime(subscription_end, '%Y-%m-%d %H:%M:%S') > datetime.now():
                    # Если есть активная подписка, добавляем 30 дней к текущей дате окончания
                    end_date = datetime.strptime(subscription_end, '%Y-%m-%d %H:%M:%S') + timedelta(days=30)
                elif not trial_used:
                    # Если есть пробный период, добавляем его оставшиеся дни + 30 дней
                    trial_end = datetime.strptime(join_date, '%Y-%m-%d %H:%M:%S') + timedelta(days=TRIAL_DAYS)
                    remaining_days = max(0, ceil((trial_end - datetime.now()).total_seconds() / (24 * 3600)))
                    end_date = datetime.now() + timedelta(days=30 + remaining_days)
                else:
                    # Если нет активной подписки, устанавливаем 30 дней с текущей даты
                    end_date = datetime.now() + timedelta(days=30)
            else:
                # Новый пользователь без подписки
                end_date = datetime.now() + timedelta(days=30)
            
            cursor.execute('''
            UPDATE users
            SET active = 1, subscription_end = ?, trial_used = 1
            WHERE user_id = ?
            ''', (end_date.strftime('%Y-%m-%d %H:%M:%S'), user_id))
            
            cursor.execute('''
            INSERT INTO payments (payment_id, user_id, amount, status)
            VALUES (?, ?, ?, 'succeeded')
            ON CONFLICT(payment_id) DO UPDATE SET status = 'succeeded'
            ''', (payment_id, user_id, amount))
            
            conn.commit()
            conn.close()
            print(f"Updated subscription for user {user_id} to {end_date}")
    except Exception as e:
        print(f"Error updating subscription for user {user_id}: {e}")
        raise e

if __name__ == "__main__":
    init_db()