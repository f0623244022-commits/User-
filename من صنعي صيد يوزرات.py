import asyncio
import sqlite3
import json
import logging
import re
import aiohttp
import time
import random
import io
import csv
from datetime import datetime, timedelta
from typing import Dict, Tuple, Optional, List

from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.types import (InlineKeyboardButton, InlineKeyboardMarkup, ParseMode, 
                          InputFile, LabeledPrice)
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher.filters import Command

BOT_TOKEN = "8596813163:AAHMO71HioIa9HX_eY6XwkYY8QsZI6wF4vg"
ADMIN_ID = 8018653004
PAYMENT_TOKEN = "390546812:LIVE:i390546812"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

PLANS = {
    "free": {"name": "🆓 مجاني", "daily": 5, "sites": 3, "speed": "بطيء", "stars": 0},
    "pro": {"name": "⭐ برو", "daily": 100, "sites": 11, "speed": "سريع", "stars": 49, "batch": 100},
    "premium": {"name": "⭐⭐⭐ بريميوم", "daily": 500, "sites": 11, "speed": "فوري", "stars": 99, "batch": 500}
}

class Database:
    def __init__(self):
        self.db = "bot.db"
        self.init()
    
    def init(self):
        conn = sqlite3.connect(self.db)
        cursor = conn.cursor()
        
        try:
            cursor.execute('DROP TABLE IF EXISTS users')
            cursor.execute('DROP TABLE IF EXISTS checks')
            cursor.execute('DROP TABLE IF EXISTS payments')
            
            cursor.execute('''CREATE TABLE users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                plan TEXT DEFAULT "free",
                subs_until TEXT,
                checks INTEGER DEFAULT 0,
                total INTEGER DEFAULT 0,
                joined TEXT,
                upgraded_by INTEGER)''')
            
            cursor.execute('''CREATE TABLE checks (
                check_id INTEGER PRIMARY KEY,
                user_id INTEGER,
                username TEXT,
                results TEXT,
                check_date TEXT,
                duration INTEGER,
                sites INTEGER)''')
            
            cursor.execute('''CREATE TABLE payments (
                payment_id INTEGER PRIMARY KEY,
                user_id INTEGER,
                stars INTEGER,
                plan TEXT,
                status TEXT,
                pay_date TEXT)''')
            
            conn.commit()
            logger.info("✅ قاعدة البيانات جاهزة")
        except Exception as e:
            logger.error(f"خطأ في قاعدة البيانات: {e}")
        finally:
            conn.close()
    
    def add_user(self, uid, username, fname):
        try:
            conn = sqlite3.connect(self.db)
            cursor = conn.cursor()
            cursor.execute('SELECT user_id FROM users WHERE user_id=?', (uid,))
            if cursor.fetchone():
                conn.close()
                return
            cursor.execute('''INSERT INTO users VALUES(?,?,?,?,?,?,?,?,?)''',
                          (uid, username, fname, "free", None, 0, 0, datetime.now().isoformat(), None))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"خطأ: {e}")
    
    def get_user(self, uid):
        try:
            conn = sqlite3.connect(self.db)
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE user_id=?', (uid,))
            row = cursor.fetchone()
            conn.close()
            if row:
                return {
                    'id': row[0], 'user': row[1], 'name': row[2],
                    'plan': row[3], 'subs': row[4], 'checks': row[5] or 0, 
                    'total': row[6] or 0, 'upgraded_by': row[8]
                }
            return None
        except Exception as e:
            logger.error(f"خطأ: {e}")
            return None
    
    def update_plan(self, uid, plan, stars, admin_id=None):
        try:
            conn = sqlite3.connect(self.db)
            cursor = conn.cursor()
            days = 30
            end = (datetime.now() + timedelta(days=days)).isoformat()
            cursor.execute('''UPDATE users SET plan=?, subs_until=?, checks=0, upgraded_by=? WHERE user_id=?''',
                          (plan, end, admin_id, uid))
            cursor.execute('''INSERT INTO payments VALUES(NULL,?,?,?,?,?)''',
                          (uid, stars, plan, 'done', datetime.now().isoformat()))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"خطأ: {e}")
            return False
    
    def add_check(self, uid, username, results, duration, sites):
        try:
            conn = sqlite3.connect(self.db)
            cursor = conn.cursor()
            cursor.execute('INSERT INTO checks VALUES(NULL,?,?,?,?,?,?)',
                          (uid, username, results, datetime.now().isoformat(), duration, sites))
            cursor.execute('UPDATE users SET checks=checks+1, total=total+1 WHERE user_id=?', (uid,))
            conn.commit()
            conn.close()
        except:
            pass
    
    def get_top(self, limit=10):
        try:
            conn = sqlite3.connect(self.db)
            cursor = conn.cursor()
            cursor.execute('SELECT user_id, first_name, total FROM users WHERE total>0 ORDER BY total DESC LIMIT ?', (limit,))
            result = cursor.fetchall()
            conn.close()
            return [{'id': r[0], 'name': r[1], 'checks': r[2]} for r in result]
        except:
            return []
    
    def get_stats(self):
        try:
            conn = sqlite3.connect(self.db)
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM users')
            users = cursor.fetchone()[0]
            cursor.execute('SELECT COUNT(*) FROM checks')
            checks = cursor.fetchone()[0]
            cursor.execute('SELECT SUM(stars) FROM payments WHERE status="done"')
            earnings = cursor.fetchone()[0] or 0
            conn.close()
            return {'users': users, 'checks': checks, 'earnings': earnings}
        except:
            return {'users': 0, 'checks': 0, 'earnings': 0}
    
    def upgrade_user(self, uid, admin_id):
        try:
            conn = sqlite3.connect(self.db)
            cursor = conn.cursor()
            end = (datetime.now() + timedelta(days=365)).isoformat()
            cursor.execute('''UPDATE users SET plan="premium", subs_until=?, upgraded_by=? WHERE user_id=?''', 
                          (end, admin_id, uid))
            conn.commit()
            conn.close()
            return True
        except:
            return False
    
    def ban_user(self, uid):
        try:
            conn = sqlite3.connect(self.db)
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET plan="banned" WHERE user_id=?', (uid,))
            conn.commit()
            conn.close()
            return True
        except:
            return False
    
    def unban_user(self, uid):
        try:
            conn = sqlite3.connect(self.db)
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET plan="free" WHERE user_id=?', (uid,))
            conn.commit()
            conn.close()
            return True
        except:
            return False

