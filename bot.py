import os
import re
import json
import time
import threading
import sqlite3
from datetime import datetime, timedelta, timezone
import pandas as pd
import telebot
from telebot import types
from flask import Flask, request, jsonify
from flask_cors import CORS

# ================= SOZLAMALAR =================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "9250053752:AAHW1tI5OZAXio-fcbnIy-wF24yOxIEQGCk")
SUPER_ADMIN_ID = int(os.environ.get("ADMIN_ID", "5055854613"))
RENDER_URL = "https://vitora-bot.onrender.com"
WEBAPP_URL = "https://uzumseller41-jpg.github.io/vitora-shop/?v=9"
DB_FILE = "vitora.db"
BACKUP_STATE_FILE = "backup_meta.json"
HUMO_CARD = "9860 1501 1189 2918"
PHARMACY_ADDRESS = {
    "cyr": "Самарқанд шаҳар, Қозизода Румий 56 А уй",
    "lat": "Samarqand shahar, Qozizoda Rumiy 56 A uy",
    "ru": "г. Самарканд, ул. Козизода Румий, дом 56 А",
    "en": "56 A Qozizoda Rumiy Street, Samarkand"
}
WORK_HOURS = "08:00 – 24:00"
UZ_TZ = timezone(timedelta(hours=5))

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
app = Flask(__name__)
CORS(app)

waiting_support = set()
user_states = {}
ephemeral_msgs = {}


# ================= 4 TILLI LUG'AT (BOT UCHUN TO'LIQ) =================
BTXT = {
    "cyr": {
        "open_shop": "🛍 Буюртма бериш",
        "open_staff_shop": "🏪 Дўкон ва QR Сканер",
        "bonuses": "🎁 Бонусларим",
        "orders": "🧾 Харидларим",
        "need_med": "💊 Менга керак дори",
        "location": "📍 Жойлашув",
        "support": "💬 Мурожаат",
        "lang_btn": "🌐 Тилни ўзгартириш",
        "search_client": "🔍 Мижозни қидириш",
        "my_kpi": "👷 Менинг профилим (KPI)",
        "prixod": "📥 Приход",
        "edit_prod": "✏️ Товарни таҳрирлаш",
        "discount": "🏷 Скидка эълон қилиш",
        "news": "📢 Янгилик тарқатиш",
        "categories": "📂 Дўкон менюлари",
        "med_reqs": "💊 Сўралган дорилар",
        "director_panel": "👔 Директор панели",
        "season_design": "🎨 Дўкон дизайни (4 фасл)",
        "receipts": "🧾 Чеки ва Савдолар",
        "staff_btn": "👥 Ходим ва Директор",
        "back": "⬅️ Орқага",
        "cancel": "❌ Бекор қилиш",
        "finish_px": "✅ Приходни якунлаш",
        "skip_photo": "⏭ Расмсиз ўтиш",
        "no_expiry": "⏭ Муддатсиз",
        "lang_changed": "✅ Тил муваффақиятли ўзгартирилди!",
        "ask_phone": "Давом этиш учун телефон рақамингизни юборинг 👇",
        "send_phone": "📱 Рақамни юбориш",
        "use_menu": "Пастдаги менюдан фойдаланинг 👇"
    },
    "lat": {
        "open_shop": "🛍 Buyurtma berish",
        "open_staff_shop": "🏪 Do'kon va QR Skaner",
        "bonuses": "🎁 Bonuslarim",
        "orders": "🧾 Xaridlarim",
        "need_med": "💊 Menga kerak dori",
        "location": "📍 Joylashuv",
        "support": "💬 Murojaat",
        "lang_btn": "🌐 Tilni o'zgartirish",
        "search_client": "🔍 Mijozni qidirish",
        "my_kpi": "👷 Mening profilim (KPI)",
        "prixod": "📥 Prixod",
        "edit_prod": "✏️ Tovarni tahrirlash",
        "discount": "🏷 Skidka e'lon qilish",
        "news": "📢 Yangilik tarqatish",
        "categories": "📂 Do'kon menyulari",
        "med_reqs": "💊 So'ralgan dorilar",
        "director_panel": "👔 Direktor paneli",
        "season_design": "🎨 Do'kon dizayni (4 fasl)",
        "receipts": "🧾 Cheklar va Savdolar",
        "staff_btn": "👥 Xodim va Direktor",
        "back": "⬅️ Orqaga",
        "cancel": "❌ Bekor qilish",
        "finish_px": "✅ Prixodni yakunlash",
        "skip_photo": "⏭ Rasmsiz o'tish",
        "no_expiry": "⏭ Muddatsiz",
        "lang_changed": "✅ Til muvaffaqiyatli o'zgartirildi!",
        "ask_phone": "Davom etish uchun telefon raqamingizni yuboring 👇",
        "send_phone": "📱 Raqamni yuborish",
        "use_menu": "Pastdagi menyudan foydalaning 👇"
    },
    "ru": {
        "open_shop": "🛍 Заказать",
        "open_staff_shop": "🏪 Магазин и QR Сканер",
        "bonuses": "🎁 Мои бонусы",
        "orders": "🧾 Мои покупки",
        "need_med": "💊 Нужное лекарство",
        "location": "📍 Локация",
        "support": "💬 Обращение",
        "lang_btn": "🌐 Сменить язык",
        "search_client": "🔍 Поиск клиента",
        "my_kpi": "👷 Мой профиль (KPI)",
        "prixod": "📥 Приход товара",
        "edit_prod": "✏️ Редактировать товар",
        "discount": "🏷 Объявить скидку",
        "news": "📢 Рассылка новостей",
        "categories": "📂 Меню магазина",
        "med_reqs": "💊 Запросы лекарств",
        "director_panel": "👔 Панель Директора",
        "season_design": "🎨 Дизайн (4 сезона)",
        "receipts": "🧾 Чеки и Продажи",
        "staff_btn": "👥 Сотрудники и Директор",
        "back": "⬅️ Назад",
        "cancel": "❌ Отмена",
        "finish_px": "✅ Завершить приход",
        "skip_photo": "⏭ Без фото",
        "no_expiry": "⏭ Без срока",
        "lang_changed": "✅ Язык успешно изменён!",
        "ask_phone": "Для продолжения отправьте ваш номер телефона 👇",
        "send_phone": "📱 Отправить номер",
        "use_menu": "Используйте меню ниже 👇"
    },
    "en": {
        "open_shop": "🛍 Order Now",
        "open_staff_shop": "🏪 Shop & QR Scanner",
        "bonuses": "🎁 My Bonuses",
        "orders": "🧾 My Orders",
        "need_med": "💊 Request Medicine",
        "location": "📍 Location",
        "support": "💬 Support",
        "lang_btn": "🌐 Change Language",
        "search_client": "🔍 Find Client",
        "my_kpi": "👷 My Profile (KPI)",
        "prixod": "📥 Stock Intake",
        "edit_prod": "✏️ Edit Products",
        "discount": "🏷 Set Discount",
        "news": "📢 Broadcast News",
        "categories": "📂 Shop Categories",
        "med_reqs": "💊 Medicine Requests",
        "director_panel": "👔 Director Panel",
        "season_design": "🎨 4-Season Theme",
        "receipts": "🧾 Receipts & Sales",
        "staff_btn": "👥 Staff & Director",
        "back": "⬅️ Back",
        "cancel": "❌ Cancel",
        "finish_px": "✅ Finish Intake",
        "skip_photo": "⏭ Skip Photo",
        "no_expiry": "⏭ No Expiry",
        "lang_changed": "✅ Language updated successfully!",
        "ask_phone": "Please share your phone number to continue 👇",
        "send_phone": "📱 Share Phone Number",
        "use_menu": "Please use the menu below 👇"
    }
}


def t(lang, key):
    return BTXT.get(lang, BTXT["cyr"]).get(key, BTXT["cyr"].get(key, key))


# ================= MA'LUMOTLAR BAZASI VA DOIMIY SAQLASH =================
def get_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def get_or_create_short_code(user_id):
    uid = int(user_id or 0)
    if uid <= 0:
        return "VTR-1000"
    conn = get_db()
    row = conn.execute("SELECT short_code FROM users WHERE user_id = ?", (uid,)).fetchone()
    if row and row["short_code"]:
        conn.close()
        return row["short_code"]

    all_codes = conn.execute("SELECT short_code FROM users WHERE short_code LIKE 'VTR-%'").fetchall()
    max_num = 1000
    for r in all_codes:
        try:
            num = int(r["short_code"].split("-")[1])
            if num > max_num:
                max_num = num
        except Exception:
            pass
    new_code = f"VTR-{max_num + 1}"
    if row:
        conn.execute("UPDATE users SET short_code = ? WHERE user_id = ?", (new_code, uid))
    else:
        conn.execute("INSERT INTO users (user_id, name, username, phone, lang, bonus, total_spent, short_code) VALUES (?, '', '', '', 'cyr', 2000, 0, ?)",
                     (uid, new_code))
    conn.commit()
    conn.close()
    return new_code


def get_tier_info(total_spent):
    spent = int(total_spent or 0)
    if spent >= 3000000:
        return {"name_cyr": "💎 Бриллиант", "name_lat": "💎 Brilliant", "name_ru": "💎 Бриллиант", "name_en": "💎 Diamond", "rate": 0.03, "pct": 3}
    elif spent >= 1500000:
        return {"name_cyr": "🥇 Олтин", "name_lat": "🥇 Oltin", "name_ru": "🥇 Золото", "name_en": "🥇 Gold", "rate": 0.02, "pct": 2}
    elif spent >= 500000:
        return {"name_cyr": "🥈 Кумуш", "name_lat": "🥈 Kumush", "name_ru": "🥈 Серебро", "name_en": "🥈 Silver", "rate": 0.015, "pct": 1.5}
    else:
        return {"name_cyr": "🥉 Бронза", "name_lat": "🥉 Bronza", "name_ru": "🥉 Бронза", "name_en": "🥉 Bronze", "rate": 0.01, "pct": 1}


