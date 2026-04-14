#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
بوت توفل المتكامل - النسخة النهائية مع نظام المساعدة بين المستخدمين
تم إضافة: اختبار مستوى إلزامي عند أول دخول (مبتدئ/متوسط/متقدم) مع أسئلة من الكلمات الخاصة بكل مستوى
تم التعديل: دعم قاعدة البيانات القديمة عبر إضافة عمود initial_test_done ديناميكياً
"""

import telebot
from telebot.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
    CallbackQuery, Message, PollAnswer
)
from gtts import gTTS
import os
import time
import sqlite3
import random
from datetime import datetime, timedelta
import threading
import schedule
import logging
from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass, field
import json
import sys
import csv
from io import StringIO
import re

# ================== إعدادات التسجيل ==================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ================== متغيرات البيئة والإعدادات ==================
TOKEN = "8733112337:AAGLcvft_GpLtnwRE0LnufQnS4io4L4nJOA"  # استبدل بتوكنك
if not TOKEN:
    logger.error("❌ لم يتم تعيين التوكن!")
    sys.exit(1)

OWNER_ID = 8536981262  # معرف المالك الرئيسي (صاحب البوت)

# ================== قوائم الكلمات للاختبار الإلزامي (يمكنك ملؤها لاحقًا) ==================
# كل قائمة تتسع لـ 480 كلمة من المستوى المحدد
LEVEL_TEST_WORDS_BEGINNER = []      # هنا ضع كلمات المستوى المبتدئ (480 كلمة)
LEVEL_TEST_WORDS_INTERMEDIATE = []  # هنا ضع كلمات المستوى المتوسط (480 كلمة)
LEVEL_TEST_WORDS_ADVANCED = []      # هنا ضع كلمات المستوى المتقدم (480 كلمة)

# ================== قفل لمزامنة القواميس المشتركة ==================
state_lock = threading.Lock()

# ================== تعريفات البيانات (Dataclasses) ==================
@dataclass
class Word:
    eng: str
    ar: str
    example: str
    level: str  # مبتدئ، متوسط، متقدم
    
    def to_dict(self):
        return {"eng": self.eng, "ar": self.ar, "example": self.example, "level": self.level}

@dataclass
class QuizState:
    user_id: int
    day: int
    session: str
    words: List[Word]
    types: List[str]
    current: int = 0
    score: int = 0
    total: int = 0
    poll_ids: List[str] = field(default_factory=list)
    answers: List[Dict] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.now)

@dataclass
class LevelTestState:
    user_id: int
    words: List[Word]
    types: List[str]
    current: int = 0
    score: int = 0
    total: int = 10
    poll_ids: List[str] = field(default_factory=list)
    answers: List[Dict] = field(default_factory=list)
    percent: int = 50

@dataclass
class InfiniteQuizState:
    user_id: int
    words: List[Word]
    types: List[str]
    current: int = 0
    score: int = 0
    poll_ids: List[str] = field(default_factory=list)
    answers: List[Dict] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.now)

@dataclass
class BroadcastState:
    admin_id: int
    type: str  # 'all', 'one', 'group', 'scheduled'
    target: Optional[int] = None
    message: Optional[str] = None
    group_message: Optional[str] = None
    group_sender: Optional[int] = None
    scheduled_time: Optional[datetime] = None

@dataclass
class AdminPermissions:
    can_manage_admins: bool = False
    can_manage_users: bool = False
    can_manage_content: bool = False
    can_broadcast: bool = False
    can_view_stats: bool = False
    can_manage_settings: bool = False
    can_view_logs: bool = False

# ================== قاعدة البيانات المحسنة ==================
class Database:
    """إدارة قاعدة البيانات بشكل آمن مع أقفال"""
    
    def __init__(self, db_path='toefl_master.db'):
        self.db_path = db_path
        self.lock = threading.Lock()
        self._init_db()
    
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _init_db(self):
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            
            # الجداول الأساسية
            c.execute('''CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                name TEXT,
                current_day INTEGER DEFAULT 1,
                join_date TEXT,
                level INTEGER DEFAULT 0,
                level_tested INTEGER DEFAULT 0,
                reminders_enabled INTEGER DEFAULT 1,
                last_active TEXT
            )''')
            
            # التحقق من وجود عمود initial_test_done وإضافته إذا لم يكن موجوداً
            c.execute("PRAGMA table_info(users)")
            columns = [col[1] for col in c.fetchall()]
            if 'initial_test_done' not in columns:
                c.execute("ALTER TABLE users ADD COLUMN initial_test_done INTEGER DEFAULT 0")
                logger.info("✅ تمت إضافة عمود initial_test_done إلى جدول users")
            
            c.execute('''CREATE TABLE IF NOT EXISTS progress (
                user_id INTEGER,
                day INTEGER,
                session TEXT,
                completed INTEGER DEFAULT 0,
                completed_at TIMESTAMP,
                PRIMARY KEY (user_id, day, session)
            )''')
            
            c.execute('''CREATE TABLE IF NOT EXISTS favorites (
                user_id INTEGER,
                word TEXT,
                meaning TEXT,
                example TEXT,
                level TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, word)
            )''')
            
            c.execute('''CREATE TABLE IF NOT EXISTS daily_results (
                user_id INTEGER,
                day INTEGER,
                session TEXT,
                score INTEGER,
                total INTEGER,
                date TEXT,
                details TEXT,
                PRIMARY KEY (user_id, day, session, date)
            )''')
            
            c.execute('''CREATE TABLE IF NOT EXISTS quiz_details (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                day INTEGER,
                session TEXT,
                question_number INTEGER,
                word TEXT,
                user_answer TEXT,
                correct_answer TEXT,
                is_correct INTEGER,
                taken_at TIMESTAMP
            )''')
            
            # جداول المساعدة الجديدة
            c.execute('''CREATE TABLE IF NOT EXISTS help_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                question TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP,
                approved_at TIMESTAMP,
                approved_by INTEGER
            )''')
            
            c.execute('''CREATE TABLE IF NOT EXISTS help_responses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id INTEGER,
                responder_id INTEGER,
                response_text TEXT,
                created_at TIMESTAMP
            )''')
            
            c.execute('''CREATE TABLE IF NOT EXISTS chat_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_user INTEGER,
                to_user INTEGER,
                message TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP,
                responded_at TIMESTAMP,
                response_message TEXT
            )''')
            
            c.execute('''CREATE TABLE IF NOT EXISTS active_chats (
                user1 INTEGER,
                user2 INTEGER,
                started_at TIMESTAMP,
                last_message TIMESTAMP,
                PRIMARY KEY (user1, user2)
            )''')
            
            c.execute('''CREATE TABLE IF NOT EXISTS banned_users (
                user_id INTEGER PRIMARY KEY,
                banned_by INTEGER,
                banned_at TIMESTAMP,
                reason TEXT
            )''')
            
            c.execute('''CREATE TABLE IF NOT EXISTS user_levels (
                user_id INTEGER PRIMARY KEY,
                level INTEGER DEFAULT 1,
                xp INTEGER DEFAULT 0,
                total_xp INTEGER DEFAULT 0,
                last_reminder TIMESTAMP,
                streak INTEGER DEFAULT 0,
                longest_streak INTEGER DEFAULT 0
            )''')
            
            c.execute('''CREATE TABLE IF NOT EXISTS broadcasts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER,
                message TEXT,
                type TEXT,
                sent_at TIMESTAMP,
                recipients_count INTEGER,
                failed_count INTEGER
            )''')
            
            c.execute('''CREATE TABLE IF NOT EXISTS level_test_results (
                user_id INTEGER,
                test_date TIMESTAMP,
                score INTEGER,
                total INTEGER,
                percentage INTEGER,
                details TEXT,
                PRIMARY KEY (user_id, test_date)
            )''')
            
            c.execute('''CREATE TABLE IF NOT EXISTS daily_activity (
                user_id INTEGER,
                date TEXT,
                sessions_completed INTEGER DEFAULT 0,
                quiz_score INTEGER DEFAULT 0,
                xp_gained INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, date)
            )''')
            
            c.execute('''CREATE TABLE IF NOT EXISTS infinite_quiz_stats (
                user_id INTEGER PRIMARY KEY,
                total_questions INTEGER DEFAULT 0,
                correct_answers INTEGER DEFAULT 0,
                last_played TIMESTAMP
            )''')
            
            c.execute('''CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT
            )''')
            
            c.execute('''CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                permissions TEXT DEFAULT '{}'
            )''')
            
            c.execute('''CREATE TABLE IF NOT EXISTS banned_words (
                word TEXT PRIMARY KEY,
                added_by INTEGER,
                added_at TIMESTAMP
            )''')
            
            c.execute('''CREATE TABLE IF NOT EXISTS auto_replies (
                keyword TEXT PRIMARY KEY,
                response TEXT,
                added_by INTEGER,
                added_at TIMESTAMP
            )''')
            
            c.execute('''CREATE TABLE IF NOT EXISTS user_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reporter_id INTEGER,
                reported_id INTEGER,
                reason TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP,
                resolved_by INTEGER,
                resolved_at TIMESTAMP
            )''')
            
            c.execute('''CREATE TABLE IF NOT EXISTS spam_warnings (
                user_id INTEGER PRIMARY KEY,
                warning_count INTEGER DEFAULT 0,
                last_warning TIMESTAMP,
                muted_until TIMESTAMP
            )''')
            
            c.execute('''CREATE TABLE IF NOT EXISTS admin_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER,
                action TEXT,
                details TEXT,
                timestamp TIMESTAMP
            )''')
            
            c.execute('''CREATE TABLE IF NOT EXISTS scheduled_broadcasts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER,
                message TEXT,
                scheduled_time TIMESTAMP,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP
            )''')
            
            c.execute('''CREATE TABLE IF NOT EXISTS custom_words (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                eng TEXT,
                ar TEXT,
                example TEXT,
                level TEXT,
                added_by INTEGER,
                added_at TIMESTAMP
            )''')
            
            c.execute('''CREATE TABLE IF NOT EXISTS maintenance_mode (
                enabled INTEGER DEFAULT 0
            )''')
            
            c.execute("INSERT OR IGNORE INTO maintenance_mode (enabled) VALUES (0)")
            
            conn.commit()
            conn.close()
            logger.info("✅ قاعدة البيانات مهيأة بنجاح")
    
    # ================== دوال المساعدة الجديدة ==================
    def add_help_request(self, user_id: int, question: str) -> int:
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute('''INSERT INTO help_requests (user_id, question, created_at)
                         VALUES (?,?,?)''', (user_id, question, datetime.now().isoformat()))
            conn.commit()
            rid = c.lastrowid
            conn.close()
            return rid
    
    def get_pending_help_requests(self) -> List[Dict]:
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute("SELECT * FROM help_requests WHERE status='pending' ORDER BY created_at")
            rows = c.fetchall()
            conn.close()
            return [dict(row) for row in rows]
    
    def approve_help_request(self, request_id: int, admin_id: int):
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute('''UPDATE help_requests SET status='approved', approved_at=?, approved_by=?
                         WHERE id=?''', (datetime.now().isoformat(), admin_id, request_id))
            conn.commit()
            conn.close()
    
    def reject_help_request(self, request_id: int):
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute("UPDATE help_requests SET status='rejected' WHERE id=?", (request_id,))
            conn.commit()
            conn.close()
    
    def get_help_request(self, request_id: int) -> Optional[Dict]:
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute("SELECT * FROM help_requests WHERE id=?", (request_id,))
            row = c.fetchone()
            conn.close()
            return dict(row) if row else None
    
    def add_help_response(self, request_id: int, responder_id: int, response: str):
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute('''INSERT INTO help_responses (request_id, responder_id, response_text, created_at)
                         VALUES (?,?,?,?)''', (request_id, responder_id, response, datetime.now().isoformat()))
            conn.commit()
            conn.close()
    
    # ================== دوال المستخدمين ==================
    def get_user(self, user_id: int) -> Optional[Dict]:
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
            row = c.fetchone()
            conn.close()
            return dict(row) if row else None
    
    def add_user(self, user_id: int, username: str, name: str):
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            now = datetime.now().isoformat()
            
            # التأكد من وجود العمود initial_test_done (للمستخدمين القدامى)
            c.execute("PRAGMA table_info(users)")
            columns = [col[1] for col in c.fetchall()]
            if 'initial_test_done' not in columns:
                c.execute("ALTER TABLE users ADD COLUMN initial_test_done INTEGER DEFAULT 0")
                conn.commit()
            
            c.execute('''INSERT OR IGNORE INTO users 
                         (user_id, username, name, join_date, last_active, initial_test_done) 
                         VALUES (?,?,?,?,?,0)''',
                      (user_id, username, name, now, now))
            conn.commit()
            conn.close()
    
    def update_user_activity(self, user_id: int):
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute("UPDATE users SET last_active=? WHERE user_id=?", 
                      (datetime.now().isoformat(), user_id))
            conn.commit()
            conn.close()
    
    def get_user_day(self, user_id: int) -> int:
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute("SELECT current_day FROM users WHERE user_id=?", (user_id,))
            row = c.fetchone()
            conn.close()
            return row['current_day'] if row else 1
    
    def update_user_day(self, user_id: int, day: int):
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute("UPDATE users SET current_day=? WHERE user_id=?", (day, user_id))
            conn.commit()
            conn.close()
    
    def reset_user_progress(self, user_id: int):
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute("UPDATE users SET current_day=1 WHERE user_id=?", (user_id,))
            c.execute("DELETE FROM progress WHERE user_id=?", (user_id,))
            c.execute("DELETE FROM daily_results WHERE user_id=?", (user_id,))
            c.execute("DELETE FROM quiz_details WHERE user_id=?", (user_id,))
            c.execute("DELETE FROM user_levels WHERE user_id=?", (user_id,))
            c.execute("DELETE FROM infinite_quiz_stats WHERE user_id=?", (user_id,))
            conn.commit()
            conn.close()
    
    def mark_session_completed(self, user_id: int, day: int, session: str):
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute('''INSERT OR REPLACE INTO progress 
                         (user_id, day, session, completed, completed_at) 
                         VALUES (?,?,?,1,?)''',
                      (user_id, day, session, datetime.now().isoformat()))
            conn.commit()
            conn.close()
    
    def get_completed_sessions(self, user_id: int, day: int) -> List[str]:
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute('''SELECT session FROM progress 
                         WHERE user_id=? AND day=? AND completed=1''', 
                      (user_id, day))
            rows = c.fetchall()
            conn.close()
            return [row['session'] for row in rows]
    
    def get_completed_days(self, user_id: int) -> List[int]:
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute('''SELECT day, COUNT(*) as cnt FROM progress 
                         WHERE user_id=? AND completed=1 
                         GROUP BY day HAVING cnt>=4''', (user_id,))
            rows = c.fetchall()
            conn.close()
            return [row['day'] for row in rows]
    
    def get_total_completed_sessions(self, user_id: int) -> int:
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM progress WHERE user_id=? AND completed=1", (user_id,))
            row = c.fetchone()
            conn.close()
            return row[0] if row else 0
    
    def add_favorite(self, user_id: int, word: Word):
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute('''INSERT OR IGNORE INTO favorites 
                         (user_id, word, meaning, example, level) 
                         VALUES (?,?,?,?,?)''',
                      (user_id, word.eng, word.ar, word.example, word.level))
            conn.commit()
            conn.close()
    
    def remove_favorite(self, user_id: int, word: str):
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute("DELETE FROM favorites WHERE user_id=? AND word=?", (user_id, word))
            conn.commit()
            conn.close()
    
    def get_favorites(self, user_id: int) -> List[Dict]:
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute("SELECT word, meaning, example, level FROM favorites WHERE user_id=? ORDER BY word", (user_id,))
            rows = c.fetchall()
            conn.close()
            return [dict(row) for row in rows]
    
    def add_xp(self, user_id: int, xp_amount: int) -> Tuple[int, int, bool]:
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute("INSERT OR IGNORE INTO user_levels (user_id, level, xp, total_xp) VALUES (?, 1, 0, 0)", (user_id,))
            c.execute("SELECT level, xp, total_xp FROM user_levels WHERE user_id=?", (user_id,))
            row = c.fetchone()
            current_level = row['level']
            current_xp = row['xp']
            total_xp = row['total_xp'] + xp_amount
            
            new_xp = current_xp + xp_amount
            new_level = current_level
            leveled_up = False
            
            while new_xp >= new_level * 100:
                new_xp -= new_level * 100
                new_level += 1
                leveled_up = True
            
            c.execute("UPDATE user_levels SET level=?, xp=?, total_xp=? WHERE user_id=?", 
                      (new_level, new_xp, total_xp, user_id))
            conn.commit()
            conn.close()
            
            return new_level, total_xp, leveled_up
    
    def get_level_info(self, user_id: int) -> Dict:
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute("SELECT level, xp, total_xp, streak, longest_streak FROM user_levels WHERE user_id=?", (user_id,))
            row = c.fetchone()
            conn.close()
            if row:
                return {
                    'level': row['level'],
                    'xp': row['xp'],
                    'total_xp': row['total_xp'],
                    'streak': row['streak'],
                    'longest_streak': row['longest_streak'],
                    'next_level_xp': row['level'] * 100
                }
            return {'level': 1, 'xp': 0, 'total_xp': 0, 'streak': 0, 'longest_streak': 0, 'next_level_xp': 100}
    
    def update_streak(self, user_id: int) -> Dict:
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            today = datetime.now().date().isoformat()
            c.execute("SELECT date FROM daily_activity WHERE user_id=? AND date=?", (user_id, today))
            if c.fetchone():
                conn.close()
                return self.get_level_info(user_id)
            
            yesterday = (datetime.now().date() - timedelta(days=1)).isoformat()
            c.execute("SELECT date FROM daily_activity WHERE user_id=? AND date=?", (user_id, yesterday))
            has_yesterday = c.fetchone() is not None
            
            c.execute("INSERT OR IGNORE INTO user_levels (user_id, level, xp, total_xp, streak, longest_streak) VALUES (?, 1, 0, 0, 0, 0)", (user_id,))
            c.execute("SELECT streak, longest_streak FROM user_levels WHERE user_id=?", (user_id,))
            row = c.fetchone()
            current_streak = row['streak']
            longest_streak = row['longest_streak']
            
            if has_yesterday:
                new_streak = current_streak + 1
            else:
                new_streak = 1
            
            new_longest = max(longest_streak, new_streak)
            
            c.execute("UPDATE user_levels SET streak=?, longest_streak=? WHERE user_id=?", 
                      (new_streak, new_longest, user_id))
            conn.commit()
            conn.close()
            return {'streak': new_streak, 'longest_streak': new_longest}
    
    def is_banned(self, user_id: int) -> bool:
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute("SELECT 1 FROM banned_users WHERE user_id=?", (user_id,))
            result = c.fetchone() is not None
            conn.close()
            return result
    
    def ban_user(self, user_id: int, admin_id: int, reason: str = ""):
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute('''INSERT OR REPLACE INTO banned_users 
                         (user_id, banned_by, banned_at, reason) 
                         VALUES (?,?,?,?)''',
                      (user_id, admin_id, datetime.now().isoformat(), reason))
            conn.commit()
            conn.close()
    
    def unban_user(self, user_id: int):
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute("DELETE FROM banned_users WHERE user_id=?", (user_id,))
            conn.commit()
            conn.close()
    
    def get_banned_users(self) -> List[Dict]:
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute("SELECT * FROM banned_users ORDER BY banned_at DESC")
            rows = c.fetchall()
            conn.close()
            return [dict(row) for row in rows]
    
    def create_chat_request(self, from_user: int, to_user: int, message: str) -> int:
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute('''INSERT INTO chat_requests 
                         (from_user, to_user, message, created_at) 
                         VALUES (?,?,?,?)''',
                      (from_user, to_user, message, datetime.now().isoformat()))
            conn.commit()
            request_id = c.lastrowid
            conn.close()
            return request_id
    
    def get_pending_requests(self) -> List[Dict]:
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute("SELECT * FROM chat_requests WHERE status='pending' ORDER BY created_at")
            rows = c.fetchall()
            conn.close()
            return [dict(row) for row in rows]
    
    def update_request_status(self, request_id: int, status: str, response: str = ""):
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute('''UPDATE chat_requests 
                         SET status=?, responded_at=?, response_message=? 
                         WHERE id=?''',
                      (status, datetime.now().isoformat(), response, request_id))
            conn.commit()
            conn.close()
    
    def start_chat(self, user1: int, user2: int):
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            now = datetime.now().isoformat()
            c.execute('''INSERT OR REPLACE INTO active_chats 
                         (user1, user2, started_at, last_message) 
                         VALUES (?,?,?,?)''',
                      (min(user1, user2), max(user1, user2), now, now))
            conn.commit()
            conn.close()
    
    def get_chat_partner(self, user_id: int) -> Optional[int]:
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute('''SELECT user1, user2 FROM active_chats 
                         WHERE user1=? OR user2=?''', (user_id, user_id))
            row = c.fetchone()
            conn.close()
            if row:
                return row['user2'] if row['user1'] == user_id else row['user1']
            return None
    
    def end_chat(self, user1: int, user2: int):
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute('''DELETE FROM active_chats 
                         WHERE (user1=? AND user2=?) OR (user1=? AND user2=?)''',
                      (user1, user2, user2, user1))
            conn.commit()
            conn.close()
    
    def get_leaderboard(self, limit: int = 10) -> List[Dict]:
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute('''SELECT u.user_id, u.name, ul.level, ul.total_xp, ul.streak
                         FROM users u 
                         JOIN user_levels ul ON u.user_id = ul.user_id 
                         ORDER BY ul.level DESC, ul.total_xp DESC 
                         LIMIT ?''', (limit,))
            rows = c.fetchall()
            conn.close()
            return [dict(row) for row in rows]
    
    def save_quiz_result(self, user_id: int, day: int, session: str, score: int, total: int, details: List[Dict]):
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            date = datetime.now().date().isoformat()
            
            c.execute('''INSERT INTO daily_results 
                         (user_id, day, session, score, total, date, details) 
                         VALUES (?,?,?,?,?,?,?)''',
                      (user_id, day, session, score, total, date, json.dumps(details, ensure_ascii=False)))
            
            for ans in details:
                c.execute('''INSERT INTO quiz_details 
                             (user_id, day, session, question_number, word, user_answer, correct_answer, is_correct, taken_at) 
                             VALUES (?,?,?,?,?,?,?,?,?)''',
                          (user_id, day, session, ans['question_number'], ans['word'], 
                           ans['user_answer'], ans['correct_answer'], ans['is_correct'], datetime.now().isoformat()))
            
            today = datetime.now().date().isoformat()
            c.execute('''INSERT INTO daily_activity (user_id, date, sessions_completed, quiz_score, xp_gained) 
                         VALUES (?,?,1,?,0) 
                         ON CONFLICT(user_id, date) DO UPDATE SET 
                         sessions_completed = sessions_completed + 1,
                         quiz_score = quiz_score + ?''',
                      (user_id, today, score, score))
            
            conn.commit()
            conn.close()
    
    def get_user_stats(self, user_id: int) -> Dict:
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            stats = {}
            c.execute("SELECT COUNT(*) FROM progress WHERE user_id=? AND completed=1", (user_id,))
            stats['total_sessions'] = c.fetchone()[0]
            c.execute("SELECT AVG(score*1.0/total) FROM daily_results WHERE user_id=?", (user_id,))
            avg_row = c.fetchone()
            avg = avg_row[0] if avg_row else None
            stats['avg_score'] = round(avg * 100, 2) if avg is not None else 0
            c.execute("SELECT COUNT(*) FROM favorites WHERE user_id=?", (user_id,))
            stats['favorites_count'] = c.fetchone()[0]
            c.execute("SELECT last_active FROM users WHERE user_id=?", (user_id,))
            row = c.fetchone()
            stats['last_active'] = row['last_active'] if row else None
            conn.close()
            return stats
    
    def get_all_users(self) -> List[int]:
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute("SELECT user_id FROM users")
            rows = c.fetchall()
            conn.close()
            return [row['user_id'] for row in rows]
    
    def get_all_users_with_details(self, page: int = 0, page_size: int = 10) -> Tuple[List[Dict], int]:
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM users")
            total = c.fetchone()[0]
            
            offset = page * page_size
            c.execute('''SELECT u.user_id, u.username, u.name, u.join_date, u.last_active,
                                ul.level, ul.total_xp, ul.streak,
                                (SELECT COUNT(*) FROM progress WHERE user_id=u.user_id AND completed=1) as sessions
                         FROM users u
                         LEFT JOIN user_levels ul ON u.user_id = ul.user_id
                         ORDER BY u.join_date DESC
                         LIMIT ? OFFSET ?''', (page_size, offset))
            rows = c.fetchall()
            conn.close()
            return [dict(row) for row in rows], total
    
    def save_broadcast(self, admin_id: int, message: str, type: str, recipients: int, failed: int):
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute('''INSERT INTO broadcasts 
                         (admin_id, message, type, sent_at, recipients_count, failed_count) 
                         VALUES (?,?,?,?,?,?)''',
                      (admin_id, message, type, datetime.now().isoformat(), recipients, failed))
            conn.commit()
            conn.close()
    
    def update_infinite_stats(self, user_id: int, correct: int, total: int):
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute('''INSERT INTO infinite_quiz_stats (user_id, total_questions, correct_answers, last_played)
                         VALUES (?, ?, ?, ?)
                         ON CONFLICT(user_id) DO UPDATE SET
                         total_questions = total_questions + ?,
                         correct_answers = correct_answers + ?,
                         last_played = ?''',
                      (user_id, total, correct, datetime.now().isoformat(), total, correct, datetime.now().isoformat()))
            conn.commit()
            conn.close()
    
    def get_infinite_stats(self, user_id: int) -> Dict:
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute("SELECT total_questions, correct_answers, last_played FROM infinite_quiz_stats WHERE user_id=?", (user_id,))
            row = c.fetchone()
            conn.close()
            if row:
                return dict(row)
            return {'total_questions': 0, 'correct_answers': 0, 'last_played': None}
    
    def set_config(self, key: str, value: str):
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, value))
            conn.commit()
            conn.close()
    
    def get_config(self, key: str) -> Optional[str]:
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute("SELECT value FROM config WHERE key=?", (key,))
            row = c.fetchone()
            conn.close()
            return row['value'] if row else None
    
    def add_admin(self, user_id: int, permissions: Dict = None) -> bool:
        if permissions is None:
            permissions = {}
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            try:
                c.execute("INSERT OR IGNORE INTO admins (user_id, permissions) VALUES (?, ?)",
                          (user_id, json.dumps(permissions)))
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"فشل إضافة أدمن: {e}")
                return False
            finally:
                conn.close()
    
    def remove_admin(self, user_id: int):
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute("DELETE FROM admins WHERE user_id=?", (user_id,))
            conn.commit()
            conn.close()
    
    def get_admins(self) -> List[int]:
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute("SELECT user_id FROM admins")
            rows = c.fetchall()
            conn.close()
            return [row['user_id'] for row in rows]
    
    def get_admin_permissions(self, user_id: int) -> Dict:
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute("SELECT permissions FROM admins WHERE user_id=?", (user_id,))
            row = c.fetchone()
            conn.close()
            if row:
                return json.loads(row['permissions'])
            return {}
    
    def update_admin_permissions(self, user_id: int, permissions: Dict):
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute("UPDATE admins SET permissions=? WHERE user_id=?", (json.dumps(permissions), user_id))
            conn.commit()
            conn.close()
    
    def is_admin(self, user_id: int) -> bool:
        return user_id in self.get_admins() or user_id == OWNER_ID
    
    def add_banned_word(self, word: str, admin_id: int):
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute("INSERT OR IGNORE INTO banned_words (word, added_by, added_at) VALUES (?,?,?)",
                      (word.lower(), admin_id, datetime.now().isoformat()))
            conn.commit()
            conn.close()
    
    def remove_banned_word(self, word: str):
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute("DELETE FROM banned_words WHERE word=?", (word.lower(),))
            conn.commit()
            conn.close()
    
    def get_banned_words(self) -> List[str]:
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute("SELECT word FROM banned_words")
            rows = c.fetchall()
            conn.close()
            return [row['word'] for row in rows]
    
    def contains_banned_word(self, text: str) -> bool:
        words = self.get_banned_words()
        text_lower = text.lower()
        for word in words:
            if word in text_lower:
                return True
        return False
    
    def add_auto_reply(self, keyword: str, response: str, admin_id: int):
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO auto_replies (keyword, response, added_by, added_at) VALUES (?,?,?,?)",
                      (keyword.lower(), response, admin_id, datetime.now().isoformat()))
            conn.commit()
            conn.close()
    
    def remove_auto_reply(self, keyword: str):
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute("DELETE FROM auto_replies WHERE keyword=?", (keyword.lower(),))
            conn.commit()
            conn.close()
    
    def get_auto_reply(self, text: str) -> Optional[str]:
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute("SELECT response FROM auto_replies WHERE keyword=?", (text.lower(),))
            row = c.fetchone()
            conn.close()
            return row['response'] if row else None
    
    def get_all_auto_replies(self) -> List[Dict]:
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute("SELECT keyword, response FROM auto_replies ORDER BY keyword")
            rows = c.fetchall()
            conn.close()
            return [dict(row) for row in rows]
    
    def create_report(self, reporter_id: int, reported_id: int, reason: str) -> int:
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute('''INSERT INTO user_reports 
                         (reporter_id, reported_id, reason, created_at) 
                         VALUES (?,?,?,?)''',
                      (reporter_id, reported_id, reason, datetime.now().isoformat()))
            conn.commit()
            report_id = c.lastrowid
            conn.close()
            return report_id
    
    def get_pending_reports(self) -> List[Dict]:
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute("SELECT * FROM user_reports WHERE status='pending' ORDER BY created_at")
            rows = c.fetchall()
            conn.close()
            return [dict(row) for row in rows]
    
    def resolve_report(self, report_id: int, admin_id: int, resolution: str = "resolved"):
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute('''UPDATE user_reports 
                         SET status=?, resolved_by=?, resolved_at=? 
                         WHERE id=?''',
                      (resolution, admin_id, datetime.now().isoformat(), report_id))
            conn.commit()
            conn.close()
    
    def add_spam_warning(self, user_id: int) -> int:
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            now = datetime.now().isoformat()
            c.execute('''INSERT INTO spam_warnings (user_id, warning_count, last_warning) 
                         VALUES (?, 1, ?)
                         ON CONFLICT(user_id) DO UPDATE SET
                         warning_count = warning_count + 1,
                         last_warning = ?''',
                      (user_id, now, now))
            conn.commit()
            c.execute("SELECT warning_count FROM spam_warnings WHERE user_id=?", (user_id,))
            row = c.fetchone()
            conn.close()
            return row['warning_count'] if row else 1
    
    def mute_user(self, user_id: int, duration_minutes: int = 60):
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            muted_until = (datetime.now() + timedelta(minutes=duration_minutes)).isoformat()
            c.execute('''INSERT INTO spam_warnings (user_id, muted_until) 
                         VALUES (?, ?)
                         ON CONFLICT(user_id) DO UPDATE SET
                         muted_until = ?''',
                      (user_id, muted_until, muted_until))
            conn.commit()
            conn.close()
    
    def is_muted(self, user_id: int) -> Tuple[bool, Optional[datetime]]:
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute("SELECT muted_until FROM spam_warnings WHERE user_id=?", (user_id,))
            row = c.fetchone()
            conn.close()
            if row and row['muted_until']:
                try:
                    muted_until = datetime.fromisoformat(row['muted_until'])
                    if datetime.now() < muted_until:
                        return True, muted_until
                except:
                    pass
            return False, None
    
    def log_admin_action(self, admin_id: int, action: str, details: str = ""):
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute('''INSERT INTO admin_logs (admin_id, action, details, timestamp) 
                         VALUES (?,?,?,?)''',
                      (admin_id, action, details, datetime.now().isoformat()))
            conn.commit()
            conn.close()
    
    def get_admin_logs(self, limit: int = 50) -> List[Dict]:
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute('''SELECT * FROM admin_logs 
                         ORDER BY timestamp DESC 
                         LIMIT ?''', (limit,))
            rows = c.fetchall()
            conn.close()
            return [dict(row) for row in rows]
    
    def schedule_broadcast(self, admin_id: int, message: str, scheduled_time: datetime):
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute('''INSERT INTO scheduled_broadcasts 
                         (admin_id, message, scheduled_time, created_at) 
                         VALUES (?,?,?,?)''',
                      (admin_id, message, scheduled_time.isoformat(), datetime.now().isoformat()))
            conn.commit()
            conn.close()
    
    def get_pending_scheduled_broadcasts(self) -> List[Dict]:
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            now = datetime.now().isoformat()
            c.execute('''SELECT * FROM scheduled_broadcasts 
                         WHERE status='pending' AND scheduled_time <= ?''', (now,))
            rows = c.fetchall()
            conn.close()
            return [dict(row) for row in rows]
    
    def mark_broadcast_sent(self, broadcast_id: int):
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute("UPDATE scheduled_broadcasts SET status='sent' WHERE id=?", (broadcast_id,))
            conn.commit()
            conn.close()
    
    def add_custom_word(self, eng: str, ar: str, example: str, level: str, admin_id: int) -> int:
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute('''INSERT INTO custom_words (eng, ar, example, level, added_by, added_at)
                         VALUES (?,?,?,?,?,?)''',
                      (eng, ar, example, level, admin_id, datetime.now().isoformat()))
            conn.commit()
            word_id = c.lastrowid
            conn.close()
            return word_id
    
    def get_custom_words(self) -> List[Dict]:
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute("SELECT * FROM custom_words ORDER BY added_at DESC")
            rows = c.fetchall()
            conn.close()
            return [dict(row) for row in rows]
    
    def delete_custom_word(self, word_id: int):
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute("DELETE FROM custom_words WHERE id=?", (word_id,))
            conn.commit()
            conn.close()
    
    def clear_custom_words(self):
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute("DELETE FROM custom_words")
            conn.commit()
            conn.close()
    
    def get_maintenance_mode(self) -> bool:
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute("SELECT enabled FROM maintenance_mode")
            row = c.fetchone()
            conn.close()
            return row[0] == 1 if row else False
    
    def set_maintenance_mode(self, enabled: bool):
        with self.lock:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute("UPDATE maintenance_mode SET enabled=?", (1 if enabled else 0,))
            conn.commit()
            conn.close()

# ================== تهيئة قاعدة البيانات ==================
db = Database()

# ================== بيانات الكلمات (480 كلمة - 30 يوم) ==================
vocab: Dict[int, Dict[str, List[Word]]] = {}

def load_vocab():
    global vocab
    
    # اليوم 1
    vocab[1] = {
        "morning": [
            Word("book", "كتاب", "I read a book every night.", "مبتدئ"),
            Word("door", "باب", "Please close the door.", "مبتدئ"),
            Word("chair", "كرسي", "The chair is comfortable.", "مبتدئ"),
            Word("table", "طاولة", "Put the book on the table.", "مبتدئ")
        ],
        "noon": [
            Word("house", "منزل", "My house is big.", "مبتدئ"),
            Word("car", "سيارة", "He drives a red car.", "مبتدئ"),
            Word("water", "ماء", "I drink water.", "مبتدئ"),
            Word("food", "طعام", "The food is delicious.", "مبتدئ")
        ],
        "afternoon": [
            Word("big", "كبير", "A big house.", "مبتدئ"),
            Word("small", "صغير", "A small cat.", "مبتدئ"),
            Word("hot", "حار", "The weather is hot.", "مبتدئ"),
            Word("cold", "بارد", "Cold water.", "مبتدئ")
        ],
        "night": [
            Word("run", "يجري", "He runs fast.", "مبتدئ"),
            Word("walk", "يمشي", "I walk to school.", "مبتدئ"),
            Word("eat", "يأكل", "We eat dinner.", "مبتدئ"),
            Word("sleep", "ينام", "She sleeps early.", "مبتدئ")
        ]
    }
    
    # اليوم 2
    vocab[2] = {
        "morning": [
            Word("red", "أحمر", "Red apple.", "مبتدئ"),
            Word("blue", "أزرق", "Blue sky.", "مبتدئ"),
            Word("green", "أخضر", "Green grass.", "مبتدئ"),
            Word("yellow", "أصفر", "Yellow sun.", "مبتدئ")
        ],
        "noon": [
            Word("father", "أب", "My father is kind.", "مبتدئ"),
            Word("mother", "أم", "My mother cooks.", "مبتدئ"),
            Word("brother", "أخ", "I have a brother.", "مبتدئ"),
            Word("sister", "أخت", "My sister is young.", "مبتدئ")
        ],
        "afternoon": [
            Word("one", "واحد", "One apple.", "مبتدئ"),
            Word("two", "اثنان", "Two cats.", "مبتدئ"),
            Word("three", "ثلاثة", "Three books.", "مبتدئ"),
            Word("four", "أربعة", "Four chairs.", "مبتدئ")
        ],
        "night": [
            Word("hello", "مرحبا", "Hello, how are you?", "مبتدئ"),
            Word("goodbye", "وداعا", "Goodbye, see you later.", "مبتدئ"),
            Word("please", "من فضلك", "Please help me.", "مبتدئ"),
            Word("thank", "شكرا", "Thank you very much.", "مبتدئ")
        ]
    }
    
    # اليوم 3
    vocab[3] = {
        "morning": [
            Word("happy", "سعيد", "I am happy today.", "مبتدئ"),
            Word("sad", "حزين", "She feels sad.", "مبتدئ"),
            Word("angry", "غاضب", "He is angry.", "مبتدئ"),
            Word("tired", "متعب", "I am tired.", "مبتدئ")
        ],
        "noon": [
            Word("teacher", "معلم", "The teacher explains.", "مبتدئ"),
            Word("student", "طالب", "The student studies.", "مبتدئ"),
            Word("school", "مدرسة", "I go to school.", "مبتدئ"),
            Word("class", "فصل", "The class is big.", "مبتدئ")
        ],
        "afternoon": [
            Word("write", "يكتب", "Write your name.", "مبتدئ"),
            Word("read", "يقرأ", "Read the book.", "مبتدئ"),
            Word("speak", "يتحدث", "Speak English.", "مبتدئ"),
            Word("listen", "يستمع", "Listen to music.", "مبتدئ")
        ],
        "night": [
            Word("morning", "صباح", "Good morning!", "مبتدئ"),
            Word("afternoon", "بعد الظهر", "Good afternoon.", "مبتدئ"),
            Word("evening", "مساء", "Good evening.", "مبتدئ"),
            Word("night", "ليل", "Good night.", "مبتدئ")
        ]
    }
    
    # اليوم 4
    vocab[4] = {
        "morning": [
            Word("pen", "قلم", "I write with a pen.", "مبتدئ"),
            Word("pencil", "قلم رصاص", "Draw with a pencil.", "مبتدئ"),
            Word("paper", "ورق", "A piece of paper.", "مبتدئ"),
            Word("desk", "مكتب", "The teacher's desk.", "مبتدئ")
        ],
        "noon": [
            Word("dog", "كلب", "The dog barks.", "مبتدئ"),
            Word("cat", "قطة", "The cat sleeps.", "مبتدئ"),
            Word("bird", "طائر", "The bird flies.", "مبتدئ"),
            Word("fish", "سمكة", "Fish swim.", "مبتدئ")
        ],
        "afternoon": [
            Word("apple", "تفاح", "An apple a day.", "مبتدئ"),
            Word("banana", "موز", "Yellow banana.", "مبتدئ"),
            Word("orange", "برتقال", "Orange juice.", "مبتدئ"),
            Word("grape", "عنب", "Sweet grapes.", "مبتدئ")
        ],
        "night": [
            Word("milk", "حليب", "Drink milk.", "مبتدئ"),
            Word("bread", "خبز", "Fresh bread.", "مبتدئ"),
            Word("cheese", "جبن", "Cheese sandwich.", "مبتدئ"),
            Word("egg", "بيضة", "Fried egg.", "مبتدئ")
        ]
    }
    
    # اليوم 5
    vocab[5] = {
        "morning": [
            Word("day", "يوم", "Today is a nice day.", "مبتدئ"),
            Word("week", "أسبوع", "A week has 7 days.", "مبتدئ"),
            Word("month", "شهر", "This month is January.", "مبتدئ"),
            Word("year", "سنة", "Happy new year.", "مبتدئ")
        ],
        "noon": [
            Word("sun", "شمس", "The sun is bright.", "مبتدئ"),
            Word("moon", "قمر", "The moon at night.", "مبتدئ"),
            Word("star", "نجم", "Twinkling stars.", "مبتدئ"),
            Word("sky", "سماء", "Blue sky.", "مبتدئ")
        ],
        "afternoon": [
            Word("up", "فوق", "Look up.", "مبتدئ"),
            Word("down", "تحت", "Sit down.", "مبتدئ"),
            Word("left", "يسار", "Turn left.", "مبتدئ"),
            Word("right", "يمين", "Turn right.", "مبتدئ")
        ],
        "night": [
            Word("open", "يفتح", "Open the window.", "مبتدئ"),
            Word("close", "يغلق", "Close the door.", "مبتدئ"),
            Word("enter", "يدخل", "Enter the room.", "مبتدئ"),
            Word("exit", "يخرج", "Exit the building.", "مبتدئ")
        ]
    }
    
    # اليوم 6
    vocab[6] = {
        "morning": [
            Word("man", "رجل", "A tall man.", "مبتدئ"),
            Word("woman", "امرأة", "A woman with a bag.", "مبتدئ"),
            Word("boy", "ولد", "The boy plays.", "مبتدئ"),
            Word("girl", "بنت", "The girl sings.", "مبتدئ")
        ],
        "noon": [
            Word("friend", "صديق", "Best friend.", "مبتدئ"),
            Word("family", "عائلة", "My family is large.", "مبتدئ"),
            Word("baby", "طفل", "The baby cries.", "مبتدئ"),
            Word("people", "ناس", "Many people.", "مبتدئ")
        ],
        "afternoon": [
            Word("work", "عمل", "I work hard.", "مبتدئ"),
            Word("play", "يلعب", "Children play.", "مبتدئ"),
            Word("study", "يدرس", "Study for exam.", "مبتدئ"),
            Word("rest", "يستريح", "Rest after work.", "مبتدئ")
        ],
        "night": [
            Word("city", "مدينة", "Big city.", "مبتدئ"),
            Word("town", "بلدة", "Small town.", "مبتدئ"),
            Word("village", "قرية", "Quiet village.", "مبتدئ"),
            Word("country", "ريف", "Live in the country.", "مبتدئ")
        ]
    }
    
    # اليوم 7
    vocab[7] = {
        "morning": [
            Word("ask", "يسأل", "Ask a question.", "مبتدئ"),
            Word("answer", "يجيب", "Answer the phone.", "مبتدئ"),
            Word("give", "يعطي", "Give me the book.", "مبتدئ"),
            Word("take", "يأخذ", "Take a seat.", "مبتدئ")
        ],
        "noon": [
            Word("help", "يساعد", "Help me, please.", "مبتدئ"),
            Word("find", "يجد", "Find your keys.", "مبتدئ"),
            Word("lose", "يفقد", "Don't lose hope.", "مبتدئ"),
            Word("need", "يحتاج", "I need water.", "مبتدئ")
        ],
        "afternoon": [
            Word("love", "حب", "I love you.", "مبتدئ"),
            Word("like", "يعجبني", "I like pizza.", "مبتدئ"),
            Word("hate", "يكره", "I hate spiders.", "مبتدئ"),
            Word("want", "يريد", "I want to travel.", "مبتدئ")
        ],
        "night": [
            Word("come", "يأتي", "Come here.", "مبتدئ"),
            Word("go", "يذهب", "Go away.", "مبتدئ"),
            Word("arrive", "يصل", "Arrive at station.", "مبتدئ"),
            Word("leave", "يغادر", "Leave the room.", "مبتدئ")
        ]
    }
    
    # اليوم 8
    vocab[8] = {
        "morning": [
            Word("begin", "يبدأ", "Let's begin.", "مبتدئ"),
            Word("start", "يبدأ", "Start the car.", "مبتدئ"),
            Word("finish", "ينهي", "Finish your work.", "مبتدئ"),
            Word("stop", "يتوقف", "Stop here.", "مبتدئ")
        ],
        "noon": [
            Word("buy", "يشتري", "Buy some milk.", "مبتدئ"),
            Word("sell", "يبيع", "Sell your car.", "مبتدئ"),
            Word("pay", "يدفع", "Pay the bill.", "مبتدئ"),
            Word("cost", "يكلف", "How much does it cost?", "مبتدئ")
        ],
        "afternoon": [
            Word("cheap", "رخيص", "Cheap price.", "مبتدئ"),
            Word("expensive", "غالي", "Expensive car.", "مبتدئ"),
            Word("free", "مجاني", "Free admission.", "مبتدئ"),
            Word("price", "سعر", "The price is high.", "مبتدئ")
        ],
        "night": [
            Word("time", "وقت", "What time is it?", "مبتدئ"),
            Word("hour", "ساعة", "One hour later.", "مبتدئ"),
            Word("minute", "دقيقة", "Wait a minute.", "مبتدئ"),
            Word("second", "ثانية", "Just a second.", "مبتدئ")
        ]
    }
    
    # اليوم 9
    vocab[9] = {
        "morning": [
            Word("today", "اليوم", "Today is Monday.", "مبتدئ"),
            Word("tomorrow", "غداً", "See you tomorrow.", "مبتدئ"),
            Word("yesterday", "أمس", "Yesterday was Sunday.", "مبتدئ"),
            Word("now", "الآن", "Do it now.", "مبتدئ")
        ],
        "noon": [
            Word("always", "دائماً", "Always be kind.", "مبتدئ"),
            Word("usually", "عادةً", "I usually wake up early.", "مبتدئ"),
            Word("sometimes", "أحياناً", "Sometimes it rains.", "مبتدئ"),
            Word("never", "أبداً", "I never smoke.", "مبتدئ")
        ],
        "afternoon": [
            Word("here", "هنا", "Come here.", "مبتدئ"),
            Word("there", "هناك", "Put it there.", "مبتدئ"),
            Word("everywhere", "في كل مكان", "I looked everywhere.", "مبتدئ"),
            Word("somewhere", "في مكان ما", "It's somewhere here.", "مبتدئ")
        ],
        "night": [
            Word("fast", "سريع", "Fast car.", "مبتدئ"),
            Word("slow", "بطيء", "Slow down.", "مبتدئ"),
            Word("quick", "سريع", "Quick response.", "مبتدئ"),
            Word("early", "مبكر", "Wake up early.", "مبتدئ")
        ]
    }
    
    # اليوم 10
    vocab[10] = {
        "morning": [
            Word("new", "جديد", "New phone.", "مبتدئ"),
            Word("old", "قديم", "Old house.", "مبتدئ"),
            Word("young", "شاب", "Young people.", "مبتدئ"),
            Word("modern", "حديث", "Modern design.", "مبتدئ")
        ],
        "noon": [
            Word("easy", "سهل", "Easy test.", "مبتدئ"),
            Word("difficult", "صعب", "Difficult exam.", "مبتدئ"),
            Word("hard", "صعب", "Hard work.", "مبتدئ"),
            Word("simple", "بسيط", "Simple answer.", "مبتدئ")
        ],
        "afternoon": [
            Word("clean", "نظيف", "Clean room.", "مبتدئ"),
            Word("dirty", "قذر", "Dirty clothes.", "مبتدئ"),
            Word("empty", "فارغ", "Empty box.", "مبتدئ"),
            Word("full", "ممتلئ", "Full glass.", "مبتدئ")
        ],
        "night": [
            Word("light", "خفيف/ضوء", "Light weight.", "مبتدئ"),
            Word("heavy", "ثقيل", "Heavy bag.", "مبتدئ"),
            Word("dark", "مظلم", "Dark night.", "مبتدئ"),
            Word("bright", "مشرق", "Bright sun.", "مبتدئ")
        ]
    }
    
    # اليوم 11
    vocab[11] = {
        "morning": [
            Word("ability", "قدرة", "He has the ability to sing.", "متوسط"),
            Word("absence", "غياب", "His absence was noticed.", "متوسط"),
            Word("absolute", "مطلق", "Absolute power.", "متوسط"),
            Word("absorb", "يمتص", "The sponge absorbs water.", "متوسط")
        ],
        "noon": [
            Word("academic", "أكاديمي", "Academic year.", "متوسط"),
            Word("accept", "يقبل", "Accept the offer.", "متوسط"),
            Word("access", "وصول", "Access to information.", "متوسط"),
            Word("accident", "حادث", "Car accident.", "متوسط")
        ],
        "afternoon": [
            Word("achieve", "يحقق", "Achieve your goals.", "متوسط"),
            Word("act", "يتصرف", "Act quickly.", "متوسط"),
            Word("active", "نشط", "Active lifestyle.", "متوسط"),
            Word("actual", "فعلي", "Actual facts.", "متوسط")
        ],
        "night": [
            Word("adapt", "يتكيف", "Adapt to changes.", "متوسط"),
            Word("add", "يضيف", "Add some salt.", "متوسط"),
            Word("adjust", "يعدل", "Adjust the volume.", "متوسط"),
            Word("admire", "يعجب", "I admire your work.", "متوسط")
        ]
    }
    
    # اليوم 12
    vocab[12] = {
        "morning": [
            Word("admit", "يعترف", "Admit your mistake.", "متوسط"),
            Word("adopt", "يتبنى", "Adopt a child.", "متوسط"),
            Word("adult", "بالغ", "Adult education.", "متوسط"),
            Word("advance", "يتقدم", "Advance in career.", "متوسط")
        ],
        "noon": [
            Word("advantage", "ميزة", "Take advantage.", "متوسط"),
            Word("advice", "نصيحة", "Good advice.", "متوسط"),
            Word("affair", "شأن", "Personal affair.", "متوسط"),
            Word("affect", "يؤثر", "Affect the result.", "متوسط")
        ],
        "afternoon": [
            Word("afford", "يستطيع شراء", "I can't afford it.", "متوسط"),
            Word("afraid", "خائف", "Afraid of dogs.", "متوسط"),
            Word("against", "ضد", "Fight against.", "متوسط"),
            Word("age", "عمر", "At your age.", "متوسط")
        ],
        "night": [
            Word("agency", "وكالة", "Travel agency.", "متوسط"),
            Word("agent", "وكيل", "Secret agent.", "متوسط"),
            Word("agree", "يوافق", "I agree with you.", "متوسط"),
            Word("ahead", "قدماً", "Go ahead.", "متوسط")
        ]
    }
    
    # اليوم 13
    vocab[13] = {
        "morning": [
            Word("aid", "مساعدة", "First aid.", "متوسط"),
            Word("aim", "هدف", "Aim high.", "متوسط"),
            Word("air", "هواء", "Fresh air.", "متوسط"),
            Word("allow", "يسمح", "Allow entry.", "متوسط")
        ],
        "noon": [
            Word("almost", "تقريباً", "Almost done.", "متوسط"),
            Word("alone", "وحيد", "Live alone.", "متوسط"),
            Word("along", "بطول", "Walk along.", "متوسط"),
            Word("already", "بالفعل", "Already finished.", "متوسط")
        ],
        "afternoon": [
            Word("alright", "حسناً", "Alright, let's go.", "متوسط"),
            Word("although", "مع أن", "Although it's raining.", "متوسط"),
            Word("always", "دائماً", "Always ready.", "متوسط"),
            Word("among", "بين", "Among friends.", "متوسط")
        ],
        "night": [
            Word("amount", "كمية", "Large amount.", "متوسط"),
            Word("ancient", "قديم", "Ancient history.", "متوسط"),
            Word("anger", "غضب", "Control your anger.", "متوسط"),
            Word("angle", "زاوية", "Right angle.", "متوسط")
        ]
    }
    
    # اليوم 14
    vocab[14] = {
        "morning": [
            Word("announce", "يعلن", "Announce the news.", "متوسط"),
            Word("annoy", "يزعج", "Don't annoy me.", "متوسط"),
            Word("annual", "سنوي", "Annual meeting.", "متوسط"),
            Word("another", "آخر", "Another chance.", "متوسط")
        ],
        "noon": [
            Word("answer", "إجابة", "Correct answer.", "متوسط"),
            Word("anticipate", "يتوقع", "Anticipate results.", "متوسط"),
            Word("anxiety", "قلق", "Feel anxiety.", "متوسط"),
            Word("anyway", "على أي حال", "Anyway, let's continue.", "متوسط")
        ],
        "afternoon": [
            Word("apart", "منفصل", "Apart from that.", "متوسط"),
            Word("apologize", "يعتذر", "Apologize for being late.", "متوسط"),
            Word("apparent", "واضح", "Apparent reason.", "متوسط"),
            Word("appeal", "يستأنف/يجذب", "Appeal to the court.", "متوسط")
        ],
        "night": [
            Word("appear", "يظهر", "Appear suddenly.", "متوسط"),
            Word("apply", "يتقدم/يطبق", "Apply for a job.", "متوسط"),
            Word("approach", "يقترب", "Approach the problem.", "متوسط"),
            Word("appropriate", "مناسب", "Appropriate time.", "متوسط")
        ]
    }
    
    # اليوم 15
    vocab[15] = {
        "morning": [
            Word("approve", "يوافق", "Approve the plan.", "متوسط"),
            Word("area", "منطقة", "Residential area.", "متوسط"),
            Word("argue", "يتجادل", "Argue about politics.", "متوسط"),
            Word("arrange", "يرتب", "Arrange the books.", "متوسط")
        ],
        "noon": [
            Word("arrest", "يعتقل", "Arrest the thief.", "متوسط"),
            Word("arrival", "وصول", "Arrival time.", "متوسط"),
            Word("article", "مقال", "Read an article.", "متوسط"),
            Word("ashamed", "خجول", "Feel ashamed.", "متوسط")
        ],
        "afternoon": [
            Word("aside", "جانباً", "Step aside.", "متوسط"),
            Word("ask", "يسأل", "Ask a question.", "متوسط"),
            Word("asleep", "نائم", "Fall asleep.", "متوسط"),
            Word("aspect", "جانب", "Consider every aspect.", "متوسط")
        ],
        "night": [
            Word("assemble", "يجمع", "Assemble the team.", "متوسط"),
            Word("assess", "يقيم", "Assess the situation.", "متوسط"),
            Word("assign", "يعين", "Assign a task.", "متوسط"),
            Word("assist", "يساعد", "Assist the teacher.", "متوسط")
        ]
    }
    
    # اليوم 16
    vocab[16] = {
        "morning": [
            Word("assume", "يفترض", "Assume it's true.", "متوسط"),
            Word("assure", "يؤكد", "Assure safety.", "متوسط"),
            Word("atmosphere", "جو", "Friendly atmosphere.", "متوسط"),
            Word("attach", "يرفق", "Attach a file.", "متوسط")
        ],
        "noon": [
            Word("attack", "يهاجم", "Attack the enemy.", "متوسط"),
            Word("attempt", "يحاول", "Attempt to win.", "متوسط"),
            Word("attend", "يحضر", "Attend the meeting.", "متوسط"),
            Word("attention", "انتباه", "Pay attention.", "متوسط")
        ],
        "afternoon": [
            Word("attitude", "موقف", "Positive attitude.", "متوسط"),
            Word("attract", "يجذب", "Attract tourists.", "متوسط"),
            Word("audience", "جمهور", "Large audience.", "متوسط"),
            Word("author", "مؤلف", "Book author.", "متوسط")
        ],
        "night": [
            Word("authority", "سلطة", "Local authority.", "متوسط"),
            Word("automatic", "تلقائي", "Automatic door.", "متوسط"),
            Word("available", "متاح", "Available now.", "متوسط"),
            Word("average", "متوسط", "Average score.", "متوسط")
        ]
    }
    
    # اليوم 17
    vocab[17] = {
        "morning": [
            Word("avoid", "يتجنب", "Avoid trouble.", "متوسط"),
            Word("award", "جائزة", "Win an award.", "متوسط"),
            Word("aware", "مدرك", "Be aware.", "متوسط"),
            Word("awful", "فظيع", "Awful weather.", "متوسط")
        ],
        "noon": [
            Word("back", "ظهر/يعود", "Come back.", "متوسط"),
            Word("background", "خلفية", "Educational background.", "متوسط"),
            Word("balance", "توازن", "Work-life balance.", "متوسط"),
            Word("ban", "يحظر", "Ban smoking.", "متوسط")
        ],
        "afternoon": [
            Word("band", "فرقة", "Rock band.", "متوسط"),
            Word("bar", "شريط/حانة", "Coffee bar.", "متوسط"),
            Word("barely", "بالكاد", "Barely enough.", "متوسط"),
            Word("battle", "معركة", "Battle field.", "متوسط")
        ],
        "night": [
            Word("bear", "يتحمل", "Bear the pain.", "متوسط"),
            Word("beat", "يضرب/يهزم", "Beat the record.", "متوسط"),
            Word("beauty", "جمال", "Natural beauty.", "متوسط"),
            Word("because", "لأن", "Because of you.", "متوسط")
        ]
    }
    
    # اليوم 18
    vocab[18] = {
        "morning": [
            Word("become", "يصبح", "Become a doctor.", "متوسط"),
            Word("before", "قبل", "Before the war.", "متوسط"),
            Word("begin", "يبدأ", "Begin now.", "متوسط"),
            Word("behave", "يتصرف", "Behave yourself.", "متوسط")
        ],
        "noon": [
            Word("behind", "خلف", "Behind the door.", "متوسط"),
            Word("believe", "يؤمن", "Believe in yourself.", "متوسط"),
            Word("belong", "ينتمي", "Belong to a group.", "متوسط"),
            Word("below", "أسفل", "Below zero.", "متوسط")
        ],
        "afternoon": [
            Word("beneath", "تحت", "Beneath the surface.", "متوسط"),
            Word("benefit", "فائدة", "Health benefits.", "متوسط"),
            Word("beside", "بجانب", "Beside the river.", "متوسط"),
            Word("bet", "يراهن", "I bet you can.", "متوسط")
        ],
        "night": [
            Word("better", "أفضل", "Better than before.", "متوسط"),
            Word("between", "بين", "Between us.", "متوسط"),
            Word("beyond", "وراء", "Beyond imagination.", "متوسط"),
            Word("bill", "فاتورة", "Pay the bill.", "متوسط")
        ]
    }
    
    # اليوم 19
    vocab[19] = {
        "morning": [
            Word("billion", "مليار", "Billions of stars.", "متوسط"),
            Word("bind", "يربط", "Bind the books.", "متوسط"),
            Word("birth", "ولادة", "Birth day.", "متوسط"),
            Word("bit", "قطعة صغيرة", "A bit of sugar.", "متوسط")
        ],
        "noon": [
            Word("bite", "يعض", "Dog bite.", "متوسط"),
            Word("blame", "يلوم", "Blame someone.", "متوسط"),
            Word("blank", "فارغ", "Blank page.", "متوسط"),
            Word("blind", "أعمى", "Blind man.", "متوسط")
        ],
        "afternoon": [
            Word("block", "كتلة/يمنع", "Block the road.", "متوسط"),
            Word("blood", "دم", "Blood pressure.", "متوسط"),
            Word("blow", "ينفخ", "Blow out the candle.", "متوسط"),
            Word("board", "لوح", "Board of directors.", "متوسط")
        ],
        "night": [
            Word("boast", "يتفاخر", "Boast about success.", "متوسط"),
            Word("boat", "قارب", "Fishing boat.", "متوسط"),
            Word("body", "جسم", "Human body.", "متوسط"),
            Word("boil", "يغلي", "Boil the water.", "متوسط")
        ]
    }
    
    # اليوم 20
    vocab[20] = {
        "morning": [
            Word("bold", "جريء", "Bold move.", "متوسط"),
            Word("bomb", "قنبلة", "Bomb explosion.", "متوسط"),
            Word("bond", "رابطة", "Family bond.", "متوسط"),
            Word("bone", "عظمة", "Broken bone.", "متوسط")
        ],
        "noon": [
            Word("book", "يحجز", "Book a ticket.", "متوسط"),
            Word("border", "حدود", "Border crossing.", "متوسط"),
            Word("bother", "يزعج", "Don't bother me.", "متوسط"),
            Word("bottom", "قاع", "Bottom of the sea.", "متوسط")
        ],
        "afternoon": [
            Word("bound", "ملزم", "Bound by law.", "متوسط"),
            Word("bow", "ينحني", "Bow down.", "متوسط"),
            Word("brain", "دماغ", "Use your brain.", "متوسط"),
            Word("branch", "فرع", "Tree branch.", "متوسط")
        ],
        "night": [
            Word("brave", "شجاع", "Brave soldier.", "متوسط"),
            Word("break", "يكسر", "Break the glass.", "متوسط"),
            Word("breath", "نفس", "Take a breath.", "متوسط"),
            Word("breathe", "يتنفس", "Breathe deeply.", "متوسط")
        ]
    }
    
    # اليوم 21 (مستوى متقدم)
    vocab[21] = {
        "morning": [
            Word("abandon", "يهجر", "Abandon the project.", "متقدم"),
            Word("abstract", "مجرد", "Abstract idea.", "متقدم"),
            Word("absurd", "عبثي", "Absurd suggestion.", "متقدم"),
            Word("abuse", "يسيء", "Abuse power.", "متقدم")
        ],
        "noon": [
            Word("accelerate", "يسرع", "Accelerate the car.", "متقدم"),
            Word("accommodate", "يستوعب", "Accommodate guests.", "متقدم"),
            Word("accompany", "يرافق", "Accompany me.", "متقدم"),
            Word("accomplish", "ينجز", "Accomplish a goal.", "متقدم")
        ],
        "afternoon": [
            Word("account", "حساب", "Bank account.", "متقدم"),
            Word("accumulate", "يتراكم", "Dust accumulates.", "متقدم"),
            Word("accuse", "يتهم", "Accuse of theft.", "متقدم"),
            Word("achieve", "يحقق", "Achieve success.", "متقدم")
        ],
        "night": [
            Word("acknowledge", "يعترف", "Acknowledge mistake.", "متقدم"),
            Word("acquire", "يكتسب", "Acquire knowledge.", "متقدم"),
            Word("adapt", "يتكيف", "Adapt to environment.", "متقدم"),
            Word("address", "يعالج/عنوان", "Address the issue.", "متقدم")
        ]
    }
    
    # اليوم 22
    vocab[22] = {
        "morning": [
            Word("adequate", "كاف", "Adequate supply.", "متقدم"),
            Word("adjust", "يعدل", "Adjust settings.", "متقدم"),
            Word("administer", "يدير", "Administer medicine.", "متقدم"),
            Word("admire", "يعجب", "Admire the view.", "متقدم")
        ],
        "noon": [
            Word("admit", "يعترف", "Admit guilt.", "متقدم"),
            Word("adopt", "يتبنى", "Adopt a method.", "متقدم"),
            Word("advance", "يتقدم", "Advance in career.", "متقدم"),
            Word("adverse", "سلبي", "Adverse effects.", "متقدم")
        ],
        "afternoon": [
            Word("advocate", "يدافع", "Advocate for rights.", "متقدم"),
            Word("affect", "يؤثر", "Affect the outcome.", "متقدم"),
            Word("aggregate", "إجمالي", "Aggregate data.", "متقدم"),
            Word("allocate", "يخصص", "Allocate resources.", "متقدم")
        ],
        "night": [
            Word("anticipate", "يتوقع", "Anticipate needs.", "متقدم"),
            Word("apparent", "واضح", "Apparent reason.", "متقدم"),
            Word("appeal", "يستأنف", "Appeal the decision.", "متقدم"),
            Word("apply", "يطبق", "Apply the theory.", "متقدم")
        ]
    }
    
    # اليوم 23
    vocab[23] = {
        "morning": [
            Word("approach", "يقترب", "Approach the problem.", "متقدم"),
            Word("appropriate", "مناسب", "Appropriate response.", "متقدم"),
            Word("approve", "يوافق", "Approve the plan.", "متقدم"),
            Word("arise", "ينشأ", "Problems arise.", "متقدم")
        ],
        "noon": [
            Word("aspect", "جانب", "Various aspects.", "متقدم"),
            Word("assemble", "يجمع", "Assemble the team.", "متقدم"),
            Word("assess", "يقيم", "Assess the damage.", "متقدم"),
            Word("assign", "يعين", "Assign tasks.", "متقدم")
        ],
        "afternoon": [
            Word("assist", "يساعد", "Assist in research.", "متقدم"),
            Word("assume", "يفترض", "Assume responsibility.", "متقدم"),
            Word("assure", "يؤكد", "Assure quality.", "متقدم"),
            Word("attach", "يرفق", "Attach documents.", "متقدم")
        ],
        "night": [
            Word("attain", "يحقق", "Attain success.", "متقدم"),
            Word("attempt", "يحاول", "Attempt to escape.", "متقدم"),
            Word("attend", "يحضر", "Attend conference.", "متقدم"),
            Word("attribute", "ينسب", "Attribute to luck.", "متقدم")
        ]
    }
    
    # اليوم 24
    vocab[24] = {
        "morning": [
            Word("beneficial", "مفيد", "Beneficial advice.", "متقدم"),
            Word("challenge", "تحدي", "Face the challenge.", "متقدم"),
            Word("characteristic", "صفة", "Main characteristic.", "متقدم"),
            Word("circumstance", "ظرف", "Under circumstances.", "متقدم")
        ],
        "noon": [
            Word("coherent", "مترابط", "Coherent argument.", "متقدم"),
            Word("coincide", "يتزامن", "Events coincide.", "متقدم"),
            Word("collapse", "ينهار", "Building collapses.", "متقدم"),
            Word("colleague", "زميل", "Work colleague.", "متقدم")
        ],
        "afternoon": [
            Word("commence", "يبدأ", "Commence ceremony.", "متقدم"),
            Word("commit", "يرتكب", "Commit a crime.", "متقدم"),
            Word("commodity", "سلعة", "Commodity prices.", "متقدم"),
            Word("compensate", "يعوض", "Compensate for loss.", "متقدم")
        ],
        "night": [
            Word("compile", "يجمع", "Compile data.", "متقدم"),
            Word("comply", "يمتثل", "Comply with rules.", "متقدم"),
            Word("compose", "يؤلف", "Compose music.", "متقدم"),
            Word("comprehend", "يستوعب", "Comprehend the text.", "متقدم")
        ]
    }
    
    # اليوم 25
    vocab[25] = {
        "morning": [
            Word("comprise", "يتكون من", "Comprise many parts.", "متقدم"),
            Word("compromise", "حل وسط", "Reach a compromise.", "متقدم"),
            Word("conceal", "يخفي", "Conceal the truth.", "متقدم"),
            Word("conceive", "يتصور", "Conceive an idea.", "متقدم")
        ],
        "noon": [
            Word("concentrate", "يركز", "Concentrate on work.", "متقدم"),
            Word("concept", "مفهوم", "Key concept.", "متقدم"),
            Word("concern", "يهتم", "Concern about safety.", "متقدم"),
            Word("conclude", "يستنتج", "Conclude the meeting.", "متقدم")
        ],
        "afternoon": [
            Word("concrete", "ملموس", "Concrete evidence.", "متقدم"),
            Word("conduct", "يقود", "Conduct research.", "متقدم"),
            Word("confer", "يتشاور", "Confer with experts.", "متقدم"),
            Word("confess", "يعترف", "Confess the crime.", "متقدم")
        ],
        "night": [
            Word("confine", "يقيد", "Confine in prison.", "متقدم"),
            Word("confirm", "يؤكد", "Confirm the news.", "متقدم"),
            Word("conflict", "صراع", "Conflict of interest.", "متقدم"),
            Word("conform", "يتوافق", "Conform to rules.", "متقدم")
        ]
    }
    
    # اليوم 26
    vocab[26] = {
        "morning": [
            Word("confront", "يواجه", "Confront the enemy.", "متقدم"),
            Word("confuse", "يربك", "Confuse the issue.", "متقدم"),
            Word("connect", "يربط", "Connect the wires.", "متقدم"),
            Word("consent", "موافقة", "Parental consent.", "متقدم")
        ],
        "noon": [
            Word("consequence", "نتيجة", "Face consequences.", "متقدم"),
            Word("conserve", "يحافظ", "Conserve energy.", "متقدم"),
            Word("consider", "يعتبر", "Consider the options.", "متقدم"),
            Word("consist", "يتكون", "Consist of parts.", "متقدم")
        ],
        "afternoon": [
            Word("consistent", "متناسق", "Consistent results.", "متقدم"),
            Word("consolidate", "يوحد", "Consolidate power.", "متقدم"),
            Word("conspicuous", "واضح", "Conspicuous place.", "متقدم"),
            Word("constant", "ثابت", "Constant speed.", "متقدم")
        ],
        "night": [
            Word("constitute", "يشكل", "Constitute a threat.", "متقدم"),
            Word("constrain", "يقيد", "Constrained by law.", "متقدم"),
            Word("construct", "يبني", "Construct a building.", "متقدم"),
            Word("consult", "يستشير", "Consult a doctor.", "متقدم")
        ]
    }
    
    # اليوم 27
    vocab[27] = {
        "morning": [
            Word("consume", "يستهلك", "Consume food.", "متقدم"),
            Word("contact", "يتصل", "Contact me later.", "متقدم"),
            Word("contemporary", "معاصر", "Contemporary art.", "متقدم"),
            Word("contend", "ينافس", "Contend for title.", "متقدم")
        ],
        "noon": [
            Word("content", "محتوى", "Table of contents.", "متقدم"),
            Word("contest", "مسابقة", "Win the contest.", "متقدم"),
            Word("context", "سياق", "In this context.", "متقدم"),
            Word("contract", "عقد", "Sign a contract.", "متقدم")
        ],
        "afternoon": [
            Word("contradict", "يناقض", "Contradict yourself.", "متقدم"),
            Word("contrary", "عكس", "Contrary to belief.", "متقدم"),
            Word("contrast", "تباين", "In contrast to.", "متقدم"),
            Word("contribute", "يساهم", "Contribute to society.", "متقدم")
        ],
        "night": [
            Word("controversy", "جدل", "Cause controversy.", "متقدم"),
            Word("convenient", "ملائم", "Convenient time.", "متقدم"),
            Word("convention", "اتفاقية", "International convention.", "متقدم"),
            Word("converse", "يتحدث", "Converse with friends.", "متقدم")
        ]
    }
    
    # اليوم 28
    vocab[28] = {
        "morning": [
            Word("convert", "يحول", "Convert currency.", "متقدم"),
            Word("convey", "ينقل", "Convey a message.", "متقدم"),
            Word("convict", "يدين", "Convict the criminal.", "متقدم"),
            Word("convince", "يقنع", "Convince the jury.", "متقدم")
        ],
        "noon": [
            Word("cooperate", "يتعاون", "Cooperate with team.", "متقدم"),
            Word("coordinate", "ينسق", "Coordinate efforts.", "متقدم"),
            Word("cope", "يتأقلم", "Cope with stress.", "متقدم"),
            Word("core", "جوهر", "Core values.", "متقدم")
        ],
        "afternoon": [
            Word("corporate", "شركة", "Corporate identity.", "متقدم"),
            Word("correspond", "يتوافق", "Correspond with facts.", "متقدم"),
            Word("counsel", "يستشير", "Seek counsel.", "متقدم"),
            Word("counter", "يعارض", "Counter the argument.", "متقدم")
        ],
        "night": [
            Word("courtesy", "لباقة", "Courtesy and respect.", "متقدم"),
            Word("craft", "حرفة", "Art and craft.", "متقدم"),
            Word("crash", "يتحطم", "Car crash.", "متقدم"),
            Word("create", "يخلق", "Create new ideas.", "متقدم")
        ]
    }
    
    # اليوم 29
    vocab[29] = {
        "morning": [
            Word("credible", "موثوق", "Credible source.", "متقدم"),
            Word("crime", "جريمة", "Crime rate.", "متقدم"),
            Word("crisis", "أزمة", "Economic crisis.", "متقدم"),
            Word("criteria", "معايير", "Selection criteria.", "متقدم")
        ],
        "noon": [
            Word("critic", "ناقد", "Film critic.", "متقدم"),
            Word("crucial", "حاسم", "Crucial moment.", "متقدم"),
            Word("crude", "خام", "Crude oil.", "متقدم"),
            Word("cultivate", "يزرع", "Cultivate the land.", "متقدم")
        ],
        "afternoon": [
            Word("curious", "فضولي", "Curious mind.", "متقدم"),
            Word("currency", "عملة", "Foreign currency.", "متقدم"),
            Word("current", "حالي", "Current situation.", "متقدم"),
            Word("curriculum", "منهج", "School curriculum.", "متقدم")
        ],
        "night": [
            Word("custom", "عادة", "Local customs.", "متقدم"),
            Word("damage", "ضرر", "Cause damage.", "متقدم"),
            Word("debate", "مناظرة", "Political debate.", "متقدم"),
            Word("decade", "عقد", "For decades.", "متقدم")
        ]
    }
    
    # اليوم 30
    vocab[30] = {
        "morning": [
            Word("decay", "تحلل", "Tooth decay.", "متقدم"),
            Word("deceive", "يخدع", "Deceive the public.", "متقدم"),
            Word("decent", "لائق", "Decent living.", "متقدم"),
            Word("decide", "يقرر", "Decide quickly.", "متقدم")
        ],
        "noon": [
            Word("declare", "يعلن", "Declare independence.", "متقدم"),
            Word("decline", "ينخفض", "Decline in value.", "متقدم"),
            Word("decrease", "يقلل", "Decrease speed.", "متقدم"),
            Word("dedicate", "يكرس", "Dedicate your life.", "متقدم")
        ],
        "afternoon": [
            Word("defeat", "هزيمة", "Accept defeat.", "متقدم"),
            Word("defend", "يدافع", "Defend the country.", "متقدم"),
            Word("deficiency", "نقص", "Vitamin deficiency.", "متقدم"),
            Word("define", "يعرف", "Define the term.", "متقدم")
        ],
        "night": [
            Word("definite", "محدد", "Definite answer.", "متقدم"),
            Word("delay", "تأخير", "Delay the flight.", "متقدم"),
            Word("delegate", "مندوب", "Delegate authority.", "متقدم"),
            Word("deliberate", "متعمد", "Deliberate act.", "متقدم")
        ]
    }

load_vocab()

# ================== إعدادات البوت ==================
bot = telebot.TeleBot(TOKEN)
FORCE_CHANNEL = db.get_config('force_channel')

# ================== حالة المستخدمين (مع قفل) ==================
user_sessions: Dict[int, List[Word]] = {}
quiz_states: Dict[int, QuizState] = {}
level_test_states: Dict[int, LevelTestState] = {}
infinite_quiz_states: Dict[int, InfiniteQuizState] = {}
broadcast_states: Dict[int, BroadcastState] = {}
pending_polls: Dict[str, Dict] = {}
poll_timeouts: Dict[str, threading.Timer] = {}
admin_states: Dict[int, Dict] = {}

# ================== دوال مساعدة ==================
def safe_send_message(chat_id: int, text: str, **kwargs):
    try:
        return bot.send_message(chat_id, text, **kwargs)
    except Exception as e:
        logger.error(f"فشل إرسال رسالة إلى {chat_id}: {e}")
        return None

def safe_delete_message(chat_id: int, message_id: int):
    try:
        bot.delete_message(chat_id, message_id)
    except Exception as e:
        logger.error(f"فشل حذف رسالة {message_id}: {e}")

def create_colored_button(text: str, callback_data: str, color: str = "🟢", url: str = None) -> InlineKeyboardButton:
    colored_text = f"{color} {text}"
    if url:
        return InlineKeyboardButton(text=colored_text, url=url)
    return InlineKeyboardButton(text=colored_text, callback_data=callback_data)

def get_session_name(session: str) -> str:
    names = {
        "morning": "🌅 الصباح",
        "noon": "☀️ الظهر",
        "afternoon": "🌇 العصر",
        "night": "🌙 الليل",
        "extra": "🎮 تدريب إضافي"
    }
    return names.get(session, session)

def check_subscription(user_id: int) -> bool:
    global FORCE_CHANNEL
    if not FORCE_CHANNEL:
        return True
    try:
        channel_id = FORCE_CHANNEL
        if channel_id.startswith('@'):
            channel_id = channel_id[1:]
        chat_member = bot.get_chat_member(chat_id=f"@{channel_id}", user_id=user_id)
        status = chat_member.status
        return status in ['member', 'administrator', 'creator']
    except Exception as e:
        logger.error(f"خطأ في التحقق من الاشتراك للمستخدم {user_id}: {e}")
        if "chat not found" in str(e).lower():
            return True
        return False

def require_subscription(func):
    def wrapper(message: Message, *args, **kwargs):
        user_id = message.from_user.id
        if db.is_banned(user_id):
            safe_send_message(message.chat.id, "🚫 لقد تم حظرك من استخدام هذا البوت.")
            return
        if not check_subscription(user_id):
            markup = InlineKeyboardMarkup()
            if FORCE_CHANNEL:
                channel_link = FORCE_CHANNEL
                if not channel_link.startswith('https://t.me/'):
                    if channel_link.startswith('@'):
                        channel_link = channel_link[1:]
                    channel_link = f"https://t.me/{channel_link}"
                markup.add(create_colored_button(
                    "📢 اشترك الآن في القناة", 
                    callback_data="dummy", 
                    color="🔴",
                    url=channel_link
                ))
                markup.add(create_colored_button(
                    "🔄 تحقق من الاشتراك", 
                    "check_subscription", 
                    "🟢"
                ))
            safe_send_message(
                message.chat.id,
                f"❗️ **للاستمرار في استخدام البوت، يجب عليك الاشتراك في القناة أولاً:**\n\n"
                f"👉 {FORCE_CHANNEL}\n\n"
                f"بعد الاشتراك، اضغط على زر 'تحقق من الاشتراك'",
                parse_mode="Markdown",
                reply_markup=markup
            )
            return
        return func(message, *args, **kwargs)
    return wrapper

def require_subscription_callback(func):
    def wrapper(call: CallbackQuery, *args, **kwargs):
        user_id = call.from_user.id
        if db.is_banned(user_id):
            bot.answer_callback_query(call.id, "🚫 أنت محظور.", show_alert=True)
            return
        if not check_subscription(user_id):
            bot.answer_callback_query(call.id, "❗️ يجب الاشتراك في القناة أولاً.", show_alert=True)
            return
        return func(call, *args, **kwargs)
    return wrapper

def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID

def has_permission(user_id: int, permission: str) -> bool:
    if user_id == OWNER_ID:
        return True
    perms = db.get_admin_permissions(user_id)
    return perms.get(permission, False)

def get_random_wrong_meaning(correct: str, exclude_word: Optional[str] = None, level: Optional[str] = None) -> str:
    all_meanings = []
    for day in range(1, 31):
        for session in ["morning", "noon", "afternoon", "night"]:
            for word in vocab[day][session]:
                if word.ar != correct and (not level or word.level == level):
                    all_meanings.append(word.ar)
    custom_words = db.get_custom_words()
    for w in custom_words:
        if w['ar'] != correct and (not level or w['level'] == level):
            all_meanings.append(w['ar'])
    if not all_meanings:
        return "✗ " + correct
    return random.choice(all_meanings)

def get_random_wrong_example(correct: str, exclude_word: Optional[str] = None, level: Optional[str] = None) -> str:
    all_examples = []
    for day in range(1, 31):
        for session in ["morning", "noon", "afternoon", "night"]:
            for word in vocab[day][session]:
                if word.example != correct and (not level or word.level == level):
                    all_examples.append(word.example)
    custom_words = db.get_custom_words()
    for w in custom_words:
        if w['example'] != correct and (not level or w['level'] == level):
            all_examples.append(w['example'])
    if not all_examples:
        return "✗ " + correct
    return random.choice(all_examples)

def send_poll_question(chat_id: int, word: Word, qtype: str, q_num: int, total: int = 0) -> Optional[telebot.types.Poll]:
    if qtype == "meaning":
        if total == 0:
            question = f"({q_num}) ❓ ما معنى كلمة '{word.eng}'؟"
        else:
            question = f"({q_num}/{total}) ❓ ما معنى كلمة '{word.eng}'؟"
        options = [word.ar]
        for _ in range(3):
            wrong = get_random_wrong_meaning(word.ar, level=word.level)
            options.append(wrong)
        random.shuffle(options)
        correct_id = options.index(word.ar)
        explanation = f"✅ {word.ar}\n📝 مثال: {word.example}"
        
    elif qtype == "example":
        if total == 0:
            question = f"({q_num}) ❓ أي جملة تستخدم كلمة '{word.eng}' بشكل صحيح؟"
        else:
            question = f"({q_num}/{total}) ❓ أي جملة تستخدم كلمة '{word.eng}' بشكل صحيح؟"
        options = [word.example]
        for _ in range(3):
            wrong = get_random_wrong_example(word.example, level=word.level)
            options.append(wrong)
        random.shuffle(options)
        correct_id = options.index(word.example)
        explanation = f"✅ الجملة الصحيحة: {word.example}"
        
    elif qtype == "true_false":
        if random.choice([True, False]):
            statement = f"كلمة '{word.eng}' تعني '{word.ar}'"
            correct = True
        else:
            wrong_ar = get_random_wrong_meaning(word.ar, level=word.level)
            statement = f"كلمة '{word.eng}' تعني '{wrong_ar}'"
            correct = False
        if total == 0:
            question = f"({q_num}) ❓ هل العبارة التالية صحيحة؟\n\n{statement}"
        else:
            question = f"({q_num}/{total}) ❓ هل العبارة التالية صحيحة؟\n\n{statement}"
        options = ["✅ صحيح", "❌ خطأ"]
        correct_id = 0 if correct else 1
        explanation = f"المعنى الصحيح: {word.ar}\nمثال: {word.example}"
    
    else:
        return None
    
    try:
        poll = bot.send_poll(
            chat_id, question, options,
            type='quiz',
            correct_option_id=correct_id,
            explanation=explanation,
            open_period=30,
            is_anonymous=False
        )
        
        def timeout_handler(poll_id):
            with state_lock:
                if poll_id in pending_polls:
                    logger.info(f"انتهت مهلة الاستفتاء {poll_id} للمستخدم {chat_id}")
                    poll_data = pending_polls.pop(poll_id)
                    user_id = poll_data['user_id']
                    chat_id = poll_data['chat_id']
                    state_type = poll_data['state_type']
                    
                    if state_type == 'quiz':
                        with state_lock:
                            state = quiz_states.get(user_id)
                        if state and poll_data['q_index'] == state.current:
                            state.answers.append({
                                "question_number": state.current + 1,
                                "word": poll_data['word'].eng,
                                "user_answer": "لم يجب",
                                "correct_answer": "خطأ (لم يجب)",
                                "is_correct": 0
                            })
                            state.current += 1
                            send_next_quiz_question(chat_id, user_id)
                    elif state_type == 'level_test':
                        with state_lock:
                            state = level_test_states.get(user_id)
                        if state and poll_data['q_index'] == state.current:
                            state.answers.append({
                                "question_number": state.current + 1,
                                "word": poll_data['word'].eng,
                                "user_answer": "لم يجب",
                                "correct_answer": "خطأ (لم يجب)",
                                "is_correct": 0
                            })
                            state.current += 1
                            send_next_level_question(chat_id, user_id)
                    elif state_type == 'infinite':
                        with state_lock:
                            state = infinite_quiz_states.get(user_id)
                        if state and poll_data['q_index'] == state.current:
                            state.answers.append({
                                "question_number": state.current + 1,
                                "word": poll_data['word'].eng,
                                "user_answer": "لم يجب",
                                "correct_answer": "خطأ (لم يجب)",
                                "is_correct": 0
                            })
                            state.current += 1
                            send_next_infinite_question(chat_id, user_id)
            
            with state_lock:
                if poll_id in poll_timeouts:
                    del poll_timeouts[poll_id]
        
        timer = threading.Timer(31.0, timeout_handler, args=[poll.poll.id])
        timer.daemon = True
        timer.start()
        with state_lock:
            poll_timeouts[poll.poll.id] = timer
        
        return poll
    except Exception as e:
        logger.error(f"فشل إرسال الاستفتاء: {e}")
        return None

def start_quiz(chat_id: int, user_id: int, day: int, session: str):
    words = vocab[day][session].copy()
    
    if day > 1:
        review_words = []
        for d in range(max(1, day-3), day):
            for s in ["morning", "noon", "afternoon", "night"]:
                review_words.extend(vocab[d][s][:2])
        if review_words:
            review_sample = random.sample(review_words, min(4, len(review_words)))
            words.extend(review_sample)
    
    custom_words = db.get_custom_words()
    if custom_words:
        sample_custom = random.sample(custom_words, min(2, len(custom_words)))
        for cw in sample_custom:
            words.append(Word(cw['eng'], cw['ar'], cw['example'], cw['level']))
    
    random.shuffle(words)
    quiz_words = words[:8]
    question_types = [random.choice(["meaning", "example", "true_false"]) for _ in range(8)]
    
    with state_lock:
        quiz_states[user_id] = QuizState(
            user_id=user_id,
            day=day,
            session=session,
            words=quiz_words,
            types=question_types,
            total=8
        )
    
    safe_send_message(chat_id, "🎯 **بدء الاختبار**\nسيتم عرض 8 أسئلة. أجب عليها في غضون 30 ثانية لكل سؤال.", parse_mode="Markdown")
    send_next_quiz_question(chat_id, user_id)

def send_next_quiz_question(chat_id: int, user_id: int):
    with state_lock:
        state = quiz_states.get(user_id)
    
    if not state:
        logger.warning(f"حالة اختبار غير موجودة للمستخدم {user_id}")
        return
    
    if state.current >= state.total:
        finish_quiz(chat_id, user_id)
        return
    
    word = state.words[state.current]
    qtype = state.types[state.current]
    
    poll = send_poll_question(chat_id, word, qtype, state.current + 1, state.total)
    
    if poll:
        with state_lock:
            state.poll_ids.append(poll.poll.id)
            pending_polls[poll.poll.id] = {
                "user_id": user_id,
                "chat_id": chat_id,
                "state_type": "quiz",
                "q_index": state.current,
                "word": word,
                "qtype": qtype
            }
    else:
        with state_lock:
            state.current += 1
        send_next_quiz_question(chat_id, user_id)

def finish_quiz(chat_id: int, user_id: int):
    with state_lock:
        state = quiz_states.pop(user_id, None)
    
    if not state:
        return
    
    score = state.score
    total = state.total
    percentage = (score / total) * 100
    
    xp_gained = score * 10
    new_level, total_xp, leveled_up = db.add_xp(user_id, xp_gained)
    streak_info = db.update_streak(user_id)
    
    db.save_quiz_result(user_id, state.day, state.session, score, total, state.answers)
    
    stars = "⭐" * int(percentage / 20) + "✨" * (5 - int(percentage / 20))
    
    msg = f"📊 **نتيجة الاختبار**\n\n"
    msg += f"📅 اليوم {state.day} - {get_session_name(state.session)}\n"
    msg += f"✅ الإجابات الصحيحة: {score}/{total}\n"
    msg += f"📈 النسبة: {percentage:.1f}%\n"
    msg += f"{stars}\n\n"
    msg += f"✨ **المكافآت:**\n"
    msg += f"• +{xp_gained} XP\n"
    msg += f"• المستوى الحالي: {new_level}\n"
    msg += f"• 🔥 التتابع: {streak_info['streak']} يوم\n\n"
    
    if leveled_up:
        msg += f"🎉 **تهانينا! لقد ارتفع مستواك إلى {new_level}**\n"
    
    if percentage >= 80:
        msg += "🌟 **أداء ممتاز!**"
    elif percentage >= 60:
        msg += "👍 **أداء جيد جداً**"
    else:
        msg += "💪 **حاول مرة أخرى لتحسين نتيجتك**"
    
    safe_send_message(chat_id, msg, parse_mode="Markdown")
    
    if state.session != "extra":
        db.mark_session_completed(user_id, state.day, state.session)
        
        completed = db.get_completed_sessions(user_id, state.day)
        all_sessions = ["morning", "noon", "afternoon", "night"]
        remaining = [s for s in all_sessions if s not in completed]
        
        if remaining:
            next_sesh = remaining[0]
            markup = InlineKeyboardMarkup()
            markup.add(create_colored_button(
                f"⏩ الانتقال إلى {get_session_name(next_sesh)}",
                f"session_{state.day}_{next_sesh}",
                "🟢"
            ))
            safe_send_message(
                chat_id,
                f"✅ تم إكمال جلسة {get_session_name(state.session)}!\nتابع إلى الجلسة التالية:",
                reply_markup=markup
            )
        else:
            safe_send_message(chat_id, f"🎉 **تهانينا! لقد أكملت اليوم {state.day} بنجاح!**")
            
            current_day = db.get_user_day(user_id)
            if state.day == current_day and state.day < 30:
                db.update_user_day(user_id, current_day + 1)
            
            if state.day < 30:
                can_access, message = can_access_day(user_id, state.day + 1)
                markup = InlineKeyboardMarkup(row_width=1)
                markup.add(create_colored_button("🔙 العودة إلى اليوم", f"day_{state.day}", "🔵"))
                markup.add(create_colored_button("🎮 تدريبات إضافية", f"extra_{state.day}", "🟡"))
                
                if can_access:
                    markup.add(create_colored_button("🚀 ابدأ اليوم التالي", f"day_{state.day + 1}", "🟢"))
                    safe_send_message(chat_id, "يمكنك البدء باليوم التالي الآن!", reply_markup=markup)
                else:
                    markup.add(create_colored_button(f"⏳ انتظر", "wait", "🔴"))
                    safe_send_message(chat_id, message or "الرجاء الانتظار لبدء اليوم التالي", reply_markup=markup)
    else:
        markup = InlineKeyboardMarkup()
        markup.add(
            create_colored_button("🔙 العودة لليوم", f"day_{state.day}", "🔵"),
            create_colored_button("🎮 تدريب آخر", f"extra_{state.day}", "🟢")
        )
        safe_send_message(chat_id, "🎮 انتهى التدريب الإضافي!", reply_markup=markup)

# ================== دوال التقدير الذاتي للمستوى + الاختبار المخصص ==================
def show_level_estimation(chat_id: int, user_id: int):
    markup = InlineKeyboardMarkup(row_width=2)
    buttons = [
        create_colored_button("🔰 مبتدئ", "level_beginner", "🟢"),
        create_colored_button("⚜️ متوسط", "level_intermediate", "🟡"),
        create_colored_button("🏅 متقدم", "level_advanced", "🔴")
    ]
    markup.add(*buttons)
    markup.add(create_colored_button("🔙 العودة", "back_main", "🔴"))
    
    safe_send_message(
        chat_id,
        "🎯 **اختر مستواك الحالي**\n\n"
        "سيتم عرض 10 أسئلة من المستوى الذي تختاره. بناءً على إجاباتك، سنحدد مستواك الفعلي ونوجهك للأيام المناسبة.",
        parse_mode="Markdown",
        reply_markup=markup
    )

def start_level_test_by_choice(chat_id: int, user_id: int, chosen_level: str):
    """بدء اختبار تحديد المستوى بناءً على المستوى المختار (مبتدئ/متوسط/متقدم)"""
    # جمع الكلمات من المستوى المختار فقط
    level_words = []
    for day in range(1, 31):
        for session in ["morning", "noon", "afternoon", "night"]:
            for word in vocab[day][session]:
                if word.level == chosen_level:
                    level_words.append(word)
    
    # إضافة كلمات مخصصة من نفس المستوى إن وجدت
    custom_words = db.get_custom_words()
    for cw in custom_words:
        if cw['level'] == chosen_level:
            level_words.append(Word(cw['eng'], cw['ar'], cw['example'], cw['level']))
    
    if len(level_words) < 10:
        # إذا لم تكن هناك كلمات كافية من هذا المستوى، نستخدم جميع الكلمات
        level_words = []
        for day in range(1, 31):
            for session in ["morning", "noon", "afternoon", "night"]:
                level_words.extend(vocab[day][session])
        random.shuffle(level_words)
    
    # اختيار 10 كلمات عشوائية
    test_words = random.sample(level_words, min(10, len(level_words)))
    question_types = [random.choice(["meaning", "example", "true_false"]) for _ in range(10)]
    
    with state_lock:
        state = LevelTestState(
            user_id=user_id,
            words=test_words,
            types=question_types,
            total=10,
            percent=0  # لا نستخدمها بعد الآن
        )
        level_test_states[user_id] = state
    
    safe_send_message(
        chat_id,
        f"📋 **اختبار تحديد المستوى - {chosen_level}**\n"
        f"سيتم عرض 10 أسئلة. أجب في غضون 30 ثانية لكل سؤال.\n\n"
        f"⚠️ حاول الإجابة بأفضل ما لديك للحصول على تقييم دقيق.",
        parse_mode="Markdown"
    )
    send_next_level_question(chat_id, user_id)

def send_next_level_question(chat_id: int, user_id: int, mandatory=False):
    with state_lock:
        state = level_test_states.get(user_id)
    
    if not state:
        return
    
    if state.current >= state.total:
        finish_customized_test(chat_id, user_id, mandatory=mandatory)
        return
    
    word = state.words[state.current]
    qtype = state.types[state.current]
    
    poll = send_poll_question(chat_id, word, qtype, state.current + 1, state.total)
    
    if poll:
        with state_lock:
            state.poll_ids.append(poll.poll.id)
            pending_polls[poll.poll.id] = {
                "user_id": user_id,
                "chat_id": chat_id,
                "state_type": "level_test",
                "q_index": state.current,
                "word": word,
                "qtype": qtype
            }
    else:
        with state_lock:
            state.current += 1
        send_next_level_question(chat_id, user_id, mandatory)

def finish_customized_test(chat_id: int, user_id: int, mandatory=False):
    with state_lock:
        state = level_test_states.pop(user_id, None)
    
    if not state:
        return
    
    score = state.score
    total = state.total
    percentage = int((score / total) * 100)
    
    # تحديد المستوى الفعلي بناءً على النسبة
    if percentage >= 70:
        actual_level = "متقدم"
        recommended_start_day = 21
        level_name = "متقدم (ممتاز)"
    elif percentage >= 40:
        actual_level = "متوسط"
        recommended_start_day = 11
        level_name = "متوسط (جيد)"
    else:
        actual_level = "مبتدئ"
        recommended_start_day = 1
        level_name = "مبتدئ (يحتاج تحسين)"
    
    # حفظ المستوى في قاعدة البيانات
    conn = sqlite3.connect('toefl_master.db')
    c = conn.cursor()
    c.execute('''INSERT INTO level_test_results 
                 (user_id, test_date, score, total, percentage, details) 
                 VALUES (?,?,?,?,?,?)''',
              (user_id, datetime.now().isoformat(), score, total, percentage, json.dumps(state.answers)))
    c.execute("UPDATE users SET level=?, level_tested=1 WHERE user_id=?", (percentage, user_id))
    if mandatory:
        c.execute("UPDATE users SET initial_test_done=1 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()
    
    # منح XP
    xp_gained = score * 5
    new_level, total_xp, leveled_up = db.add_xp(user_id, xp_gained)
    
    # بناء الرسالة
    msg = f"📊 **نتيجة اختبار المستوى**\n\n"
    msg += f"✅ الإجابات الصحيحة: {score}/{total}\n"
    msg += f"📈 نسبتك الفعلية: {percentage}%\n"
    msg += f"🏅 تصنيفك: {level_name}\n\n"
    msg += f"🎯 **بناءً على نتيجتك، نوصيك بالبدء من الأيام المتخصصة لمستوى {actual_level}.**\n"
    msg += f"📅 الأيام {recommended_start_day} إلى 30 متاحة لك الآن.\n\n"
    msg += f"✨ حصلت على {xp_gained} XP كمكافأة!"
    
    safe_send_message(chat_id, msg, parse_mode="Markdown")
    
    # عرض الأيام المناسبة
    markup = InlineKeyboardMarkup(row_width=5)
    for day in range(recommended_start_day, 31):
        markup.add(create_colored_button(f"{day}", f"day_{day}", "🟢" if day == recommended_start_day else "🔵"))
    markup.add(create_colored_button("🔙 القائمة الرئيسية", "back_main", "🔴"))
    
    safe_send_message(
        chat_id,
        f"📅 **اختر يومًا للبدء (من {recommended_start_day} إلى 30):**",
        reply_markup=markup
    )

# ================== دوال الاختبار اللانهائي (رفع المستوى) ==================
def start_infinite_quiz(chat_id: int, user_id: int):
    all_words = []
    for day in range(1, 31):
        for session in ["morning", "noon", "afternoon", "night"]:
            all_words.extend(vocab[day][session])
    
    custom_words = db.get_custom_words()
    all_words.extend([Word(w['eng'], w['ar'], w['example'], w['level']) for w in custom_words])
    
    random.shuffle(all_words)
    initial_words = all_words[:20]
    question_types = [random.choice(["meaning", "example", "true_false"]) for _ in range(20)]
    
    with state_lock:
        infinite_quiz_states[user_id] = InfiniteQuizState(
            user_id=user_id,
            words=initial_words,
            types=question_types,
            current=0,
            score=0
        )
    
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add(KeyboardButton("🏁 إنهاء التحدي"))
    
    safe_send_message(
        chat_id,
        "🏆 **تحدي رفع المستوى اللانهائي**\n\nأجب على أكبر عدد ممكن من الأسئلة. كل إجابة صحيحة تمنحك XP إضافية. يمكنك الاستمرار إلى ما لا نهاية!\n\nلإنهاء التحدي في أي وقت، اضغط على زر '🏁 إنهاء التحدي' في لوحة المفاتيح.",
        parse_mode="Markdown",
        reply_markup=markup
    )
    send_next_infinite_question(chat_id, user_id)

def send_next_infinite_question(chat_id: int, user_id: int):
    with state_lock:
        state = infinite_quiz_states.get(user_id)
    
    if not state:
        return
    
    if state.current >= len(state.words):
        all_words = []
        for day in range(1, 31):
            for session in ["morning", "noon", "afternoon", "night"]:
                all_words.extend(vocab[day][session])
        custom_words = db.get_custom_words()
        all_words.extend([Word(w['eng'], w['ar'], w['example'], w['level']) for w in custom_words])
        random.shuffle(all_words)
        state.words = all_words[:20]
        state.types = [random.choice(["meaning", "example", "true_false"]) for _ in range(20)]
        state.current = 0
    
    word = state.words[state.current]
    qtype = state.types[state.current]
    
    poll = send_poll_question(chat_id, word, qtype, state.score + 1, 0)
    
    if poll:
        with state_lock:
            state.poll_ids.append(poll.poll.id)
            pending_polls[poll.poll.id] = {
                "user_id": user_id,
                "chat_id": chat_id,
                "state_type": "infinite",
                "q_index": state.current,
                "word": word,
                "qtype": qtype
            }
    else:
        with state_lock:
            state.current += 1
        send_next_infinite_question(chat_id, user_id)

def finish_infinite_quiz(chat_id: int, user_id: int, forced: bool = False):
    with state_lock:
        state = infinite_quiz_states.pop(user_id, None)
    
    if not state:
        return
    
    score = state.score
    total_questions = state.current
    xp_gained = score * 2
    new_level, total_xp, leveled_up = db.add_xp(user_id, xp_gained)
    
    db.update_infinite_stats(user_id, score, total_questions)
    
    msg = f"🏁 **نتيجة تحدي رفع المستوى**\n\n"
    msg += f"✅ الإجابات الصحيحة: {score}\n"
    msg += f"📊 عدد الأسئلة: {total_questions}\n"
    msg += f"✨ XP المكتسب: {xp_gained}\n"
    msg += f"🏅 مستواك الحالي: {new_level}\n\n"
    
    if leveled_up:
        msg += f"🎉 **تهانينا! لقد ارتفع مستواك إلى {new_level}**\n"
    
    msg += "يمكنك بدء تحدي جديد في أي وقت!"
    
    safe_send_message(chat_id, msg, parse_mode="Markdown", reply_markup=get_main_keyboard(user_id))

@bot.message_handler(commands=['stop_infinite'])
@require_subscription
def cmd_stop_infinite(message: Message):
    user_id = message.from_user.id
    if user_id in infinite_quiz_states:
        finish_infinite_quiz(message.chat.id, user_id, forced=True)
    else:
        safe_send_message(message.chat.id, "❌ ليس لديك تحدي نشط حالياً.")

# ================== دوال المساعدة بين المستخدمين ==================
def show_help_menu(message: Message):
    """عرض قائمة المساعدة (طلب مساعدة أو سؤال)"""
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        create_colored_button("📝 طلب مساعدة", "help_request_type", "🟢"),
        create_colored_button("❓ سؤال", "help_question_type", "🔵")
    )
    safe_send_message(message.chat.id, "🆘 **مركز المساعدة**\n\nاختر نوع طلبك:", parse_mode="Markdown", reply_markup=markup)

def ask_for_help_question(message: Message, help_type: str):
    """طلب من المستخدم كتابة مشكلته أو سؤاله"""
    user_id = message.from_user.id
    safe_send_message(message.chat.id, f"📝 أرسل {help_type} الآن (نص حر):")
    bot.register_next_step_handler(message, lambda m: process_help_question(m, help_type))

def process_help_question(message: Message, help_type: str):
    user_id = message.from_user.id
    question = message.text.strip()
    if not question:
        safe_send_message(message.chat.id, "❌ لا يمكن إرسال نص فارغ.")
        return
    
    # حفظ الطلب في قاعدة البيانات
    request_id = db.add_help_request(user_id, f"[{help_type}] {question}")
    
    # إرسال الطلب للمالك للموافقة
    markup = InlineKeyboardMarkup()
    markup.add(
        create_colored_button("✅ نشر للجميع", f"approve_help_{request_id}", "🟢"),
        create_colored_button("❌ رفض", f"reject_help_{request_id}", "🔴")
    )
    safe_send_message(OWNER_ID, f"📢 **طلب {help_type} جديد**\nمن: {user_id}\nالنص:\n{question}", reply_markup=markup)
    safe_send_message(message.chat.id, "✅ تم إرسال طلبك إلى الإدارة. سيتم نشره بعد الموافقة.")

def publish_help_request(request_id: int, question: str, user_id: int):
    """نشر طلب المساعدة لجميع المستخدمين"""
    users = db.get_all_users()
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        create_colored_button("💬 رد", f"reply_help_{request_id}_{user_id}", "🟢"),
        create_colored_button("⚠️ إبلاغ", f"report_help_{request_id}_{user_id}", "🔴")
    )
    sent = 0
    for uid in users:
        if not db.is_banned(uid):
            try:
                bot.send_message(uid, f"🆘 **طلب مساعدة من مستخدم:**\n\n{question}\n\nيمكنك الرد عليه بشكل خاص أو الإبلاغ عن سوء الاستخدام.", parse_mode="Markdown", reply_markup=markup)
                sent += 1
                time.sleep(0.05)
            except:
                pass
    logger.info(f"تم نشر طلب المساعدة {request_id} لـ {sent} مستخدم")

def ask_for_reply(message: Message, request_id: int, requester_id: int):
    """طلب من المستخدم كتابة رده الخاص"""
    responder_id = message.from_user.id
    safe_send_message(message.chat.id, "📝 اكتب ردك على هذا الطلب (سيصل فقط إلى صاحب الطلب):")
    bot.register_next_step_handler(message, lambda m: send_reply_to_requester(m, request_id, requester_id))

def send_reply_to_requester(message: Message, request_id: int, requester_id: int):
    responder_id = message.from_user.id
    response_text = message.text.strip()
    if not response_text:
        safe_send_message(message.chat.id, "❌ لا يمكن إرسال رد فارغ.")
        return
    
    # حفظ الرد في قاعدة البيانات
    db.add_help_response(request_id, responder_id, response_text)
    
    # إرسال الرد إلى صاحب الطلب
    try:
        bot.send_message(requester_id, f"💬 **رد على طلب مساعدتك**\nمن: {responder_id}\nالرد:\n{response_text}")
        safe_send_message(message.chat.id, "✅ تم إرسال ردك إلى المستخدم.")
    except Exception as e:
        safe_send_message(message.chat.id, f"❌ فشل إرسال الرد: {e}")

def report_help_abuse(call: CallbackQuery, request_id: int, requester_id: int):
    """إبلاغ عن طلب مساعدة مسيء"""
    reporter_id = call.from_user.id
    report_reason = "سوء استخدام في طلب المساعدة"
    db.create_report(reporter_id, requester_id, report_reason)
    bot.answer_callback_query(call.id, "✅ تم إبلاغ الإدارة. شكراً لك.", show_alert=False)
    safe_send_message(OWNER_ID, f"⚠️ **إبلاغ عن طلب مساعدة**\nالطلب رقم: {request_id}\nمن: {requester_id}\nالمُبلِّغ: {reporter_id}")

# ================== دوال الرسائل الجماعية (بموافقة الأدمن) ==================
def request_chat(message: Message):
    user_id = message.from_user.id
    safe_send_message(
        message.chat.id,
        "📝 أرسل الرسالة التي تريد إرسالها لجميع المستخدمين (سيتم مراجعتها من قبل المشرف):"
    )
    with state_lock:
        broadcast_states[user_id] = BroadcastState(admin_id=user_id, type="group", group_sender=user_id)
    bot.register_next_step_handler(message, process_broadcast_message_request)

def process_broadcast_message_request(message: Message):
    user_id = message.from_user.id
    msg_text = message.text
    
    with state_lock:
        state = broadcast_states.pop(user_id, None)
    
    if not state or state.type != "group":
        return
    
    state.group_message = msg_text
    state.group_sender = user_id
    
    request_id = f"{user_id}_{int(time.time())}"
    with state_lock:
        broadcast_states[request_id] = state
    
    admins = db.get_admins()
    for admin_id in admins:
        if has_permission(admin_id, 'can_broadcast') or admin_id == OWNER_ID:
            markup = InlineKeyboardMarkup()
            markup.add(
                create_colored_button("✅ قبول الإرسال للجميع", f"approve_group_{request_id}", "🟢"),
                create_colored_button("❌ رفض", f"reject_group_{request_id}", "🔴")
            )
            safe_send_message(
                admin_id,
                f"📢 **طلب إرسال رسالة جماعية**\n\n"
                f"من: {user_id} - {message.from_user.first_name}\n"
                f"الرسالة: {msg_text}",
                parse_mode="Markdown",
                reply_markup=markup
            )
    
    safe_send_message(message.chat.id, "✅ تم إرسال طلبك إلى المشرف. سيتم إعلامك عند الموافقة.")

# ================== دوال عرض المعلومات ==================
def show_favorites(message: Message):
    user_id = message.from_user.id
    favorites = db.get_favorites(user_id)
    
    if not favorites:
        safe_send_message(
            message.chat.id,
            "⭐ لا توجد كلمات مفضلة بعد.\nأثناء عرض الكلمات اضغط على ⭐ لإضافتها إلى المفضلة."
        )
        return
    
    msg = "⭐ **كلماتك المفضلة:**\n\n"
    for i, fav in enumerate(favorites, 1):
        msg += f"{i}. **{fav['word']}** - {fav['meaning']}\n"
    
    safe_send_message(message.chat.id, msg, parse_mode="Markdown")

def show_stats(message: Message):
    user_id = message.from_user.id
    
    total_sessions = db.get_total_completed_sessions(user_id)
    current_day = db.get_user_day(user_id)
    level_info = db.get_level_info(user_id)
    stats = db.get_user_stats(user_id)
    user = db.get_user(user_id)
    infinite_stats = db.get_infinite_stats(user_id)
    
    msg = f"📊 **إحصائياتك الشخصية**\n\n"
    msg += f"✅ **الجلسات المنجزة:** {total_sessions}/120\n"
    msg += f"📅 **اليوم الحالي:** {current_day}\n"
    msg += f"🔥 **التتابع:** {level_info['streak']} يوم\n"
    msg += f"🏆 **أطول تتابع:** {level_info['longest_streak']}\n"
    msg += f"⭐ **المفضلة:** {stats['favorites_count']}\n"
    msg += f"📈 **متوسط النتائج:** {stats['avg_score']}%\n"
    msg += f"🏅 **مستوى XP:** {level_info['level']}\n"
    msg += f"✨ **إجمالي XP:** {level_info['total_xp']}\n"
    msg += f"🏋️‍♂️ **تحديات لانهائية:** {infinite_stats['total_questions']} سؤال، {infinite_stats['correct_answers']} صحيحة\n"
    
    if user:
        msg += f"🎯 **مستواك التقديري:** {user.get('level', 0)}%"
    
    safe_send_message(message.chat.id, msg, parse_mode="Markdown")

def request_certificate(message: Message):
    user_id = message.from_user.id
    total_sessions = db.get_total_completed_sessions(user_id)
    
    if total_sessions < 120:
        remaining = 120 - total_sessions
        safe_send_message(
            message.chat.id,
            f"🎓 لم تكمل البرنامج بعد! تحتاج {remaining} جلسة أخرى للحصول على الشهادة."
        )
        return
    
    safe_send_message(message.chat.id, "📝 أرسل اسمك الذي تريد كتابته على الشهادة:")
    bot.register_next_step_handler(message, process_certificate_name)

def process_certificate_name(message: Message):
    user_id = message.from_user.id
    name = message.text
    
    safe_send_message(
        message.chat.id,
        f"🎉 **تهانينا {name}!**\nلقد أكملت برنامج تحضير التوفل بنجاح.\n\nسيتم إرسال الشهادة قريباً (قيد التطوير).",
        parse_mode="Markdown"
    )

def show_leaderboard(message: Message):
    leaders = db.get_leaderboard(10)
    
    if not leaders:
        safe_send_message(message.chat.id, "لا توجد بيانات كافية بعد.")
        return
    
    msg = "🏆 **لوحة المتصدرين**\n\n"
    medals = ["🥇", "🥈", "🥉"]
    
    for i, user in enumerate(leaders, 1):
        medal = medals[i-1] if i <= 3 else f"{i}."
        msg += f"{medal} **{user['name']}**\n"
        msg += f"   • المستوى: {user['level']} | XP: {user['total_xp']}\n"
        msg += f"   • 🔥 {user['streak']} يوم\n\n"
    
    markup = InlineKeyboardMarkup()
    markup.add(create_colored_button("🔄 تحديث", "refresh_leaderboard", "🟢"))
    markup.add(create_colored_button("⚠️ الإبلاغ عن مستخدم", "report_user", "🔴"))
    
    safe_send_message(message.chat.id, msg, parse_mode="Markdown", reply_markup=markup)

def show_settings(message: Message):
    markup = InlineKeyboardMarkup()
    markup.add(
        create_colored_button("🔔 تفعيل التذكيرات", "reminders_on", "🟢"),
        create_colored_button("🔕 تعطيل التذكيرات", "reminders_off", "🔴"),
        create_colored_button("⏰ تذكير فوري", "remind_now", "🔵")
    )
    
    safe_send_message(message.chat.id, "⚙️ **الإعدادات**\nاختر الخيار المناسب:", parse_mode="Markdown", reply_markup=markup)

# ================== دوال إدارة الأدمن ==================
def show_admin_stats(chat_id: int):
    conn = sqlite3.connect('toefl_master.db')
    c = conn.cursor()
    
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    
    week_ago = (datetime.now() - timedelta(days=7)).isoformat()
    c.execute("SELECT COUNT(*) FROM users WHERE last_active > ?", (week_ago,))
    active_users = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM progress WHERE completed=1")
    total_sessions = c.fetchone()[0]
    
    c.execute("SELECT AVG(score*1.0/total) FROM daily_results")
    avg_row = c.fetchone()
    avg_score = round(avg_row[0] * 100, 2) if avg_row and avg_row[0] else 0
    
    c.execute("SELECT COUNT(*) FROM chat_requests WHERE status='pending'")
    pending_chats = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM infinite_quiz_stats")
    infinite_players = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM admins")
    admin_count = c.fetchone()[0]
    
    conn.close()
    
    msg = "📊 **إحصائيات البوت**\n\n"
    msg += f"👥 إجمالي المستخدمين: {total_users}\n"
    msg += f"📱 نشطون آخر 7 أيام: {active_users}\n"
    msg += f"✅ إجمالي الجلسات: {total_sessions}\n"
    msg += f"📈 متوسط النتائج: {avg_score}%\n"
    msg += f"⏳ طلبات محادثة معلقة: {pending_chats}\n"
    msg += f"🏋️‍♂️ لاعبو التحدي اللانهائي: {infinite_players}\n"
    msg += f"👑 عدد الأدمن: {admin_count}"
    
    safe_send_message(chat_id, msg, parse_mode="Markdown")

def show_admin_logs(chat_id: int):
    logs = db.get_admin_logs(20)
    msg = "📋 **آخر 20 حدث**\n\n"
    for log in logs:
        msg += f"🕒 {log['timestamp'][:16]} - أدمن {log['admin_id']}\n"
        msg += f"   {log['action']}: {log['details']}\n\n"
    safe_send_message(chat_id, msg, parse_mode="Markdown")

def show_users_page(chat_id: int, page: int = 0, message_id: int = None):
    users, total = db.get_all_users_with_details(page, page_size=10)
    total_pages = (total + 9) // 10
    
    msg = f"📋 **قائمة المستخدمين (الصفحة {page+1}/{total_pages})**\n\n"
    for i, user in enumerate(users, 1):
        msg += f"{i}. **{user['name']}** (@{user['username'] or 'لا يوجد'})\n"
        msg += f"   🆔 {user['user_id']} | 📅 {user['join_date'][:10]}\n"
        msg += f"   🏅 المستوى {user['level']} | 🔥 {user['streak']} | ✅ {user['sessions']} جلسة\n\n"
    
    markup = InlineKeyboardMarkup(row_width=2)
    if page > 0:
        markup.add(create_colored_button("◀️ السابق", f"users_page_{page-1}", "🔵"))
    if page < total_pages - 1:
        markup.add(create_colored_button("التالي ▶️", f"users_page_{page+1}", "🔵"))
    markup.add(create_colored_button("🔙 العودة", "admin_back_main", "🔴"))
    
    try:
        if message_id:
            bot.edit_message_text(msg, chat_id, message_id, parse_mode="Markdown", reply_markup=markup)
        else:
            safe_send_message(chat_id, msg, parse_mode="Markdown", reply_markup=markup)
    except Exception as e:
        logger.error(f"فشل عرض الصفحة: {e}")

def show_banned_words_menu(chat_id: int):
    words = db.get_banned_words()
    msg = "🚫 **الكلمات الممنوعة**\n\n"
    if words:
        for i, w in enumerate(words, 1):
            msg += f"{i}. {w}\n"
    else:
        msg += "لا توجد كلمات ممنوعة.\n"
    
    markup = InlineKeyboardMarkup()
    markup.add(create_colored_button("➕ إضافة كلمة", "admin_add_banned_word", "🟢"))
    markup.add(create_colored_button("🗑️ حذف كلمة", "admin_remove_banned_word", "🔴"))
    markup.add(create_colored_button("🔙 العودة", "admin_back_main", "🔵"))
    
    safe_send_message(chat_id, msg, parse_mode="Markdown", reply_markup=markup)

def show_auto_replies_menu(chat_id: int):
    replies = db.get_all_auto_replies()
    msg = "🤖 **الردود التلقائية**\n\n"
    if replies:
        for r in replies:
            msg += f"🔑 {r['keyword']} ➜ {r['response']}\n"
    else:
        msg += "لا توجد ردود تلقائية.\n"
    
    markup = InlineKeyboardMarkup()
    markup.add(create_colored_button("➕ إضافة رد", "admin_add_auto_reply", "🟢"))
    markup.add(create_colored_button("🗑️ حذف رد", "admin_remove_auto_reply", "🔴"))
    markup.add(create_colored_button("🔙 العودة", "admin_back_main", "🔵"))
    
    safe_send_message(chat_id, msg, parse_mode="Markdown", reply_markup=markup)

def show_reports_menu(chat_id: int):
    reports = db.get_pending_reports()
    msg = "⚠️ **الإبلاغات المعلقة**\n\n"
    if reports:
        for r in reports:
            msg += f"📌 {r['id']}: من {r['reporter_id']} على {r['reported_id']}\n"
            msg += f"السبب: {r['reason']}\n"
            msg += f"التاريخ: {r['created_at'][:16]}\n\n"
    else:
        msg += "لا توجد إبلاغات معلقة.\n"
    
    markup = InlineKeyboardMarkup()
    markup.add(create_colored_button("🔙 العودة", "admin_back_main", "🔵"))
    
    safe_send_message(chat_id, msg, parse_mode="Markdown", reply_markup=markup)

def process_report(message: Message):
    user_id = message.from_user.id
    text = message.text
    try:
        parts = text.split(maxsplit=1)
        reported_id = int(parts[0])
        reason = parts[1] if len(parts) > 1 else "بدون سبب"
        report_id = db.create_report(user_id, reported_id, reason)
        safe_send_message(message.chat.id, f"✅ تم الإبلاغ بنجاح. معرف البلاغ: {report_id}")
    except Exception as e:
        safe_send_message(message.chat.id, f"❌ خطأ: {e}")

# ================== دوال معالجة أدمن متعددة الخطوات ==================
def prompt_for_admin_input(chat_id: int, user_id: int, action: str, prompt: str, next_handler):
    safe_send_message(chat_id, prompt)
    with state_lock:
        admin_states[user_id] = {"action": action, "next": next_handler}

def handle_admin_input(message: Message):
    user_id = message.from_user.id
    with state_lock:
        state = admin_states.pop(user_id, None)
    if not state:
        return
    action = state["action"]
    text = message.text.strip()

    if action == "reset_words":
        if text.lower() != "نعم":
            safe_send_message(message.chat.id, "❌ تم الإلغاء.")
            return
        db.clear_custom_words()
        db.log_admin_action(user_id, "reset_words", "Cleared custom words")
        safe_send_message(message.chat.id, "✅ تم إعادة ضبط الكلمات المخصصة.")
        return

    if action == "add_admin":
        try:
            target_id = int(text)
            db.add_admin(target_id, {})
            db.log_admin_action(user_id, "add_admin", f"Added admin {target_id}")
            safe_send_message(message.chat.id, f"✅ تم إضافة المستخدم {target_id} كأدمن.")
        except:
            safe_send_message(message.chat.id, "❌ خطأ: المعرف غير صحيح.")
    elif action == "remove_admin":
        try:
            target_id = int(text)
            db.remove_admin(target_id)
            db.log_admin_action(user_id, "remove_admin", f"Removed admin {target_id}")
            safe_send_message(message.chat.id, f"✅ تم إزالة الأدمن {target_id}.")
        except:
            safe_send_message(message.chat.id, "❌ خطأ: المعرف غير صحيح.")
    elif action == "ban_user":
        try:
            target_id = int(text)
            db.ban_user(target_id, user_id, "سبب غير محدد")
            db.log_admin_action(user_id, "ban_user", f"Banned user {target_id}")
            safe_send_message(message.chat.id, f"✅ تم حظر المستخدم {target_id}.")
        except:
            safe_send_message(message.chat.id, "❌ خطأ: المعرف غير صحيح.")
    elif action == "unban_user":
        try:
            target_id = int(text)
            db.unban_user(target_id)
            db.log_admin_action(user_id, "unban_user", f"Unbanned user {target_id}")
            safe_send_message(message.chat.id, f"✅ تم إلغاء حظر المستخدم {target_id}.")
        except:
            safe_send_message(message.chat.id, "❌ خطأ: المعرف غير صحيح.")
    elif action == "reset_user":
        try:
            target_id = int(text)
            db.reset_user_progress(target_id)
            db.log_admin_action(user_id, "reset_user", f"Reset user {target_id}")
            safe_send_message(message.chat.id, f"✅ تم إعادة تعيين المستخدم {target_id}.")
        except:
            safe_send_message(message.chat.id, "❌ خطأ: المعرف غير صحيح.")
    elif action == "send_private":
        try:
            target_id = int(text)
            with state_lock:
                admin_states[user_id] = {"action": "send_private_msg", "target": target_id}
            safe_send_message(message.chat.id, "📝 أرسل الرسالة التي تريد إرسالها:")
        except:
            safe_send_message(message.chat.id, "❌ خطأ: المعرف غير صحيح.")
    elif action == "send_private_msg":
        target_id = state["target"]
        try:
            bot.send_message(target_id, f"📨 **رسالة من الإدارة:**\n\n{text}", parse_mode="Markdown")
            safe_send_message(message.chat.id, f"✅ تم إرسال الرسالة إلى {target_id}.")
            db.log_admin_action(user_id, "send_private", f"Sent to {target_id}")
        except:
            safe_send_message(message.chat.id, f"❌ فشل إرسال الرسالة إلى {target_id}.")
    elif action == "add_word":
        parts = text.split("|")
        if len(parts) >= 4:
            eng, ar, example, level = parts[0].strip(), parts[1].strip(), parts[2].strip(), parts[3].strip()
            if level not in ["مبتدئ", "متوسط", "متقدم"]:
                level = "متوسط"
            db.add_custom_word(eng, ar, example, level, user_id)
            safe_send_message(message.chat.id, f"✅ تمت إضافة الكلمة '{eng}' بنجاح.")
            db.log_admin_action(user_id, "add_word", f"Added word: {eng}")
        else:
            safe_send_message(message.chat.id, "❌ الصيغة غير صحيحة. استخدم: كلمة|معنى|جملة|المستوى")
    elif action == "delete_word":
        try:
            word_id = int(text)
            db.delete_custom_word(word_id)
            safe_send_message(message.chat.id, f"✅ تم حذف الكلمة بنجاح.")
            db.log_admin_action(user_id, "delete_word", f"Deleted word ID {word_id}")
        except:
            safe_send_message(message.chat.id, "❌ خطأ: المعرف غير صحيح.")
    elif action == "broadcast_all":
        users = db.get_all_users()
        success = 0
        for uid in users:
            if not db.is_banned(uid):
                try:
                    bot.send_message(uid, f"📢 **إذاعة من الإدارة:**\n\n{text}", parse_mode="Markdown")
                    success += 1
                    time.sleep(0.05)
                except:
                    pass
        safe_send_message(message.chat.id, f"✅ تم إرسال الإذاعة لـ {success} مستخدم.")
        db.log_admin_action(user_id, "broadcast_all", f"Sent to {success} users")
    elif action == "broadcast_target":
        try:
            ids_part, msg_part = text.split("|", 1)
            target_ids = [int(x.strip()) for x in ids_part.split(",")]
            success = 0
            for uid in target_ids:
                try:
                    bot.send_message(uid, f"📢 **رسالة خاصة:**\n\n{msg_part}", parse_mode="Markdown")
                    success += 1
                except:
                    pass
            safe_send_message(message.chat.id, f"✅ تم إرسال الرسالة لـ {success} من {len(target_ids)} مستخدم.")
            db.log_admin_action(user_id, "broadcast_target", f"Sent to {success} users")
        except:
            safe_send_message(message.chat.id, "❌ الصيغة غير صحيحة. استخدم: معرف1,معرف2|الرسالة")
    elif action == "schedule_broadcast":
        try:
            time_str, msg = text.split("|", 1)
            scheduled_time = datetime.strptime(time_str.strip(), "%Y-%m-%d %H:%M")
            db.schedule_broadcast(user_id, msg, scheduled_time)
            safe_send_message(message.chat.id, f"✅ تم جدولة الإذاعة في {scheduled_time}.")
            db.log_admin_action(user_id, "schedule_broadcast", f"Scheduled at {scheduled_time}")
        except:
            safe_send_message(message.chat.id, "❌ صيغة غير صحيحة. استخدم: YYYY-MM-DD HH:MM|الرسالة")
    elif action == "set_channel":
        if text.strip():
            db.set_config("force_channel", text.strip())
            global FORCE_CHANNEL
            FORCE_CHANNEL = text.strip()
            safe_send_message(message.chat.id, f"✅ تم تعيين القناة الإجبارية: {text}")
            db.log_admin_action(user_id, "set_channel", f"Set to {text}")
        else:
            db.set_config("force_channel", "")
            FORCE_CHANNEL = None
            safe_send_message(message.chat.id, "✅ تم إلغاء القناة الإجبارية.")
    elif action == "reminder_settings":
        if text.lower() == "on":
            db.set_config("reminders_enabled", "1")
            safe_send_message(message.chat.id, "✅ تم تفعيل التذكيرات.")
        elif text.lower() == "off":
            db.set_config("reminders_enabled", "0")
            safe_send_message(message.chat.id, "✅ تم تعطيل التذكيرات.")
        else:
            safe_send_message(message.chat.id, "❌ اختر 'on' أو 'off'.")
    elif action == "maintenance":
        if text.lower() == "on":
            db.set_maintenance_mode(True)
            safe_send_message(message.chat.id, "⚠️ تم تفعيل وضع الصيانة. فقط الأدمن يمكنهم استخدام البوت.")
        elif text.lower() == "off":
            db.set_maintenance_mode(False)
            safe_send_message(message.chat.id, "✅ تم إلغاء وضع الصيانة.")
        else:
            safe_send_message(message.chat.id, "❌ اختر 'on' أو 'off'.")
    elif action == "add_banned_word":
        word = text.strip().lower()
        db.add_banned_word(word, user_id)
        safe_send_message(message.chat.id, f"✅ تمت إضافة الكلمة '{word}' إلى القائمة الممنوعة.")
        db.log_admin_action(user_id, "add_banned_word", f"Added {word}")
    elif action == "remove_banned_word":
        word = text.strip().lower()
        db.remove_banned_word(word)
        safe_send_message(message.chat.id, f"✅ تمت إزالة الكلمة '{word}' من القائمة الممنوعة.")
        db.log_admin_action(user_id, "remove_banned_word", f"Removed {word}")
    elif action == "add_auto_reply":
        if "|" in text:
            keyword, response = text.split("|", 1)
            db.add_auto_reply(keyword.strip(), response.strip(), user_id)
            safe_send_message(message.chat.id, f"✅ تمت إضافة الرد التلقائي للكلمة '{keyword}'.")
            db.log_admin_action(user_id, "add_auto_reply", f"Added {keyword}")
        else:
            safe_send_message(message.chat.id, "❌ استخدم الصيغة: كلمة|الرد")
    elif action == "remove_auto_reply":
        keyword = text.strip()
        db.remove_auto_reply(keyword)
        safe_send_message(message.chat.id, f"✅ تمت إزالة الرد التلقائي للكلمة '{keyword}'.")
        db.log_admin_action(user_id, "remove_auto_reply", f"Removed {keyword}")
    else:
        safe_send_message(message.chat.id, "❌ إجراء غير معروف.")
    return

# ================== لوحات المفاتيح الملونة ==================
def get_main_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        KeyboardButton("📚 ابدأ اليوم"),
        KeyboardButton("📘 قواعد أساسية")
    )
    markup.add(
        KeyboardButton("⭐ مفضلتي"),
        KeyboardButton("📊 إحصائياتي")
    )
    markup.add(
        KeyboardButton("🎓 شهادتي"),
        KeyboardButton("🆘 مساعدة بين مستخدمين البوت")
    )
    markup.add(
        KeyboardButton("🏆 لوحة المتصدرين"),
        KeyboardButton("⚙️ الإعدادات")
    )
    markup.add(KeyboardButton("🏋️‍♂️ رفع المستوى (لانهائي)"))
    
    user = db.get_user(user_id)
    if user and user.get('level_tested', 0) == 0:
        markup.add(KeyboardButton("📋 اختبار تحديد المستوى"))
    
    if db.is_admin(user_id):
        markup.add(KeyboardButton("👤 لوحة الأدمن"))
    
    return markup

def get_days_keyboard(user_id: int) -> InlineKeyboardMarkup:
    completed_days = db.get_completed_days(user_id)
    current_day = db.get_user_day(user_id)
    
    markup = InlineKeyboardMarkup(row_width=5)
    buttons = []
    
    for day in range(1, 31):
        if day in completed_days:
            text = f"✅ {day}"
            color = "🟢"
        elif day < current_day:
            text = f"📖 {day}"
            color = "🔵"
        elif day == current_day:
            text = f"▶️ {day}"
            color = "🟡"
        else:
            text = f"🔒 {day}"
            color = "🔴"
        
        buttons.append(create_colored_button(text, f"day_{day}", color))
    
    for i in range(0, 30, 5):
        markup.add(*buttons[i:i+5])
    
    return markup

def get_grammar_keyboard() -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    
    topics = [
        ("🔤 الحروف المتحركة", "grammar_vowels", "🔵"),
        ("🔠 الحروف الساكنة", "grammar_consonants", "🔵"),
        ("📖 أدوات التعريف", "grammar_articles", "🔵"),
        ("👤 الضمائر الشخصية", "grammar_pronouns", "🔵"),
        ("⏰ الأزمنة البسيطة", "grammar_tenses", "🔵"),
        ("➕ جمع الأسماء", "grammar_plurals", "🔵"),
        ("📍 حروف الجر", "grammar_prepositions", "🔵"),
        ("❓ أدوات الاستفهام", "grammar_questions", "🔵")
    ]
    
    for text, callback, color in topics:
        markup.add(create_colored_button(text, callback, color))
    
    markup.add(create_colored_button("🔙 العودة للقائمة", "back_main", "🔴"))
    
    return markup

def get_session_keyboard(day: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    
    sessions = [
        ("🌅 صباح", f"session_{day}_morning", "🟢"),
        ("☀️ ظهر", f"session_{day}_noon", "🟢"),
        ("🌇 عصر", f"session_{day}_afternoon", "🟢"),
        ("🌙 ليل", f"session_{day}_night", "🟢")
    ]
    
    for text, callback, color in sessions:
        markup.add(create_colored_button(text, callback, color))
    
    markup.add(create_colored_button("🔙 العودة للأيام", "back_to_days", "🔴"))
    
    return markup

def get_admin_keyboard(user_id: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    
    if has_permission(user_id, 'can_manage_users') or is_owner(user_id):
        markup.add(create_colored_button("👥 إدارة المستخدمين", "admin_users_menu", "🟢"))
    if has_permission(user_id, 'can_manage_admins') or is_owner(user_id):
        markup.add(create_colored_button("👑 إدارة الأدمنية", "admin_admins_menu", "🟢"))
    if has_permission(user_id, 'can_manage_content') or is_owner(user_id):
        markup.add(create_colored_button("📚 إدارة المحتوى", "admin_content_menu", "🟢"))
    if has_permission(user_id, 'can_broadcast') or is_owner(user_id):
        markup.add(create_colored_button("📢 الإذاعة", "admin_broadcast_menu", "🟢"))
    if has_permission(user_id, 'can_view_stats') or is_owner(user_id):
        markup.add(create_colored_button("📊 الإحصائيات", "admin_stats", "🔵"))
    if has_permission(user_id, 'can_manage_settings') or is_owner(user_id):
        markup.add(create_colored_button("⚙️ إعدادات البوت", "admin_settings_menu", "🔵"))
    if has_permission(user_id, 'can_view_logs') or is_owner(user_id):
        markup.add(create_colored_button("📋 السجلات", "admin_logs", "🔵"))
    
    if is_owner(user_id):
        markup.add(create_colored_button("🔍 عرض جميع المستخدمين", "admin_list_users", "🟡"))
        markup.add(create_colored_button("🚫 الكلمات الممنوعة", "admin_banned_words", "🟡"))
        markup.add(create_colored_button("🤖 الردود التلقائية", "admin_auto_replies", "🟡"))
        markup.add(create_colored_button("⚠️ الإبلاغات", "admin_reports", "🟡"))
        markup.add(create_colored_button("🔄 إعادة تشغيل البوت", "admin_restart", "🔴"))
    
    markup.add(create_colored_button("🔙 العودة للقائمة", "back_main", "🔴"))
    
    return markup

def get_admin_users_keyboard(user_id: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    
    if has_permission(user_id, 'can_manage_users') or is_owner(user_id):
        markup.add(create_colored_button("🔍 بحث عن مستخدم", "admin_user_search", "🟢"))
        markup.add(create_colored_button("🚫 حظر مستخدم", "admin_ban_user", "🔴"))
        markup.add(create_colored_button("✅ إلغاء حظر", "admin_unban_user", "🟢"))
        markup.add(create_colored_button("📋 المحظورين", "admin_banned_list", "🔵"))
        markup.add(create_colored_button("🔄 إعادة تعيين مستخدم", "admin_reset_user", "🟡"))
        markup.add(create_colored_button("📨 رسالة خاصة", "admin_send_private", "🟢"))
    
    if is_owner(user_id):
        markup.add(create_colored_button("📋 عرض جميع المستخدمين", "admin_list_users", "🟡"))
    
    markup.add(create_colored_button("🔙 العودة", "admin_back_main", "🔴"))
    
    return markup

def get_admin_admins_keyboard() -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(create_colored_button("➕ إضافة أدمن", "admin_add_admin", "🟢"))
    markup.add(create_colored_button("➖ إزالة أدمن", "admin_remove_admin", "🔴"))
    markup.add(create_colored_button("📋 قائمة الأدمن", "admin_list_admins", "🔵"))
    markup.add(create_colored_button("🔙 العودة", "admin_back_main", "🔴"))
    return markup

def get_admin_content_keyboard() -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(create_colored_button("➕ إضافة كلمة", "admin_add_word", "🟢"))
    markup.add(create_colored_button("✏️ تعديل كلمة", "admin_edit_word", "🟡"))
    markup.add(create_colored_button("🗑️ حذف كلمة", "admin_delete_word", "🔴"))
    markup.add(create_colored_button("🔄 إعادة ضبط", "admin_reset_words", "🟡"))
    markup.add(create_colored_button("🔙 العودة", "admin_back_main", "🔴"))
    return markup

def get_admin_broadcast_keyboard() -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(create_colored_button("📢 للجميع", "admin_broadcast_all", "🟢"))
    markup.add(create_colored_button("🎯 لمجموعة محددة", "admin_broadcast_target", "🟢"))
    markup.add(create_colored_button("⏰ جدولة إذاعة", "admin_schedule_broadcast", "🟢"))
    markup.add(create_colored_button("🔙 العودة", "admin_back_main", "🔴"))
    return markup

def get_admin_settings_keyboard() -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(create_colored_button("📌 تعيين قناة", "admin_set_channel", "🟢"))
    markup.add(create_colored_button("🔔 التذكيرات", "admin_reminder_settings", "🟢"))
    markup.add(create_colored_button("⚙️ وضع الصيانة", "admin_maintenance", "🟢"))
    markup.add(create_colored_button("🔙 العودة", "admin_back_main", "🔴"))
    return markup

# ================== معالج الأوامر ==================
@bot.message_handler(commands=['start', 'menu'])
@require_subscription
def cmd_start(message: Message):
    user_id = message.from_user.id
    
    if db.get_maintenance_mode() and not db.is_admin(user_id):
        safe_send_message(message.chat.id, "⚠️ البوت في وضع الصيانة حالياً. الرجاء المحاولة لاحقاً.")
        return
    
    username = message.from_user.username or ""
    name = message.from_user.first_name
    db.add_user(user_id, username, name)
    db.update_user_activity(user_id)
    
    user = db.get_user(user_id)
    if user and user.get('initial_test_done', 0) == 0:
        # لم يقم بإجراء الاختبار الإلزامي بعد
        send_mandatory_level_selection(message.chat.id, user_id)
    else:
        welcome = f"👋 مرحباً {name}!\n\n"
        welcome += "أهلاً بك في بوت تحضير اختبار التوفل المتكامل. سأساعدك على تعلم 480 كلمة أساسية خلال 30 يوماً، مع 4 جلسات يومياً.\n\n"
        welcome += "اختر من القائمة للبدء:"
        
        safe_send_message(message.chat.id, welcome, reply_markup=get_main_keyboard(user_id))
        safe_send_message(message.chat.id, "📅 اختر اليوم الذي تريد البدء به:", reply_markup=get_days_keyboard(user_id))

def send_mandatory_level_selection(chat_id: int, user_id: int):
    markup = InlineKeyboardMarkup(row_width=2)
    buttons = [
        create_colored_button("🔰 مبتدئ", "mandatory_level_beginner", "🟢"),
        create_colored_button("⚜️ متوسط", "mandatory_level_intermediate", "🟡"),
        create_colored_button("🏅 متقدم", "mandatory_level_advanced", "🔴")
    ]
    markup.add(*buttons)
    
    safe_send_message(
        chat_id,
        "👋 **مرحباً بك في بوت تعلم اللغة الإنجليزية وتحضير التوفل خلال شهر واحد!**\n\n"
        "من أجل الاستمرار، يرجى اختيار مستواك للبدء:",
        parse_mode="Markdown",
        reply_markup=markup
    )

def start_mandatory_test_by_choice(chat_id: int, user_id: int, chosen_level: str):
    """بدء الاختبار الإلزامي (10 أسئلة من المستوى المختار)"""
    level_map = {
        "beginner": "مبتدئ",
        "intermediate": "متوسط",
        "advanced": "متقدم"
    }
    level_ar = level_map.get(chosen_level, "مبتدئ")
    
    # جمع الكلمات من القوائم الخاصة بالاختبار (إذا كانت موجودة) أو من الكلمات العامة من نفس المستوى
    level_words = []
    
    # أولاً نستخدم القوائم المخصصة إن كانت تحتوي على كلمات
    if chosen_level == "beginner" and LEVEL_TEST_WORDS_BEGINNER:
        level_words = LEVEL_TEST_WORDS_BEGINNER.copy()
    elif chosen_level == "intermediate" and LEVEL_TEST_WORDS_INTERMEDIATE:
        level_words = LEVEL_TEST_WORDS_INTERMEDIATE.copy()
    elif chosen_level == "advanced" and LEVEL_TEST_WORDS_ADVANCED:
        level_words = LEVEL_TEST_WORDS_ADVANCED.copy()
    
    # إذا كانت القوائم المخصصة فارغة، نستخدم الكلمات من المنهج اليومي بنفس المستوى
    if not level_words:
        for day in range(1, 31):
            for session in ["morning", "noon", "afternoon", "night"]:
                for word in vocab[day][session]:
                    if word.level == level_ar:
                        level_words.append(word)
    
    # إضافة كلمات مخصصة (إن وجدت) من نفس المستوى
    custom_words = db.get_custom_words()
    for cw in custom_words:
        if cw['level'] == level_ar:
            level_words.append(Word(cw['eng'], cw['ar'], cw['example'], cw['level']))
    
    # إذا لم توجد كلمات كافية، نأخذ من جميع الكلمات
    if len(level_words) < 10:
        all_words = []
        for day in range(1, 31):
            for session in ["morning", "noon", "afternoon", "night"]:
                all_words.extend(vocab[day][session])
        level_words = all_words
    
    random.shuffle(level_words)
    test_words = level_words[:10]
    question_types = [random.choice(["meaning", "example", "true_false"]) for _ in range(10)]
    
    with state_lock:
        state = LevelTestState(
            user_id=user_id,
            words=test_words,
            types=question_types,
            total=10,
            percent=0
        )
        level_test_states[user_id] = state
    
    safe_send_message(
        chat_id,
        f"📋 **اختبار تحديد المستوى - {level_ar}**\n"
        f"سيتم عرض 10 أسئلة. أجب في غضون 30 ثانية لكل سؤال.\n\n"
        f"⚠️ حاول الإجابة بأفضل ما لديك.",
        parse_mode="Markdown"
    )
    send_next_level_question(chat_id, user_id, mandatory=True)

def send_next_level_question(chat_id: int, user_id: int, mandatory=False):
    with state_lock:
        state = level_test_states.get(user_id)
    
    if not state:
        return
    
    if state.current >= state.total:
        finish_customized_test(chat_id, user_id, mandatory=mandatory)
        return
    
    word = state.words[state.current]
    qtype = state.types[state.current]
    
    poll = send_poll_question(chat_id, word, qtype, state.current + 1, state.total)
    
    if poll:
        with state_lock:
            state.poll_ids.append(poll.poll.id)
            pending_polls[poll.poll.id] = {
                "user_id": user_id,
                "chat_id": chat_id,
                "state_type": "level_test",
                "q_index": state.current,
                "word": word,
                "qtype": qtype
            }
    else:
        with state_lock:
            state.current += 1
        send_next_level_question(chat_id, user_id, mandatory)

@bot.message_handler(commands=['remind'])
@require_subscription
def cmd_remind(message: Message):
    user_id = message.from_user.id
    send_reminder_to_user(user_id)
    safe_send_message(message.chat.id, "✅ تم إرسال التذكير لك.")

@bot.message_handler(commands=['endchat'])
@require_subscription
def cmd_endchat(message: Message):
    user_id = message.from_user.id
    partner = db.get_chat_partner(user_id)
    
    if partner:
        db.end_chat(user_id, partner)
        safe_send_message(message.chat.id, "✅ تم إنهاء المحادثة.")
        safe_send_message(partner, "🔚 تم إنهاء المحادثة من قبل الطرف الآخر.")
    else:
        safe_send_message(message.chat.id, "❌ لست في محادثة حالياً.")

# ================== معالج النصوص ==================
@bot.message_handler(func=lambda m: True)
@require_subscription
def handle_text(message: Message):
    user_id = message.from_user.id
    text = message.text
    
    if db.get_maintenance_mode() and not db.is_admin(user_id):
        safe_send_message(message.chat.id, "⚠️ البوت في وضع الصيانة حالياً. الرجاء المحاولة لاحقاً.")
        return
    
    db.update_user_activity(user_id)
    
    # التحقق من الردود التلقائية أولاً
    reply = db.get_auto_reply(text)
    if reply:
        safe_send_message(message.chat.id, reply)
        return
    
    # التحقق من وجود كلمات ممنوعة
    if not db.is_admin(user_id) and db.contains_banned_word(text):
        safe_delete_message(message.chat.id, message.message_id)
        safe_send_message(message.chat.id, "⚠️ رسالتك تحتوي على كلمة ممنوعة وتم حذفها.")
        warning_count = db.add_spam_warning(user_id)
        if warning_count >= 3:
            db.mute_user(user_id, 60)
            safe_send_message(message.chat.id, "🔇 تم كتمك لمدة ساعة بسبب تكرار المخالفات.")
        return
    
    # التحقق من الكتم
    is_muted, muted_until = db.is_muted(user_id)
    if is_muted:
        remaining = (muted_until - datetime.now()).seconds // 60
        safe_send_message(message.chat.id, f"🔇 أنت مكتوم حتى {muted_until.strftime('%H:%M')} (متبقي {remaining} دقيقة).")
        return
    
    # معالجة حالة إدخال الأدمن
    if user_id in admin_states:
        handle_admin_input(message)
        return
    
    # الأزرار العادية
    if text == "📚 ابدأ اليوم":
        safe_send_message(message.chat.id, "📅 اختر اليوم:", reply_markup=get_days_keyboard(user_id))
    
    elif text == "📘 قواعد أساسية":
        safe_send_message(message.chat.id, "اختر موضوع القواعد:", reply_markup=get_grammar_keyboard())
    
    elif text == "⭐ مفضلتي":
        show_favorites(message)
    
    elif text == "📊 إحصائياتي":
        show_stats(message)
    
    elif text == "🎓 شهادتي":
        request_certificate(message)
    
    elif text == "🆘 مساعدة بين مستخدمين البوت":
        show_help_menu(message)
    
    elif text == "🏆 لوحة المتصدرين":
        show_leaderboard(message)
    
    elif text == "⚙️ الإعدادات":
        show_settings(message)
    
    elif text == "🏋️‍♂️ رفع المستوى (لانهائي)":
        start_infinite_quiz(message.chat.id, user_id)
    
    elif text == "🏁 إنهاء التحدي":
        if user_id in infinite_quiz_states:
            finish_infinite_quiz(message.chat.id, user_id, forced=True)
        else:
            safe_send_message(message.chat.id, "❌ لا يوجد تحدي نشط.")
    
    elif text == "📋 اختبار تحديد المستوى":
        user = db.get_user(user_id)
        if user and user.get('level_tested', 0) == 1:
            safe_send_message(message.chat.id, "لقد أجريت اختبار المستوى بالفعل. يمكنك رؤية نتيجتك في الإحصائيات.")
        else:
            show_level_estimation(message.chat.id, user_id)
    
    elif text == "👤 لوحة الأدمن" and db.is_admin(user_id):
        safe_send_message(message.chat.id, "👤 لوحة تحكم الأدمن:", reply_markup=get_admin_keyboard(user_id))
    
    else:
        with state_lock:
            broadcast = broadcast_states.get(user_id)
        
        if broadcast:
            process_broadcast_message_request(message)
        else:
            safe_send_message(message.chat.id, "❓ أمر غير معروف. اختر من القائمة.")

# ================== معالج الاستفتاءات ==================
@bot.poll_answer_handler()
def handle_poll_answer(pollAnswer: PollAnswer):
    poll_id = pollAnswer.poll_id
    user_id = pollAnswer.user.id
    selected = pollAnswer.option_ids
    
    with state_lock:
        poll_data = pending_polls.pop(poll_id, None)
        if poll_id in poll_timeouts:
            poll_timeouts[poll_id].cancel()
            del poll_timeouts[poll_id]
    
    if not poll_data:
        return
    
    if poll_data["user_id"] != user_id:
        return
    
    chat_id = poll_data["chat_id"]
    state_type = poll_data["state_type"]
    
    if state_type == "quiz":
        with state_lock:
            state = quiz_states.get(user_id)
        
        if not state or poll_data["q_index"] != state.current:
            return
        
        is_correct = 1 if selected and selected[0] == 0 else 0
        
        if is_correct:
            state.score += 1
        
        word = poll_data["word"]
        state.answers.append({
            "question_number": state.current + 1,
            "word": word.eng,
            "user_answer": str(selected),
            "correct_answer": "صحيح" if is_correct else "خطأ",
            "is_correct": is_correct
        })
        
        state.current += 1
        send_next_quiz_question(chat_id, user_id)
    
    elif state_type == "level_test":
        with state_lock:
            state = level_test_states.get(user_id)
        
        if not state or poll_data["q_index"] != state.current:
            return
        
        is_correct = 1 if selected and selected[0] == 0 else 0
        
        if is_correct:
            state.score += 1
        
        word = poll_data["word"]
        state.answers.append({
            "question_number": state.current + 1,
            "word": word.eng,
            "user_answer": str(selected),
            "correct_answer": "صحيح" if is_correct else "خطأ",
            "is_correct": is_correct
        })
        
        state.current += 1
        send_next_level_question(chat_id, user_id)
    
    elif state_type == "infinite":
        with state_lock:
            state = infinite_quiz_states.get(user_id)
        
        if not state or poll_data["q_index"] != state.current:
            return
        
        is_correct = 1 if selected and selected[0] == 0 else 0
        
        if is_correct:
            state.score += 1
        
        word = poll_data["word"]
        state.answers.append({
            "question_number": state.current + 1,
            "word": word.eng,
            "user_answer": str(selected),
            "correct_answer": "صحيح" if is_correct else "خطأ",
            "is_correct": is_correct
        })
        
        state.current += 1
        send_next_infinite_question(chat_id, user_id)

# ================== معالج الكولباك ==================
@bot.callback_query_handler(func=lambda call: True)
@require_subscription_callback
def handle_callback(call: CallbackQuery):
    cid = call.message.chat.id
    user_id = call.from_user.id
    data = call.data
    
    db.update_user_activity(user_id)
    
    try:
        # معالجة زر التحقق من الاشتراك
        if data == "check_subscription":
            if check_subscription(user_id):
                bot.answer_callback_query(call.id, "✅ تم التحقق! اشتراكك صحيح.", show_alert=False)
                safe_delete_message(cid, call.message.message_id)
                safe_send_message(cid, "✅ تم تأكيد اشتراكك! يمكنك الآن استخدام البوت.", reply_markup=get_main_keyboard(user_id))
            else:
                bot.answer_callback_query(call.id, "❌ لم يتم العثور على اشتراك. يرجى الاشتراك أولاً.", show_alert=True)
            return
        
        # ================== معالجة الاختبار الإلزامي ==================
        if data.startswith("mandatory_level_"):
            level = data.split("_")[2]
            safe_delete_message(cid, call.message.message_id)
            start_mandatory_test_by_choice(cid, user_id, level)
            bot.answer_callback_query(call.id)
            return
        
        # ================== معالجة طلبات المساعدة ==================
        if data == "help_request_type":
            ask_for_help_question(call.message, "مشكلة")
            bot.answer_callback_query(call.id)
            return
        if data == "help_question_type":
            ask_for_help_question(call.message, "سؤال")
            bot.answer_callback_query(call.id)
            return
        
        if data.startswith("approve_help_"):
            if not is_owner(user_id):
                bot.answer_callback_query(call.id, "غير مصرح", show_alert=True)
                return
            request_id = int(data.split("_")[2])
            req = db.get_help_request(request_id)
            if req and req['status'] == 'pending':
                db.approve_help_request(request_id, user_id)
                publish_help_request(request_id, req['question'], req['user_id'])
                bot.edit_message_text("✅ تمت الموافقة ونشر الطلب.", cid, call.message.message_id)
                bot.answer_callback_query(call.id, "تم النشر")
            else:
                bot.answer_callback_query(call.id, "الطلب غير موجود أو تمت معالجته", show_alert=True)
            return
        
        if data.startswith("reject_help_"):
            if not is_owner(user_id):
                bot.answer_callback_query(call.id, "غير مصرح", show_alert=True)
                return
            request_id = int(data.split("_")[2])
            db.reject_help_request(request_id)
            bot.edit_message_text("❌ تم رفض الطلب.", cid, call.message.message_id)
            bot.answer_callback_query(call.id, "تم الرفض")
            return
        
        if data.startswith("reply_help_"):
            parts = data.split("_")
            if len(parts) == 4:
                request_id = int(parts[2])
                requester_id = int(parts[3])
                ask_for_reply(call.message, request_id, requester_id)
                bot.answer_callback_query(call.id)
            return
        
        if data.startswith("report_help_"):
            parts = data.split("_")
            if len(parts) == 4:
                request_id = int(parts[2])
                requester_id = int(parts[3])
                report_help_abuse(call, request_id, requester_id)
            return
        
        # ================== معالجة اختيار المستوى (اختياري) ==================
        if data.startswith("level_"):
            level_map = {
                "beginner": "مبتدئ",
                "intermediate": "متوسط",
                "advanced": "متقدم"
            }
            level_key = data.split("_")[1]
            chosen_level = level_map.get(level_key)
            if chosen_level:
                safe_delete_message(cid, call.message.message_id)
                start_level_test_by_choice(cid, user_id, chosen_level)
                bot.answer_callback_query(call.id)
            return
        
        # ================== معالجة الأيام ==================
        if data.startswith("day_"):
            day = int(data.split("_")[1])
            
            allowed, message = can_access_day(user_id, day)
            if not allowed:
                bot.answer_callback_query(call.id, message, show_alert=True)
                return
            
            bot.edit_message_text(
                f"📅 **اليوم {day}**\nاختر وقت الجلسة:",
                cid,
                call.message.message_id,
                parse_mode="Markdown",
                reply_markup=get_session_keyboard(day)
            )
            bot.answer_callback_query(call.id)
            return
        
        if data == "back_to_days":
            bot.edit_message_text(
                "📅 اختر اليوم:",
                cid,
                call.message.message_id,
                reply_markup=get_days_keyboard(user_id)
            )
            bot.answer_callback_query(call.id)
            return
        
        if data == "back_main":
            bot.edit_message_text(
                "القائمة الرئيسية:",
                cid,
                call.message.message_id,
                reply_markup=get_grammar_keyboard()
            )
            bot.answer_callback_query(call.id)
            return
        
        if data.startswith("session_"):
            parts = data.split("_", 2)
            if len(parts) == 3:
                _, day_str, session = parts
                day = int(day_str)
                
                words = vocab[day][session].copy()
                
                if day > 1:
                    review_words = []
                    for d in range(max(1, day-3), day):
                        for s in ["morning", "noon", "afternoon", "night"]:
                            review_words.extend(vocab[d][s][:2])
                    if review_words:
                        review_sample = random.sample(review_words, min(4, len(review_words)))
                        for w in review_sample:
                            w_copy = Word(
                                eng=f"🔄 {w.eng}",
                                ar=w.ar,
                                example=w.example,
                                level=w.level
                            )
                            words.append(w_copy)
                
                with state_lock:
                    user_sessions[user_id] = words
                
                safe_delete_message(cid, call.message.message_id)
                
                session_name = get_session_name(session)
                safe_send_message(cid, f"**{session_name} - يوم {day}**\nعرض الكلمات:", parse_mode="Markdown")
                
                for idx, word in enumerate(words):
                    display_eng = word.eng.replace("🔄 ", "")
                    msg = f"**{idx+1}. {display_eng}**\n📝 {word.ar}\n💬 {word.example}\n📊 المستوى: {word.level}"
                    
                    markup = InlineKeyboardMarkup()
                    callback_data = f"addfav_{day}_{session}_{idx}"
                    markup.add(create_colored_button("⭐ أضف للمفضلة", callback_data, "🟡"))
                    
                    safe_send_message(cid, msg, parse_mode="Markdown", reply_markup=markup)
                    
                    try:
                        tts = gTTS(display_eng, lang='en')
                        filename = f"audio_{user_id}_{int(time.time())}.mp3"
                        tts.save(filename)
                        with open(filename, 'rb') as f:
                            bot.send_voice(cid, f)
                        os.remove(filename)
                    except Exception as e:
                        logger.error(f"فشل إنشاء الصوت: {e}")
                
                markup = InlineKeyboardMarkup(row_width=2)
                markup.add(
                    create_colored_button("✅ إنهاء الجلسة", f"complete_{day}_{session}", "🟢"),
                    create_colored_button("🎯 اختبار", f"quiz_{day}_{session}", "🔵")
                )
                safe_send_message(cid, "ماذا تريد أن تفعل الآن؟", reply_markup=markup)
                bot.answer_callback_query(call.id)
                return
        
        if data.startswith("addfav_"):
            parts = data.split("_", 3)
            if len(parts) == 4:
                _, day_str, session, idx_str = parts
                day = int(day_str)
                idx = int(idx_str)
                
                with state_lock:
                    words = user_sessions.get(user_id, [])
                
                if 0 <= idx < len(words):
                    word = words[idx]
                    clean_eng = word.eng.replace("🔄 ", "")
                    
                    fav_word = Word(clean_eng, word.ar, word.example, word.level)
                    db.add_favorite(user_id, fav_word)
                    
                    bot.answer_callback_query(call.id, f"✅ تمت إضافة '{clean_eng}' إلى المفضلة")
                else:
                    bot.answer_callback_query(call.id, "❌ حدث خطأ", show_alert=True)
            else:
                bot.answer_callback_query(call.id, "❌ بيانات غير صحيحة", show_alert=True)
            return
        
        if data.startswith("complete_"):
            parts = data.split("_", 2)
            if len(parts) == 3:
                _, day_str, session = parts
                day = int(day_str)
                
                db.mark_session_completed(user_id, day, session)
                bot.answer_callback_query(call.id, "✅ تم حفظ التقدم")
                
                safe_delete_message(cid, call.message.message_id)
                
                completed = db.get_completed_sessions(user_id, day)
                all_sessions = ["morning", "noon", "afternoon", "night"]
                remaining = [s for s in all_sessions if s not in completed]
                
                if remaining:
                    next_sesh = remaining[0]
                    markup = InlineKeyboardMarkup()
                    markup.add(create_colored_button(
                        f"⏩ الانتقال إلى {get_session_name(next_sesh)}",
                        f"session_{day}_{next_sesh}",
                        "🟢"
                    ))
                    safe_send_message(
                        cid,
                        f"✅ تم إكمال جلسة {get_session_name(session)}!\nتابع إلى الجلسة التالية:",
                        reply_markup=markup
                    )
                else:
                    safe_send_message(cid, f"🎉 **تهانينا! لقد أكملت اليوم {day} بنجاح!**")
                    
                    current_day = db.get_user_day(user_id)
                    if day == current_day and day < 30:
                        db.update_user_day(user_id, current_day + 1)
                    
                    if day < 30:
                        can_access, msg = can_access_day(user_id, day + 1)
                        markup = InlineKeyboardMarkup(row_width=1)
                        markup.add(create_colored_button("🔙 العودة لليوم", f"day_{day}", "🔵"))
                        markup.add(create_colored_button("🎮 تدريبات إضافية", f"extra_{day}", "🟡"))
                        
                        if can_access:
                            markup.add(create_colored_button("🚀 ابدأ اليوم التالي", f"day_{day + 1}", "🟢"))
                            safe_send_message(cid, "يمكنك البدء باليوم التالي الآن!", reply_markup=markup)
                        else:
                            markup.add(create_colored_button(f"⏳ انتظر", "wait", "🔴"))
                            safe_send_message(cid, msg or "الرجاء الانتظار لبدء اليوم التالي", reply_markup=markup)
                return
        
        if data.startswith("quiz_"):
            parts = data.split("_", 2)
            if len(parts) == 3:
                _, day_str, session = parts
                day = int(day_str)
                
                safe_delete_message(cid, call.message.message_id)
                
                start_quiz(cid, user_id, day, session)
                bot.answer_callback_query(call.id)
                return
        
        if data.startswith("extra_"):
            day = int(data.split("_")[1])
            
            words = []
            for s in ["morning", "noon", "afternoon", "night"]:
                words.extend(vocab[day][s])
            random.shuffle(words)
            quiz_words = words[:5]
            question_types = [random.choice(["meaning", "example", "true_false"]) for _ in range(5)]
            
            with state_lock:
                quiz_states[user_id] = QuizState(
                    user_id=user_id,
                    day=day,
                    session="extra",
                    words=quiz_words,
                    types=question_types,
                    total=5
                )
            
            safe_delete_message(cid, call.message.message_id)
            
            safe_send_message(cid, "🎮 **تدريب إضافي**\n5 أسئلة سريعة!", parse_mode="Markdown")
            send_next_quiz_question(cid, user_id)
            bot.answer_callback_query(call.id)
            return
        
        if data.startswith("grammar_"):
            topic = data[8:]
            
            grammar_texts = {
                "vowels": "🔤 **الحروف المتحركة** (Vowels)\n\nالحروف المتحركة في الإنجليزية هي: A, E, I, O, U (وأحياناً Y).\nتظهر في كل كلمة تقريباً وتؤثر على طريقة النطق.",
                "consonants": "🔠 **الحروف الساكنة** (Consonants)\n\nهي باقي الحروف الأبجدية (21 حرفاً). غالباً ما يكون نطقها ثابتاً.",
                "articles": "📖 **أدوات التعريف** (Articles)\n\n• **a**: تستخدم قبل الكلمات التي تبدأ بصوت ساكن (a book, a car)\n• **an**: تستخدم قبل الكلمات التي تبدأ بصوت متحرك (an apple, an hour)\n• **the**: تستخدم للمعرفة (the book, the sun)",
                "pronouns": "👤 **الضمائر الشخصية** (Personal Pronouns)\n\n**فاعل:**\nI, You, He, She, It, We, They\n\n**مفعول به:**\nme, you, him, her, it, us, them\n\n**صفات الملكية:**\nmy, your, his, her, its, our, their",
                "tenses": "⏰ **الأزمنة البسيطة** (Simple Tenses)\n\n• **الماضي**: I walked, You ate\n• **المضارع**: I walk, He walks\n• **المستقبل**: I will walk, They will eat",
                "plurals": "➕ **جمع الأسماء** (Plurals)\n\n• القاعدة العامة: إضافة s (cat → cats)\n• إذا انتهى بـ s, ss, sh, ch, x, o: نضيف es (box → boxes)\n• إذا انتهى بحرف ساكن + y: نحذف y ونضيف ies (baby → babies)\n\n**استثناءات:**\nchild → children\nman → men\nwoman → women\ntooth → teeth",
                "prepositions": "📍 **حروف الجر** (Prepositions)\n\n• **in**: في (داخل)\n• **on**: على (سطح)\n• **at**: في (مكان محدد)\n• **to**: إلى\n• **from**: من\n• **with**: مع\n• **about**: عن",
                "questions": "❓ **أدوات الاستفهام** (Question Words)\n\n• **What**: ماذا/ما\n• **Where**: أين\n• **When**: متى\n• **Why**: لماذا\n• **How**: كيف\n• **Who**: من"
            }
            
            content = grammar_texts.get(topic, "معلومات عن القواعد")
            safe_send_message(cid, content, parse_mode="Markdown")
            bot.answer_callback_query(call.id)
            return
        
        if data == "wait":
            bot.answer_callback_query(call.id, "الرجاء الانتظار حتى انتهاء الوقت المتبقي", show_alert=False)
            return
        
        if data == "refresh_leaderboard":
            leaders = db.get_leaderboard(10)
            
            if not leaders:
                bot.edit_message_text("لا توجد بيانات كافية بعد.", cid, call.message.message_id)
                bot.answer_callback_query(call.id)
                return
            
            msg = "🏆 **لوحة المتصدرين**\n\n"
            medals = ["🥇", "🥈", "🥉"]
            
            for i, user in enumerate(leaders, 1):
                medal = medals[i-1] if i <= 3 else f"{i}."
                msg += f"{medal} **{user['name']}**\n"
                msg += f"   • المستوى: {user['level']} | XP: {user['total_xp']}\n"
                msg += f"   • 🔥 {user['streak']} يوم\n\n"
            
            markup = InlineKeyboardMarkup()
            markup.add(create_colored_button("🔄 تحديث", "refresh_leaderboard", "🟢"))
            
            bot.edit_message_text(msg, cid, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
            bot.answer_callback_query(call.id, "✅ تم التحديث")
            return
        
        if data == "reminders_on":
            db.set_config("reminders_enabled", "1")
            bot.answer_callback_query(call.id, "✅ تم تفعيل التذكيرات")
            safe_send_message(cid, "سيتم تذكيرك يومياً في الساعة 8 مساءً إذا لم تكمل جلساتك.")
            return
        
        if data == "reminders_off":
            db.set_config("reminders_enabled", "0")
            bot.answer_callback_query(call.id, "✅ تم تعطيل التذكيرات")
            safe_send_message(cid, "لن تصلك تذكيرات بعد الآن.")
            return
        
        if data == "remind_now":
            send_reminder_to_user(user_id)
            bot.answer_callback_query(call.id, "✅ تم إرسال التذكير", show_alert=False)
            return
        
        if data == "report_user":
            bot.answer_callback_query(call.id, "الرجاء إرسال معرف المستخدم الذي تريد الإبلاغ عنه مع السبب.")
            safe_send_message(cid, "أرسل معرف المستخدم (ID) والسبب في سطر واحد (مثال: 123456789 هذا مستخدم مسيء)")
            bot.register_next_step_handler(call.message, process_report)
            return
        
        # ================== أوامر الأدمن ==================
        if data.startswith("admin_"):
            if not db.is_admin(user_id):
                bot.answer_callback_query(call.id, "غير مصرح", show_alert=True)
                return
            
            admin_cmd = data.split("_", 1)[1]
            
            if admin_cmd == "users_menu":
                bot.edit_message_text(
                    "👥 **إدارة المستخدمين**\nاختر الإجراء:",
                    cid,
                    call.message.message_id,
                    parse_mode="Markdown",
                    reply_markup=get_admin_users_keyboard(user_id)
                )
                bot.answer_callback_query(call.id)
                return
            
            elif admin_cmd == "admins_menu":
                if not (has_permission(user_id, 'can_manage_admins') or is_owner(user_id)):
                    bot.answer_callback_query(call.id, "لا تملك صلاحية إدارة الأدمنية", show_alert=True)
                    return
                bot.edit_message_text(
                    "👑 **إدارة الأدمنية**\nاختر الإجراء:",
                    cid,
                    call.message.message_id,
                    parse_mode="Markdown",
                    reply_markup=get_admin_admins_keyboard()
                )
                bot.answer_callback_query(call.id)
                return
            
            elif admin_cmd == "content_menu":
                if not (has_permission(user_id, 'can_manage_content') or is_owner(user_id)):
                    bot.answer_callback_query(call.id, "لا تملك صلاحية إدارة المحتوى", show_alert=True)
                    return
                bot.edit_message_text(
                    "📚 **إدارة المحتوى**\nاختر الإجراء:",
                    cid,
                    call.message.message_id,
                    parse_mode="Markdown",
                    reply_markup=get_admin_content_keyboard()
                )
                bot.answer_callback_query(call.id)
                return
            
            elif admin_cmd == "broadcast_menu":
                if not (has_permission(user_id, 'can_broadcast') or is_owner(user_id)):
                    bot.answer_callback_query(call.id, "لا تملك صلاحية الإذاعة", show_alert=True)
                    return
                bot.edit_message_text(
                    "📢 **الإذاعة**\nاختر نوع الإذاعة:",
                    cid,
                    call.message.message_id,
                    parse_mode="Markdown",
                    reply_markup=get_admin_broadcast_keyboard()
                )
                bot.answer_callback_query(call.id)
                return
            
            elif admin_cmd == "settings_menu":
                if not (has_permission(user_id, 'can_manage_settings') or is_owner(user_id)):
                    bot.answer_callback_query(call.id, "لا تملك صلاحية إعدادات البوت", show_alert=True)
                    return
                bot.edit_message_text(
                    "⚙️ **إعدادات البوت**\nاختر الإجراء:",
                    cid,
                    call.message.message_id,
                    parse_mode="Markdown",
                    reply_markup=get_admin_settings_keyboard()
                )
                bot.answer_callback_query(call.id)
                return
            
            elif admin_cmd == "stats":
                if not (has_permission(user_id, 'can_view_stats') or is_owner(user_id)):
                    bot.answer_callback_query(call.id, "لا تملك صلاحية الاطلاع على الإحصائيات", show_alert=True)
                    return
                show_admin_stats(cid)
                bot.answer_callback_query(call.id)
                return
            
            elif admin_cmd == "logs":
                if not (has_permission(user_id, 'can_view_logs') or is_owner(user_id)):
                    bot.answer_callback_query(call.id, "لا تملك صلاحية الاطلاع على السجلات", show_alert=True)
                    return
                show_admin_logs(cid)
                bot.answer_callback_query(call.id)
                return
            
            elif admin_cmd == "list_users":
                if not is_owner(user_id):
                    bot.answer_callback_query(call.id, "هذه الميزة للمالك فقط", show_alert=True)
                    return
                show_users_page(cid, page=0)
                bot.answer_callback_query(call.id)
                return
            
            elif admin_cmd == "banned_words":
                if not is_owner(user_id):
                    bot.answer_callback_query(call.id, "هذه الميزة للمالك فقط", show_alert=True)
                    return
                show_banned_words_menu(cid)
                bot.answer_callback_query(call.id)
                return
            
            elif admin_cmd == "auto_replies":
                if not is_owner(user_id):
                    bot.answer_callback_query(call.id, "هذه الميزة للمالك فقط", show_alert=True)
                    return
                show_auto_replies_menu(cid)
                bot.answer_callback_query(call.id)
                return
            
            elif admin_cmd == "reports":
                if not is_owner(user_id):
                    bot.answer_callback_query(call.id, "هذه الميزة للمالك فقط", show_alert=True)
                    return
                show_reports_menu(cid)
                bot.answer_callback_query(call.id)
                return
            
            elif admin_cmd == "restart":
                if not is_owner(user_id):
                    bot.answer_callback_query(call.id, "هذه الميزة للمالك فقط", show_alert=True)
                    return
                safe_send_message(cid, "🔄 جاري إعادة تشغيل البوت...")
                os.execl(sys.executable, sys.executable, *sys.argv)
                return
            
            elif admin_cmd == "back_main":
                bot.edit_message_text(
                    "👤 لوحة تحكم الأدمن:",
                    cid,
                    call.message.message_id,
                    reply_markup=get_admin_keyboard(user_id)
                )
                bot.answer_callback_query(call.id)
                return
            
            elif admin_cmd in ["add_admin", "remove_admin", "user_search", "ban_user", "unban_user", "reset_user", "send_private",
                               "add_word", "delete_word", "reset_words", "broadcast_all", "broadcast_target", "schedule_broadcast",
                               "set_channel", "reminder_settings", "maintenance", "add_banned_word", "remove_banned_word",
                               "add_auto_reply", "remove_auto_reply"]:
                prompt_for_admin_input(cid, user_id, admin_cmd, f"أرسل البيانات المطلوبة للإجراء: {admin_cmd}", None)
                bot.answer_callback_query(call.id)
                return
            
            elif admin_cmd == "list_admins":
                admins = db.get_admins()
                names = []
                for aid in admins:
                    try:
                        name = bot.get_chat(aid).first_name
                        names.append(f"{aid} ({name})")
                    except:
                        names.append(str(aid))
                msg = "👑 **قائمة الأدمن:**\n" + "\n".join(f"• {n}" for n in names)
                safe_send_message(cid, msg, parse_mode="Markdown")
                bot.answer_callback_query(call.id)
                return
            
            elif admin_cmd == "banned_list":
                banned = db.get_banned_users()
                if banned:
                    msg = "🚫 **المستخدمون المحظورون:**\n"
                    for b in banned:
                        msg += f"• {b['user_id']} (حظر بواسطة {b['banned_by']} في {b['banned_at'][:16]})\n"
                else:
                    msg = "لا يوجد محظورون."
                safe_send_message(cid, msg, parse_mode="Markdown")
                bot.answer_callback_query(call.id)
                return
            
            elif admin_cmd == "edit_word":
                safe_send_message(cid, "هذه الميزة غير متاحة حالياً. يمكنك حذف الكلمة وإضافتها مرة أخرى.")
                bot.answer_callback_query(call.id)
                return
            
            else:
                bot.answer_callback_query(call.id, "هذه الميزة قيد التطوير", show_alert=True)
                return
        
        if data.startswith("users_page_"):
            if not is_owner(user_id):
                bot.answer_callback_query(call.id, "غير مصرح", show_alert=True)
                return
            page = int(data.split("_")[2])
            show_users_page(cid, page, call.message.message_id)
            bot.answer_callback_query(call.id)
            return
        
        if data.startswith("approve_group_") or data.startswith("reject_group_"):
            if not db.is_admin(user_id):
                bot.answer_callback_query(call.id, "غير مصرح", show_alert=True)
                return
            
            parts = data.split("_", 2)
            if len(parts) == 3:
                action_type = parts[0]
                request_id = parts[2]
                
                with state_lock:
                    state = broadcast_states.pop(request_id, None)
                
                if not state or state.type != "group":
                    bot.answer_callback_query(call.id, "الطلب غير موجود", show_alert=True)
                    return
                
                if action_type == "approve":
                    msg_text = state.group_message
                    sender_id = state.group_sender
                    try:
                        sender_name = bot.get_chat(sender_id).first_name
                    except:
                        sender_name = str(sender_id)
                    
                    users = db.get_all_users()
                    success = 0
                    failed = 0
                    
                    for uid in users:
                        if not db.is_banned(uid):
                            try:
                                bot.send_message(
                                    uid,
                                    f"📢 **رسالة جماعية من {sender_name}:**\n\n{msg_text}",
                                    parse_mode="Markdown"
                                )
                                success += 1
                                time.sleep(0.05)
                            except:
                                failed += 1
                    
                    safe_send_message(sender_id, f"✅ تمت الموافقة على رسالتك وإرسالها لـ {success} مستخدم.")
                    
                    bot.edit_message_text(
                        f"✅ تمت الموافقة وإرسال الرسالة لـ {success} مستخدم، فشل {failed}.",
                        cid,
                        call.message.message_id
                    )
                    
                    bot.answer_callback_query(call.id, "تم الإرسال")
                
                else:
                    safe_send_message(state.group_sender, "❌ تم رفض طلب إرسال رسالتك الجماعية.")
                    bot.edit_message_text(
                        f"❌ تم رفض الطلب",
                        cid,
                        call.message.message_id
                    )
                    bot.answer_callback_query(call.id, "تم الرفض")
            return
        
        bot.answer_callback_query(call.id, "هذا الزر غير متوفر حالياً", show_alert=False)
    
    except Exception as e:
        logger.error(f"خطأ في معالجة الكولباك: {e}")
        try:
            bot.answer_callback_query(call.id, "حدث خطأ، حاول مرة أخرى", show_alert=True)
        except:
            pass

# ================== دوال المساعدة الإضافية ==================
def get_time_until_next_day(user_id: int, day: int) -> Optional[str]:
    conn = sqlite3.connect('toefl_master.db')
    c = conn.cursor()
    c.execute('''SELECT completed_at FROM progress 
                 WHERE user_id=? AND day=? AND completed=1 
                 ORDER BY completed_at ASC''', (user_id, day))
    rows = c.fetchall()
    conn.close()
    
    if len(rows) < 4:
        return None
    
    try:
        first_time = datetime.fromisoformat(rows[0][0])
    except (ValueError, TypeError):
        return None
    
    target_time = first_time + timedelta(hours=24)
    now = datetime.now()
    
    if now >= target_time:
        return "0"
    
    delta = target_time - now
    hours = delta.seconds // 3600
    minutes = (delta.seconds % 3600) // 60
    return f"{hours} ساعة و {minutes} دقيقة"

def can_access_day(user_id: int, day: int) -> Tuple[bool, Optional[str]]:
    if day == 1:
        return True, None
    
    completed = db.get_completed_sessions(user_id, day-1)
    if len(completed) < 4:
        return False, "❌ يجب إكمال جميع جلسات اليوم السابق أولاً."
    
    time_left = get_time_until_next_day(user_id, day-1)
    if time_left and time_left != "0":
        return False, f"⏳ الوقت المتبقي لفتح اليوم التالي: {time_left}"
    
    return True, None

def send_reminder_to_user(user_id: int):
    if db.get_config("reminders_enabled") != "1":
        return
    try:
        current_day = db.get_user_day(user_id)
        completed = db.get_completed_sessions(user_id, current_day)
        
        if len(completed) < 4:
            msg = f"🔔 **تذكير يومي**\n\n"
            msg += f"لم تكمل جميع جلسات اليوم {current_day} بعد!\n"
            msg += f"الجلسات المتبقية: {4 - len(completed)}\n\n"
            msg += f"📅 استمر في التقدم نحو هدفك 💪"
            
            bot.send_message(user_id, msg, parse_mode="Markdown")
            logger.info(f"تم إرسال تذكير للمستخدم {user_id}")
    except Exception as e:
        logger.error(f"فشل إرسال تذكير للمستخدم {user_id}: {e}")

def send_daily_reminders():
    logger.info("بدء إرسال التذكيرات اليومية...")
    
    users = db.get_all_users()
    sent = 0
    
    for user_id in users:
        if not db.is_banned(user_id):
            send_reminder_to_user(user_id)
            sent += 1
            time.sleep(0.1)
    
    logger.info(f"تم إرسال {sent} تذكير")

def setup_scheduler():
    schedule.every().day.at("20:00").do(send_daily_reminders)
    
    def check_scheduled_broadcasts():
        broadcasts = db.get_pending_scheduled_broadcasts()
        for b in broadcasts:
            users = db.get_all_users()
            success = 0
            failed = 0
            for uid in users:
                try:
                    bot.send_message(uid, f"📢 **بث مجدول:**\n\n{b['message']}", parse_mode="Markdown")
                    success += 1
                    time.sleep(0.05)
                except:
                    failed += 1
            db.mark_broadcast_sent(b['id'])
            logger.info(f"تم إرسال البث المجدول {b['id']}: نجاح {success}, فشل {failed}")
    
    def run_scheduler():
        while True:
            schedule.run_pending()
            check_scheduled_broadcasts()
            time.sleep(60)
    
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    logger.info("✅ تم تشغيل مجدول التذكيرات")

# ================== تشغيل البوت ==================
if __name__ == "__main__":
    logger.info("🚀 بدء تشغيل بوت توفل المتكامل...")
    
    admins = db.get_admins()
    if OWNER_ID not in admins:
        db.add_admin(OWNER_ID, {"can_manage_admins": True, "can_manage_users": True, "can_manage_content": True, "can_broadcast": True, "can_view_stats": True, "can_manage_settings": True, "can_view_logs": True})
    
    FORCE_CHANNEL = db.get_config('force_channel')
    
    setup_scheduler()
    
    logger.info("✅ البوت يعمل...")
    bot.infinity_polling()
   