class UsernameChecker:
    sites = {
        "📱 تيليجرام": "https://t.me/{}",
        "📷 إنستغرام": "https://instagram.com/{}",
        "🎵 تيك توك": "https://tiktok.com/@{}",
        "🐦 تويتر": "https://twitter.com/{}",
        "📺 يوتيوب": "https://youtube.com/@{}",
        "🎮 تويتش": "https://twitch.tv/{}",
        "🔧 جيت هب": "https://github.com/{}",
        "🔴 ريديت": "https://reddit.com/u/{}",
        "👻 سناب شات": "https://snapchat.com/add/{}",
        "💼 لينكد ان": "https://linkedin.com/in/{}",
        "📌 بينتيريست": "https://pinterest.com/{}"
    }
    
    @staticmethod
    def validate(username):
        u = username.lstrip('@').strip()
        if len(u) < 3 or len(u) > 30:
            return False, "❌ الاسم يجب أن يكون بين 3-30 حرف"
        if not re.match(r'^[a-zA-Z0-9_.-]+$', u):
            return False, "❌ استخدم أحرف وأرقام فقط"
        return True, "✅"
    
    @staticmethod
    async def check_site(name, url):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=3), ssl=False,
                                      headers={'User-Agent': 'Mozilla/5.0'}) as r:
                    if r.status == 200:
                        return False, "❌ مشغول", url
                    return True, "✅ متاح", ""
        except:
            return None, "⚠️ خطأ", ""
    
    @staticmethod
    async def check_all(username, count=3):
        u = username.lstrip('@')
        results = {}
        start = time.time()
        
        items = list(UsernameChecker.sites.items())
        selected = random.sample(items, min(count, len(items)))
        
        for name, url_tpl in selected:
            avail, status, link = await UsernameChecker.check_site(name, url_tpl.format(u))
            results[name] = {"avail": avail, "status": status, "link": link}
        
        return {"username": u, "data": results, "time": int((time.time() - start) * 1000)}