def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            name TEXT,
            username TEXT,
            phone TEXT,
            lang TEXT DEFAULT 'cyr',
            bonus INTEGER DEFAULT 2000,
            total_spent INTEGER DEFAULT 0,
            short_code TEXT DEFAULT ''
        )
    """)
    for sql in [
        "ALTER TABLE users ADD COLUMN lang TEXT DEFAULT 'cyr'",
        "ALTER TABLE users ADD COLUMN total_spent INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN short_code TEXT DEFAULT ''"
    ]:
        try:
            cur.execute(sql)
        except Exception:
            pass

    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('season_theme', 'spring')")
    cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('superadmin_orders', '1')")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE
        )
    """)
    for default_cat in ["БАДы", "Витамины", "Минералы", "Омега и Жирные кислоты", "Коллаген и Красота", "Протеины и Спорт", "Иммунитет"]:
        cur.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (default_cat,))

    cur.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            brand TEXT DEFAULT 'Vitora',
            category TEXT DEFAULT 'БАДы',
            price INTEGER NOT NULL,
            cost_price INTEGER DEFAULT 0,
            old_price INTEGER DEFAULT 0,
            discount_pct INTEGER DEFAULT 0,
            stock INTEGER DEFAULT 1,
            sold_count INTEGER DEFAULT 0,
            rating_avg REAL DEFAULT 5.0,
            rating_cnt INTEGER DEFAULT 1,
            expiry_date TEXT DEFAULT '',
            expiry_alert_sent INTEGER DEFAULT 0,
            description TEXT DEFAULT '',
            dosage TEXT DEFAULT '',
            benefits TEXT DEFAULT '',
            warnings TEXT DEFAULT '',
            combine_with TEXT DEFAULT '',
            image TEXT DEFAULT ''
        )
    """)
    for sql in [
        "ALTER TABLE products ADD COLUMN brand TEXT DEFAULT 'Vitora'",
        "ALTER TABLE products ADD COLUMN cost_price INTEGER DEFAULT 0",
        "ALTER TABLE products ADD COLUMN old_price INTEGER DEFAULT 0",
        "ALTER TABLE products ADD COLUMN discount_pct INTEGER DEFAULT 0",
        "ALTER TABLE products ADD COLUMN sold_count INTEGER DEFAULT 0",
        "ALTER TABLE products ADD COLUMN rating_avg REAL DEFAULT 5.0",
        "ALTER TABLE products ADD COLUMN rating_cnt INTEGER DEFAULT 1",
        "ALTER TABLE products ADD COLUMN expiry_date TEXT DEFAULT ''",
        "ALTER TABLE products ADD COLUMN expiry_alert_sent INTEGER DEFAULT 0",
        "ALTER TABLE products ADD COLUMN dosage TEXT DEFAULT ''",
        "ALTER TABLE products ADD COLUMN benefits TEXT DEFAULT ''",
        "ALTER TABLE products ADD COLUMN warnings TEXT DEFAULT ''",
        "ALTER TABLE products ADD COLUMN combine_with TEXT DEFAULT ''"
    ]:
        try:
            cur.execute(sql)
        except Exception:
            pass

    cur.execute("""
        CREATE TABLE IF NOT EXISTS cart_reservations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            product_id INTEGER,
            qty INTEGER,
            expires_at REAL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS staff (
            user_id INTEGER PRIMARY KEY,
            role TEXT NOT NULL,
            name TEXT DEFAULT '',
            served_count INTEGER DEFAULT 0,
            total_stars REAL DEFAULT 0,
            rating_count INTEGER DEFAULT 0,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            user_id INTEGER,
            staff_id INTEGER,
            scores_json TEXT,
            avg_score REAL,
            comment TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            body TEXT,
            image TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS receipts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            user_id INTEGER,
            client_name TEXT,
            card_code TEXT,
            items_text TEXT,
            total INTEGER,
            discount_used INTEGER DEFAULT 0,
            final_paid INTEGER,
            payment_method TEXT,
            photo_file_id TEXT DEFAULT '',
            day_str TEXT,
            time_str TEXT,
            created_ts REAL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT,
            username TEXT,
            card TEXT,
            phone TEXT,
            delivery_type TEXT,
            address TEXT,
            payment_method TEXT,
            payment_status TEXT DEFAULT 'Кутилмоқда',
            order_status TEXT DEFAULT 'Янги',
            served_by INTEGER DEFAULT 0,
            items TEXT,
            cart_json TEXT DEFAULT '[]',
            clicked_buttons TEXT DEFAULT '[]',
            total INTEGER,
            discount_used INTEGER DEFAULT 0,
            final_payable INTEGER DEFAULT 0,
            cashback_earned INTEGER DEFAULT 0,
            notified INTEGER DEFAULT 0,
            created_ts REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    for sql in [
        "ALTER TABLE orders ADD COLUMN discount_used INTEGER DEFAULT 0",
        "ALTER TABLE orders ADD COLUMN final_payable INTEGER DEFAULT 0",
        "ALTER TABLE orders ADD COLUMN notified INTEGER DEFAULT 0",
        "ALTER TABLE orders ADD COLUMN clicked_buttons TEXT DEFAULT '[]'"
    ]:
        try:
            cur.execute(sql)
        except Exception:
            pass

    cur.execute("""
        CREATE TABLE IF NOT EXISTS order_notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            chat_id INTEGER,
            message_id INTEGER
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS restock_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            product_id INTEGER,
            product_name TEXT,
            notified INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS medicine_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            client_name TEXT,
            client_code TEXT,
            med_text TEXT,
            photo_file_id TEXT DEFAULT '',
            status TEXT DEFAULT 'Кутилмоқда',
            reply_text TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            product_id INTEGER,
            product_name TEXT,
            qty INTEGER,
            price INTEGER,
            subtotal INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS stock_in (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER,
            product_name TEXT,
            category TEXT,
            qty INTEGER,
            price INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def get_setting(key, default=""):
    conn = get_db()
    r = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return r["value"] if r else default


def set_setting(key, value):
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()


def backup_db_to_telegram():
    try:
        if not os.path.exists(DB_FILE):
            return
        with open(DB_FILE, "rb") as f:
            msg = bot.send_document(
                SUPER_ADMIN_ID,
                f,
                caption="#VITORA_DB_BACKUP (Автоматик база захираси — ўчирманг)",
                disable_notification=True
            )
        old_mid = None
        if os.path.exists(BACKUP_STATE_FILE):
            try:
                old_mid = json.load(open(BACKUP_STATE_FILE)).get("msg_id")
            except Exception:
                pass
        try:
            bot.pin_chat_message(SUPER_ADMIN_ID, msg.message_id, disable_notification=True)
        except Exception:
            pass
        if old_mid and old_mid != msg.message_id:
            try:
                bot.delete_message(SUPER_ADMIN_ID, old_mid)
            except Exception:
                pass
        with open(BACKUP_STATE_FILE, "w") as out:
            json.dump({"msg_id": msg.message_id, "file_id": msg.document.file_id}, out)
    except Exception as e:
        print("Backup xato:", e)


def restore_db_from_telegram_if_empty():
    try:
        conn = get_db()
        cnt = conn.execute("SELECT COUNT(*) as c FROM products").fetchone()["c"]
        conn.close()
        if cnt > 0:
            return
        chat = bot.get_chat(SUPER_ADMIN_ID)
        pinned = getattr(chat, "pinned_message", None)
        if pinned and getattr(pinned, "document", None) and "vitora" in (pinned.document.file_name or "").lower():
            finfo = bot.get_file(pinned.document.file_id)
            raw = bot.download_file(finfo.file_path)
            with open(DB_FILE, "wb") as f:
                f.write(raw)
    except Exception as e:
        print("Restore xato:", e)


init_db()
restore_db_from_telegram_if_empty()
init_db()


# ================= CHATNI TOZA SAQLASH VA YORDAMCHILAR =================
def track_msg(chat_id, msg_id):
    if msg_id:
        ephemeral_msgs.setdefault(chat_id, []).append(msg_id)


def clear_ephemeral(chat_id):
    for mid in ephemeral_msgs.pop(chat_id, []):
        try:
            bot.delete_message(chat_id, mid)
        except Exception:
            pass


def safe_del_msg(chat_id, msg_id):
    try:
        bot.delete_message(chat_id, msg_id)
    except Exception:
        pass


def detect_brand(raw_name):
    nl = raw_name.lower()
    for b in ["Solgar", "Now Foods", "Doppelherz", "Evalar", "California Gold", "Nature's Bounty", "Vitrum", "Complivit", "Orthomol", "Bayer", "Optimum Nutrition", "MyProtein"]:
        if b.lower() in nl:
            return b
    return "Vitora"


def get_user_lang(uid):
    conn = get_db()
    row = conn.execute("SELECT lang FROM users WHERE user_id = ?", (uid,)).fetchone()
    conn.close()
    return row["lang"] if row and row["lang"] else "cyr"


def get_role(uid):
    if uid == SUPER_ADMIN_ID:
        return "superadmin"
    conn = get_db()
    row = conn.execute("SELECT role FROM staff WHERE user_id = ?", (uid,)).fetchone()
    conn.close()
    return row["role"] if row else "client"


def is_admin_or_super(uid):
    return get_role(uid) in ("superadmin", "admin", "admin_director")


def is_director_or_super(uid):
    return get_role(uid) in ("superadmin", "director", "admin_director")


def is_operational_staff(uid):
    # Direktor (faqat director roli) zakaz qabul qilmaydi!
    r = get_role(uid)
    if r == "superadmin":
        return get_setting("superadmin_orders", "1") == "1"
    return r in ("admin", "admin_director", "worker")


def is_staff_any(uid):
    return get_role(uid) in ("superadmin", "admin", "director", "admin_director", "worker")


def get_operational_staff_ids():
    ids = set()
    if get_setting("superadmin_orders", "1") == "1":
        ids.add(SUPER_ADMIN_ID)
    conn = get_db()
    rows = conn.execute("SELECT user_id, role FROM staff").fetchall()
    conn.close()
    for r in rows:
        if r["role"] in ("worker", "admin", "admin_director"):
            ids.add(int(r["user_id"]))
    return list(ids)


def get_admin_and_super_ids():
    ids = {SUPER_ADMIN_ID}
    conn = get_db()
    rows = conn.execute("SELECT user_id, role FROM staff").fetchall()
    conn.close()
    for r in rows:
        if r["role"] in ("admin", "admin_director"):
            ids.add(int(r["user_id"]))
    return list(ids)


def clean_expired_reservations(conn):
    conn.execute("DELETE FROM cart_reservations WHERE expires_at <= ?", (time.time(),))


def get_available_stock(conn, pid):
    clean_expired_reservations(conn)
    p = conn.execute("SELECT stock FROM products WHERE id = ?", (pid,)).fetchone()
    if not p:
        return 0
    res = conn.execute("SELECT COALESCE(SUM(qty), 0) as rqty FROM cart_reservations WHERE product_id = ?", (pid,)).fetchone()
    return max(0, int(p["stock"]) - int(res["rqty"]))


def broadcast_to_clients(text, photo_file_id=None):
    conn = get_db()
    users = conn.execute("SELECT user_id FROM users").fetchall()
    conn.close()
    sent = 0
    for u in users:
        uid = u["user_id"]
        try:
            if photo_file_id:
                bot.send_photo(uid, photo_file_id, caption=text, parse_mode="HTML")
            else:
                bot.send_message(uid, text, parse_mode="HTML")
            sent += 1
            time.sleep(0.04)
        except Exception:
            pass
    return sent


def notify_waiting_restock_clients(pid, prod_name, price):
    conn = get_db()
    reqs = conn.execute("SELECT id, user_id FROM restock_requests WHERE (product_id = ? OR LOWER(product_name) = LOWER(?)) AND notified = 0",
                        (pid, prod_name)).fetchall()
    if not reqs:
        conn.close()
        return 0
    notified_users = set()
    for r in reqs:
        uid = r["user_id"]
        conn.execute("UPDATE restock_requests SET notified = 1 WHERE id = ?", (r["id"],))
        if uid and uid not in notified_users:
            notified_users.add(uid)
            lang = get_user_lang(uid)
            msg = {
                "cyr": f"🔔 <b>СИЗ КУТГАН ТОВАР КЕЛДИ!</b>\n\n💊 <b>{prod_name}</b>\n💵 Нархи: <b>{price:,} сўм</b>\n\n🛍 Дўконга кириб ҳозироқ буюртма беришингиз мумкин!",
                "lat": f"🔔 <b>SIZ KUTGAN TOVAR KELDI!</b>\n\n💊 <b>{prod_name}</b>\n💵 Narxi: <b>{price:,} so'm</b>\n\n🛍 Do'konga kirib hoziroq buyurtma berishingiz mumkin!",
                "ru": f"🔔 <b>ТОВАР, КОТОРЫЙ ВЫ ЖДАЛИ, ПОСТУПИЛ!</b>\n\n💊 <b>{prod_name}</b>\n💵 Цена: <b>{price:,} сум</b>\n\n🛍 Вы можете оформить заказ прямо сейчас!",
                "en": f"🔔 <b>YOUR REQUESTED ITEM IS BACK IN STOCK!</b>\n\n💊 <b>{prod_name}</b>\n💵 Price: <b>{price:,} UZS</b>\n\n🛍 Open the shop to order now!"
            }[lang]
            try:
                bot.send_message(uid, msg, parse_mode="HTML", reply_markup=main_menu_keyboard(uid))
            except Exception:
                pass
    conn.commit()
    conn.close()
    return len(notified_users)


def parse_number(val):
    s = str(val).strip().lower().replace(" ", "").replace("\xa0", "").replace(",", ".").replace("сум", "").replace("сўм", "")
    cleaned = re.sub(r"[^\d.]", "", s)
    if not cleaned:
        return 0
    try:
        return int(float(cleaned))
    except Exception:
        return 0


# ================= ASOSIY MENYU KLAVIATURASI (ROLLAR VA 4 TIL BO'YICHA) =================
def main_menu_keyboard(user_id=0):
    role = get_role(user_id)
    lang = get_user_lang(user_id)
    theme = get_setting("season_theme", "spring")
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)

    # 1. ODDIY MIJOZLAR UCHUN MENYU
    if role == "client":
        url = f"{WEBAPP_URL}&lang={lang}&role=client&theme={theme}"
        kb.row(types.KeyboardButton(text=t(lang, "open_shop"), web_app=types.WebAppInfo(url=url)))
        kb.row(types.KeyboardButton(text=t(lang, "bonuses")), types.KeyboardButton(text=t(lang, "orders")))
        kb.row(types.KeyboardButton(text=t(lang, "need_med")), types.KeyboardButton(text=t(lang, "location")))
        kb.row(types.KeyboardButton(text=t(lang, "support")), types.KeyboardButton(text=t(lang, "lang_btn")))
        return kb

    # 2. FAQAT DIREKTOR (BOSHLIK) UCHUN MAXSUS MENYU
    if role == "director":
        kb.row(types.KeyboardButton(text=t(lang, "director_panel")))
        kb.row(types.KeyboardButton(text=t(lang, "med_reqs")), types.KeyboardButton(text=t(lang, "lang_btn")))
        return kb

    # 3. ISHCHI, ADMIN, ADMIN+DIREKTOR VA SUPERADMIN UCHUN MENYU
    staff_url = f"{WEBAPP_URL}&lang={lang}&role={role}&staff_id={user_id}&theme={theme}"
    kb.row(types.KeyboardButton(text=t(lang, "open_staff_shop"), web_app=types.WebAppInfo(url=staff_url)))
    kb.row(types.KeyboardButton(text=t(lang, "prixod")), types.KeyboardButton(text=t(lang, "search_client")))

    if role == "worker":
        kb.row(types.KeyboardButton(text=t(lang, "my_kpi")), types.KeyboardButton(text=t(lang, "lang_btn")))
        return kb

    # Admin, Admin+Director, SuperAdmin
    kb.row(types.KeyboardButton(text=t(lang, "edit_prod")), types.KeyboardButton(text=t(lang, "discount")))
    kb.row(types.KeyboardButton(text=t(lang, "categories")), types.KeyboardButton(text=t(lang, "med_reqs")))
    kb.row(types.KeyboardButton(text=t(lang, "news")), types.KeyboardButton(text=t(lang, "my_kpi")))

    if role == "admin_director":
        kb.row(types.KeyboardButton(text=t(lang, "director_panel")), types.KeyboardButton(text=t(lang, "lang_btn")))
    elif role == "superadmin":
        kb.row(types.KeyboardButton(text=t(lang, "director_panel")), types.KeyboardButton(text=t(lang, "season_design")))
        kb.row(types.KeyboardButton(text=t(lang, "receipts")), types.KeyboardButton(text=t(lang, "staff_btn")))
        kb.row(types.KeyboardButton(text=t(lang, "lang_btn")))
    else:
        kb.row(types.KeyboardButton(text=t(lang, "lang_btn")))

    return kb


def all_lang_variants(key):
    return {BTXT[l][key] for l in BTXT if key in BTXT[l]}


# ================= DIREKTOR PANELI VA MOLIYAVIY EXCEL OTCHOT =================
def build_director_dashboard_text_and_excel():
    conn = get_db()
    now_uz = datetime.now(UZ_TZ)
    today_str = now_uz.strftime("%Y-%m-%d")
    since_7d = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    since_30d = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")

    # Kunlik savdo
    day_rcp = conn.execute("SELECT COUNT(*) as c, COALESCE(SUM(final_paid), 0) as rev, COALESCE(SUM(discount_used), 0) as disc FROM receipts WHERE day_str = ?", (today_str,)).fetchone()
    # 7 kunlik savdo va sof foyda hisobi
    week_ord = conn.execute("SELECT COUNT(*) as c, COALESCE(SUM(final_payable), 0) as rev, COALESCE(SUM(discount_used), 0) as disc FROM orders WHERE created_at >= ? AND order_status != 'Бекор қилинган ❌'", (since_7d,)).fetchone()
    # 30 kunlik savdo
    month_ord = conn.execute("SELECT COUNT(*) as c, COALESCE(SUM(final_payable), 0) as rev FROM orders WHERE created_at >= ? AND order_status != 'Бекор қилинган ❌'", (since_30d,)).fetchone()

    # Sof foyda (Sotilgan tovarlar narxi - tannarx)
    profit_row = conn.execute("""
        SELECT COALESCE(SUM(oi.subtotal), 0) as gross_rev,
               COALESCE(SUM(oi.qty * COALESCE(p.cost_price, 0)), 0) as total_cost
        FROM order_items oi
        LEFT JOIN products p ON oi.product_id = p.id
        WHERE oi.created_at >= ?
    """, (since_30d,)).fetchone()

    gross_30 = int(profit_row["gross_rev"] or 0)
    cost_30 = int(profit_row["total_cost"] or 0)
    net_profit_30 = gross_30 - cost_30 if cost_30 > 0 else 0
    margin_pct = round((net_profit_30 / gross_30) * 100, 1) if (gross_30 > 0 and cost_30 > 0) else 0

    # Ombor kapitali
    inv = conn.execute("""
        SELECT COUNT(*) as sku,
               COALESCE(SUM(stock), 0) as total_units,
               COALESCE(SUM(stock * cost_price), 0) as stock_cost_val,
               COALESCE(SUM(stock * price), 0) as stock_retail_val
        FROM products WHERE stock > 0
    """).fetchone()

    low_stock = conn.execute("SELECT name, stock FROM products WHERE stock > 0 AND stock <= 5 ORDER BY stock ASC LIMIT 5").fetchall()
    top_prods = conn.execute("SELECT name, sold_count, price FROM products WHERE sold_count > 0 ORDER BY sold_count DESC LIMIT 5").fetchall()
    staff_rows = conn.execute("SELECT user_id, role, name, served_count, total_stars, rating_count FROM staff").fetchall()
    med_reqs_cnt = conn.execute("SELECT COUNT(*) as c FROM medicine_requests WHERE status = 'Кутилмоқда'").fetchone()["c"]
    users_cnt = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
    all_prods = conn.execute("SELECT id, name, brand, category, cost_price, price, discount_pct, stock, sold_count, expiry_date FROM products ORDER BY id DESC").fetchall()
    conn.close()

    avg_check = int(month_ord["rev"] / month_ord["c"]) if month_ord["c"] > 0 else 0

    lines = [
        f"👔 <b>VITORA | ДИРЕКТОР ТАҲЛИЛ ПАНЕЛИ</b>",
        f"🕒 <i>{now_uz.strftime('%d.%m.%Y %H:%M')}</i>\n",
        f"💰 <b>МОЛИЯВИЙ КЎРСАТКИЧЛАР:</b>",
        f"• Бугунги касса: <b>{day_rcp['rev']:,} сўм</b> ({day_rcp['c']} та чек)",
        f"• 7 кунлик тушум: <b>{week_ord['rev']:,} сўм</b> ({week_ord['c']} та буюртма)",
        f"• 30 кунлик тушум: <b>{month_ord['rev']:,} сўм</b> | Ўртача чек: <b>{avg_check:,} сўм</b>",
        f"• 30 кунлик соф фойда (таннарх киритилганлардан): <b>{net_profit_30:,} сўм</b> ({margin_pct}% маржа)\n",
        f"📦 <b>ОМБОР ВА КАПИТАЛ:</b>",
        f"• Турлар (SKU): <b>{inv['sku']} хил</b> ({inv['total_units']} дона)",
        f"• Омбор сотув қиймати: <b>{inv['stock_retail_val']:,} сўм</b>",
        f"• Омбор таннарх қиймати: <b>{inv['stock_cost_val']:,} сўм</b>\n",
        f"👥 <b>МИЖОЗЛАР ВА ДЕФЕКТУРА:</b>",
        f"• Жами мижозлар базаси: <b>{users_cnt} киши</b>",
        f"• Мижозлар сўраган ноёб дорилар: <b>{med_reqs_cnt} та янги сўров</b>\n"
    ]

    if top_prods:
        lines.append("🏆 <b>ЭНГ ХАРИДОРГИР ТОВАРЛАР:</b>")
        for idx, tp in enumerate(top_prods, 1):
            lines.append(f"  {idx}. {tp['name']} — <b>{tp['sold_count']} дона</b>")
        lines.append("")

    if low_stock:
        lines.append("⚠️ <b>ТУГАБ БОРАЁТГАН ТОВАРЛАР (≤5 дона):</b>")
        for ls in low_stock:
            lines.append(f"  • {ls['name']} — <b>{ls['stock']} дона қолди</b>")
        lines.append("")

    if staff_rows:
        lines.append("👷 <b>ХОДИМЛАР KPI РЕЙТИНГИ:</b>")
        for s in staff_rows:
            avg_s = round(s["total_stars"] / s["rating_count"], 2) if s["rating_count"] else 5.0
            lines.append(f"  • ID <code>{s['user_id']}</code> ({s['role']}): <b>{s['served_count']} та</b> хизмат | ⭐ <b>{avg_s}/5</b>")

    excel_path = f"Vitora_Director_Report_{now_uz.strftime('%Y%m%d_%H%M')}.xlsx"
    with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
        pd.DataFrame([{
            "Сана": now_uz.strftime("%d.%m.%Y %H:%M"),
            "Бугунги_тушум": day_rcp["rev"],
            "7_кунлик_тушум": week_ord["rev"],
            "30_кунлик_тушум": month_ord["rev"],
            "30_кунлик_соф_фойда": net_profit_30,
            "Омбор_сотув_қиймати": inv["stock_retail_val"],
            "Омбор_таннарх_қиймати": inv["stock_cost_val"],
            "Мижозлар_сони": users_cnt
        }]).to_excel(writer, sheet_name="Директор_KPI", index=False)
        pd.DataFrame([dict(r) for r in all_prods] if all_prods else []).to_excel(writer, sheet_name="Омбор_ва_Таннарх", index=False)
        pd.DataFrame([
            {
                "ID": r["user_id"], "Роль": r["role"], "Хизматлар": r["served_count"],
                "Рейтинг": round(r["total_stars"] / r["rating_count"], 2) if r["rating_count"] else 5.0
            } for r in staff_rows
        ] if staff_rows else []).to_excel(writer, sheet_name="Ходимлар_KPI", index=False)

    return "\n".join(lines), excel_path


@bot.message_handler(func=lambda m: m.text in all_lang_variants("director_panel") and is_director_or_super(m.from_user.id))
def btn_director_panel(message):
    uid = message.from_user.id
    safe_del_msg(message.chat.id, message.message_id)
    text, path = build_director_dashboard_text_and_excel()

    ikb = types.InlineKeyboardMarkup()
    if uid == SUPER_ADMIN_ID:
        cur_ord = get_setting("superadmin_orders", "1")
        lbl = "🔕 Менга буюртма SMS келмасин (Директор режими)" if cur_ord == "1" else "🔔 Менга ҳам буюртма SMS келсин"
        ikb.add(types.InlineKeyboardButton(lbl, callback_data="dir_toggle_ord"))
    ikb.add(types.InlineKeyboardButton("❌ Ёпиш", callback_data="close_msg"))

    bot.send_message(message.chat.id, text, parse_mode="HTML", reply_markup=ikb)
    with open(path, "rb") as f:
        bot.send_document(message.chat.id, f, caption="📊 Директор учун тўлиқ Excel молиявий ҳисобот")
    if os.path.exists(path):
        os.remove(path)


@bot.callback_query_handler(func=lambda c: c.data == "dir_toggle_ord")
def cb_dir_toggle_ord(call):
    if call.from_user.id != SUPER_ADMIN_ID:
        return
    cur = get_setting("superadmin_orders", "1")
    nxt = "0" if cur == "1" else "1"
    set_setting("superadmin_orders", nxt)
    msg = "🔕 Энди сизга буюртма хабарлари келмайди (фақат ходимларга боради)." if nxt == "0" else "🔔 Буюртма хабарлари ёқилди."
    bot.answer_callback_query(call.id, msg, show_alert=True)
    safe_del_msg(call.message.chat.id, call.message.message_id)


# ================= 4 FASL DIZAYN PANELI =================
@bot.message_handler(func=lambda m: m.text in all_lang_variants("season_design") and get_role(m.from_user.id) == "superadmin")
def btn_season_design(message):
    safe_del_msg(message.chat.id, message.message_id)
    cur = get_setting("season_theme", "spring")
    names = {"spring": "🌸 Баҳор", "summer": "☀️ Ёз", "autumn": "🍂 Куз (Хазонрезги)", "winter": "❄️ Қиш (Қорли)"}
    ikb = types.InlineKeyboardMarkup()
    ikb.row(
        types.InlineKeyboardButton("🌸 Баҳор (Spring)", callback_data="set_season:spring"),
        types.InlineKeyboardButton("☀️ Ёз (Summer)", callback_data="set_season:summer")
    )
    ikb.row(
        types.InlineKeyboardButton("🍂 Куз (Хазон барглар)", callback_data="set_season:autumn"),
        types.InlineKeyboardButton("❄️ Қиш (Қор парчалари)", callback_data="set_season:winter")
    )
    ikb.add(types.InlineKeyboardButton("❌ Ёпиш", callback_data="close_msg"))
    m = bot.send_message(
        message.chat.id,
        f"🎨 <b>ДЎКОН ДИЗАЙНИ (4 ФАСЛ)</b>\n\nҲозирги фаол дизайн: <b>{names.get(cur, cur)}</b>\nҚайси фасл дизайнини ёқамиз?",
        parse_mode="HTML",
        reply_markup=ikb
    )
    track_msg(message.chat.id, m.message_id)


@bot.callback_query_handler(func=lambda c: c.data.startswith("set_season:"))
def cb_set_season(call):
    if get_role(call.from_user.id) != "superadmin":
        return
    season = call.data.split(":")[1]
    set_setting("season_theme", season)
    names = {"spring": "🌸 Баҳор", "summer": "☀️ Ёз", "autumn": "🍂 Куз (Хазон барглар)", "winter": "❄️ Қиш (Қор парчалари)"}
    bot.answer_callback_query(call.id, f"✅ {names.get(season)} ёқилди!")
    safe_del_msg(call.message.chat.id, call.message.message_id)
    bot.send_message(call.message.chat.id, f"✅ Дўкон дизайни <b>{names.get(season)}</b> услубига ўзгарди!", parse_mode="HTML", reply_markup=main_menu_keyboard(call.from_user.id))


# ================= DO'KON MENYULARI (KATEGORIYALAR) PANELI =================
@bot.message_handler(func=lambda m: m.text in all_lang_variants("categories") and is_admin_or_super(m.from_user.id))
def btn_categories_panel(message):
    safe_del_msg(message.chat.id, message.message_id)
    conn = get_db()
    cats = conn.execute("SELECT id, name FROM categories ORDER BY id ASC").fetchall()
    conn.close()
    lines = ["📂 <b>ДЎКОН МЕНЮЛАРИ (КАТЕГОРИЯЛАР)</b>\n"]
    for idx, c in enumerate(cats, 1):
        lines.append(f"{idx}. <b>{c['name']}</b>")

    ikb = types.InlineKeyboardMarkup()
    ikb.add(types.InlineKeyboardButton("➕ Янги меню (категория) қўшиш", callback_data="cat_add"))
    if cats:
        ikb.add(types.InlineKeyboardButton("🗑 Менюни ўчириш", callback_data="cat_del_menu"))
    ikb.add(types.InlineKeyboardButton("❌ Ёпиш", callback_data="close_msg"))
    m = bot.send_message(message.chat.id, "\n".join(lines), parse_mode="HTML", reply_markup=ikb)
    track_msg(message.chat.id, m.message_id)


@bot.callback_query_handler(func=lambda c: c.data.startswith("cat_"))
def cb_categories_actions(call):
    uid = call.from_user.id
    if not is_admin_or_super(uid):
        return
    if call.data == "cat_add":
        safe_del_msg(call.message.chat.id, call.message.message_id)
        user_states[uid] = {"mode": "add_category"}
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add(types.KeyboardButton("⬅️ Орқага"))
        m = bot.send_message(call.message.chat.id, "✍️ Янги дўкон менюси (категория) номини ёзинг (масалан: <i>Протеинлар</i> ёки <i>Болалар витаминлари</i>):", parse_mode="HTML", reply_markup=kb)
        track_msg(call.message.chat.id, m.message_id)
    elif call.data == "cat_del_menu":
        conn = get_db()
        cats = conn.execute("SELECT id, name FROM categories ORDER BY id ASC").fetchall()
        conn.close()
        ikb = types.InlineKeyboardMarkup()
        for c in cats:
            ikb.add(types.InlineKeyboardButton(f"🗑 {c['name']}", callback_data=f"cat_rm:{c['id']}"))
        ikb.add(types.InlineKeyboardButton("⬅️ Орқага", callback_data="close_msg"))
        bot.edit_message_text("Ўчириладиган менюни танланг:", call.message.chat.id, call.message.message_id, reply_markup=ikb)
    elif call.data.startswith("cat_rm:"):
        cid = int(call.data.split(":")[1])
        conn = get_db()
        conn.execute("DELETE FROM categories WHERE id = ?", (cid,))
        conn.commit()
        conn.close()
        safe_del_msg(call.message.chat.id, call.message.message_id)
        bot.answer_callback_query(call.id, "🗑 Меню ўчирилди!")


# ================= MENGA KERAK DORI (MIJOZ VA ADMIN/SUPERADMIN UCHUN) =================
@bot.message_handler(func=lambda m: m.text in all_lang_variants("need_med") and get_role(m.from_user.id) == "client")
def btn_client_need_med(message):
    uid = message.from_user.id
    lang = get_user_lang(uid)
    user_states[uid] = {"mode": "client_need_med"}
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton(t(lang, "back")))
    ask = {
        "cyr": "💊 Дўкондан топа олмаган дорингиз <b>номини</b> ёзинг ёки <b>расмини</b> юборинг.\nБиз уни топиб, келиши ҳақида сизга шахсан жавоб берамиз:",
        "lat": "💊 Do'kondan topa olmagan doringiz <b>nomini</b> yozing yoki <b>rasmini</b> yuboring.\nBiz uni topib, kelishi haqida sizga shaxsan javob beramiz:",
        "ru": "💊 Напишите <b>название</b> или отправьте <b>фото</b> лекарства, которое не нашли в магазине.\nМы закажем его и лично ответим вам:",
        "en": "💊 Type the <b>name</b> or send a <b>photo</b> of the medicine you couldn't find.\nWe will check availability and reply to you directly:"
    }[lang]
    m = bot.send_message(message.chat.id, ask, parse_mode="HTML", reply_markup=kb)
    track_msg(message.chat.id, m.message_id)


@bot.message_handler(func=lambda m: m.text in all_lang_variants("med_reqs") and is_staff_any(m.from_user.id))
def btn_view_med_reqs(message):
    safe_del_msg(message.chat.id, message.message_id)
    conn = get_db()
    rows = conn.execute("SELECT * FROM medicine_requests ORDER BY id DESC LIMIT 15").fetchall()
    conn.close()
    if not rows:
        bot.send_message(message.chat.id, "💊 Ҳозирча мижозлардан сўралган дорилар йўқ.", reply_markup=main_menu_keyboard(message.from_user.id))
        return
    for r in rows:
        ikb = types.InlineKeyboardMarkup()
        if is_admin_or_super(message.from_user.id):
            ikb.row(
                types.InlineKeyboardButton("✅ Олиб келамиз", callback_data=f"mreq_ans:yes:{r['id']}"),
                types.InlineKeyboardButton("❌ Топилмади", callback_data=f"mreq_ans:no:{r['id']}")
            )
            ikb.add(types.InlineKeyboardButton("✍️ Шахсий жавоб ёзиш", callback_data=f"mreq_ans:custom:{r['id']}"))
        cap = (
            f"💊 <b>СЎРОВ #{r['id']}</b> ({r['status']})\n"
            f"👤 Мижоз: <b>{r['client_name']}</b> (<code>{r['client_code']}</code>)\n"
            f"📝 Дори: <b>{r['med_text']}</b>"
        )
        if r["photo_file_id"]:
            bot.send_photo(message.chat.id, r["photo_file_id"], caption=cap, parse_mode="HTML", reply_markup=ikb)
        else:
            bot.send_message(message.chat.id, cap, parse_mode="HTML", reply_markup=ikb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("mreq_ans:"))
def cb_med_req_reply(call):
    uid = call.from_user.id
    if not is_admin_or_super(uid):
        return
    _, kind, rid_s = call.data.split(":")
    rid = int(rid_s)
    conn = get_db()
    req = conn.execute("SELECT * FROM medicine_requests WHERE id = ?", (rid,)).fetchone()
    if not req:
        conn.close()
        return

    if kind in ("yes", "no"):
        if kind == "yes":
            status = "Олиб келинади ✅"
            client_msg = f"💊 <b>Сиз сўраган дори бўйича хушхабар!</b>\n\n📝 Дори: <b>{req['med_text']}</b>\n✅ Ушбу дорини буюртма қилдик, тез орада дорихонамизга келади ва сизга хабар берамиз!"
        else:
            status = "Келмайди ❌"
            client_msg = f"💊 <b>Сиз сўраган дори бўйича маълумот:</b>\n\n📝 Дори: <b>{req['med_text']}</b>\n❌ Афсуски, ҳозирча ушбу дори омборларда топилмади."
        conn.execute("UPDATE medicine_requests SET status = ?, reply_text = ? WHERE id = ?", (status, client_msg, rid))
        conn.commit()
        conn.close()
        safe_del_msg(call.message.chat.id, call.message.message_id)
        bot.answer_callback_query(call.id, "✅ Мижозга жавоб юборилди!")
        try:
            bot.send_message(req["user_id"], client_msg, parse_mode="HTML")
        except Exception:
            pass
    else:
        conn.close()
        user_states[uid] = {"mode": "reply_med_req", "rid": rid, "target_uid": req["user_id"], "med_text": req["med_text"]}
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add(types.KeyboardButton("⬅️ Орқага"))
        m = bot.send_message(call.message.chat.id, f"✍️ <b>{req['client_name']}</b> га (<b>{req['med_text']}</b> бўйича) шахсий жавоб ёзинг:", parse_mode="HTML", reply_markup=kb)
        track_msg(call.message.chat.id, m.message_id)


# ================= FON TEKSHIRUVLARI =================
def background_monitor_loop():
    while True:
        try:
            conn = get_db()
            clean_expired_reservations(conn)
            conn.execute("DELETE FROM receipts WHERE created_ts < ?", (time.time() - (90 * 86400),))
            conn.commit()
            conn.close()
        except Exception:
            pass
        time.sleep(60)


threading.Thread(target=background_monitor_loop, daemon=True).start()


# ================= START, TIL TANLASH VA KONTAKT =================
def ask_language(chat_id):
    ikb = types.InlineKeyboardMarkup()
    ikb.row(
        types.InlineKeyboardButton("🇺🇿 Ўзбекча (Кирилл)", callback_data="setlang:cyr"),
        types.InlineKeyboardButton("🇺🇿 O'zbekcha (Lotin)", callback_data="setlang:lat")
    )
    ikb.row(
        types.InlineKeyboardButton("🇷🇺 Русский", callback_data="setlang:ru"),
        types.InlineKeyboardButton("🇬🇧 English", callback_data="setlang:en")
    )
    m = bot.send_message(chat_id, "🌐 Тилни танланг / Tilni tanlang / Выберите язык / Choose language:", reply_markup=ikb)
    track_msg(chat_id, m.message_id)


@bot.message_handler(commands=["start"])
def cmd_start(message):
    uid = message.from_user.id
    waiting_support.discard(uid)
    user_states.pop(uid, None)
    clear_ephemeral(message.chat.id)
    get_or_create_short_code(uid)
    ask_language(message.chat.id)


@bot.message_handler(func=lambda m: m.text in all_lang_variants("lang_btn"))
def btn_change_lang(message):
    safe_del_msg(message.chat.id, message.message_id)
    ask_language(message.chat.id)


@bot.callback_query_handler(func=lambda c: c.data.startswith("setlang:"))
def cb_set_lang(call):
    uid = call.from_user.id
    lang = call.data.split(":")[1]
    code = get_or_create_short_code(uid)
    conn = get_db()
    row = conn.execute("SELECT phone FROM users WHERE user_id = ?", (uid,)).fetchone()
    conn.execute("UPDATE users SET lang = ?, name = ?, username = ? WHERE user_id = ?",
                 (lang, call.from_user.first_name, call.from_user.username or "", uid))
    conn.commit()
    conn.close()
    bot.answer_callback_query(call.id, "✅")
    safe_del_msg(call.message.chat.id, call.message.message_id)

    if is_staff_any(uid) or (row and row["phone"]):
        bot.send_message(call.message.chat.id, t(lang, "lang_changed"), reply_markup=main_menu_keyboard(uid))
    else:
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.add(types.KeyboardButton(text=t(lang, "send_phone"), request_contact=True))
        m = bot.send_message(call.message.chat.id, t(lang, "ask_phone"), reply_markup=kb)
        track_msg(call.message.chat.id, m.message_id)


@bot.message_handler(content_types=["contact"])
def handle_contact(message):
    if not message.contact:
        return
    phone = message.contact.phone_number
    if not phone.startswith("+"):
        phone = "+" + phone
    uid = message.from_user.id
    lang = get_user_lang(uid)
    card = get_or_create_short_code(uid)
    clear_ephemeral(message.chat.id)

    conn = get_db()
    conn.execute("UPDATE users SET phone = ?, name = ?, username = ? WHERE user_id = ?",
                 (phone, message.from_user.first_name, message.from_user.username or "", uid))
    conn.commit()
    conn.close()
    threading.Thread(target=backup_db_to_telegram, daemon=True).start()

    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=260x260&data={card}"
    caption = {
        "cyr": f"✅ Рўйхатдан ўтдингиз!\n💳 Шахсий кодингиз: <b>{card}</b>\nДўконга келганингизда ушбу QR-кодни ёки <b>{card}</b> рақамини айтинг!",
        "lat": f"✅ Ro'yxatdan o'tdingiz!\n💳 Shaxsiy kodingiz: <b>{card}</b>\nDo'konga kelganingizda ushbu QR-kodni yoki <b>{card}</b> raqamini ayting!",
        "ru": f"✅ Вы зарегистрированы!\n💳 Ваш личный код: <b>{card}</b>\nПокажите QR-код или назовите <b>{card}</b> в аптеке!",
        "en": f"✅ Registration complete!\n💳 Your personal ID: <b>{card}</b>\nShow this QR code or tell <b>{card}</b> at the pharmacy!"
    }[lang]
    try:
        bot.send_photo(message.chat.id, qr_url, caption=caption, parse_mode="HTML", reply_markup=main_menu_keyboard(uid))
    except Exception:
        bot.send_message(message.chat.id, caption, parse_mode="HTML", reply_markup=main_menu_keyboard(uid))


# ================= PRIXOD (ODDIY XODIMLAR UCHUN HAM OCHIQ + QO'LDA DOZIROVKA + KATEGORIYA) =================
@bot.message_handler(func=lambda m: m.text in all_lang_variants("prixod") and is_operational_staff(m.from_user.id))
def btn_unified_prixod(message):
    uid = message.from_user.id
    safe_del_msg(message.chat.id, message.message_id)
    clear_ephemeral(message.chat.id)

    user_states[uid] = {"mode": "prixod_choose_method", "batch": []}
    ikb = types.InlineKeyboardMarkup()
    ikb.add(types.InlineKeyboardButton("➕ 1. Янги товар киритиш (Қўлда нарх)", callback_data="px_m:manual"))
    if get_role(uid) == "superadmin":
        ikb.add(types.InlineKeyboardButton("🤖 2. Авто-приход (Келган нарх + % устама)", callback_data="px_m:auto"))
    ikb.add(types.InlineKeyboardButton("♻️ 3. Эски (базадаги) товарни тўлдириш", callback_data="px_m:old"))
    ikb.add(types.InlineKeyboardButton("⬅️ Орқага", callback_data="px_cancel"))

    m = bot.send_message(
        message.chat.id,
        "📥 <b>ПРИХОД БЎЛИМИ</b>\n\nҚайси усулда товар киритасиз?",
        parse_mode="HTML",
        reply_markup=ikb
    )
    track_msg(message.chat.id, m.message_id)


@bot.callback_query_handler(func=lambda c: c.data.startswith("px_"))
def cb_prixod_controls(call):
    uid = call.from_user.id
    lang = get_user_lang(uid)
    if not is_operational_staff(uid):
        return
    st = user_states.get(uid) or {"batch": []}
    batch = st.get("batch", [])
    action = call.data

    if action == "px_cancel":
        user_states.pop(uid, None)
        clear_ephemeral(call.message.chat.id)
        safe_del_msg(call.message.chat.id, call.message.message_id)
        bot.send_message(call.message.chat.id, "⬅️ Асосий менюга қайтдингиз.", reply_markup=main_menu_keyboard(uid))
        return

    if action == "px_finish":
        user_states.pop(uid, None)
        clear_ephemeral(call.message.chat.id)
        safe_del_msg(call.message.chat.id, call.message.message_id)
        if not batch:
            bot.send_message(call.message.chat.id, "✅ Приход якунланди.", reply_markup=main_menu_keyboard(uid))
            return

        lines = ["🆕 <b>ДОРИХОНАМИЗГА ЯНГИ МАҲСУЛОТЛАР КЕЛДИ!</b>\n"]
        for idx, b in enumerate(batch, 1):
            lines.append(f"{idx}. 💊 <b>{b['name']}</b> — <b>{b['price']:,} сўм</b>")
        lines.append("\n🛍 Онлайн буюртма бериш учун дўконни очинг!")
        cnt = broadcast_to_clients("\n".join(lines))

        threading.Thread(target=backup_db_to_telegram, daemon=True).start()
        bot.send_message(
            call.message.chat.id,
            f"🎉 <b>ПРИХОД ЯКУНЛАНДИ!</b>\n📦 Жами <b>{len(batch)} та</b> товар базага сақланди.\n📨 Мижозларга хабар ({cnt} кишига) юборилди!",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(uid)
        )
        return

    if action.startswith("px_m:"):
        mtype = action.split(":")[1]
        safe_del_msg(call.message.chat.id, call.message.message_id)
        if mtype == "old":
            conn = get_db()
            prods = conn.execute("SELECT id, name, stock FROM products ORDER BY id DESC LIMIT 40").fetchall()
            conn.close()
            if not prods:
                bot.send_message(call.message.chat.id, "Базада ҳозирча товар йўқ. Янги товар киритинг.")
                return
            user_states[uid] = {"mode": "prixod_choose_method", "batch": batch}
            ikb = types.InlineKeyboardMarkup()
            for p in prods:
                ikb.add(types.InlineKeyboardButton(f"{p['name']} (қолдиқ: {p['stock']})", callback_data=f"oldp:{p['id']}"))
            ikb.add(types.InlineKeyboardButton("⬅️ Орқага", callback_data="px_back_menu"))
            m = bot.send_message(call.message.chat.id, "♻️ Базадаги товарни танланг:", reply_markup=ikb)
            track_msg(call.message.chat.id, m.message_id)
            return

        is_auto = (mtype == "auto")
        user_states[uid] = {"mode": "prixod", "is_old": False, "is_auto": is_auto, "step": "photo", "image": "", "batch": batch}
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        kb.row(types.KeyboardButton(t(lang, "skip_photo")), types.KeyboardButton(t(lang, "back")))
        m = bot.send_message(
            call.message.chat.id,
            "1️⃣ Товар <b>расмини</b> юборинг (ёки «Расмсиз ўтиш» ни босинг):",
            parse_mode="HTML",
            reply_markup=kb
        )
        track_msg(call.message.chat.id, m.message_id)
        return

    if action == "px_back_menu":
        safe_del_msg(call.message.chat.id, call.message.message_id)
        user_states[uid] = {"mode": "prixod_choose_method", "batch": batch}
        ikb = types.InlineKeyboardMarkup()
        ikb.add(types.InlineKeyboardButton("➕ 1. Янги товар киритиш (Қўлда нарх)", callback_data="px_m:manual"))
        if get_role(uid) == "superadmin":
            ikb.add(types.InlineKeyboardButton("🤖 2. Авто-приход (Келган нарх + % устама)", callback_data="px_m:auto"))
        ikb.add(types.InlineKeyboardButton("♻️ 3. Эски (базадаги) товарни тўлдириш", callback_data="px_m:old"))
        if batch:
            ikb.add(types.InlineKeyboardButton(f"✅ Приходни якунлаш ({len(batch)} та товар)", callback_data="px_finish"))
        ikb.add(types.InlineKeyboardButton("⬅️ Орқага", callback_data="px_cancel"))
        m = bot.send_message(call.message.chat.id, f"📥 <b>ПРИХОД ОЙНАСИ</b> (Саватда: {len(batch)} та товар):", parse_mode="HTML", reply_markup=ikb)
        track_msg(call.message.chat.id, m.message_id)


@bot.callback_query_handler(func=lambda c: c.data.startswith("oldp:"))
def cb_pick_old_product(call):
    uid = call.from_user.id
    lang = get_user_lang(uid)
    if not is_operational_staff(uid):
        return
    pid = int(call.data.split(":")[1])
    conn = get_db()
    prod = conn.execute("SELECT * FROM products WHERE id = ?", (pid,)).fetchone()
    conn.close()
    if not prod:
        return

    safe_del_msg(call.message.chat.id, call.message.message_id)
    prev = user_states.get(uid, {})
    user_states[uid] = {
        "mode": "prixod",
        "is_old": True,
        "is_auto": False,
        "pid": pid,
        "name": prod["name"],
        "category": prod["category"],
        "price": prod["price"],
        "cost_price": prod["cost_price"],
        "image": prod["image"],
        "batch": prev.get("batch", []),
        "step": "qty"
    }
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton(t(lang, "back")))
    m = bot.send_message(call.message.chat.id, f"♻️ <b>{prod['name']}</b>\nНеча <b>дона</b> келди?", parse_mode="HTML", reply_markup=kb)
    track_msg(call.message.chat.id, m.message_id)
    bot.answer_callback_query(call.id)


# ================= CHEKLAR VA KUNLIK SAVDO ARXIVI =================
@bot.message_handler(func=lambda m: m.text in all_lang_variants("receipts") and get_role(m.from_user.id) == "superadmin")
def btn_receipts_days(message):
    safe_del_msg(message.chat.id, message.message_id)
    conn = get_db()
    days = conn.execute("SELECT day_str, COUNT(*) as cnt, COALESCE(SUM(final_paid), 0) as s FROM receipts GROUP BY day_str ORDER BY day_str DESC LIMIT 30").fetchall()
    conn.close()

    if not days:
        m = bot.send_message(message.chat.id, "🧾 Ҳозирча сақланган тўлов чеклари йўқ.", reply_markup=main_menu_keyboard(message.from_user.id))
        track_msg(message.chat.id, m.message_id)
        return

    ikb = types.InlineKeyboardMarkup()
    for d in days:
        ikb.add(types.InlineKeyboardButton(
            text=f"📅 {d['day_str']}  |  {d['cnt']} та чек  |  {d['s']:,} сўм",
            callback_data=f"rcp_day:{d['day_str']}"
        ))
    ikb.add(types.InlineKeyboardButton("⬅️ Орқага", callback_data="close_msg"))
    m = bot.send_message(message.chat.id, "🧾 <b>ТЎЛОВ ЧЕКЛАРИ ВА КУНЛИК САВДО АРХИВИ</b>\n<i>Кунни танланг:</i>", parse_mode="HTML", reply_markup=ikb)
    track_msg(message.chat.id, m.message_id)


@bot.callback_query_handler(func=lambda c: c.data.startswith("rcp_day:"))
def cb_receipts_by_day(call):
    if get_role(call.from_user.id) != "superadmin":
        return
    day_str = call.data.split(":")[1]
    conn = get_db()
    rows = conn.execute("SELECT * FROM receipts WHERE day_str = ? ORDER BY id ASC", (day_str,)).fetchall()
    conn.close()
    if not rows:
        return

    total_day_sum = sum(int(r["final_paid"] or r["total"] or 0) for r in rows)
    total_disc_sum = sum(int(r["discount_used"] or 0) for r in rows)
    lines = [f"📅 <b>{day_str} — КУНЛИК ЧЕКЛАР ВА САВДО</b>\n━━━━━━━━━━━━━━━━━━━━"]
    for r in rows:
        paid = int(r["final_paid"] or r["total"] or 0)
        disc = int(r["discount_used"] or 0)
        lines.append(
            f"🕒 <b>{r['time_str']}</b> | Чек #{r['order_id']} ({r['payment_method']})\n"
            f"👤 {r['client_name']} (<code>{r['card_code']}</code>)\n"
            f"{r['items_text']}\n"
            f"💵 Тўланди: <b>{paid:,} сўм</b>" + (f" (Скидка: -{disc:,})" if disc else "") + "\n"
        )
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"📊 <b>КУНЛИК УМУМИЙ ХУЛОСА:</b> {len(rows)} та чек | Скидка: {total_disc_sum:,} сўм | 💰 <b>ЖАМИ: {total_day_sum:,} сўм</b>")

    ikb = types.InlineKeyboardMarkup()
    ikb.add(types.InlineKeyboardButton("⬅️ Орқага", callback_data="close_msg"))
    bot.edit_message_text("\n".join(lines), call.message.chat.id, call.message.message_id, parse_mode="HTML", reply_markup=ikb)


@bot.callback_query_handler(func=lambda c: c.data == "close_msg")
def cb_close_msg(call):
    safe_del_msg(call.message.chat.id, call.message.message_id)
    bot.answer_callback_query(call.id)


# ================= BUYURTMANI BIRINCHI QABUL QILISH VA KETMA-KET O'CHUVCHI STATUS TUGMALARI =================
def build_order_step_keyboard(oid, clicked_list):
    ikb = types.InlineKeyboardMarkup()
    row1 = []
    if "prep" not in clicked_list:
        row1.append(types.InlineKeyboardButton("⏳ Тайёрланмоқда", callback_data=f"ost:prep:{oid}"))
    if "ready" not in clicked_list:
        row1.append(types.InlineKeyboardButton("✅ Тайёр", callback_data=f"ost:ready:{oid}"))
    if row1:
        ikb.row(*row1)

    row2 = []
    if "sent" not in clicked_list:
        row2.append(types.InlineKeyboardButton("🚚 Юборилди", callback_data=f"ost:sent:{oid}"))
    if "done" not in clicked_list:
        row2.append(types.InlineKeyboardButton("📦 Доставка қилинди", callback_data=f"ost:done:{oid}"))
    if row2:
        ikb.row(*row2)

    ikb.row(
        types.InlineKeyboardButton("✍️ Бошқа", callback_data=f"ost:custom:{oid}"),
        types.InlineKeyboardButton("🏁 Эгасига берилди", callback_data=f"handover:{oid}")
    )
    return ikb


@bot.callback_query_handler(func=lambda c: c.data.startswith("claim_ord:"))
def cb_claim_order(call):
    staff_uid = call.from_user.id
    if not is_operational_staff(staff_uid):
        return
    oid = int(call.data.split(":")[1])
    conn = get_db()
    order = conn.execute("SELECT * FROM orders WHERE id = ?", (oid,)).fetchone()
    if not order:
        conn.close()
        return

    if order["served_by"] and int(order["served_by"]) != 0 and int(order["served_by"]) != staff_uid:
        conn.close()
        safe_del_msg(call.message.chat.id, call.message.message_id)
        bot.answer_callback_query(call.id, "⚠️ Бу буюртмани бошқа ходим қабул қилиб бўлди!", show_alert=True)
        return

    conn.execute("UPDATE orders SET served_by = ?, order_status = 'Қабул қилинди ✅' WHERE id = ?", (staff_uid, oid))
    notifs = conn.execute("SELECT chat_id, message_id FROM order_notifications WHERE order_id = ?", (oid,)).fetchall()
    conn.execute("DELETE FROM order_notifications WHERE order_id = ?", (oid,))
    conn.commit()
    conn.close()

    # Qolgan barcha ishchilar uchun bu zakaz xabarini o'chirib tashlaymiz!
    for n in notifs:
        if int(n["chat_id"]) != int(call.message.chat.id):
            safe_del_msg(n["chat_id"], n["message_id"])

    bot.answer_callback_query(call.id, "✅ Буюртмани қабул қилдингиз!")
    clicked = json.loads(order["clicked_buttons"] or "[]")
    ikb = build_order_step_keyboard(oid, clicked)
    claimed_text = (
        f"✅ <b>СИЗ ҚАБУЛ ҚИЛГАН БУЮРТМА #{oid}</b> | <code>{order['card']}</code>\n"
        f"👤 {order['name']} ({order['phone']}) | {order['delivery_type']}\n"
        f"💰 Тўлов: <b>{order['payment_method']}</b> ({order['payment_status']})\n"
        f"📦 {order['items']}\n"
        f"💵 <b>Олинади: {order['final_payable']:,} сўм</b>"
    )
    try:
        bot.edit_message_text(claimed_text, call.message.chat.id, call.message.message_id, parse_mode="HTML", reply_markup=ikb)
    except Exception:
        pass

    if order["user_id"]:
        try:
            bot.send_message(order["user_id"], f"👨‍⚕️ <b>Буюртмангиз #{oid} ходим томонидан қабул қилинди!</b>", parse_mode="HTML")
        except Exception:
            pass


@bot.callback_query_handler(func=lambda c: c.data.startswith("ost:"))
def cb_order_status(call):
    staff_uid = call.from_user.id
    if not is_operational_staff(staff_uid):
        return
    _, code, oid_s = call.data.split(":")
    oid = int(oid_s)
    conn = get_db()
    order = conn.execute("SELECT * FROM orders WHERE id = ?", (oid,)).fetchone()
    if not order:
        conn.close()
        return

    if code == "custom":
        conn.close()
        user_states[staff_uid] = {"mode": "custom_order_msg", "target_uid": order["user_id"], "oid": oid}
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add(types.KeyboardButton("⬅️ Орқага"))
        m = bot.send_message(call.message.chat.id, f"✍️ Буюртма #{oid} мижозига юбориладиган хабарни ёзинг:", reply_markup=kb)
        track_msg(call.message.chat.id, m.message_id)
        return

    status_map = {
        "prep": ("⏳ Тайёрланмоқда", f"⏳ <b>Буюртмангиз #{oid} ҳозир тайёрланмоқда!</b>"),
        "ready": ("✅ Тайёр", f"✅ <b>Буюртмангиз #{oid} тайёр!</b> Дорихонадан олиб кетишингиз мумкин."),
        "sent": ("🚚 Юборилди", f"🚚 <b>Буюртмангиз #{oid} курьер орқали йўлга чиқди!</b>"),
        "done": ("📦 Доставка қилинди", f"📦 <b>Буюртмангиз #{oid} етказиб берилди!</b>\nҚабул қилиб олганингизни тасдиқланг ва хизматни баҳоланг 👇")
    }
    st_label, client_txt = status_map[code]
    clicked = json.loads(order["clicked_buttons"] or "[]")
    if code not in clicked:
        clicked.append(code)

    conn.execute("UPDATE orders SET order_status = ?, served_by = ?, clicked_buttons = ? WHERE id = ?",
                 (st_label, staff_uid, json.dumps(clicked), oid))
    conn.commit()
    conn.close()

    bot.answer_callback_query(call.id, st_label)
    # Bosilgan tugma ketma-ket o'chib ketadi!
    new_ikb = build_order_step_keyboard(oid, clicked)
    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=new_ikb)
    except Exception:
        pass

    if order["user_id"]:
        try:
            ckb = None
            if code in ("sent", "done"):
                ckb = types.InlineKeyboardMarkup()
                ckb.add(types.InlineKeyboardButton("📦 Қабул қилиб олдим (Сифатни баҳолаш)", callback_data=f"client_recv:{oid}"))
            bot.send_message(order["user_id"], client_txt, parse_mode="HTML", reply_markup=ckb)
        except Exception:
            pass


# ================= TOLOV TASDIQLASH VA TOPSHIRISH =================
@bot.callback_query_handler(func=lambda c: c.data.startswith("pay_ok:"))
def cb_confirm_payment(call):
    if not is_operational_staff(call.from_user.id):
        return
    oid = int(call.data.split(":")[1])
    conn = get_db()
    order = conn.execute("SELECT * FROM orders WHERE id = ?", (oid,)).fetchone()
    if order and order["payment_status"] != "Тўланган ✅":
        conn.execute("UPDATE orders SET payment_status = 'Тўланган ✅' WHERE id = ?", (oid,))
        uz_now = datetime.now(UZ_TZ)
        paid_amt = int(order["final_payable"] if order["final_payable"] else order["total"])
        conn.execute("""
            INSERT INTO receipts (order_id, user_id, client_name, card_code, items_text, total, discount_used, final_paid, payment_method, day_str, time_str, created_ts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (oid, order["user_id"], order["name"], order["card"], order["items"], order["total"], order["discount_used"], paid_amt, order["payment_method"], uz_now.strftime("%Y-%m-%d"), uz_now.strftime("%H:%M"), time.time()))
        conn.commit()
    conn.close()

    safe_del_msg(call.message.chat.id, call.message.message_id)
    bot.answer_callback_query(call.id, "✅ Тўлов тасдиқланди!")
    threading.Thread(target=backup_db_to_telegram, daemon=True).start()

    if order and order["user_id"]:
        try:
            bot.send_message(order["user_id"], f"✅ <b>Буюртмангиз #{oid} учун тўлов тасдиқланди!</b>", parse_mode="HTML")
        except Exception:
            pass


def trigger_7_skill_rating(client_uid, oid, staff_id):
    if not client_uid:
        return
    skills = ["Муомала маданияти", "Тезкорлик", "Аниқлик", "Дорини тушунтириш", "Дорихона тозалиги", "Ишончлилик", "Умумий хизмат"]
    user_states[client_uid] = {"mode": "rate_staff", "oid": oid, "staff_id": staff_id, "skills": skills, "idx": 0, "scores": {}}
    ikb = types.InlineKeyboardMarkup()
    ikb.row(*[types.InlineKeyboardButton(f"⭐ {i}", callback_data=f"rscore:{i}") for i in range(1, 6)])
    try:
        bot.send_message(client_uid, f"🙏 <b>Харидингиз учун раҳмат! (#{oid})</b>\nХизмат сифатини баҳоланг:\n1/7. <b>{skills[0]}</b>:", parse_mode="HTML", reply_markup=ikb)
    except Exception:
        pass


@bot.callback_query_handler(func=lambda c: c.data.startswith("handover:"))
def cb_handover(call):
    staff_uid = call.from_user.id
    if not is_operational_staff(staff_uid):
        return
    oid = int(call.data.split(":")[1])
    conn = get_db()
    order = conn.execute("SELECT * FROM orders WHERE id = ?", (oid,)).fetchone()
    if order and order["order_status"] != "Топширилган ✅":
        conn.execute("UPDATE orders SET order_status = 'Топширилган ✅', served_by = ? WHERE id = ?", (staff_uid, oid))
        conn.execute("UPDATE staff SET served_count = served_count + 1 WHERE user_id = ?", (staff_uid,))
        conn.commit()
    conn.close()
    safe_del_msg(call.message.chat.id, call.message.message_id)
    bot.answer_callback_query(call.id, "✅ Топширилди!")
    if order:
        trigger_7_skill_rating(order["user_id"], oid, staff_uid)


@bot.callback_query_handler(func=lambda c: c.data.startswith("client_recv:"))
def cb_client_received_online(call):
    uid = call.from_user.id
    oid = int(call.data.split(":")[1])
    conn = get_db()
    order = conn.execute("SELECT * FROM orders WHERE id = ? AND user_id = ?", (oid, uid)).fetchone()
    if not order:
        conn.close()
        return
    staff_id = order["served_by"] or SUPER_ADMIN_ID
    if order["order_status"] != "Топширилган ✅":
        conn.execute("UPDATE orders SET order_status = 'Топширилган ✅', served_by = ? WHERE id = ?", (staff_id, oid))
        conn.execute("UPDATE staff SET served_count = served_count + 1 WHERE user_id = ?", (staff_id,))
        conn.commit()
    conn.close()
    safe_del_msg(call.message.chat.id, call.message.message_id)
    bot.answer_callback_query(call.id, "✅ Қабул қилинди!")
    trigger_7_skill_rating(uid, oid, staff_id)


@bot.callback_query_handler(func=lambda c: c.data.startswith("rscore:"))
def cb_rate_score(call):
    uid = call.from_user.id
    st = user_states.get(uid)
    if not st or st.get("mode") != "rate_staff":
        return
    score = int(call.data.split(":")[1])
    st["scores"][st["skills"][st["idx"]]] = score
    st["idx"] += 1
    bot.answer_callback_query(call.id, f"⭐ {score}")
    if st["idx"] < len(st["skills"]):
        ikb = types.InlineKeyboardMarkup()
        ikb.row(*[types.InlineKeyboardButton(f"⭐ {i}", callback_data=f"rscore:{i}") for i in range(1, 6)])
        bot.edit_message_text(f"Хизмат сифатини баҳоланг:\n<b>{st['idx']+1}/7. {st['skills'][st['idx']]}</b>:", call.message.chat.id, call.message.message_id, parse_mode="HTML", reply_markup=ikb)
    else:
        st["mode"] = "rate_comment"
        bot.edit_message_text("✍️ Барча 7 та мезон баҳоланди! Қисқача <b>фикр (коммент)</b> ёзинг (ёки «-»):", call.message.chat.id, call.message.message_id, parse_mode="HTML")


@bot.callback_query_handler(func=lambda c: c.data.startswith("cancel_ord:"))
def cb_client_cancel_order(call):
    uid = call.from_user.id
    oid = int(call.data.split(":")[1])
    conn = get_db()
    order = conn.execute("SELECT * FROM orders WHERE id = ? AND user_id = ?", (oid, uid)).fetchone()
    if not order or order["order_status"] in ("Бекор қилинган ❌", "Топширилган ✅"):
        conn.close()
        return
    if time.time() - float(order["created_ts"] or 0) > 900:
        conn.close()
        bot.answer_callback_query(call.id, "⏰ 15 дақиқалик вақт тугаган!", show_alert=True)
        return

    for it in json.loads(order["cart_json"] or "[]"):
        conn.execute("UPDATE products SET stock = stock + ?, sold_count = MAX(0, sold_count - ?) WHERE id = ?",
                     (int(it.get("qty", 0)), int(it.get("qty", 0)), int(it.get("id", 0))))
    conn.execute("UPDATE users SET bonus = MAX(0, bonus - ? + ?), total_spent = MAX(0, total_spent - ?) WHERE user_id = ?",
                 (int(order["cashback_earned"]), int(order["discount_used"] or 0), int(order["total"]), uid))
    conn.execute("UPDATE orders SET order_status = 'Бекор қилинган ❌' WHERE id = ?", (oid,))
    conn.commit()
    conn.close()
    bot.edit_message_text(f"❌ <b>Буюртмангиз #{oid} бекор қилинди.</b>", call.message.chat.id, call.message.message_id, parse_mode="HTML")


# ================= TOVAR TAHRIRLASH / SKIDKA / YANGILIK / QIDIRUV / XODIMLAR =================
@bot.message_handler(func=lambda m: m.text in all_lang_variants("edit_prod") and is_admin_or_super(m.from_user.id))
def btn_edit_products(message):
    safe_del_msg(message.chat.id, message.message_id)
    conn = get_db()
    rows = conn.execute("SELECT id, name, price, stock FROM products ORDER BY id DESC LIMIT 30").fetchall()
    conn.close()
    if not rows:
        bot.send_message(message.chat.id, "📦 Базада товар йўқ.")
        return
    ikb = types.InlineKeyboardMarkup()
    for r in rows:
        ikb.add(types.InlineKeyboardButton(f"#{r['id']} | {r['name'][:25]} ({r['price']:,})", callback_data=f"ed_pick:{r['id']}"))
    ikb.add(types.InlineKeyboardButton("⬅️ Орқага", callback_data="close_msg"))
    m = bot.send_message(message.chat.id, "✏️ Товарни танланг:", reply_markup=ikb)
    track_msg(message.chat.id, m.message_id)


@bot.callback_query_handler(func=lambda c: c.data.startswith("ed_"))
def cb_edit_product(call):
    uid = call.from_user.id
    if not is_admin_or_super(uid):
        return
    act, pid_s = call.data.split(":")
    pid = int(pid_s)
    conn = get_db()
    prod = conn.execute("SELECT * FROM products WHERE id = ?", (pid,)).fetchone()
    conn.close()
    if not prod:
        return
    if act == "ed_pick":
        ikb = types.InlineKeyboardMarkup()
        ikb.row(
            types.InlineKeyboardButton("💵 Нархни ўзгартириш", callback_data=f"ed_price:{pid}"),
            types.InlineKeyboardButton("🗑 Ўчириш", callback_data=f"ed_del:{pid}")
        )
        ikb.add(types.InlineKeyboardButton("⬅️ Орқага", callback_data="close_msg"))
        bot.edit_message_text(f"💊 <b>{prod['name']}</b> — {prod['price']:,} сўм ({prod['stock']} дона)", call.message.chat.id, call.message.message_id, parse_mode="HTML", reply_markup=ikb)
    elif act == "ed_price":
        safe_del_msg(call.message.chat.id, call.message.message_id)
        user_states[uid] = {"mode": "edit_price", "pid": pid}
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add(types.KeyboardButton("⬅️ Орқага"))
        m = bot.send_message(call.message.chat.id, f"💵 <b>{prod['name']}</b> учун янги нархни ёзинг:", parse_mode="HTML", reply_markup=kb)
        track_msg(call.message.chat.id, m.message_id)
    elif act == "ed_del":
        conn = get_db()
        conn.execute("DELETE FROM products WHERE id = ?", (pid,))
        conn.commit()
        conn.close()
        safe_del_msg(call.message.chat.id, call.message.message_id)
        threading.Thread(target=backup_db_to_telegram, daemon=True).start()
        bot.answer_callback_query(call.id, "🗑 Ўчирилди!")


@bot.message_handler(func=lambda m: m.text in all_lang_variants("discount") and is_admin_or_super(m.from_user.id))
def btn_discount(message):
    safe_del_msg(message.chat.id, message.message_id)
    conn = get_db()
    rows = conn.execute("SELECT id, name, price FROM products ORDER BY id DESC LIMIT 30").fetchall()
    conn.close()
    if not rows:
        return
    ikb = types.InlineKeyboardMarkup()
    for r in rows:
        ikb.add(types.InlineKeyboardButton(f"#{r['id']} | {r['name'][:25]} ({r['price']:,})", callback_data=f"disc_pick:{r['id']}"))
    ikb.add(types.InlineKeyboardButton("⬅️ Орқага", callback_data="close_msg"))
    m = bot.send_message(message.chat.id, "🏷 Скидка учун товарни танланг:", reply_markup=ikb)
    track_msg(message.chat.id, m.message_id)


@bot.callback_query_handler(func=lambda c: c.data.startswith("disc_pick:"))
def cb_discount_pick(call):
    uid = call.from_user.id
    if not is_admin_or_super(uid):
        return
    safe_del_msg(call.message.chat.id, call.message.message_id)
    user_states[uid] = {"mode": "discount", "pid": int(call.data.split(":")[1])}
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(types.KeyboardButton("10"), types.KeyboardButton("15"), types.KeyboardButton("20"), types.KeyboardButton("25"))
    kb.row(types.KeyboardButton("0 (Скидкани бекор қилиш)"), types.KeyboardButton("⬅️ Орқага"))
    m = bot.send_message(call.message.chat.id, "🏷 Чегирма фоизини (%) ёзинг ёки танланг:", reply_markup=kb)
    track_msg(call.message.chat.id, m.message_id)


@bot.message_handler(func=lambda m: m.text in all_lang_variants("news") and is_admin_or_super(m.from_user.id))
def btn_news(message):
    uid = message.from_user.id
    safe_del_msg(message.chat.id, message.message_id)
    user_states[uid] = {"mode": "news"}
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton("⬅️ Орқага"))
    m = bot.send_message(message.chat.id, "📢 Янгилик матни ёки расмини юборинг:", reply_markup=kb)
    track_msg(message.chat.id, m.message_id)


@bot.message_handler(func=lambda m: m.text in all_lang_variants("search_client") and is_operational_staff(m.from_user.id))
def btn_search_client(message):
    uid = message.from_user.id
    safe_del_msg(message.chat.id, message.message_id)
    user_states[uid] = {"mode": "search_client"}
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton("⬅️ Орқага"))
    m = bot.send_message(message.chat.id, "🔍 Мижознинг <code>VTR-1001</code> (ёки <code>1001</code>) кодини ёки телефонини ёзинг:", parse_mode="HTML", reply_markup=kb)
    track_msg(message.chat.id, m.message_id)


@bot.message_handler(func=lambda m: m.text in all_lang_variants("my_kpi") and is_staff_any(m.from_user.id))
def btn_staff_profile(message):
    uid = message.from_user.id
    safe_del_msg(message.chat.id, message.message_id)
    conn = get_db()
    st = conn.execute("SELECT * FROM staff WHERE user_id = ?", (uid,)).fetchone()
    revs = conn.execute("SELECT avg_score, comment FROM reviews WHERE staff_id = ? ORDER BY id DESC LIMIT 5", (uid,)).fetchall()
    conn.close()
    served = st["served_count"] if st else 0
    avg = round(st["total_stars"] / st["rating_count"], 2) if (st and st["rating_count"] > 0) else 5.0
    lines = [f"👷 <b>ХОДИМ ПРОФИЛИ</b>\n🆔 <code>{uid}</code> | 📦 {served} та | ⭐ {avg}/5.0\n"]
    for r in revs:
        lines.append(f"• ⭐ {r['avg_score']}/5 — <i>{r['comment']}</i>")
    ikb = types.InlineKeyboardMarkup()
    ikb.add(types.InlineKeyboardButton("⬅️ Орқага", callback_data="close_msg"))
    bot.send_message(message.chat.id, "\n".join(lines), parse_mode="HTML", reply_markup=ikb)