class States(StatesGroup):
    check_user = State()
    batch_file = State()
    hunt_type = State()
    broadcast_msg = State()
    ban_user_id = State()
    upgrade_user_id = State()

db = Database()

def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 فحص واحد", callback_data="check"),
         InlineKeyboardButton(text="📁 فحص ملف", callback_data="batch")],
        [InlineKeyboardButton(text="🎯 صيد أسماء", callback_data="hunt"),
         InlineKeyboardButton(text="💳 الخطط", callback_data="plans")],
        [InlineKeyboardButton(text="📊 إحصائياتي", callback_data="stats"),
         InlineKeyboardButton(text="🏆 الترتيب", callback_data="top")],
        [InlineKeyboardButton(text="ℹ️ معلومات", callback_data="info")]
    ])

def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 الإحصائيات", callback_data="adm_stat"),
         InlineKeyboardButton(text="💰 الأرباح", callback_data="adm_earn")],
        [InlineKeyboardButton(text="📢 بث عام", callback_data="adm_bcast"),
         InlineKeyboardButton(text="⭐ ترقية", callback_data="adm_upg")],
        [InlineKeyboardButton(text="🚫 حظر", callback_data="adm_ban"),
         InlineKeyboardButton(text="✅ إلغاء حظر", callback_data="adm_unban")]
    ])