@bot.message_handler(func=lambda m: m.text in all_lang_variants("staff_btn") and get_role(m.from_user.id) == "superadmin")
def btn_manage_staff(message):
    safe_del_msg(message.chat.id, message.message_id)
    conn = get_db()
    rows = conn.execute("SELECT * FROM staff").fetchall()
    conn.close()
    role_names = {"worker": "👷 Ишчи", "admin": "🛡 Админ", "director": "👔 Директор", "admin_director": "⭐ Админ+Директор"}
    lines = ["👥 <b>ХОДИМЛАР, АДМИН ВА ДИРЕКТОРЛАР</b>\n"]
    for r in rows:
        avg = round(r["total_stars"] / r["rating_count"], 2) if r["rating_count"] else 5.0
        lines.append(f"• {role_names.get(r['role'], r['role'])} | <code>{r['user_id']}</code> | {r['served_count']} та | ⭐ {avg}")
    ikb = types.InlineKeyboardMarkup()
    ikb.row(
        types.InlineKeyboardButton("👷 Ишчи қўшиш", callback_data="st_add:worker"),
        types.InlineKeyboardButton("🛡 Админ қўшиш", callback_data="st_add:admin")
    )
    ikb.row(
        types.InlineKeyboardButton("👔 Директор қўшиш", callback_data="st_add:director"),
        types.InlineKeyboardButton("⭐ Админ + Директор", callback_data="st_add:admin_director")
    )
    if rows:
        ikb.add(types.InlineKeyboardButton("🗑 Ходимни чиқариш", callback_data="st_del_list"))
    ikb.add(types.InlineKeyboardButton("⬅️ Орқага", callback_data="close_msg"))
    m = bot.send_message(message.chat.id, "\n".join(lines), parse_mode="HTML", reply_markup=ikb)
    track_msg(message.chat.id, m.message_id)


@bot.callback_query_handler(func=lambda c: c.data.startswith("st_"))
def cb_staff_manage(call):
    uid = call.from_user.id
    if get_role(uid) != "superadmin":
        return
    if call.data.startswith("st_add:"):
        safe_del_msg(call.message.chat.id, call.message.message_id)
        user_states[uid] = {"mode": "add_staff", "role": call.data.split(":")[1]}
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add(types.KeyboardButton("⬅️ Орқага"))
        m = bot.send_message(call.message.chat.id, "🆔 Ходим/Директорнинг Telegram ID рақамини юборинг:", reply_markup=kb)
        track_msg(call.message.chat.id, m.message_id)
    elif call.data == "st_del_list":
        conn = get_db()
        rows = conn.execute("SELECT user_id, role FROM staff").fetchall()
        conn.close()
        ikb = types.InlineKeyboardMarkup()
        for r in rows:
            ikb.add(types.InlineKeyboardButton(f"❌ Чиқариш: {r['user_id']} ({r['role']})", callback_data=f"st_rm:{r['user_id']}"))
        ikb.add(types.InlineKeyboardButton("⬅️ Орқага", callback_data="close_msg"))
        bot.edit_message_text("Танланг:", call.message.chat.id, call.message.message_id, reply_markup=ikb)
    elif call.data.startswith("st_rm:"):
        conn = get_db()
        conn.execute("DELETE FROM staff WHERE user_id = ?", (int(call.data.split(":")[1]),))
        conn.commit()
        conn.close()
        safe_del_msg(call.message.chat.id, call.message.message_id)
        threading.Thread(target=backup_db_to_telegram, daemon=True).start()
        bot.answer_callback_query(call.id, "🗑 Ўчирилди!")