async def start(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    db.add_user(uid, message.from_user.username, message.from_user.first_name)
    user = db.get_user(uid)
    
    if not user:
        await message.answer("❌ خطأ في النظام")
        return
    
    plan = PLANS.get(user['plan'], PLANS['free'])
    
    text = f"""
╔════════════════════════════════════╗
║   🚀 بوت فحص الأسماء الرهيب 🚀   ║
║       نظام دفع حقيقي بنجوم         ║
╚════════════════════════════════════╝

👋 مرحباً {user['name']}!

💳 <b>خطتك الحالية:</b> {plan['name']}
📊 فحوصات اليوم: {user['checks']}/{plan['daily']}
📈 إجمالي: {user['total']}
🚀 السرعة: {plan['speed']}
"""
    
    if user['subs']:
        try:
            end = datetime.fromisoformat(user['subs'])
            days_left = (end - datetime.now()).days
            text += f"⏰ ينتهي في: {days_left} يوم\n"
        except:
            pass
    
    if user['upgraded_by']:
        text += f"🎉 تمت ترقيتك من قبل الإدارة!\n"
    
    text += """
✨ <b>المميزات:</b>
🔍 فحص سريع على 11 موقع
📁 فحص ملفات CSV
🎯 صيد أسماء ثلاثية ورباعية
💳 دفع آمن بنجوم
🏆 ترتيب عام
📊 إحصائيات دقيقة

⚡ <b>اختر من الخيارات:</b>
"""
    
    await message.answer(text, reply_markup=main_kb(), parse_mode=ParseMode.HTML)
    await state.finish()

async def check(query: types.CallbackQuery, state: FSMContext):
    user = db.get_user(query.from_user.id)
    plan = PLANS.get(user['plan'], PLANS['free'])
    
    if user['plan'] == 'banned':
        await query.answer("❌ تم حظرك من البوت!", show_alert=True)
        return
    
    if user['checks'] >= plan['daily']:
        await query.answer(f"❌ وصلت للحد اليومي ({plan['daily']})", show_alert=True)
        return
    
    await query.message.answer("📝 أرسل اسم المستخدم (بدون @):")
    await state.set_state(States.check_user)
    await query.answer()

async def check_username(message: types.Message, state: FSMContext):
    user = db.get_user(message.from_user.id)
    plan = PLANS.get(user['plan'], PLANS['free'])
    username = message.text
    
    valid, msg = UsernameChecker.validate(username)
    if not valid:
        await message.answer(msg)
        return
    
    progress = await message.answer("⏳ جاري الفحص...\n\n▓░░░░░░░░░")
    
    try:
        results = await UsernameChecker.check_all(username, 11 if plan['sites'] == 11 else 3)
        
        await progress.edit_text("⏳ جاري الفحص...\n\n▓▓▓▓▓░░░░░")
        
        db.add_check(message.from_user.id, username, json.dumps(results['data']),
                    results['time'], len(results['data']))
        
        text = f"""
╔════��═══════════════════════════════╗
║   📊 نتائج الفحص لـ @{username}
╚════════════════════════════════════╝

"""
        avail = taken = err = 0
        
        for site, data in results['data'].items():
            if data['avail'] is None:
                text += f"{site} ⚠️ {data['status']}\n"
                err += 1
            elif data['avail']:
                text += f"{site} {data['status']} ✨\n"
                avail += 1
            else:
                if data['link']:
                    text += f"{site} {data['status']} <a href='{data['link']}'>🔗</a>\n"
                else:
                    text += f"{site} {data['status']}\n"
                taken += 1
        
        user = db.get_user(message.from_user.id)
        text += f"\n📈 <b>الملخص:</b>\n"
        text += f"✅ متاح: {avail} | ❌ مشغول: {taken} | ⚠️ خطأ: {err}\n"
        text += f"⚡ الوقت: {results['time']}ms\n"
        text += f"📊 فحوصاتك: {user['checks']}/{plan['daily']}\n"
        text += f"🚀 السرعة: {plan['speed']}"
        
        await progress.delete()
        await message.answer(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        
    except Exception as e:
        await progress.delete()
        await message.answer(f"❌ خطأ: {str(e)}")
    
    await state.finish()

async def batch(query: types.CallbackQuery, state: FSMContext):
    user = db.get_user(query.from_user.id)
    plan = PLANS.get(user['plan'], PLANS['free'])
    
    if user['plan'] == 'free':
        await query.answer("❌ هذه الميزة متاحة فقط للمشتركين", show_alert=True)
        return
    
    await query.message.answer(f"""
📁 <b>فحص ملف CSV</b>

الحد الأقصى: {plan.get('batch', 0)} اسم

صيغة الملف:
<code>
username1
username2
username3
</code>

أرسل الملف:
""", parse_mode=ParseMode.HTML)
    await state.set_state(States.batch_file)
    await query.answer()

async def batch_file(message: types.Message, state: FSMContext):
    user = db.get_user(message.from_user.id)
    plan = PLANS.get(user['plan'], PLANS['free'])
    
    if not message.document:
        await message.answer("❌ أرسل ملف من فضلك")
        return
    
    try:
        file = await message.bot.get_file(message.document.file_id)
        content = await message.bot.download_file(file.file_path)
        
        usernames = content.read().decode('utf-8').split('\n')
        usernames = [u.strip() for u in usernames if u.strip()]
        
        if len(usernames) > plan.get('batch', 0):
            await message.answer(f"❌ عدد الأسماء يتجاوز الحد ({plan.get('batch', 0)})")
            return
        
        progress = await message.answer(f"📁 جاري فحص {len(usernames)} اسم...\n\n▓░░░░░░░░░")
        
        results_all = []
        available = []
        
        for idx, username in enumerate(usernames):
            valid, _ = UsernameChecker.validate(username)
            if not valid:
                continue
            
            result = await UsernameChecker.check_all(username, 11)
            results_all.append(result)
            
            for site, data in result['data'].items():
                if data['avail']:
                    available.append(username)
                    break
            
            if (idx + 1) % 5 == 0:
                percent = int((idx + 1) / len(usernames) * 100)
                await progress.edit_text(f"""
📁 جاري فحص {len(usernames)} اسم...

▓{'░' * (10 - len('▓'))} {percent}%

✅ متاح: {len(available)}
📊 تم فحص: {idx + 1}
""")
        
        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer)
        writer.writerow(['اسم المستخدم', 'الحالة', 'متاح', 'الموقع'])
        
        for result in results_all:
            username = result['username']
            for site, data in result['data'].items():
                status = data['status']
                avail = 'نعم' if data['avail'] else 'لا'
                writer.writerow([username, status, avail, site])
        
        csv_file = InputFile(io.BytesIO(csv_buffer.getvalue().encode()),
                            filename=f"batch_{time.time()}.csv")
        
        await progress.delete()
        
        text = f"""
✅ <b>انتهى الفحص!</b>

📊 الإجمالي: {len(usernames)}
✅ متاح: {len(available)}
📈 معدل التوفر: {int(len(available)/max(1, len(usernames))*100)}%

📥 الملف مرفق
"""
        
        await message.answer(text, parse_mode=ParseMode.HTML)
        await message.answer_document(csv_file, caption="📊 نتائج الفحص")
        
    except Exception as e:
        await message.answer(f"❌ خطأ: {str(e)}")
    
    await state.finish()

async def hunt(query: types.CallbackQuery):
    user = db.get_user(query.from_user.id)
    
    if user['plan'] == 'free':
        await query.answer("❌ هذه الميزة متاحة فقط للمشتركين", show_alert=True)
        return
    
    text = """
🎯 <b>صيد الأسماء المتاحة</b>

اختر عدد الأحرف:
"""
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="3️⃣ ثلاثية", callback_data="hunt_3"),
         InlineKeyboardButton(text="4️⃣ رباعية", callback_data="hunt_4")]
    ])
    
    await query.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    await query.answer()