# ================= RASM QABUL QILISH =================
@bot.message_handler(content_types=["photo"])
def handle_photo(message):
    uid = message.from_user.id
    lang = get_user_lang(uid)
    st = user_states.get(uid)
    track_msg(message.chat.id, message.message_id)

    # 1. Prixod rasmi
    if is_operational_staff(uid) and st and st.get("mode") == "prixod" and st.get("step") == "photo":
        file_id = message.photo[-1].file_id
        st["image"] = f"{RENDER_URL}/api/tg_photo/{file_id}"
        cap = (message.caption or "").strip()
        if cap:
            st["name"] = cap
            st["brand"] = detect_brand(cap)
            ask_prixod_category(message.chat.id, uid, st)
        else:
            st["step"] = "name"
            kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
            kb.add(types.KeyboardButton("⬅️ Орқага"))
            m = bot.send_message(message.chat.id, "✅ Расм олинди!\n2️⃣ Товар <b>номини</b> ёзинг (масалан: <i>Solgar Omega-3 №50</i>):", parse_mode="HTML", reply_markup=kb)
            track_msg(message.chat.id, m.message_id)
        return

    # 2. Mijoz so'ragan dori rasmi
    if st and st.get("mode") == "client_need_med":
        file_id = message.photo[-1].file_id
        cap = (message.caption or "").strip() or "Расмдаги дори"
        save_and_forward_med_request(message.chat.id, uid, message.from_user.first_name, cap, file_id)
        return

    # 3. Yangilik rasmi
    if is_admin_or_super(uid) and st and st.get("mode") == "news":
        file_id = message.photo[-1].file_id
        caption = (message.caption or "").strip() or "Янгилик!"
        conn = get_db()
        conn.execute("INSERT INTO news (title, body, image) VALUES (?, ?, ?)", ("Янгилик", caption, f"{RENDER_URL}/api/tg_photo/{file_id}"))
        conn.commit()
        conn.close()
        user_states.pop(uid, None)
        clear_ephemeral(message.chat.id)
        threading.Thread(target=backup_db_to_telegram, daemon=True).start()
        cnt = broadcast_to_clients(f"📢 <b>VITORA | ЯНГИЛИК</b>\n\n{caption}", photo_file_id=file_id)
        bot.send_message(message.chat.id, f"✅ Янгилик {cnt} та мижозга юборилди!", reply_markup=main_menu_keyboard(uid))
        return

    # 4. Mijoz to'lov cheki
    if get_role(uid) == "client":
        conn = get_db()
        last_ord = conn.execute("SELECT id, final_payable, total FROM orders WHERE user_id = ? ORDER BY id DESC LIMIT 1", (uid,)).fetchone()
        conn.close()
        oid = last_ord["id"] if last_ord else 0
        amt = (last_ord["final_payable"] or last_ord["total"]) if last_ord else 0
        ikb = types.InlineKeyboardMarkup()
        if oid:
            ikb.add(types.InlineKeyboardButton("✅ Тўловни тасдиқлаш", callback_data=f"pay_ok:{oid}"))
        for sid in get_operational_staff_ids():
            try:
                bot.send_photo(sid, message.photo[-1].file_id, caption=f"🧾 <b>ТЎЛОВ ЧЕКИ</b> | #{oid} | <b>{amt:,} сўм</b>", parse_mode="HTML", reply_markup=ikb)
            except Exception:
                pass
        bot.reply_to(message, "✅ Чек қабул қилинди!")


def save_and_forward_med_request(chat_id, uid, cname, med_text, photo_fid=""):
    lang = get_user_lang(uid)
    code = get_or_create_short_code(uid)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT INTO medicine_requests (user_id, client_name, client_code, med_text, photo_file_id) VALUES (?, ?, ?, ?, ?)",
                (uid, cname, code, med_text, photo_fid))
    rid = cur.lastrowid
    conn.commit()
    conn.close()
    user_states.pop(uid, None)
    clear_ephemeral(chat_id)

    done_txt = {
        "cyr": "✅ Сўровингиз қабул қилинди! Тез орада сизга жавоб берамиз.",
        "lat": "✅ So'rovingiz qabul qilindi! Tez orada sizga javob beramiz.",
        "ru": "✅ Ваш запрос принят! Мы скоро ответим вам.",
        "en": "✅ Your request has been received! We will reply shortly."
    }[lang]
    bot.send_message(chat_id, done_txt, reply_markup=main_menu_keyboard(uid))

    ikb = types.InlineKeyboardMarkup()
    ikb.row(
        types.InlineKeyboardButton("✅ Олиб келамиз", callback_data=f"mreq_ans:yes:{rid}"),
        types.InlineKeyboardButton("❌ Топилмади", callback_data=f"mreq_ans:no:{rid}")
    )
    ikb.add(types.InlineKeyboardButton("✍️ Шахсий жавоб ёзиш", callback_data=f"mreq_ans:custom:{rid}"))
    adm_cap = f"💊 <b>МИЖОЗДАН ЯНГИ ДОРИ СЎРОВИ #{rid}</b>\n👤 <b>{cname}</b> (<code>{code}</code>)\n📝 Сўралган дори: <b>{med_text}</b>"
    for aid in set(get_admin_and_super_ids()):
        try:
            if photo_fid:
                bot.send_photo(aid, photo_fid, caption=adm_cap, parse_mode="HTML", reply_markup=ikb)
            else:
                bot.send_message(aid, adm_cap, parse_mode="HTML", reply_markup=ikb)
        except Exception:
            pass


# ================= PRIXODDA KATEGORIYA TANLASH =================
def ask_prixod_category(chat_id, uid, st):
    st["step"] = "category"
    conn = get_db()
    cats = conn.execute("SELECT name FROM categories ORDER BY id ASC").fetchall()
    conn.close()
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    row = []
    for c in cats:
        row.append(types.KeyboardButton(c["name"]))
        if len(row) == 2:
            kb.row(*row)
            row = []
    if row:
        kb.row(*row)
    kb.add(types.KeyboardButton("⬅️ Орқага"))
    m = bot.send_message(chat_id, f"3️⃣ <b>{st['name']}</b> қайси бўлимга (категорияга) киради? Танланг ёки янги ном ёзинг:", parse_mode="HTML", reply_markup=kb)
    track_msg(chat_id, m.message_id)


# ================= MIJOZ MENYULARI =================
@bot.message_handler(func=lambda m: m.text in all_lang_variants("bonuses") and get_role(m.from_user.id) == "client")
def menu_bonuses(message):
    uid = message.from_user.id
    lang = get_user_lang(uid)
    code = get_or_create_short_code(uid)
    conn = get_db()
    user = conn.execute("SELECT bonus, total_spent FROM users WHERE user_id = ?", (uid,)).fetchone()
    conn.close()
    bonus = user["bonus"] if user else 2000
    spent = user["total_spent"] if user else 0
    tier = get_tier_info(spent)
    bot.send_message(message.chat.id, f"💳 <b>ID:</b> <code>{code}</code>\n🎁 <b>Бонус:</b> <b>{bonus:,} сўм</b>\n🏅 <b>Даража:</b> <b>{tier[f'name_{lang}']} ({tier['pct']}%)</b>", parse_mode="HTML", reply_markup=main_menu_keyboard(uid))


@bot.message_handler(func=lambda m: m.text in all_lang_variants("orders") and get_role(m.from_user.id) == "client")
def menu_orders(message):
    uid = message.from_user.id
    conn = get_db()
    rows = conn.execute("SELECT id, items, total, order_status, payment_status FROM orders WHERE user_id = ? ORDER BY id DESC LIMIT 8", (uid,)).fetchall()
    conn.close()
    if not rows:
        bot.send_message(message.chat.id, "Ҳали харидлар мавжуд эмас.", reply_markup=main_menu_keyboard(uid))
        return
    lines = ["🧾 <b>Харидларингиз:</b>\n"]
    for r in rows:
        lines.append(f"🔹 <b>#{r['id']}</b> — {r['total']:,} сўм | {r['payment_status']} | {r['order_status']}\n{r['items']}\n")
    bot.send_message(message.chat.id, "\n".join(lines), parse_mode="HTML", reply_markup=main_menu_keyboard(uid))


@bot.message_handler(func=lambda m: m.text in all_lang_variants("location") and get_role(m.from_user.id) == "client")
def menu_location(message):
    uid = message.from_user.id
    lang = get_user_lang(uid)
    addr = PHARMACY_ADDRESS.get(lang, PHARMACY_ADDRESS["cyr"])
    bot.send_message(message.chat.id, f"🏥 <b>Vitora | Smart Pharm</b>\n\n📍 <b>Манзил:</b> {addr}\n🕒 <b>Иш вақти:</b> {WORK_HOURS}", parse_mode="HTML", reply_markup=main_menu_keyboard(uid))


@bot.message_handler(func=lambda m: m.text in all_lang_variants("support") and get_role(m.from_user.id) == "client")
def menu_support(message):
    uid = message.from_user.id
    lang = get_user_lang(uid)
    waiting_support.add(uid)
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton(t(lang, "back")))
    bot.send_message(message.chat.id, "✍️ Саволингизни ёзинг:", reply_markup=kb)