async def hunt_process(query: types.CallbackQuery):
    count = int(query.data.split('_')[1])
    
    progress = await query.message.edit_text(f"🎯 جاري الصيد - {count} أحرف...\n\n▓░░░░░░░░░")
    
    available = []
    chars = 'abcdefghijklmnopqrstuvwxyz0123456789_'
    
    for i in range(100):
        username = ''.join(random.choices(chars, k=count))
        
        valid, _ = UsernameChecker.validate(username)
        if not valid:
            continue
        
        avail, status, _ = await UsernameChecker.check_site("تيليجرام", f"https://t.me/{username}")
        
        if avail:
            available.append(username)
        
        if (i + 1) % 10 == 0:
            percent = int((i + 1) / 100 * 100)
            await progress.edit_text(f"""
🎯 جاري الصيد - {count} أحرف...

▓{'░' * (10 - len('▓'))} {percent}%

📊 عدد المتاح: {len(available)}
""")
    
    if available:
        text = f"""
✅ <b>تم اكتشاف أسماء متاحة!</b>

📊 العدد: {len(available)}
📋 <b>الأسماء المتاحة:</b>

"""
        for name in available[:20]:
            text += f"✨ <code>{name}</code>\n"
        
        if len(available) > 20:
            text += f"\n... و {len(available) - 20} أخرى"
        
        csv_data = '\n'.join(available)
        
        await progress.delete()
        await query.message.answer(text, parse_mode=ParseMode.HTML)
        
        file = InputFile(io.BytesIO(csv_data.encode()), filename=f"hunt_{count}_{time.time()}.txt")
        await query.message.answer_document(file, caption="📥 تحميل الأسماء المتاحة")
    else:
        await progress.edit_text("❌ لم يتم اكتشاف أسماء متاحة حالياً")

async def plans(query: types.CallbackQuery):
    text = "💳 <b>اختر خطتك - ادفع بنجوم Telegram آمنة</b>\n\n"
    
    for key, plan in PLANS.items():
        text += f"<b>{plan['name']}</b>\n"
        text += f"📊 {plan['daily']} فحص/اليوم | 🚀 {plan['sites']} موقع\n"
        if key != 'free':
            text += f"📁 فحص الملفات: ✅\n"
            text += f"💰 {plan['stars']} نجمة\n"
        text += "\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ برو (49)", callback_data="buy_pro"),
         InlineKeyboardButton(text="⭐⭐⭐ بريميوم (99)", callback_data="buy_premium")],
        [InlineKeyboardButton(text="◀️ عودة", callback_data="back")]
    ])
    
    await query.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    await query.answer()

async def buy_plan(query: types.CallbackQuery):
    plan_key = query.data.split('_')[1]
    plan = PLANS[plan_key]
    
    await query.bot.send_invoice(
        chat_id=query.from_user.id,
        title=f"شراء خطة {plan['name']}",
        description=f"{plan['daily']} فحص يومياً - {plan['sites']} مواقع",
        payload=f"plan_{plan_key}_{query.from_user.id}",
        provider_token="390546812:LIVE:i390546812",
        currency="XTR",
        prices=[LabeledPrice(label=plan['name'], amount=plan['stars'])]
    )
    
    await query.answer()

async def pre_checkout(query: types.PreCheckoutQuery):
    await query.bot.answer_pre_checkout_query(query.id, ok=True)

async def successful_payment(message: types.Message):
    payment = message.successful_payment
    payload = payment.invoice_payload
    
    parts = payload.split('_')
    plan_key = parts[1]
    user_id = int(parts[2])
    
    plan = PLANS.get(plan_key)
    if not plan:
        return
    
    db.update_plan(user_id, plan_key, plan['stars'])
    
    end_date = (datetime.now() + timedelta(days=30)).strftime("%d/%m/%Y")
    
    text = f"""
✅ <b>تم الدفع بنجاح!</b>

🎉 تم ترقيتك إلى: {plan['name']}
💰 السعر: {plan['stars']} نجمة
📅 ينتهي: {end_date}

🎯 مميزات جديدة:
📊 {plan['daily']} فحص يومياً
🚀 السرعة: {plan['speed']}
📁 فحص الملفات CSV
🎯 صيد أسماء متقدم

شكراً لدعمك! 💚
"""
    
    await message.answer(text, parse_mode=ParseMode.HTML)

async def stats(query: types.CallbackQuery):
    user = db.get_user(query.from_user.id)
    plan = PLANS.get(user['plan'], PLANS['free'])
    
    upgraded_text = "🎉 تمت ترقيتك من قبل الإدارة\n" if user['upgraded_by'] else ""
    
    text = f"""
📊 <b>إحصائياتك</b>

👤 الاسم: {user['name']}
💳 الخطة: {plan['name']}
{upgraded_text}
📊 فحوصات اليوم: {user['checks']}/{plan['daily']}
📈 الإجمالي: {user['total']}
🚀 السرعة: {plan['speed']}
🏢 المواقع: {plan['sites']}
"""
    
    if user['subs']:
        try:
            end = datetime.fromisoformat(user['subs'])
            days_left = (end - datetime.now()).days
            text += f"⏰ ينتهي في: {days_left} يوم\n"
        except:
            pass
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬆️ ترقية", callback_data="plans")],
        [InlineKeyboardButton(text="◀️ عودة", callback_data="back")]
    ])
    
    await query.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    await query.answer()

async def top(query: types.CallbackQuery):
    leaders = db.get_top(10)
    
    text = "🏆 <b>أفضل 10 فاحصين</b>\n\n"
    
    medals = ["🥇", "🥈", "🥉"]
    for i, user in enumerate(leaders):
        medal = medals[i] if i < 3 else f"{i+1}️⃣"
        text += f"{medal} <b>{user['name']}</b> - {user['checks']} فحص\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ عودة", callback_data="back")]
    ])
    
    await query.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    await query.answer()

async def info(query: types.CallbackQuery):
    stats = db.get_stats()
    
    text = f"""
ℹ️ <b>معلومات البوت</b>

🎯 <b>وظيفتنا:</b>
فحص أسماء على 11 موقع + صيد متقدم

📱 <b>المواقع:</b>
تيليجرام - إنستغرام - تيك توك - تويتر
يوتيوب - تويتش - جيت هب - ريديت
سناب شات - لينكد ان - بينتيريست

🚀 <b>المميزات:</b>
⚡ فحص فوري
💳 دفع حقيقي بنجوم
📁 فحص الملفات CSV
🎯 صيد أسماء ثلاثية ورباعية
🏆 ترتيب عام
🎛️ إدارة متقدمة

📊 <b>الإحصائيات:</b>
👥 المستخدمين: {stats['users']}
📈 الفحوصات: {stats['checks']}
💰 الأرباح: {stats['earnings']} نجمة

👨‍💻 <b>النسخة:</b> 6.0 PRO
🔒 آمن 100%
⭐ تقييم: ⭐⭐⭐⭐⭐
"""
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 الخطط", callback_data="plans")],
        [InlineKeyboardButton(text="◀️ عودة", callback_data="back")]
    ])
    
    await query.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    await query.answer()