# ================= BARCHA MATNLI BOSQICHLAR =================
@bot.message_handler(func=lambda m: True)
def handle_all_text(message):
    uid = message.from_user.id
    lang = get_user_lang(uid)
    txt = (message.text or "").strip()
    st = user_states.get(uid)

    # Ortga / Bekor qilish har qanday holatda ishlaydi
    if txt in all_lang_variants("back") or txt in all_lang_variants("cancel"):
        waiting_support.discard(uid)
        user_states.pop(uid, None)
        clear_ephemeral(message.chat.id)
        bot.send_message(message.chat.id, "⬅️ Асосий меню.", reply_markup=main_menu_keyboard(uid))
        return

    if st:
        track_msg(message.chat.id, message.message_id)
        mode = st.get("mode")

        if mode == "client_need_med":
            save_and_forward_med_request(message.chat.id, uid, message.from_user.first_name, txt, "")
            return

        if mode == "reply_med_req":
            rid = st["rid"]
            target_uid = st["target_uid"]
            med_txt = st["med_text"]
            user_states.pop(uid, None)
            clear_ephemeral(message.chat.id)
            conn = get_db()
            conn.execute("UPDATE medicine_requests SET status = 'Жавоб берилди ✅', reply_text = ? WHERE id = ?", (txt, rid))
            conn.commit()
            conn.close()
            try:
                bot.send_message(target_uid, f"💊 <b>Сиз сўраган дори ({med_txt}) бўйича дорихона жавоби:</b>\n\n{txt}", parse_mode="HTML")
                bot.send_message(message.chat.id, "✅ Мижозга шахсий жавоб юборилди!", reply_markup=main_menu_keyboard(uid))
            except Exception:
                bot.send_message(message.chat.id, "❌ Юбориб бўлмади.", reply_markup=main_menu_keyboard(uid))
            return

        if mode == "add_category":
            conn = get_db()
            conn.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (txt,))
            conn.commit()
            conn.close()
            user_states.pop(uid, None)
            clear_ephemeral(message.chat.id)
            threading.Thread(target=backup_db_to_telegram, daemon=True).start()
            bot.send_message(message.chat.id, f"✅ Янги меню <b>«{txt}»</b> дўконга қўшилди!", parse_mode="HTML", reply_markup=main_menu_keyboard(uid))
            return

        if mode == "rate_comment":
            comment = txt if txt != "-" else "Изоҳ қолдирилмади"
            scores = st["scores"]
            avg = round(sum(scores.values()) / len(scores), 2)
            staff_id = st["staff_id"]
            conn = get_db()
            conn.execute("INSERT INTO reviews (order_id, user_id, staff_id, scores_json, avg_score, comment) VALUES (?, ?, ?, ?, ?, ?)",
                         (st["oid"], uid, staff_id, json.dumps(scores, ensure_ascii=False), avg, comment))
            conn.execute("UPDATE staff SET total_stars = total_stars + ?, rating_count = rating_count + 1 WHERE user_id = ?", (avg, staff_id))
            conn.commit()
            conn.close()
            user_states.pop(uid, None)
            bot.send_message(message.chat.id, f"🙏 Баҳоингиз учун катта раҳмат! (⭐ {avg}/5)", reply_markup=main_menu_keyboard(uid))
            return

        if mode == "search_client":
            q = txt.upper()
            if q.isdigit() and len(q) <= 6:
                q = f"VTR-{q}"
            conn = get_db()
            u = conn.execute("SELECT * FROM users").fetchall()
            found = next((r for r in u if (r["short_code"] or "").upper() == q or (r["phone"] and q in r["phone"])), None)
            conn.close()
            clear_ephemeral(message.chat.id)
            if not found:
                user_states.pop(uid, None)
                bot.send_message(message.chat.id, "❌ Мижоз топилмади.", reply_markup=main_menu_keyboard(uid))
                return
            user_states[uid] = {"mode": "custom_order_msg", "target_uid": found["user_id"], "oid": 0}
            m = bot.send_message(message.chat.id, f"✅ Топилди: <b>{found['name']}</b> (<code>{found['short_code']}</code>)\n✍️ Юбориладиган хабарни ёзинг:", parse_mode="HTML")
            track_msg(message.chat.id, m.message_id)
            return

        if mode == "custom_order_msg":
            target = st["target_uid"]
            oid = st["oid"]
            user_states.pop(uid, None)
            clear_ephemeral(message.chat.id)
            prefix = f"📩 <b>Vitora | Smart Pharm (#{oid}):</b>\n\n" if oid else "📩 <b>Vitora | Smart Pharm:</b>\n\n"
            try:
                bot.send_message(target, prefix + txt, parse_mode="HTML")
                bot.send_message(message.chat.id, "✅ Юборилди!", reply_markup=main_menu_keyboard(uid))
            except Exception:
                bot.send_message(message.chat.id, "❌ Юбориб бўлмади.", reply_markup=main_menu_keyboard(uid))
            return

        if mode == "prixod":
            step = st["step"]
            if step == "photo" and txt in all_lang_variants("skip_photo"):
                st["image"] = ""
                st["step"] = "name"
                kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
                kb.add(types.KeyboardButton("⬅️ Орқага"))
                m = bot.send_message(message.chat.id, "2️⃣ Товар <b>номини</b> ёзинг (масалан: <i>Solgar Omega-3 №50</i>):", parse_mode="HTML", reply_markup=kb)
                track_msg(message.chat.id, m.message_id)
                return

            if step == "name":
                st["name"] = txt
                st["brand"] = detect_brand(txt)
                ask_prixod_category(message.chat.id, uid, st)
                return

            if step == "category":
                st["category"] = txt
                conn = get_db()
                conn.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (txt,))
                conn.commit()
                conn.close()
                st["step"] = "dosage"
                kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
                kb.add(types.KeyboardButton("⬅️ Орқага"))
                m = bot.send_message(
                    message.chat.id,
                    "4️⃣ <b>Қўлланилиши / Кунига неча марта ичилишини</b> қўлда ёзинг:\n<i>(Масалан: Катталарга кунига 2 маҳал овқат вақтида 1 капсуладан)</i>",
                    parse_mode="HTML",
                    reply_markup=kb
                )
                track_msg(message.chat.id, m.message_id)
                return

            if step == "dosage":
                st["dosage"] = txt
                st["step"] = "qty"
                kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
                kb.add(types.KeyboardButton("⬅️ Орқага"))
                m = bot.send_message(message.chat.id, "5️⃣ Неча <b>дона</b> келди?", parse_mode="HTML", reply_markup=kb)
                track_msg(message.chat.id, m.message_id)
                return

            if step == "qty":
                qty = parse_number(txt)
                if qty <= 0:
                    return
                st["qty"] = qty
                st["step"] = "expiry"
                kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
                kb.row(types.KeyboardButton(t(lang, "no_expiry")), types.KeyboardButton("⬅️ Орқага"))
                m = bot.send_message(message.chat.id, "6️⃣ Яроқлилик муддатини (<b>ЙЙЙЙ-ОО-КК</b>, масалан: <code>2027-06-01</code>) ёзинг:", parse_mode="HTML", reply_markup=kb)
                track_msg(message.chat.id, m.message_id)
                return

            if step == "expiry":
                st["expiry"] = "" if txt in all_lang_variants("no_expiry") else txt
                if st.get("is_old"):
                    st["step"] = "ask_price_change"
                    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
                    kb.row(types.KeyboardButton("✅ Ҳа, нархи ўзгарди"), types.KeyboardButton("❌ Йўқ, ўша нархда"))
                    m = bot.send_message(message.chat.id, f"Нархи ўзгардими? (Ҳозирги: <b>{st['price']:,} сўм</b>)", parse_mode="HTML", reply_markup=kb)
                    track_msg(message.chat.id, m.message_id)
                else:
                    st["step"] = "price_input"
                    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
                    kb.add(types.KeyboardButton("⬅️ Орқага"))
                    prompt = "7️⃣ Келган (тан) нархини ёзинг (сўмда):" if st.get("is_auto") else "7️⃣ Сотув нархини ёзинг (сўмда):"
                    m = bot.send_message(message.chat.id, prompt, reply_markup=kb)
                    track_msg(message.chat.id, m.message_id)
                return

            if step == "ask_price_change":
                if "Ҳа" in txt:
                    st["step"] = "price_input"
                    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
                    kb.add(types.KeyboardButton("⬅️ Орқага"))
                    m = bot.send_message(message.chat.id, "Янги сотув нархини ёзинг (сўмда):", reply_markup=kb)
                    track_msg(message.chat.id, m.message_id)
                else:
                    save_single_item_and_continue_batch(message.chat.id, uid, st)
                return

            if step == "price_input":
                val = parse_number(txt)
                if val <= 0:
                    return
                if st.get("is_auto"):
                    st["cost_price"] = val
                    st["step"] = "auto_pct"
                    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
                    kb.row(types.KeyboardButton("15%"), types.KeyboardButton("16%"), types.KeyboardButton("17%"))
                    kb.row(types.KeyboardButton("18%"), types.KeyboardButton("19%"), types.KeyboardButton("20%"))
                    m = bot.send_message(message.chat.id, f"🤖 Келган нарх: <b>{val:,} сўм</b>. Неча % устама қўясиз?", parse_mode="HTML", reply_markup=kb)
                    track_msg(message.chat.id, m.message_id)
                else:
                    st["price"] = val
                    save_single_item_and_continue_batch(message.chat.id, uid, st)
                return

            if step == "auto_pct":
                pct = parse_number(txt)
                if 1 <= pct <= 100:
                    st["price"] = int(round(st["cost_price"] * (100 + pct) / 100.0))
                    save_single_item_and_continue_batch(message.chat.id, uid, st)
                return

        if mode == "edit_price":
            np = parse_number(txt)
            if np > 0:
                conn = get_db()
                conn.execute("UPDATE products SET price = ?, old_price = 0, discount_pct = 0 WHERE id = ?", (np, st["pid"]))
                conn.commit()
                conn.close()
                user_states.pop(uid, None)
                clear_ephemeral(message.chat.id)
                threading.Thread(target=backup_db_to_telegram, daemon=True).start()
                bot.send_message(message.chat.id, f"✅ Нарх <b>{np:,} сўм</b> қилиб янгиланди!", parse_mode="HTML", reply_markup=main_menu_keyboard(uid))
            return

        if mode == "discount":
            pid = st["pid"]
            conn = get_db()
            prod = conn.execute("SELECT * FROM products WHERE id = ?", (pid,)).fetchone()
            if prod:
                if txt.startswith("0"):
                    orig = prod["old_price"] if prod["old_price"] > 0 else prod["price"]
                    conn.execute("UPDATE products SET price = ?, old_price = 0, discount_pct = 0 WHERE id = ?", (orig, pid))
                    conn.commit()
                    conn.close()
                    user_states.pop(uid, None)
                    clear_ephemeral(message.chat.id)
                    bot.send_message(message.chat.id, "✅ Скидка бекор қилинди.", reply_markup=main_menu_keyboard(uid))
                    return
                pct = parse_number(txt)
                if 0 < pct < 95:
                    base = prod["old_price"] if prod["old_price"] > 0 else prod["price"]
                    new_p = int(round(base * (100 - pct) / 100.0))
                    conn.execute("UPDATE products SET price = ?, old_price = ?, discount_pct = ? WHERE id = ?", (new_p, base, pct, pid))
                    conn.commit()
                    conn.close()
                    user_states.pop(uid, None)
                    clear_ephemeral(message.chat.id)
                    threading.Thread(target=backup_db_to_telegram, daemon=True).start()
                    broadcast_to_clients(f"🔥 <b>СКИДКА (-{pct}%)!</b>\n💊 <b>{prod['name']}</b>\n<s>{base:,} сўм</s> → <b>{new_p:,} сўм</b>")
                    bot.send_message(message.chat.id, "✅ Скидка эълон қилинди!", reply_markup=main_menu_keyboard(uid))
                    return
            conn.close()
            return

        if mode == "news":
            conn = get_db()
            conn.execute("INSERT INTO news (title, body, image) VALUES (?, ?, ?)", ("Янгилик", txt, ""))
            conn.commit()
            conn.close()
            user_states.pop(uid, None)
            clear_ephemeral(message.chat.id)
            cnt = broadcast_to_clients(f"📢 <b>VITORA | ЯНГИЛИК</b>\n\n{txt}")
            bot.send_message(message.chat.id, f"✅ Янгилик {cnt} та мижозга юборилди!", reply_markup=main_menu_keyboard(uid))
            return

        if mode == "add_staff":
            tid = parse_number(txt)
            if tid > 10000:
                role = st["role"]
                conn = get_db()
                conn.execute("INSERT OR REPLACE INTO staff (user_id, role, name) VALUES (?, ?, ?)", (tid, role, str(tid)))
                conn.commit()
                conn.close()
                user_states.pop(uid, None)
                clear_ephemeral(message.chat.id)
                threading.Thread(target=backup_db_to_telegram, daemon=True).start()
                bot.send_message(message.chat.id, f"✅ ID <code>{tid}</code> ({role}) қўшилди!", parse_mode="HTML", reply_markup=main_menu_keyboard(uid))
            return

    if uid in waiting_support:
        waiting_support.discard(uid)
        code = get_or_create_short_code(uid)
        for sid in get_operational_staff_ids():
            try:
                bot.send_message(sid, f"📩 <b>Мурожаат ({code}):</b>\n{txt}", parse_mode="HTML")
            except Exception:
                pass
        bot.send_message(message.chat.id, "✅ Мурожаатингиз юборилди!", reply_markup=main_menu_keyboard(uid))
        return

    bot.send_message(message.chat.id, t(lang, "use_menu"), reply_markup=main_menu_keyboard(uid))


def save_single_item_and_continue_batch(chat_id, uid, st):
    conn = get_db()
    cur = conn.cursor()
    if st.get("is_old"):
        pid = st["pid"]
        cur.execute("UPDATE products SET stock = stock + ?, price = ?, cost_price = ?, expiry_date = ?, expiry_alert_sent = 0 WHERE id = ?",
                    (st["qty"], st["price"], st.get("cost_price", 0), st.get("expiry", ""), pid))
    else:
        cur.execute("""
            INSERT INTO products (name, brand, category, price, cost_price, old_price, discount_pct, stock, expiry_date, description, dosage, benefits, warnings, combine_with, image)
            VALUES (?, ?, ?, ?, ?, 0, 0, ?, ?, ?, ?, '', '', '', ?)
        """, (
            st["name"], st.get("brand", "Vitora"), st.get("category", "БАДы"), st["price"], st.get("cost_price", 0),
            st["qty"], st.get("expiry", ""), st["name"], st.get("dosage", ""), st.get("image", "")
        ))
        pid = cur.lastrowid

    cur.execute("INSERT INTO stock_in (product_id, product_name, category, qty, price) VALUES (?, ?, ?, ?, ?)",
                (pid, st["name"], st.get("category", "БАДы"), st["qty"], st["price"]))
    conn.commit()
    conn.close()

    # Ushbu tovarni kutayotgan mijozlarga alohida shaxsiy SMS yuboramiz!
    notified_cnt = notify_waiting_restock_clients(pid, st["name"], st["price"])

    batch = st.get("batch", [])
    batch.append({"name": st["name"], "qty": st["qty"], "price": st["price"]})
    clear_ephemeral(chat_id)

    user_states[uid] = {"mode": "prixod_choose_method", "batch": batch}

    ikb = types.InlineKeyboardMarkup()
    ikb.add(types.InlineKeyboardButton("➕ Яна янги товар киритиш", callback_data="px_m:manual"))
    if get_role(uid) == "superadmin":
        ikb.add(types.InlineKeyboardButton("🤖 Яна Авто-приход (Устама %)", callback_data="px_m:auto"))
    ikb.add(types.InlineKeyboardButton("♻️ Эски товарни тўлдириш", callback_data="px_m:old"))
    ikb.add(types.InlineKeyboardButton(f"✅ Приходни якунлаш ({len(batch)} та товар)", callback_data="px_finish"))

    wait_note = f"\n🔔 Ушбу товарни кутаётган <b>{notified_cnt} та мижозга</b> шахсий хабар юборилди!" if notified_cnt else ""
    summary_lines = "\n".join([f"  {i}. <b>{b['name']}</b> (+{b['qty']} дона) — {b['price']:,} сўм" for i, b in enumerate(batch, 1)])
    m = bot.send_message(
        chat_id,
        f"✅ <b>Базага қўшилди!</b>{wait_note}\n\n"
        f"📋 <b>Жорий приход рўйхати ({len(batch)} та):</b>\n{summary_lines}\n\n"
        f"Яна товар қўшасизми ёки якунлайсизми?",
        parse_mode="HTML",
        reply_markup=ikb
    )
    track_msg(chat_id, m.message_id)