async def back(query: types.CallbackQuery):
    user = db.get_user(query.from_user.id)
    plan = PLANS.get(user['plan'], PLANS['free'])
    
    text = f"👤 {user['name']} | 💳 {plan['name']} | 📊 {user['checks']}/{plan['daily']}"
    
    await query.message.edit_text(text, reply_markup=main_kb(), parse_mode=ParseMode.HTML)
    await query.answer()

async def admin_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    stats = db.get_stats()
    
    text = f"""
🎛️ <b>لوحة التحكم الإدارية</b>

👥 المستخدمين: {stats['users']}
📈 الفحوصات: {stats['checks']}
💰 الأرباح: {stats['earnings']} نجمة

⚙️ <b>الخيارات الإدارية:</b>
"""
    
    await message.answer(text, reply_markup=admin_kb(), parse_mode=ParseMode.HTML)

async def adm_stat(query: types.CallbackQuery):
    if query.from_user.id != ADMIN_ID:
        return
    
    stats = db.get_stats()
    leaders = db.get_top(5)
    
    text = f"""
📊 <b>الإحصائيات الشاملة</b>

👥 المستخدمين: {stats['users']}
📈 الفحوصات: {stats['checks']}
💰 الأرباح: {stats['earnings']} نجمة

🏆 <b>أفضل 5:</b>
"""
    
    for i, user in enumerate(leaders, 1):
        text += f"{i}. {user['name']} - {user['checks']} فحص\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ عودة", callback_data="adm_back")]
    ])
    
    await query.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    await query.answer()

async def adm_earn(query: types.CallbackQuery):
    if query.from_user.id != ADMIN_ID:
        return
    
    stats = db.get_stats()
    
    text = f"""
💰 <b>الأرباح</b>

💵 إجمالي الأرباح: {stats['earnings']} نجمة
👥 عدد المستخدمين: {stats['users']}
📊 متوسط اللاعب: {int(stats['earnings'] / max(1, stats['users']))} نجمة

🎯 الهدف الشهري: 1000 نجمة
📈 التقدم: {int((stats['earnings'] / 1000) * 100)}%
"""
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ عودة", callback_data="adm_back")]
    ])
    
    await query.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    await query.answer()

async def adm_bcast(query: types.CallbackQuery, state: FSMContext):
    if query.from_user.id != ADMIN_ID:
        return
    
    await query.message.answer("📢 أرسل الرسالة للبث:")
    await state.set_state(States.broadcast_msg)
    await query.answer()