# ================= WEBHOOK VA FLASK API =================
@app.route("/webhook", methods=["POST"])
def telegram_webhook():
    json_str = request.get_data().decode("UTF-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "OK", 200


@app.route("/set_webhook", methods=["GET"])
def set_webhook_route():
    bot.remove_webhook()
    time.sleep(0.5)
    ok = bot.set_webhook(url=f"{RENDER_URL}/webhook")
    return jsonify({"webhook_set": ok})


@app.route("/")
def home():
    return "Vitora Smart Pharm API v9 ishlamoqda!"


@app.route("/api/tg_photo/<file_id>")
def api_tg_photo(file_id):
    try:
        file_info = bot.get_file(file_id)
        downloaded = bot.download_file(file_info.file_path)
        return downloaded, 200, {"Content-Type": "image/jpeg", "Cache-Control": "public, max-age=86400"}
    except Exception:
        return "", 404


@app.route("/api/products", methods=["GET"])
def api_products():
    conn = get_db()
    clean_expired_reservations(conn)
    conn.commit()
    rows = conn.execute("SELECT * FROM products ORDER BY CASE WHEN stock > 0 THEN 0 ELSE 1 END, id DESC").fetchall()
    prods = []
    for r in rows:
        d = dict(r)
        d["available_stock"] = get_available_stock(conn, r["id"])
        prods.append(d)
    news_rows = conn.execute("SELECT * FROM news ORDER BY id DESC LIMIT 15").fetchall()
    cat_rows = conn.execute("SELECT name FROM categories ORDER BY id ASC").fetchall()
    conn.close()
    theme = get_setting("season_theme", "spring")
    return jsonify({
        "products": prods,
        "news": [dict(n) for n in news_rows],
        "categories": [c["name"] for c in cat_rows],
        "card_number": HUMO_CARD,
        "theme": theme
    })


@app.route("/api/notify_restock", methods=["POST"])
def api_notify_restock():
    data = request.json or {}
    uid = int(data.get("user_id") or 0)
    pid = int(data.get("product_id") or 0)
    pname = str(data.get("product_name") or "")
    if not uid:
        return jsonify({"ok": False, "error": "Telegram ID топилмади"})
    conn = get_db()
    exists = conn.execute("SELECT id FROM restock_requests WHERE user_id = ? AND product_id = ? AND notified = 0", (uid, pid)).fetchone()
    if not exists:
        conn.execute("INSERT INTO restock_requests (user_id, product_id, product_name, notified) VALUES (?, ?, ?, 0)", (uid, pid, pname))
        conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/staff/scan_lookup", methods=["GET"])
def api_staff_scan_lookup():
    q = (request.args.get("q") or "").strip().upper()
    if not q:
        return jsonify({"ok": False, "error": "Код киритилмади"})
    if q.isdigit() and len(q) <= 6:
        q = f"VTR-{q}"

    conn = get_db()
    users = conn.execute("SELECT * FROM users").fetchall()
    client = None
    for u in users:
        cid = (u["short_code"] or "").upper()
        if cid == q or (u["phone"] and q in u["phone"].upper()):
            client = dict(u)
            client["card_id"] = cid or get_or_create_short_code(u["user_id"])
            tier = get_tier_info(u["total_spent"])
            client["tier"] = tier["name_cyr"]
            break

    card_to_search = client["card_id"] if client else q
    orders = conn.execute("SELECT * FROM orders WHERE UPPER(card) = ? ORDER BY id DESC LIMIT 5", (card_to_search,)).fetchall()
    conn.close()

    if not client and not orders:
        return jsonify({"ok": False, "error": f"'{q}' бўйича мижоз ёки буюртма топилмади"})

    return jsonify({
        "ok": True,
        "client": client,
        "orders": [dict(o) for o in orders]
    })


@app.route("/api/staff/order_action", methods=["POST"])
def api_staff_order_action():
    data = request.json or {}
    staff_id = int(data.get("staff_id") or SUPER_ADMIN_ID)
    if not is_operational_staff(staff_id):
        return jsonify({"ok": False, "error": "Рухсат йўқ"})

    oid = int(data.get("order_id") or 0)
    action = data.get("action")
    conn = get_db()
    order = conn.execute("SELECT * FROM orders WHERE id = ?", (oid,)).fetchone()
    if not order:
        conn.close()
        return jsonify({"ok": False, "error": "Буюртма топилмади"})

    if action == "pay_ok" and order["payment_status"] != "Тўланган ✅":
        conn.execute("UPDATE orders SET payment_status = 'Тўланган ✅' WHERE id = ?", (oid,))
        uz_now = datetime.now(UZ_TZ)
        paid_amt = int(order["final_payable"] if order["final_payable"] else order["total"])
        conn.execute("""
            INSERT INTO receipts (order_id, user_id, client_name, card_code, items_text, total, discount_used, final_paid, payment_method, day_str, time_str, created_ts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (oid, order["user_id"], order["name"], order["card"], order["items"], order["total"], order["discount_used"], paid_amt, order["payment_method"], uz_now.strftime("%Y-%m-%d"), uz_now.strftime("%H:%M"), time.time()))
        conn.commit()
        conn.close()
        threading.Thread(target=backup_db_to_telegram, daemon=True).start()
        if order["user_id"]:
            try:
                bot.send_message(order["user_id"], f"✅ <b>Буюртмангиз #{oid} учун тўлов тасдиқланди!</b>", parse_mode="HTML")
            except Exception:
                pass
        return jsonify({"ok": True, "msg": "✅ Тўлов тасдиқланди!"})

    if action == "handover" and order["order_status"] != "Топширилган ✅":
        conn.execute("UPDATE orders SET order_status = 'Топширилган ✅', served_by = ? WHERE id = ?", (staff_id, oid))
        conn.execute("UPDATE staff SET served_count = served_count + 1 WHERE user_id = ?", (staff_id,))
        conn.commit()
        conn.close()
        threading.Thread(target=backup_db_to_telegram, daemon=True).start()
        if order["user_id"]:
            trigger_7_skill_rating(order["user_id"], oid, staff_id)
        return jsonify({"ok": True, "msg": "🏁 Товар эгасига берилди!"})

    conn.close()
    return jsonify({"ok": True, "msg": "Бажарилди"})


@app.route("/api/rate_product", methods=["POST"])
def api_rate_product():
    data = request.json or {}
    pid = int(data.get("product_id", 0))
    stars = int(data.get("stars", 5))
    if not pid or stars < 1 or stars > 5:
        return jsonify({"ok": False})
    conn = get_db()
    p = conn.execute("SELECT rating_avg, rating_cnt FROM products WHERE id = ?", (pid,)).fetchone()
    if p:
        cnt = int(p["rating_cnt"] or 1)
        avg = float(p["rating_avg"] or 5.0)
        new_cnt = cnt + 1
        new_avg = round(((avg * cnt) + stars) / new_cnt, 2)
        conn.execute("UPDATE products SET rating_avg = ?, rating_cnt = ? WHERE id = ?", (new_avg, new_cnt, pid))
        conn.commit()
        conn.close()
        return jsonify({"ok": True, "rating_avg": new_avg, "rating_cnt": new_cnt})
    conn.close()
    return jsonify({"ok": False})


@app.route("/api/reserve", methods=["POST"])
def api_reserve():
    data = request.json or {}
    session_id = str(data.get("session_id", "guest"))
    pid = int(data.get("product_id", 0))
    desired_qty = int(data.get("qty", 0))

    conn = get_db()
    clean_expired_reservations(conn)
    p = conn.execute("SELECT stock FROM products WHERE id = ?", (pid,)).fetchone()
    if not p:
        conn.close()
        return jsonify({"ok": False, "allowed_qty": 0})

    others = conn.execute("SELECT COALESCE(SUM(qty), 0) as q FROM cart_reservations WHERE product_id = ? AND session_id != ?", (pid, session_id)).fetchone()["q"]
    max_for_user = max(0, int(p["stock"]) - int(others))
    final_qty = min(max(0, desired_qty), max_for_user)

    conn.execute("DELETE FROM cart_reservations WHERE product_id = ? AND session_id = ?", (pid, session_id))
    if final_qty > 0:
        conn.execute("INSERT INTO cart_reservations (session_id, product_id, qty, expires_at) VALUES (?, ?, ?, ?)",
                     (session_id, pid, final_qty, time.time() + 900))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "allowed_qty": final_qty, "max_stock": max_for_user})


@app.route("/api/user/<int:uid>", methods=["GET"])
def api_user(uid):
    code = get_or_create_short_code(uid)
    conn = get_db()
    u = conn.execute("SELECT bonus, total_spent, lang FROM users WHERE user_id = ?", (uid,)).fetchone()
    conn.close()
    bonus = u["bonus"] if u else 2000
    spent = u["total_spent"] if u else 0
    lang = u["lang"] if u else "cyr"
    tier = get_tier_info(spent)
    return jsonify({
        "bonus": bonus,
        "total_spent": spent,
        "lang": lang,
        "card_id": code,
        "tier": tier.get(f"name_{lang}", tier["name_cyr"]),
        "cashback_pct": tier["pct"]
    })


@app.route("/api/order", methods=["POST"])
def api_order():
    data = request.json or {}
    user_id = int(data.get("user_id", 0) or 0)
    session_id = str(data.get("session_id", "guest"))
    name = data.get("name", "Mijoz")
    username = data.get("username", "yoq")
    card = get_or_create_short_code(user_id) if user_id else data.get("card", "VTR-1000")
    phone = data.get("phone", "")
    delivery_type = data.get("delivery_type", "")
    address = data.get("address", "")
    payment_method = data.get("payment_method", "")
    items_text = data.get("items", "")
    total = int(data.get("total", 0))
    use_bonus = bool(data.get("use_bonus", False))
    cart_items = data.get("cart", [])

    conn = get_db()
    cur = conn.cursor()

    u_row = cur.execute("SELECT bonus, total_spent, lang FROM users WHERE user_id = ?", (user_id,)).fetchone() if user_id else None
    old_spent = u_row["total_spent"] if u_row else 0
    old_bonus = u_row["bonus"] if u_row else 2000
    old_tier = get_tier_info(old_spent)

    discount_used = min(old_bonus, int(total * 0.3)) if (use_bonus and old_bonus > 0) else 0
    final_payable = max(0, total - discount_used)
    cashback_earned = int(round(final_payable * old_tier["rate"]))
    new_spent = old_spent + final_payable
    new_bonus = (old_bonus - discount_used) + cashback_earned

    if user_id:
        if u_row:
            cur.execute("UPDATE users SET bonus = ?, total_spent = ?, phone = ?, short_code = ? WHERE user_id = ?",
                        (new_bonus, new_spent, phone, card, user_id))
        else:
            cur.execute("INSERT INTO users (user_id, name, username, phone, lang, bonus, total_spent, short_code) VALUES (?, ?, ?, ?, 'cyr', ?, ?, ?)",
                        (user_id, name, username, phone, new_bonus, new_spent, card))

    cur.execute("""
        INSERT INTO orders (user_id, name, username, card, phone, delivery_type, address, payment_method, items, cart_json, clicked_buttons, total, discount_used, final_payable, cashback_earned, notified, created_ts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', ?, ?, ?, ?, 1, ?)
    """, (user_id, name, username, card, phone, delivery_type, address, payment_method, items_text, json.dumps(cart_items, ensure_ascii=False), total, discount_used, final_payable, cashback_earned, time.time()))
    order_id = cur.lastrowid

    cur.execute("DELETE FROM cart_reservations WHERE session_id = ?", (session_id,))

    dosage_lines = []
    sold_out_names = []
    for item in cart_items:
        pid = int(item.get("id", 0))
        pname = str(item.get("name", ""))
        qty = int(item.get("qty", 0))
        price = int(item.get("price", 0))
        if pid and qty > 0:
            cur.execute("UPDATE products SET stock = MAX(0, stock - ?), sold_count = sold_count + ? WHERE id = ?", (qty, qty, pid))
            p_info = cur.execute("SELECT stock, dosage FROM products WHERE id = ?", (pid,)).fetchone()
            if p_info and p_info["stock"] == 0:
                sold_out_names.append(pname)
            d_txt = (p_info["dosage"] if p_info and p_info["dosage"] else "Шифокор тавсиясига кўра.")
            dosage_lines.append(f"💊 <b>{pname}</b> ({qty} дона):\n   └ 📋 <i>{d_txt}</i>")
        if qty > 0:
            cur.execute("INSERT INTO order_items (order_id, product_id, product_name, qty, price, subtotal) VALUES (?, ?, ?, ?, ?, ?)",
                        (order_id, pid, pname, qty, price, qty * price))

    # Barcha faol ishchi/adminlarga "Qabul qilish" tugmasi bilan yuboramiz (Direktorga bormaydi, 1 kishiga 1 marta boradi!)
    claim_kb = types.InlineKeyboardMarkup()
    claim_kb.add(types.InlineKeyboardButton("✅ Буюртмани қабул қилиш (Олиш)", callback_data=f"claim_ord:{order_id}"))

    staff_msg = (
        f"🆕 <b>ЯНГИ БУЮРТМА #{order_id}</b> | <code>{card}</code>\n"
        f"👤 {name} ({phone}) | {delivery_type}\n"
        f"💰 Тўлов: <b>{payment_method}</b>\n"
        f"📦 {items_text}\n"
        f"💵 <b>Олинади: {final_payable:,} сўм</b>" + (f" (Скидка: -{discount_used:,})" if discount_used else "")
    )
    sent_sids = set()
    for sid in get_operational_staff_ids():
        if sid in sent_sids:
            continue
        sent_sids.add(sid)
        try:
            sent_m = bot.send_message(sid, staff_msg, parse_mode="HTML", reply_markup=claim_kb)
            cur.execute("INSERT INTO order_notifications (order_id, chat_id, message_id) VALUES (?, ?, ?)",
                        (order_id, sid, sent_m.message_id))
        except Exception:
            pass

    conn.commit()
    conn.close()
    threading.Thread(target=backup_db_to_telegram, daemon=True).start()

    for sname in sold_out_names:
        for aid in set(get_admin_and_super_ids()):
            try:
                bot.send_message(aid, f"⚠️ <b>ТОВАР ТУГАДИ (0 ДОНА)!</b>\n💊 <b>{sname}</b>", parse_mode="HTML")
            except Exception:
                pass

    if user_id:
        cancel_kb = types.InlineKeyboardMarkup()
        cancel_kb.add(types.InlineKeyboardButton("❌ Буюртмани бекор қилиш (15 дақиқа)", callback_data=f"cancel_ord:{order_id}"))
        user_msg = (
            f"✅ <b>Буюртмангиз #{order_id} қабул қилинди!</b>\n"
            f"💳 Шахсий кодингиз: <code>{card}</code>\n"
            f"💵 Тўлов суммаси: <b>{final_payable:,} сўм</b>\n"
            f"🎁 Кэшбэк: <b>+{cashback_earned:,} сўм</b> | Баланс: <b>{new_bonus:,} сўм</b>\n\n"
            + "\n".join(dosage_lines)
        )
        if payment_method in ("Click", "Payme"):
            user_msg += f"\n\n💳 Карта: <code>{HUMO_CARD}</code>\n📸 Тўлов чекини шу ботга юборинг!"
        try:
            bot.send_message(user_id, user_msg, parse_mode="HTML", reply_markup=cancel_kb)
        except Exception:
            pass

    return jsonify({"ok": True, "order_id": order_id})


if __name__ == "__main__":
    try:
        bot.remove_webhook()
        time.sleep(0.5)
        bot.set_webhook(url=f"{RENDER_URL}/webhook")
    except Exception as e:
        print("Webhook xato:", e)
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