async def broadcast_msg(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    await message.answer(f"""
✅ <b>تم إضافة البث</b>

📢 الرسالة: {message.text[:50]}...
⏰ الوقت: {datetime.now().strftime("%H:%M:%S")}
👥 سيتم الإرسال للمستخدمين
""", parse_mode=ParseMode.HTML)
    
    await state.finish()

async def adm_upg(query: types.CallbackQuery, state: FSMContext):
    if query.from_user.id != ADMIN_ID:
        return
    
    await query.message.answer("👤 أرسل User ID لترقيته:")
    await state.set_state(States.upgrade_user_id)
    await query.answer()

async def upgrade_user(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        uid = int(message.text)
        if db.upgrade_user(uid, ADMIN_ID):
            end_date = (datetime.now() + timedelta(days=365)).strftime("%d/%m/%Y")
            
            text = f"""
✅ <b>تمت ترقيتك!</b>

🎉 الخطة الجديدة: ⭐⭐⭐ بريميوم
📅 بواسطة: الإدارة
⏰ ينتهي: {end_date}

🎯 مميزات جديدة:
📊 500 فحص يومياً
🚀 سرعة فورية
📁 فحص الملفات
🎯 صيد متقدم

شكراً! 💚
"""
            
            await message.bot.send_message(uid, text, parse_mode=ParseMode.HTML)
            await message.answer(f"✅ تمت ترقية المستخدم {uid}")
        else:
            await message.answer("❌ خطأ")
    except:
        await message.answer("❌ أدخل رقم صحيح")
    
    await state.finish()

async def adm_ban(query: types.CallbackQuery, state: FSMContext):
    if query.from_user.id != ADMIN_ID:
        return
    
    await query.message.answer("🚫 أرسل User ID للحظر:")
    await state.set_state(States.ban_user_id)
    await query.answer()

async def ban_user(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        uid = int(message.text)
        if db.ban_user(uid):
            await message.answer(f"✅ تم حظر المستخدم {uid}")
        else:
            await message.answer("❌ خطأ")
    except:
        await message.answer("❌ أدخل رقم صحيح")
    
    await state.finish()

async def adm_unban(query: types.CallbackQuery, state: FSMContext):
    if query.from_user.id != ADMIN_ID:
        return
    
    await query.message.answer("✅ أرسل User ID لإلغاء الحظر:")
    await state.set_state(States.ban_user_id)
    await query.answer()

async def adm_back(query: types.CallbackQuery):
    if query.from_user.id != ADMIN_ID:
        return
    
    stats = db.get_stats()
    text = f"🎛️ اللوحة | 👥 {stats['users']} | 📈 {stats['checks']} | 💰 {stats['earnings']} نجمة"
# --- إضافة سيرفر ويب للبقاء حياً 24/7 ---
from flask import Flask
from threading import Thread

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is Running!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()


# ----------------------------------------

async def on_startup(dp):
    print("\n" + "="*50)
    print("🚀 البوت يعمل الآن!")
    print("💳 نظام الدفع: نجوم Telegram")
    print("🎯 الصيد: فعّال")
    print("📁 الملفات: متوفرة")
    print("="*50)


def main():
    keep_alive()  # تشغيل السيرفر 24/7

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(bot, storage=MemoryStorage())

    dp.register_message_handler(start, commands=['start'], state='*')
    dp.register_message_handler(admin_cmd, commands=['admin'], state='*')
    dp.register_message_handler(check_username, state=States.check_user)
    dp.register_message_handler(batch_file, content_types=['document'], state=States.batch_file)
    dp.register_message_handler(broadcast_msg, state=States.broadcast_msg)
    dp.register_message_handler(upgrade_user, state=States.upgrade_user_id)
    dp.register_message_handler(ban_user, state=States.ban_user_id)

    dp.register_callback_query_handler(check, lambda q: q.data == "check")
    dp.register_callback_query_handler(batch, lambda q: q.data == "batch")
    dp.register_callback_query_handler(hunt, lambda q: q.data == "hunt")
    dp.register_callback_query_handler(hunt_process, lambda q: q.data.startswith("hunt_"))
    dp.register_callback_query_handler(plans, lambda q: q.data == "plans")
    dp.register_callback_query_handler(buy_plan, lambda q: q.data.startswith("buy_"))
    dp.register_callback_query_handler(stats, lambda q: q.data == "stats")
    dp.register_callback_query_handler(top, lambda q: q.data == "top")
    dp.register_callback_query_handler(info, lambda q: q.data == "info")
    dp.register_callback_query_handler(back, lambda q: q.data == "back")

    dp.register_callback_query_handler(adm_stat, lambda q: q.data == "adm_stat")
    dp.register_callback_query_handler(adm_earn, lambda q: q.data == "adm_earn")
    dp.register_callback_query_handler(adm_bcast, lambda q: q.data == "adm_bcast", state='*')
    dp.register_callback_query_handler(adm_upg, lambda q: q.data == "adm_upg", state='*')
    dp.register_callback_query_handler(adm_ban, lambda q: q.data == "adm_ban", state='*')
    dp.register_callback_query_handler(adm_unban, lambda q: q.data == "adm_unban", state='*')
    dp.register_callback_query_handler(adm_back, lambda q: q.data == "adm_back")

    dp.register_pre_checkout_query_handler(pre_checkout)
    dp.register_message_handler(successful_payment, content_types=['successful_payment'])

    executor.start_polling(dp, on_startup=on_startup, skip_updates=True)


if __name__ == "__main__":
    main()#