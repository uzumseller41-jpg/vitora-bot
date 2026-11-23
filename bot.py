import os
import re
import time
import threading
import sqlite3
from datetime import datetime, timedelta, timezone
import cv2
import numpy as np
import pandas as pd
import telebot
from telebot import types
from flask import Flask, request, jsonify
from flask_cors import CORS

# ================= SOZLAMALAR =================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "9250053752:AAHW1tI5OZAXio-fcbnIy-wF24yOxIEQGCk")
SUPER_ADMIN_ID = int(os.environ.get("ADMIN_ID", "5055854613"))
RENDER_URL = "https://vitora-bot.onrender.com"
WEBAPP_URL = "https://uzumseller41-jpg.github.io/vitora-shop/?v=5"
DB_FILE = "vitora.db"
HUMO_CARD = "9860 1501 1189 2918"
PHARMACY_ADDRESS_CYR = "Самарқанд шаҳар, Қозизода Румий 56 А уй"
PHARMACY_ADDRESS_LAT = "Samarqand shahar, Qozizoda Rumiy 56 A uy"
PHARMACY_ADDRESS_RU = "г. Самарканд, ул. Козизода Румий, дом 56 А"
WORK_HOURS = "08:00 – 24:00"
UZ_TZ = timezone(timedelta(hours=5))

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
app = Flask(__name__)
CORS(app)

waiting_support = set()
user_states = {}  # prixod, auto_prixod, qr, custom_msg, search_client, rating, edit, discount, news, staff


# ================= MA'LUMOTLAR BAZASI =================
def get_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def make_card_id(user_id):
    return "VTR-" + hex(abs(int(user_id or 1)))[2:].upper().zfill(8)[:8]


# 15% ustama foydani saqlab qoluvchi optimallashtirilgan keshbek tizimi (1% -> 3%)
def get_tier_info(total_spent):
    spent = int(total_spent or 0)
    if spent >= 3000000:
        return {"name_cyr": "💎 Бриллиант", "name_lat": "💎 Brilliant", "name_ru": "💎 Бриллиант", "rate": 0.03, "pct": 3, "next": None}
    elif spent >= 1500000:
        return {"name_cyr": "🥇 Олтин", "name_lat": "🥇 Oltin", "name_ru": "🥇 Золото", "rate": 0.02, "pct": 2, "next": 3000000}
    elif spent >= 500000:
        return {"name_cyr": "🥈 Кумуш", "name_lat": "🥈 Kumush", "name_ru": "🥈 Серебро", "rate": 0.015, "pct": 1.5, "next": 1500000}
    else:
        return {"name_cyr": "🥉 Бронза", "name_lat": "🥉 Bronza", "name_ru": "🥉 Бронза", "rate": 0.01, "pct": 1, "next": 500000}


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
            total_spent INTEGER DEFAULT 0
        )
    """)
    for sql in [
        "ALTER TABLE users ADD COLUMN lang TEXT DEFAULT 'cyr'",
        "ALTER TABLE users ADD COLUMN total_spent INTEGER DEFAULT 0"
    ]:
        try:
            cur.execute(sql)
        except Exception:
            pass

    cur.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT DEFAULT 'БАДы',
            price INTEGER NOT NULL,
            cost_price INTEGER DEFAULT 0,
            old_price INTEGER DEFAULT 0,
            discount_pct INTEGER DEFAULT 0,
            stock INTEGER DEFAULT 1,
            expiry_date TEXT DEFAULT '',
            expiry_alert_sent INTEGER DEFAULT 0,
            description TEXT DEFAULT '',
            dosage TEXT DEFAULT '',
            image TEXT DEFAULT ''
        )
    """)
    for sql in [
        "ALTER TABLE products ADD COLUMN cost_price INTEGER DEFAULT 0",
        "ALTER TABLE products ADD COLUMN old_price INTEGER DEFAULT 0",
        "ALTER TABLE products ADD COLUMN discount_pct INTEGER DEFAULT 0",
        "ALTER TABLE products ADD COLUMN expiry_date TEXT DEFAULT ''",
        "ALTER TABLE products ADD COLUMN expiry_alert_sent INTEGER DEFAULT 0",
        "ALTER TABLE products ADD COLUMN dosage TEXT DEFAULT ''"
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
    for sql in [
        "ALTER TABLE staff ADD COLUMN name TEXT DEFAULT ''",
        "ALTER TABLE staff ADD COLUMN served_count INTEGER DEFAULT 0",
        "ALTER TABLE staff ADD COLUMN total_stars REAL DEFAULT 0",
        "ALTER TABLE staff ADD COLUMN rating_count INTEGER DEFAULT 0"
    ]:
        try:
            cur.execute(sql)
        except Exception:
            pass

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
            total INTEGER,
            cashback_earned INTEGER DEFAULT 0,
            created_ts REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    for sql in [
        "ALTER TABLE orders ADD COLUMN payment_status TEXT DEFAULT 'Кутилмоқда'",
        "ALTER TABLE orders ADD COLUMN order_status TEXT DEFAULT 'Янги'",
        "ALTER TABLE orders ADD COLUMN served_by INTEGER DEFAULT 0",
        "ALTER TABLE orders ADD COLUMN cart_json TEXT DEFAULT '[]'",
        "ALTER TABLE orders ADD COLUMN created_ts REAL DEFAULT 0"
    ]:
        try:
            cur.execute(sql)
        except Exception:
            pass

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


init_db()


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
    return get_role(uid) in ("superadmin", "admin")


def is_staff_any(uid):
    return get_role(uid) in ("superadmin", "admin", "worker")


def get_all_staff_ids():
    ids = {SUPER_ADMIN_ID}
    conn = get_db()
    rows = conn.execute("SELECT user_id FROM staff").fetchall()
    conn.close()
    for r in rows:
        ids.add(int(r["user_id"]))
    return list(ids)


def clean_expired_reservations(conn):
    now = time.time()
    conn.execute("DELETE FROM cart_reservations WHERE expires_at <= ?", (now,))


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


def parse_number(val):
    s = str(val).strip().lower()
    s = s.replace(" ", "").replace("\xa0", "").replace(",", ".").replace("сум", "").replace("сўм", "")
    cleaned = re.sub(r"[^\d.]", "", s)
    if not cleaned:
        return 0
    try:
        return int(float(cleaned))
    except Exception:
        return 0


def generate_scientific_promo_idea(product_name, category):
    n = (product_name + " " + category).lower()
    if "омега" in n or "omega" in n:
        return "🧬 Илмий асос: Омега-3 (EPA/DHA) юрак-қон томир ва мия фаолияти учун 1–3 ойлик узлуксиз курс талаб қилади. 💡 Ғоя: «2 та олсангиз +15% чегирма (Тўлиқ 2 ойлик курс)» акциясини эълон қилинг."
    if "витамин" in n or "иммун" in n or "цинк" in n or "d3" in n:
        return "🧬 Илмий асос: Иммунитет ҳужайралари янгиланиши учун камида 30 кунлик қабул зарур. 💡 Ғоя: «Оилавий иммунитет пакети — 20% чегирма» номи остида тез сотиш мумкин."
    if "коллаген" in n or "биотин" in n:
        return "🧬 Илмий асос: Тери ва бўғимларда коллаген синтези 4–6 ҳафтада натижа беради. 💡 Ғоя: «Курс учун махсус -20% чегирма» билан мижозларга таклиф қилинг."
    return "🧬 Илмий асос: Биологик фаол қўшимчалар курс шаклида қабул қилинганда юқори самара беради. 💡 Ғоя: Муддати тугашидан 3 ой олдин 15–25% чегирма билан курс харидини рағбатлантириш энг тўғри ечим."


# ================= ASOSIY MENYU KLAVIATURASI =================
def main_menu_keyboard(user_id=0):
    role = get_role(user_id)
    lang = get_user_lang(user_id)
    url = f"{WEBAPP_URL}&lang={lang}"

    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    if lang == "lat":
        kb.row(types.KeyboardButton(text="🛍 Buyurtma berish", web_app=types.WebAppInfo(url=url)))
        kb.row(types.KeyboardButton(text="🎁 Bonuslarim"), types.KeyboardButton(text="🧾 Xaridlarim"))
        kb.row(types.KeyboardButton(text="📍 Joylashuv"), types.KeyboardButton(text="💬 Murojaat"))
        kb.row(types.KeyboardButton(text="🌐 Tilni o'zgartirish"))
    elif lang == "ru":
        kb.row(types.KeyboardButton(text="🛍 Заказать", web_app=types.WebAppInfo(url=url)))
        kb.row(types.KeyboardButton(text="🎁 Мои бонусы"), types.KeyboardButton(text="🧾 Мои покупки"))
        kb.row(types.KeyboardButton(text="📍 Локация"), types.KeyboardButton(text="💬 Обращение"))
        kb.row(types.KeyboardButton(text="🌐 Сменить язык"))
    else:
        kb.row(types.KeyboardButton(text="🛍 Буюртма бериш", web_app=types.WebAppInfo(url=url)))
        kb.row(types.KeyboardButton(text="🎁 Бонусларим"), types.KeyboardButton(text="🧾 Харидларим"))
        kb.row(types.KeyboardButton(text="📍 Жойлашув"), types.KeyboardButton(text="💬 Мурожаат"))
        kb.row(types.KeyboardButton(text="🌐 Тилни ўзгартириш"))

    # Ishchi, Admin va SuperAdmin uchun umumiy ishchi tugmalar
    if role in ("superadmin", "admin", "worker"):
        kb.row(
            types.KeyboardButton(text="📷 QR Сканер"),
            types.KeyboardButton(text="🔍 Мижозни қидириш")
        )
        kb.row(types.KeyboardButton(text="👷 Менинг профилим (KPI)"))

    # Admin va SuperAdmin uchun (cheklangan vakolat bilan)
    if role in ("superadmin", "admin"):
        kb.row(
            types.KeyboardButton(text="➕ Приход қилиш"),
            types.KeyboardButton(text="✏️ Товарни таҳрирлаш")
        )
        kb.row(
            types.KeyboardButton(text="🏷 Скидка эълон қилиш"),
            types.KeyboardButton(text="📢 Янгилик тарқатиш")
        )

    # Faqat Bosh Admin (SuperAdmin) vakolatlari
    if role == "superadmin":
        kb.row(
            types.KeyboardButton(text="🤖 Авто-приход (Устама %)"),
            types.KeyboardButton(text="📊 Ҳафталик отчёт")
        )
        kb.row(types.KeyboardButton(text="👥 Ходим ва Админлар"))

    return kb


# ================= HAFTALIK EXCEL VA MATNLI OTCHOT =================
def generate_weekly_report_and_excel():
    conn = get_db()
    since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    summary = conn.execute("SELECT COUNT(*) as cnt, COALESCE(SUM(total), 0) as rev FROM orders WHERE created_at >= ?", (since,)).fetchone()
    top_items = conn.execute("SELECT product_name, SUM(qty) as sold_qty, SUM(subtotal) as sold_sum FROM order_items WHERE created_at >= ? GROUP BY product_name ORDER BY sold_qty DESC", (since,)).fetchall()
    staff_rows = conn.execute("SELECT user_id, role, name, served_count, total_stars, rating_count FROM staff").fetchall()
    all_prods = conn.execute("SELECT id, name, category, cost_price, price, discount_pct, stock, expiry_date FROM products ORDER BY id DESC").fetchall()
    conn.close()

    uz_now = datetime.now(UZ_TZ).strftime("%d.%m.%Y %H:%M")
    lines = [
        f"📊 <b>VITORA | ҲАФТАЛИК МОЛИЯВИЙ ОТЧЁТ</b>",
        f"🕒 Сана: <i>{uz_now}</i>\n",
        f"🛒 <b>Жами буюртмалар:</b> {summary['cnt']} та",
        f"💰 <b>Умумий тушум:</b> {summary['rev']:,} сўм"
    ]

    excel_path = f"Vitora_Otchot_{datetime.now(UZ_TZ).strftime('%Y%m%d_%H%M')}.xlsx"
    with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
        pd.DataFrame([{"Сана": uz_now, "Буюртмалар": summary["cnt"], "Тушум (сўм)": summary["rev"]}]).to_excel(writer, sheet_name="Умумий", index=False)
        pd.DataFrame([dict(r) for r in top_items] if top_items else []).to_excel(writer, sheet_name="Хит_товарлар", index=False)
        pd.DataFrame([dict(r) for r in all_prods] if all_prods else []).to_excel(writer, sheet_name="Омбор_ва_Срок", index=False)
        pd.DataFrame([
            {
                "ID": r["user_id"], "Роль": r["role"], "Хизматлар сони": r["served_count"],
                "Ўртача рейтинг": round(r["total_stars"] / r["rating_count"], 2) if r["rating_count"] else 0
            } for r in staff_rows
        ] if staff_rows else []).to_excel(writer, sheet_name="Ходимлар_KPI", index=False)

    return "\n".join(lines), excel_path


# ================= FON TEKSHIRUVLARI (3 OYLIK SROK + RESERVATION) =================
def background_monitor_loop():
    last_sent_week = None
    while True:
        try:
            conn = get_db()
            clean_expired_reservations(conn)

            # 3 oy (90 kun) oldin srok ogohlantirishi
            today = datetime.now(UZ_TZ).date()
            prods = conn.execute("SELECT id, name, category, stock, expiry_date, expiry_alert_sent FROM products WHERE expiry_date != '' AND expiry_alert_sent = 0 AND stock > 0").fetchall()
            for p in prods:
                try:
                    exp_d = datetime.strptime(p["expiry_date"], "%Y-%m-%d").date()
                    days_left = (exp_d - today).days
                    if 0 <= days_left <= 90:
                        idea = generate_scientific_promo_idea(p["name"], p["category"])
                        msg = (
                            f"⏳ <b>ЯРОҚЛИЛИК МУДДАТИ ОГОҲЛАНТИРИШИ (3 ОЙ ҚОЛДИ)!</b>\n\n"
                            f"💊 <b>{p['name']}</b>\n"
                            f"📅 Муддати: <b>{p['expiry_date']}</b> ({days_left} кун қолди)\n"
                            f"📦 Омборда: <b>{p['stock']} дона</b>\n\n"
                            f"{idea}"
                        )
                        ikb = types.InlineKeyboardMarkup()
                        ikb.add(types.InlineKeyboardButton("🏷 Шу товарга скидка қўйиш", callback_data=f"disc_pick:{p['id']}"))
                        bot.send_message(SUPER_ADMIN_ID, msg, parse_mode="HTML", reply_markup=ikb)
                        conn.execute("UPDATE products SET expiry_alert_sent = 1 WHERE id = ?", (p["id"],))
                except Exception:
                    pass
            conn.commit()
            conn.close()

            # Yakshanba 21:00 haftalik otchot
            now_uz = datetime.now(UZ_TZ)
            week_key = now_uz.strftime("%Y-%W")
            if now_uz.weekday() == 6 and now_uz.hour == 21 and last_sent_week != week_key:
                text, path = generate_weekly_report_and_excel()
                bot.send_message(SUPER_ADMIN_ID, text, parse_mode="HTML")
                with open(path, "rb") as f:
                    bot.send_document(SUPER_ADMIN_ID, f)
                if os.path.exists(path):
                    os.remove(path)
                last_sent_week = week_key
        except Exception as e:
            print("Monitor xato:", e)
        time.sleep(60)


threading.Thread(target=background_monitor_loop, daemon=True).start()


# ================= START, TIL TANLASH VA KONTAKT =================
def ask_language(chat_id):
    ikb = types.InlineKeyboardMarkup()
    ikb.row(
        types.InlineKeyboardButton("🇺🇿 Ўзбекча (Кирилл)", callback_data="setlang:cyr"),
        types.InlineKeyboardButton("🇺🇿 O'zbekcha (Lotin)", callback_data="setlang:lat")
    )
    ikb.add(types.InlineKeyboardButton("🇷🇺 Русский язык", callback_data="setlang:ru"))
    bot.send_message(chat_id, "🌐 Тилни танланг / Tilni tanlang / Выберите язык:", reply_markup=ikb)


@bot.message_handler(commands=["start"])
def cmd_start(message):
    uid = message.from_user.id
    waiting_support.discard(uid)
    user_states.pop(uid, None)
    ask_language(message.chat.id)


@bot.message_handler(func=lambda m: m.text in ("🌐 Тилни ўзгартириш", "🌐 Tilni o'zgartirish", "🌐 Сменить язык"))
def btn_change_lang(message):
    ask_language(message.chat.id)


@bot.callback_query_handler(func=lambda c: c.data.startswith("setlang:"))
def cb_set_lang(call):
    uid = call.from_user.id
    lang = call.data.split(":")[1]
    conn = get_db()
    row = conn.execute("SELECT phone FROM users WHERE user_id = ?", (uid,)).fetchone()
    if row:
        conn.execute("UPDATE users SET lang = ? WHERE user_id = ?", (lang, uid))
    else:
        conn.execute("INSERT INTO users (user_id, name, username, phone, lang, bonus, total_spent) VALUES (?, ?, ?, '', ?, 2000, 0)",
                     (uid, call.from_user.first_name, call.from_user.username or "", lang))
    conn.commit()
    conn.close()
    bot.answer_callback_query(call.id, "✅")

    if row and row["phone"]:
        greet = {"cyr": "✅ Тил ўзгартирилди!", "lat": "✅ Til o'zgartirildi!", "ru": "✅ Язык изменён!"}[lang]
        bot.send_message(call.message.chat.id, greet, reply_markup=main_menu_keyboard(uid))
    else:
        btn_txt = {"cyr": "📱 Рақамни юбориш", "lat": "📱 Raqamni yuborish", "ru": "📱 Отправить номер"}[lang]
        ask_txt = {
            "cyr": "Давом этиш учун телефон рақамингизни юборинг 👇",
            "lat": "Davom etish uchun telefon raqamingizni yuboring 👇",
            "ru": "Для продолжения отправьте ваш номер телефона 👇"
        }[lang]
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.add(types.KeyboardButton(text=btn_txt, request_contact=True))
        bot.send_message(call.message.chat.id, ask_txt, reply_markup=kb)


@bot.message_handler(content_types=["contact"])
def handle_contact(message):
    if not message.contact:
        return
    phone = message.contact.phone_number
    if not phone.startswith("+"):
        phone = "+" + phone
    uid = message.from_user.id
    lang = get_user_lang(uid)
    card = make_card_id(uid)

    conn = get_db()
    conn.execute("UPDATE users SET phone = ?, name = ?, username = ? WHERE user_id = ?",
                 (phone, message.from_user.first_name, message.from_user.username or "", uid))
    conn.commit()
    conn.close()

    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=260x260&data={card}"
    caption = {
        "cyr": f"✅ Рўйхатдан ўтдингиз!\n💳 Шахсий кодингиз: <b>{card}</b>\nДўконга келганингизда ушбу QR-кодни кўрсатинг!",
        "lat": f"✅ Ro'yxatdan o'tdingiz!\n💳 Shaxsiy kodingiz: <b>{card}</b>\nDo'konga kelganingizda ushbu QR-kodni ko'rsating!",
        "ru": f"✅ Вы зарегистрированы!\n💳 Ваш личный код: <b>{card}</b>\nПокажите этот QR-код в аптеке!"
    }[lang]
    try:
        bot.send_photo(message.chat.id, qr_url, caption=caption, parse_mode="HTML", reply_markup=main_menu_keyboard(uid))
    except Exception:
        bot.send_message(message.chat.id, caption, parse_mode="HTML", reply_markup=main_menu_keyboard(uid))


# ================= QR SKANER VA TOPSHIRISH VA BAHOLASH =================
@bot.message_handler(func=lambda m: m.text == "📷 QR Сканер" and is_staff_any(m.from_user.id))
def btn_qr_scanner(message):
    uid = message.from_user.id
    user_states[uid] = {"mode": "qr_scan"}
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton("❌ Бекор қилиш"))
    bot.send_message(
        message.chat.id,
        "📷 <b>QR-КОД СКАНЕРИ</b>\n\n"
        "Мижоз телефонидаги <b>QR-кодни расмга олиб</b> шу ерга ташланг (ёки <code>VTR-...</code> кодини ёзинг):",
        parse_mode="HTML",
        reply_markup=kb
    )


def decode_qr_from_bytes(img_bytes):
    nparr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return None
    detector = cv2.QRCodeDetector()
    data, _, _ = detector.detectAndDecode(img)
    return data.strip() if data else None


def show_client_orders_by_code(chat_id, staff_uid, code_raw):
    code = code_raw.strip().upper()
    conn = get_db()
    orders = conn.execute("SELECT * FROM orders WHERE UPPER(card) = ? ORDER BY id DESC LIMIT 5", (code,)).fetchall()
    conn.close()

    if not orders:
        bot.send_message(chat_id, f"❌ <code>{code}</code> коди бўйича буюртма топилмади.", parse_mode="HTML", reply_markup=main_menu_keyboard(staff_uid))
        return

    for o in orders:
        txt = (
            f"🧾 <b>БУЮРТМА #{o['id']}</b>\n"
            f"👤 Мижоз: <b>{o['name']}</b> ({o['phone']})\n"
            f"💳 Код: <code>{o['card']}</code>\n"
            f"💰 Тўлов тури: <b>{o['payment_method']}</b>\n"
            f"📌 Тўлов ҳолати: <b>{o['payment_status']}</b>\n"
            f"📦 Буюртма ҳолати: <b>{o['order_status']}</b>\n\n"
            f"🛒 <b>Таркиби:</b>\n{o['items']}\n\n"
            f"💵 <b>ЖАМИ: {o['total']:,} сўм</b>"
        )
        ikb = types.InlineKeyboardMarkup()
        if o["payment_status"] != "Тўланган ✅":
            ikb.add(types.InlineKeyboardButton("💳 Тўловни тасдиқлаш", callback_data=f"pay_ok:{o['id']}"))
        ikb.add(types.InlineKeyboardButton("✅ Товар эгасига берилди", callback_data=f"handover:{o['id']}"))
        bot.send_message(chat_id, txt, parse_mode="HTML", reply_markup=ikb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("pay_ok:"))
def cb_confirm_payment(call):
    staff_uid = call.from_user.id
    if not is_staff_any(staff_uid):
        return
    oid = int(call.data.split(":")[1])
    conn = get_db()
    order = conn.execute("SELECT * FROM orders WHERE id = ?", (oid,)).fetchone()
    if not order:
        conn.close()
        return
    conn.execute("UPDATE orders SET payment_status = 'Тўланган ✅' WHERE id = ?", (oid,))
    conn.commit()
    conn.close()

    bot.answer_callback_query(call.id, "Тўлов тасдиқланди!")
    bot.send_message(call.message.chat.id, f"✅ Буюртма #{oid} тўлови тасдиқланди!")
    if order["user_id"]:
        try:
            bot.send_message(order["user_id"], f"✅ <b>Буюртмангиз #{oid} учун тўлов тасдиқланди!</b> Раҳмат!", parse_mode="HTML")
        except Exception:
            pass


@bot.callback_query_handler(func=lambda c: c.data.startswith("handover:"))
def cb_handover(call):
    staff_uid = call.from_user.id
    if not is_staff_any(staff_uid):
        return
    oid = int(call.data.split(":")[1])
    conn = get_db()
    order = conn.execute("SELECT * FROM orders WHERE id = ?", (oid,)).fetchone()
    if not order:
        conn.close()
        return
    if order["order_status"] == "Топширилган ✅":
        conn.close()
        bot.answer_callback_query(call.id, "Аллақачон топширилган")
        return

    conn.execute("UPDATE orders SET order_status = 'Топширилган ✅', served_by = ? WHERE id = ?", (staff_uid, oid))
    conn.execute("UPDATE staff SET served_count = served_count + 1 WHERE user_id = ?", (staff_uid,))
    conn.commit()
    conn.close()

    bot.answer_callback_query(call.id, "Топширилди!")
    bot.send_message(call.message.chat.id, f"✅ Буюртма #{oid} эгасига берилди деб белгиланди! Профилингизга +1 хизмат қўшилди.")

    # Mijozga 7 ta skill bo'yicha baholash yuborish
    if order["user_id"]:
        skills = ["Муомала маданияти", "Тезкорлик", "Аниқлик", "Дорини тушунтириш", "Дорихона тозалиги", "Ишончлилик", "Умумий хизмат"]
        user_states[order["user_id"]] = {
            "mode": "rate_staff",
            "oid": oid,
            "staff_id": staff_uid,
            "skills": skills,
            "idx": 0,
            "scores": {}
        }
        ikb = types.InlineKeyboardMarkup()
        ikb.row(*[types.InlineKeyboardButton(f"⭐ {i}", callback_data=f"rscore:{i}") for i in range(1, 6)])
        try:
            bot.send_message(
                order["user_id"],
                f"🙏 <b>Харидингиз учун раҳмат! (Буюртма #{oid})</b>\n\n"
                f"Хизмат сифатини 7 та мезон бўйича баҳоланг (1 дан 5 гача):\n"
                f"1/7. <b>{skills[0]}</b>:",
                parse_mode="HTML",
                reply_markup=ikb
            )
        except Exception:
            pass


@bot.callback_query_handler(func=lambda c: c.data.startswith("rscore:"))
def cb_rate_score(call):
    uid = call.from_user.id
    st = user_states.get(uid)
    if not st or st.get("mode") != "rate_staff":
        bot.answer_callback_query(call.id)
        return
    score = int(call.data.split(":")[1])
    idx = st["idx"]
    skill_name = st["skills"][idx]
    st["scores"][skill_name] = score
    st["idx"] += 1
    bot.answer_callback_query(call.id, f"⭐ {score}")

    if st["idx"] < len(st["skills"]):
        next_skill = st["skills"][st["idx"]]
        ikb = types.InlineKeyboardMarkup()
        ikb.row(*[types.InlineKeyboardButton(f"⭐ {i}", callback_data=f"rscore:{i}") for i in range(1, 6)])
        bot.edit_message_text(
            f"Хизмат сифатини баҳоланг:\n<b>{st['idx']+1}/7. {next_skill}</b>:",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="HTML",
            reply_markup=ikb
        )
    else:
        st["mode"] = "rate_comment"
        bot.edit_message_text(
            "✍️ Барча 7 та мезон баҳоланди! Энди қисқача <b>фикр (коммент)</b> ёзиб юборинг (ёки «-» юборинг):",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="HTML"
        )


# ================= BUYURTMA STATUS TUGMALARI VA MIJOZ BEKOR QILISHI =================
@bot.callback_query_handler(func=lambda c: c.data.startswith("ost:"))
def cb_order_status(call):
    staff_uid = call.from_user.id
    if not is_staff_any(staff_uid):
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
        kb.add(types.KeyboardButton("❌ Бекор қилиш"))
        bot.send_message(call.message.chat.id, f"✍️ Буюртма #{oid} мижозига юбориладиган хабарни ёзинг:", reply_markup=kb)
        bot.answer_callback_query(call.id)
        return

    status_map = {
        "prep": ("⏳ Тайёрланмоқда", f"⏳ <b>Буюртмангиз #{oid} ҳозир тайёрланмоқда!</b>"),
        "ready": ("✅ Тайёр", f"✅ <b>Буюртмангиз #{oid} тайёр!</b> Дорихонадан олиб кетишингиз мумкин."),
        "sent": ("🚚 Юборилди", f"🚚 <b>Буюртмангиз #{oid} курьер орқали йўлга чиқди!</b>"),
        "done": ("📦 Доставка қилинди", f"📦 <b>Буюртмангиз #{oid} етказиб берилди!</b>")
    }
    st_label, client_txt = status_map[code]
    conn.execute("UPDATE orders SET order_status = ? WHERE id = ?", (st_label, oid))
    conn.commit()
    conn.close()

    bot.answer_callback_query(call.id, st_label)
    bot.send_message(call.message.chat.id, f"📌 Буюртма #{oid} ҳолати: <b>{st_label}</b>", parse_mode="HTML")
    if order["user_id"]:
        try:
            bot.send_message(order["user_id"], client_txt, parse_mode="HTML")
        except Exception:
            pass


@bot.callback_query_handler(func=lambda c: c.data.startswith("cancel_ord:"))
def cb_client_cancel_order(call):
    uid = call.from_user.id
    oid = int(call.data.split(":")[1])
    conn = get_db()
    order = conn.execute("SELECT * FROM orders WHERE id = ? AND user_id = ?", (oid, uid)).fetchone()
    if not order:
        conn.close()
        return

    if order["order_status"] in ("Бекор қилинган ❌", "Топширилган ✅"):
        conn.close()
        bot.answer_callback_query(call.id, "Бу буюртмани бекор қилиб бўлмайди.")
        return

    if time.time() - float(order["created_ts"] or 0) > 900:
        conn.close()
        bot.answer_callback_query(call.id, "⏰ Бекор қилиш вақти (15 дақиқа) тугаган!", show_alert=True)
        return

    # Tovar sonini va bonusni qaytarish
    import json
    items = json.loads(order["cart_json"] or "[]")
    for it in items:
        conn.execute("UPDATE products SET stock = stock + ? WHERE id = ?", (int(it.get("qty", 0)), int(it.get("id", 0))))
    conn.execute("UPDATE users SET bonus = MAX(0, bonus - ?), total_spent = MAX(0, total_spent - ?) WHERE user_id = ?",
                 (int(order["cashback_earned"]), int(order["total"]), uid))
    conn.execute("UPDATE orders SET order_status = 'Бекор қилинган ❌' WHERE id = ?", (oid,))
    conn.commit()
    conn.close()

    bot.edit_message_text(f"❌ <b>Буюртмангиз #{oid} бекор қилинди.</b> Товарлар дўконга қайтарилди.", call.message.chat.id, call.message.message_id, parse_mode="HTML")
    for sid in get_all_staff_ids():
        try:
            bot.send_message(sid, f"⚠️ <b>Мижоз буюртма #{oid} ни бекор қилди!</b> Товарлар автоматик омборга қайтарилди.", parse_mode="HTML")
        except Exception:
            pass


# ================= PRIXOD (YANGI / ESKI) VA AVTO-PRIXOD =================
@bot.message_handler(func=lambda m: m.text in ("➕ Приход қилиш", "🤖 Авто-приход (Устама %)") and is_admin_or_super(m.from_user.id))
def btn_prixod_start(message):
    uid = message.from_user.id
    is_auto = "Авто" in message.text
    if is_auto and get_role(uid) != "superadmin":
        return
    user_states[uid] = {"mode": "prixod_type", "is_auto": is_auto}
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(types.KeyboardButton("🆕 Янги дори"), types.KeyboardButton("♻️ Эски (базадаги) дори"))
    kb.row(types.KeyboardButton("❌ Бекор қилиш"))
    bot.send_message(
        message.chat.id,
        f"📥 <b>{'АВТО-ПРИХОД' if is_auto else 'ПРИХОД'} БОШЛАНДИ</b>\n\nБу янги дорими ёки аввал киритилган эски дорими?",
        parse_mode="HTML",
        reply_markup=kb
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("oldp:"))
def cb_pick_old_product(call):
    uid = call.from_user.id
    if not is_admin_or_super(uid):
        return
    pid = int(call.data.split(":")[1])
    conn = get_db()
    prod = conn.execute("SELECT * FROM products WHERE id = ?", (pid,)).fetchone()
    conn.close()
    if not prod:
        return

    prev = user_states.get(uid, {})
    is_auto = prev.get("is_auto", False)
    user_states[uid] = {
        "mode": "prixod",
        "is_old": True,
        "is_auto": is_auto,
        "pid": pid,
        "name": prod["name"],
        "category": prod["category"],
        "price": prod["price"],
        "cost_price": prod["cost_price"],
        "dosage": prod["dosage"],
        "image": prod["image"],
        "step": "qty"
    }
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton("❌ Бекор қилиш"))
    bot.send_message(
        call.message.chat.id,
        f"♻️ Танланди: <b>{prod['name']}</b> (Ҳозирги нархи: {prod['price']:,} сўм)\n\nНеча <b>дона</b> келди? Сонини ёзинг:",
        parse_mode="HTML",
        reply_markup=kb
    )
    bot.answer_callback_query(call.id)


# ================= TOVAR TAHRIRLASH / SKIDKA / YANGILIK / QIDIRUV / XODIMLAR =================
@bot.message_handler(func=lambda m: m.text == "✏️ Товарни таҳрирлаш" and is_admin_or_super(m.from_user.id))
def btn_edit_products(message):
    conn = get_db()
    rows = conn.execute("SELECT id, name, price, stock FROM products ORDER BY id DESC LIMIT 30").fetchall()
    conn.close()
    if not rows:
        bot.send_message(message.chat.id, "📦 Базада товар йўқ.")
        return
    ikb = types.InlineKeyboardMarkup()
    for r in rows:
        ikb.add(types.InlineKeyboardButton(f"#{r['id']} | {r['name'][:25]} ({r['price']:,})", callback_data=f"ed_pick:{r['id']}"))
    bot.send_message(message.chat.id, "✏️ Товарни танланг:", reply_markup=ikb)


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
        bot.edit_message_text(f"💊 <b>{prod['name']}</b> — {prod['price']:,} сўм ({prod['stock']} дона)", call.message.chat.id, call.message.message_id, parse_mode="HTML", reply_markup=ikb)
    elif act == "ed_price":
        user_states[uid] = {"mode": "edit_price", "pid": pid, "pname": prod["name"]}
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add(types.KeyboardButton("❌ Бекор қилиш"))
        bot.send_message(call.message.chat.id, f"💵 <b>{prod['name']}</b> учун янги нархни ёзинг:", parse_mode="HTML", reply_markup=kb)
    elif act == "ed_del":
        conn = get_db()
        conn.execute("DELETE FROM products WHERE id = ?", (pid,))
        conn.commit()
        conn.close()
        bot.edit_message_text(f"🗑 <b>{prod['name']}</b> ўчирилди!", call.message.chat.id, call.message.message_id, parse_mode="HTML")


@bot.message_handler(func=lambda m: m.text == "🏷 Скидка эълон қилиш" and is_admin_or_super(m.from_user.id))
def btn_discount(message):
    conn = get_db()
    rows = conn.execute("SELECT id, name, price, discount_pct FROM products ORDER BY id DESC LIMIT 30").fetchall()
    conn.close()
    if not rows:
        bot.send_message(message.chat.id, "📦 Товар йўқ.")
        return
    ikb = types.InlineKeyboardMarkup()
    for r in rows:
        ikb.add(types.InlineKeyboardButton(f"#{r['id']} | {r['name'][:25]} ({r['price']:,})", callback_data=f"disc_pick:{r['id']}"))
    bot.send_message(message.chat.id, "🏷 Скидка учун товарни танланг:", reply_markup=ikb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("disc_pick:"))
def cb_discount_pick(call):
    uid = call.from_user.id
    if not is_admin_or_super(uid):
        return
    pid = int(call.data.split(":")[1])
    user_states[uid] = {"mode": "discount", "pid": pid}
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(types.KeyboardButton("10"), types.KeyboardButton("15"), types.KeyboardButton("20"), types.KeyboardButton("25"))
    kb.row(types.KeyboardButton("0 (Скидкани бекор қилиш)"), types.KeyboardButton("❌ Бекор қилиш"))
    bot.send_message(call.message.chat.id, "🏷 Чегирма фоизини (%) ёзинг ёки танланг:", reply_markup=kb)
    bot.answer_callback_query(call.id)


@bot.message_handler(func=lambda m: m.text == "📢 Янгилик тарқатиш" and is_admin_or_super(m.from_user.id))
def btn_news(message):
    uid = message.from_user.id
    user_states[uid] = {"mode": "news"}
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton("❌ Бекор қилиш"))
    bot.send_message(message.chat.id, "📢 Мижозларга юбориладиган янгилик матни ёки расмини юборинг:", reply_markup=kb)


@bot.message_handler(func=lambda m: m.text == "🔍 Мижозни қидириш" and is_staff_any(m.from_user.id))
def btn_search_client(message):
    uid = message.from_user.id
    user_states[uid] = {"mode": "search_client"}
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton("❌ Бекор қилиш"))
    bot.send_message(message.chat.id, "🔍 Мижознинг шахсий коди (масалан: <code>VTR-0012ABCD</code>) ёки телефон рақамини ёзинг:", parse_mode="HTML", reply_markup=kb)


@bot.message_handler(func=lambda m: m.text == "👷 Менинг профилим (KPI)" and is_staff_any(m.from_user.id))
def btn_staff_profile(message):
    uid = message.from_user.id
    conn = get_db()
    st = conn.execute("SELECT * FROM staff WHERE user_id = ?", (uid,)).fetchone()
    revs = conn.execute("SELECT avg_score, comment FROM reviews WHERE staff_id = ? ORDER BY id DESC LIMIT 5", (uid,)).fetchall()
    conn.close()

    served = st["served_count"] if st else 0
    avg = round(st["total_stars"] / st["rating_count"], 2) if (st and st["rating_count"] > 0) else 5.0
    level = "🌟 Эксперт Фармацевт" if served >= 50 else ("⭐ Профессионал" if served >= 15 else "🔰 Стажёр / Мутахассис")

    lines = [
        f"👷 <b>ХОДИМ ШАХСИЙ ПРОФИЛИ</b>\n",
        f"🆔 ID: <code>{uid}</code>",
        f"🏅 Даража: <b>{level}</b>",
        f"📦 Топширилган буюртмалар: <b>{served} та</b>",
        f"⭐ Ўртача рейтинг: <b>{avg} / 5.0</b>\n"
    ]
    if revs:
        lines.append("💬 <b>Сўнгги мижоз фикрлари:</b>")
        for r in revs:
            lines.append(f"• ⭐ {r['avg_score']}/5 — <i>{r['comment']}</i>")
    bot.send_message(message.chat.id, "\n".join(lines), parse_mode="HTML", reply_markup=main_menu_keyboard(uid))


# Faqat SuperAdmin (Siz) uchun Xodim va Adminlar boshqaruvi
@bot.message_handler(func=lambda m: m.text == "👥 Ходим ва Админлар" and get_role(m.from_user.id) == "superadmin")
def btn_manage_staff(message):
    conn = get_db()
    rows = conn.execute("SELECT * FROM staff").fetchall()
    conn.close()

    lines = ["👥 <b>ХОДИМЛАР ВА АДМИНЛАР (Фақат сизнинг ваколатингиз)</b>\n"]
    for r in rows:
        avg = round(r["total_stars"] / r["rating_count"], 2) if r["rating_count"] else 0
        r_lbl = "🛡 Админ (чекланган)" if r["role"] == "admin" else "👷 Ишчи"
        lines.append(f"• {r_lbl} | ID: <code>{r['user_id']}</code> | Хизмат: {r['served_count']} та | ⭐ {avg}")

    ikb = types.InlineKeyboardMarkup()
    ikb.row(
        types.InlineKeyboardButton("🛡 Админ қўшиш", callback_data="st_add:admin"),
        types.InlineKeyboardButton("👷 Ишчи қўшиш", callback_data="st_add:worker")
    )
    if rows:
        ikb.add(types.InlineKeyboardButton("🗑 Ходимни чиқариб ташлаш", callback_data="st_del_list"))
    bot.send_message(message.chat.id, "\n".join(lines), parse_mode="HTML", reply_markup=ikb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("st_"))
def cb_staff_manage(call):
    uid = call.from_user.id
    if get_role(uid) != "superadmin":
        return
    if call.data.startswith("st_add:"):
        role = call.data.split(":")[1]
        user_states[uid] = {"mode": "add_staff", "role": role}
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add(types.KeyboardButton("❌ Бекор қилиш"))
        bot.send_message(call.message.chat.id, "🆔 Ходимнинг Telegram ID рақамини юборинг:", reply_markup=kb)
    elif call.data == "st_del_list":
        conn = get_db()
        rows = conn.execute("SELECT user_id, role FROM staff").fetchall()
        conn.close()
        ikb = types.InlineKeyboardMarkup()
        for r in rows:
            ikb.add(types.InlineKeyboardButton(f"❌ Чиқариш: {r['user_id']} ({r['role']})", callback_data=f"st_rm:{r['user_id']}"))
        bot.edit_message_text("Чиқариб ташланадиган ходимни танланг:", call.message.chat.id, call.message.message_id, reply_markup=ikb)
    elif call.data.startswith("st_rm:"):
        rm_id = int(call.data.split(":")[1])
        conn = get_db()
        conn.execute("DELETE FROM staff WHERE user_id = ?", (rm_id,))
        conn.commit()
        conn.close()
        bot.edit_message_text(f"✅ ID <code>{rm_id}</code> жамоадан чиқарилди.", call.message.chat.id, call.message.message_id, parse_mode="HTML")


@bot.message_handler(func=lambda m: m.text == "📊 Ҳафталик отчёт" and get_role(m.from_user.id) == "superadmin")
def btn_otchot(message):
    text, path = generate_weekly_report_and_excel()
    bot.send_message(message.chat.id, text, parse_mode="HTML")
    with open(path, "rb") as f:
        bot.send_document(message.chat.id, f, reply_markup=main_menu_keyboard(message.from_user.id))
    if os.path.exists(path):
        os.remove(path)


# ================= RASM QABUL QILISH (QR SKANER / PRIXOD / CHEK / YANGILIK) =================
@bot.message_handler(content_types=["photo"])
def handle_photo(message):
    uid = message.from_user.id
    st = user_states.get(uid)

    # 1. QR Skaner orqali rasm tahlili
    if is_staff_any(uid) and st and st.get("mode") == "qr_scan":
        file_info = bot.get_file(message.photo[-1].file_id)
        img_bytes = bot.download_file(file_info.file_path)
        decoded = decode_qr_from_bytes(img_bytes)
        user_states.pop(uid, None)
        if not decoded:
            bot.send_message(message.chat.id, "❌ Расмдан QR-код ўқилмади. Яқинроқдан аниқ тушириб қайта юборинг ёки VTR кодини ёзинг.", reply_markup=main_menu_keyboard(uid))
            return
        show_client_orders_by_code(message.chat.id, uid, decoded)
        return

    # 2. Prixod rasmi
    if is_admin_or_super(uid) and st and st.get("mode") == "prixod" and st.get("step") == "photo":
        file_id = message.photo[-1].file_id
        st["image"] = f"{RENDER_URL}/api/tg_photo/{file_id}"
        st["step"] = "name"
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add(types.KeyboardButton("❌ Бекор қилиш"))
        bot.send_message(message.chat.id, "✅ Расм сақланди!\n2️⃣ Товар <b>номини</b> ёзинг:", parse_mode="HTML", reply_markup=kb)
        return

    # 3. Yangilik rasmi
    if is_admin_or_super(uid) and st and st.get("mode") == "news":
        file_id = message.photo[-1].file_id
        caption = (message.caption or "").strip() or "Янгилик!"
        img_url = f"{RENDER_URL}/api/tg_photo/{file_id}"
        conn = get_db()
        conn.execute("INSERT INTO news (title, body, image) VALUES (?, ?, ?)", ("Янгилик", caption, img_url))
        conn.commit()
        conn.close()
        user_states.pop(uid, None)
        cnt = broadcast_to_clients(f"📢 <b>VITORA | ЯНГИЛИК</b>\n\n{caption}", photo_file_id=file_id)
        bot.send_message(message.chat.id, f"✅ Янгилик {cnt} та мижозга юборилди!", reply_markup=main_menu_keyboard(uid))
        return

    # 4. Mijoz to'lov cheki (Barcha xodimlar va adminga tasdiqlash tugmasi bilan boradi)
    if not is_staff_any(uid):
        conn = get_db()
        last_ord = conn.execute("SELECT id, total FROM orders WHERE user_id = ? ORDER BY id DESC LIMIT 1", (uid,)).fetchone()
        conn.close()
        oid = last_ord["id"] if last_ord else 0
        caption = (
            f"🧾 <b>ЯНГИ ТЎЛОВ ЧЕКИ!</b>\n"
            f"👤 Мижоз: {message.from_user.first_name} (<code>{make_card_id(uid)}</code>)\n"
            f"🆔 Буюртма: <b>#{oid}</b>"
        )
        ikb = types.InlineKeyboardMarkup()
        if oid:
            ikb.add(types.InlineKeyboardButton("✅ Тўловни тасдиқлаш", callback_data=f"pay_ok:{oid}"))
        for sid in get_all_staff_ids():
            try:
                bot.send_photo(sid, message.photo[-1].file_id, caption=caption, parse_mode="HTML", reply_markup=ikb)
            except Exception:
                pass
        bot.reply_to(message, "✅ Тўлов чекингиз қабул қилинди! Оператор тасдиқлагач СМС келади.")


# ================= MIJOZ MENYULARI =================
@bot.message_handler(func=lambda m: m.text in ("🎁 Бонусларим", "🎁 Bonuslarim", "🎁 Мои бонусы"))
def menu_bonuses(message):
    uid = message.from_user.id
    lang = get_user_lang(uid)
    card = make_card_id(uid)
    conn = get_db()
    user = conn.execute("SELECT bonus, total_spent FROM users WHERE user_id = ?", (uid,)).fetchone()
    conn.close()
    bonus = user["bonus"] if user else 2000
    spent = user["total_spent"] if user else 0
    tier = get_tier_info(spent)
    tname = tier[f"name_{lang}"]

    bot.send_message(
        message.chat.id,
        f"💳 <b>ID:</b> <code>{card}</code>\n"
        f"🎁 <b>Бонус:</b> <b>{bonus:,} сўм</b>\n"
        f"🏅 <b>Даража:</b> <b>{tname} ({tier['pct']}%)</b>\n"
        f"🛍 <b>Жами харид:</b> {spent:,} сўм",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(uid)
    )


@bot.message_handler(func=lambda m: m.text in ("🧾 Харидларим", "🧾 Xaridlarim", "🧾 Мои покупки"))
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


@bot.message_handler(func=lambda m: m.text in ("📍 Жойлашув", "📍 Joylashuv", "📍 Локация"))
def menu_location(message):
    uid = message.from_user.id
    lang = get_user_lang(uid)
    addr = {"cyr": PHARMACY_ADDRESS_CYR, "lat": PHARMACY_ADDRESS_LAT, "ru": PHARMACY_ADDRESS_RU}[lang]
    bot.send_message(
        message.chat.id,
        f"🏥 <b>Vitora | Smart Pharm</b>\n\n📍 <b>Манзил:</b> {addr}\n🕒 <b>Иш вақти:</b> {WORK_HOURS}",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(uid)
    )


@bot.message_handler(func=lambda m: m.text in ("💬 Мурожаат", "💬 Murojaat", "💬 Обращение"))
def menu_support(message):
    uid = message.from_user.id
    waiting_support.add(uid)
    bot.send_message(message.chat.id, "✍️ Саволингизни ёзинг:", reply_markup=main_menu_keyboard(uid))


# ================= BARCHA MATNLI BOSQICHLAR =================
@bot.message_handler(func=lambda m: True)
def handle_all_text(message):
    uid = message.from_user.id
    txt = (message.text or "").strip()
    st = user_states.get(uid)

    if st:
        if txt == "❌ Бекор қилиш":
            user_states.pop(uid, None)
            bot.send_message(message.chat.id, "❌ Бекор қилинди.", reply_markup=main_menu_keyboard(uid))
            return

        mode = st.get("mode")

        # Mijoz baholash kommenti
        if mode == "rate_comment":
            comment = txt if txt != "-" else "Изоҳ қолдирилмади"
            scores = st["scores"]
            avg = round(sum(scores.values()) / len(scores), 2)
            staff_id = st["staff_id"]
            import json
            conn = get_db()
            conn.execute("INSERT INTO reviews (order_id, user_id, staff_id, scores_json, avg_score, comment) VALUES (?, ?, ?, ?, ?, ?)",
                         (st["oid"], uid, staff_id, json.dumps(scores, ensure_ascii=False), avg, comment))
            conn.execute("UPDATE staff SET total_stars = total_stars + ?, rating_count = rating_count + 1 WHERE user_id = ?", (avg, staff_id))
            conn.commit()
            conn.close()
            user_states.pop(uid, None)
            bot.send_message(message.chat.id, f"🙏 Баҳоингиз учун катта раҳмат! (Ўртача баҳо: ⭐ {avg}/5)", reply_markup=main_menu_keyboard(uid))
            try:
                bot.send_message(staff_id, f"⭐ <b>Янги баҳо!</b> Буюртма #{st['oid']} учун сизга <b>{avg}/5</b> баҳо ва коммент қолдирилди: <i>{comment}</i>", parse_mode="HTML")
            except Exception:
                pass
            return

        # QR kodni qo'lda yozganda
        if mode == "qr_scan":
            user_states.pop(uid, None)
            show_client_orders_by_code(message.chat.id, uid, txt)
            return

        # Mijozni qidirish
        if mode == "search_client":
            q = txt.upper()
            conn = get_db()
            u = conn.execute("SELECT * FROM users WHERE UPPER(phone) LIKE ? OR user_id != 0", (f"%{q}%",)).fetchall()
            found = None
            for row in u:
                if make_card_id(row["user_id"]) == q or (row["phone"] and q in row["phone"]):
                    found = row
                    break
            conn.close()
            if not found:
                bot.send_message(message.chat.id, "❌ Мижоз топилмади.", reply_markup=main_menu_keyboard(uid))
                user_states.pop(uid, None)
                return
            user_states[uid] = {"mode": "custom_order_msg", "target_uid": found["user_id"], "oid": 0}
            bot.send_message(
                message.chat.id,
                f"✅ Топилди: <b>{found['name']}</b> ({found['phone']})\n✍️ Унга юбориладиган хабарни ёзинг:",
                parse_mode="HTML"
            )
            return

        # Mijozga shaxsiy xabar yuborish ("Boshqa" tugmasi orqali)
        if mode == "custom_order_msg":
            target = st["target_uid"]
            oid = st["oid"]
            user_states.pop(uid, None)
            prefix = f"📩 <b>Vitora | Smart Pharm (Буюртма #{oid}):</b>\n\n" if oid else "📩 <b>Vitora | Smart Pharm:</b>\n\n"
            try:
                bot.send_message(target, prefix + txt, parse_mode="HTML")
                bot.send_message(message.chat.id, "✅ Хабарингиз мижозга юборилди!", reply_markup=main_menu_keyboard(uid))
            except Exception:
                bot.send_message(message.chat.id, "❌ Мижозга хабар юбориб бўлмади.", reply_markup=main_menu_keyboard(uid))
            return

        # Prixod yangi yoki eski tanlash
        if mode == "prixod_type":
            is_auto = st.get("is_auto", False)
            if txt == "🆕 Янги дори":
                user_states[uid] = {"mode": "prixod", "is_old": False, "is_auto": is_auto, "step": "photo", "image": ""}
                kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
                kb.row(types.KeyboardButton("⏭ Расмсиз ўтиш"), types.KeyboardButton("❌ Бекор қилиш"))
                bot.send_message(message.chat.id, "1️⃣ Товар <b>расмини</b> юборинг:", parse_mode="HTML", reply_markup=kb)
            elif txt == "♻️ Эски (базадаги) дори":
                conn = get_db()
                prods = conn.execute("SELECT id, name, stock FROM products ORDER BY id DESC LIMIT 40").fetchall()
                conn.close()
                if not prods:
                    bot.send_message(message.chat.id, "Базада ҳозирча эски дори йўқ. «🆕 Янги дори» ни танланг.")
                    return
                ikb = types.InlineKeyboardMarkup()
                for p in prods:
                    ikb.add(types.InlineKeyboardButton(f"{p['name']} (қолдиқ: {p['stock']})", callback_data=f"oldp:{p['id']}"))
                bot.send_message(message.chat.id, "♻️ Базадаги дорини танланг:", reply_markup=ikb)
            return

        # Prixod va Avto-prixod bosqichlari
        if mode == "prixod":
            step = st["step"]
            if step == "photo":
                if txt == "⏭ Расмсиз ўтиш":
                    st["image"] = ""
                    st["step"] = "name"
                    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
                    kb.add(types.KeyboardButton("❌ Бекор қилиш"))
                    bot.send_message(message.chat.id, "2️⃣ Товар <b>номини</b> ёзинг:", parse_mode="HTML", reply_markup=kb)
                return

            if step == "name":
                st["name"] = txt
                st["step"] = "category"
                kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
                kb.row(types.KeyboardButton("Витамины"), types.KeyboardButton("БАДы"))
                kb.row(types.KeyboardButton("Иммунитет"), types.KeyboardButton("❌ Бекор қилиш"))
                bot.send_message(message.chat.id, "3️⃣ Категорияни танланг ёки ёзинг:", reply_markup=kb)
                return

            if step == "category":
                st["category"] = txt
                st["step"] = "qty"
                kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
                kb.add(types.KeyboardButton("❌ Бекор қилиш"))
                bot.send_message(message.chat.id, "4️⃣ Неча <b>дона</b> келди? Сонини ёзинг:", parse_mode="HTML", reply_markup=kb)
                return

            if step == "qty":
                qty = parse_number(txt)
                if qty <= 0:
                    bot.send_message(message.chat.id, "❌ Тўғри сон киритинг:")
                    return
                st["qty"] = qty
                st["step"] = "expiry"
                kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
                kb.row(types.KeyboardButton("⏭ Муддатсиз"), types.KeyboardButton("❌ Бекор қилиш"))
                bot.send_message(message.chat.id, "5️⃣ Яроқлилик муддатини (<b>ЙЙЙЙ-ОО-КК</b>, масалан: <code>2027-03-15</code>) ёзинг:", parse_mode="HTML", reply_markup=kb)
                return

            if step == "expiry":
                st["expiry"] = "" if txt == "⏭ Муддатсиз" else txt
                if st.get("is_old"):
                    st["step"] = "ask_price_change"
                    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
                    kb.row(types.KeyboardButton("✅ Ҳа, нархи ўзгарди"), types.KeyboardButton("❌ Йўқ, ўша нархда"))
                    bot.send_message(message.chat.id, f"6️⃣ Нархи ўзгардими? (Ҳозирги: <b>{st['price']:,} сўм</b>)", parse_mode="HTML", reply_markup=kb)
                else:
                    st["step"] = "price_input"
                    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
                    kb.add(types.KeyboardButton("❌ Бекор қилиш"))
                    prompt = "6️⃣ Келган (тан) нархини ёзинг (сўмда):" if st.get("is_auto") else "6️⃣ Сотув нархини ёзинг (сўмда):"
                    bot.send_message(message.chat.id, prompt, reply_markup=kb)
                return

            if step == "ask_price_change":
                if "Ҳа" in txt:
                    st["step"] = "price_input"
                    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
                    kb.add(types.KeyboardButton("❌ Бекор қилиш"))
                    prompt = "Янги келган (тан) нархини ёзинг:" if st.get("is_auto") else "Янги сотув нархини ёзинг:"
                    bot.send_message(message.chat.id, prompt, reply_markup=kb)
                else:
                    # Eski narxda to'g'ridan-to'g'ri saqlash
                    finalize_prixod(message.chat.id, uid, st)
                return

            if step == "price_input":
                val = parse_number(txt)
                if val <= 0:
                    bot.send_message(message.chat.id, "❌ Тўғри нарх ёзинг:")
                    return
                if st.get("is_auto"):
                    st["cost_price"] = val
                    st["step"] = "auto_pct"
                    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
                    kb.row(types.KeyboardButton("15%"), types.KeyboardButton("16%"), types.KeyboardButton("17%"))
                    kb.row(types.KeyboardButton("18%"), types.KeyboardButton("19%"), types.KeyboardButton("20%"))
                    kb.row(types.KeyboardButton("❌ Бекор қилиш"))
                    bot.send_message(
                        message.chat.id,
                        f"🤖 Келган нарх: <b>{val:,} сўм</b>.\nНеча фоиз устама қўясиз? (15% – 20%):",
                        parse_mode="HTML",
                        reply_markup=kb
                    )
                else:
                    st["price"] = val
                    if st.get("is_old"):
                        finalize_prixod(message.chat.id, uid, st)
                    else:
                        st["step"] = "dosage"
                        ask_dosage_step(message.chat.id)
                return

            if step == "auto_pct":
                pct = parse_number(txt)
                if pct < 1 or pct > 100:
                    bot.send_message(message.chat.id, "❌ 15 дан 20 гача фоиз танланг:")
                    return
                st["price"] = int(round(st["cost_price"] * (100 + pct) / 100.0))
                if st.get("is_old"):
                    finalize_prixod(message.chat.id, uid, st)
                else:
                    st["step"] = "dosage"
                    ask_dosage_step(message.chat.id)
                return

            if step == "dosage":
                st["dosage"] = txt
                finalize_prixod(message.chat.id, uid, st)
                return

        if mode == "edit_price":
            np = parse_number(txt)
            if np > 0:
                conn = get_db()
                conn.execute("UPDATE products SET price = ?, old_price = 0, discount_pct = 0 WHERE id = ?", (np, st["pid"]))
                conn.commit()
                conn.close()
                user_states.pop(uid, None)
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
                bot.send_message(message.chat.id, f"✅ ID <code>{tid}</code> ({role}) қўшилди!", parse_mode="HTML", reply_markup=main_menu_keyboard(uid))
                try:
                    bot.send_message(tid, "🎉 Сиз Vitora | Smart Pharm жамоасига қўшилдингиз! /start ни босинг.")
                except Exception:
                    pass
            return

    if uid in waiting_support:
        waiting_support.discard(uid)
        for sid in get_all_staff_ids():
            try:
                bot.send_message(sid, f"📩 <b>Мурожаат ({make_card_id(uid)}):</b>\n{txt}", parse_mode="HTML")
            except Exception:
                pass
        bot.send_message(message.chat.id, "✅ Мурожаатингиз юборилди!", reply_markup=main_menu_keyboard(uid))
        return

    bot.send_message(message.chat.id, "Пастдаги менюдан фойдаланинг 👇", reply_markup=main_menu_keyboard(uid))


def ask_dosage_step(chat_id):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(types.KeyboardButton("Кунига 1 маҳал эрталаб 1 тадан"))
    kb.row(types.KeyboardButton("Тунда ухлашдан олдин 2 тадан"))
    kb.row(types.KeyboardButton("❌ Бекор қилиш"))
    bot.send_message(chat_id, "7️⃣ <b>Ичиш тартибини</b> ёзинг:", parse_mode="HTML", reply_markup=kb)


def finalize_prixod(chat_id, uid, st):
    conn = get_db()
    cur = conn.cursor()
    if st.get("is_old"):
        pid = st["pid"]
        cur.execute("UPDATE products SET stock = stock + ?, price = ?, cost_price = ?, expiry_date = ?, expiry_alert_sent = 0 WHERE id = ?",
                    (st["qty"], st["price"], st.get("cost_price", 0), st.get("expiry", ""), pid))
    else:
        cur.execute("""
            INSERT INTO products (name, category, price, cost_price, old_price, discount_pct, stock, expiry_date, description, dosage, image)
            VALUES (?, ?, ?, ?, 0, 0, ?, ?, ?, ?, ?)
        """, (st["name"], st["category"], st["price"], st.get("cost_price", 0), st["qty"], st.get("expiry", ""), st["dosage"], st["dosage"], st["image"]))
        pid = cur.lastrowid

    cur.execute("INSERT INTO stock_in (product_id, product_name, category, qty, price) VALUES (?, ?, ?, ?, ?)",
                (pid, st["name"], st["category"], st["qty"], st["price"]))
    conn.commit()
    conn.close()

    user_states.pop(uid, None)
    broadcast_to_clients(f"🆕 <b>ЯНГИ ТОВАР КЕЛДИ!</b>\n💊 <b>{st['name']}</b> — <b>{st['price']:,} сўм</b>")
    bot.send_message(
        chat_id,
        f"✅ <b>ПРИХОД САҚЛАНДИ!</b>\n💊 {st['name']} (+{st['qty']} дона) — <b>{st['price']:,} сўм</b>",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(uid)
    )


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
    return "Vitora Smart Pharm API v5 ishlamoqda!"


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
    rows = conn.execute("SELECT * FROM products WHERE stock > 0 ORDER BY id DESC").fetchall()
    prods = []
    for r in rows:
        d = dict(r)
        d["available_stock"] = get_available_stock(conn, r["id"])
        prods.append(d)
    news_rows = conn.execute("SELECT * FROM news ORDER BY id DESC LIMIT 15").fetchall()
    conn.close()
    return jsonify({"products": prods, "news": [dict(n) for n in news_rows], "card_number": HUMO_CARD})


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
                     (session_id, pid, final_qty, time.time() + 900))  # 15 daqiqa bron
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "allowed_qty": final_qty, "max_stock": max_for_user})


@app.route("/api/user/<int:uid>", methods=["GET"])
def api_user(uid):
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
        "tier": tier[f"name_{lang}"],
        "cashback_pct": tier["pct"]
    })


@app.route("/api/order", methods=["POST"])
def api_order():
    import json
    data = request.json or {}
    user_id = int(data.get("user_id", 0) or 0)
    session_id = str(data.get("session_id", "guest"))
    name = data.get("name", "Mijoz")
    username = data.get("username", "yoq")
    card = data.get("card", "")
    phone = data.get("phone", "")
    delivery_type = data.get("delivery_type", "")
    address = data.get("address", "")
    payment_method = data.get("payment_method", "")
    items_text = data.get("items", "")
    total = int(data.get("total", 0))
    cart_items = data.get("cart", [])

    conn = get_db()
    cur = conn.cursor()

    u_row = cur.execute("SELECT bonus, total_spent, lang FROM users WHERE user_id = ?", (user_id,)).fetchone() if user_id else None
    old_spent = u_row["total_spent"] if u_row else 0
    old_bonus = u_row["bonus"] if u_row else 2000
    lang = u_row["lang"] if u_row else "cyr"
    old_tier = get_tier_info(old_spent)

    cashback_earned = int(round(total * old_tier["rate"]))
    new_spent = old_spent + total
    new_bonus = old_bonus + cashback_earned
    new_tier = get_tier_info(new_spent)

    if user_id:
        if u_row:
            cur.execute("UPDATE users SET bonus = ?, total_spent = ?, phone = ? WHERE user_id = ?", (new_bonus, new_spent, phone, user_id))
        else:
            cur.execute("INSERT INTO users (user_id, name, username, phone, lang, bonus, total_spent) VALUES (?, ?, ?, ?, 'cyr', ?, ?)",
                        (user_id, name, username, phone, new_bonus, new_spent))

    cur.execute("""
        INSERT INTO orders (user_id, name, username, card, phone, delivery_type, address, payment_method, items, cart_json, total, cashback_earned, created_ts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (user_id, name, username, card, phone, delivery_type, address, payment_method, items_text, json.dumps(cart_items, ensure_ascii=False), total, cashback_earned, time.time()))
    order_id = cur.lastrowid

    # Bandni yechish va haqiqiy qoldiqdan ayirish
    cur.execute("DELETE FROM cart_reservations WHERE session_id = ?", (session_id,))

    dosage_lines = []
    sold_out_names = []
    for item in cart_items:
        pid = int(item.get("id", 0))
        pname = str(item.get("name", ""))
        qty = int(item.get("qty", 0))
        price = int(item.get("price", 0))
        if pid and qty > 0:
            cur.execute("UPDATE products SET stock = MAX(0, stock - ?) WHERE id = ?", (qty, pid))
            p_info = cur.execute("SELECT stock, dosage FROM products WHERE id = ?", (pid,)).fetchone()
            if p_info and p_info["stock"] == 0:
                sold_out_names.append(pname)
            d_txt = (p_info["dosage"] if p_info and p_info["dosage"] else "Шифокор тавсиясига кўра.")
            dosage_lines.append(f"💊 <b>{pname}</b> ({qty} дона):\n   └ 📋 <i>{d_txt}</i>")
        if qty > 0:
            cur.execute("INSERT INTO order_items (order_id, product_id, product_name, qty, price, subtotal) VALUES (?, ?, ?, ?, ?, ?)",
                        (order_id, pid, pname, qty, price, qty * price))

    conn.commit()
    conn.close()

    # Tovar tugagani haqida SuperAdminga darhol SMS
    for sname in sold_out_names:
        try:
            bot.send_message(SUPER_ADMIN_ID, f"⚠️ <b>ТОВАР ТУГАДИ (0 ДОНА ҚОЛДИ)!</b>\n\n💊 <b>{sname}</b> дўкондан автоматик олиб ташланди. Янги приход қилинг!", parse_mode="HTML")
        except Exception:
            pass

    # Barcha xodimlar va adminlarga buyurtma + tayyor status tugmalari
    ikb = types.InlineKeyboardMarkup()
    ikb.row(
        types.InlineKeyboardButton("⏳ Тайёрланмоқда", callback_data=f"ost:prep:{order_id}"),
        types.InlineKeyboardButton("✅ Тайёр", callback_data=f"ost:ready:{order_id}")
    )
    ikb.row(
        types.InlineKeyboardButton("🚚 Юборилди", callback_data=f"ost:sent:{order_id}"),
        types.InlineKeyboardButton("📦 Доставка қилинди", callback_data=f"ost:done:{order_id}")
    )
    ikb.row(
        types.InlineKeyboardButton("✍️ Бошқа (Хат ёзиш)", callback_data=f"ost:custom:{order_id}"),
        types.InlineKeyboardButton("🏁 Эгасига берилди", callback_data=f"handover:{order_id}")
    )

    admin_msg = (
        f"🆕 <b>ЯНГИ БУЮРТМА #{order_id}</b>\n\n"
        f"👤 <b>Мижоз:</b> {name} (@{username})\n"
        f"💳 <b>Код:</b> <code>{card}</code>\n"
        f"📞 <b>Телефон:</b> {phone}\n"
        f"🚚 <b>Усул:</b> {delivery_type}\n"
        f"📍 <b>Манзил:</b> {address or PHARMACY_ADDRESS_CYR}\n"
        f"💰 <b>Тўлов:</b> {payment_method}\n\n"
        f"📦 <b>Маҳсулотлар:</b>\n{items_text}\n\n"
        f"💵 <b>ЖАМИ: {total:,} сўм</b>"
    )
    for sid in get_all_staff_ids():
        try:
            bot.send_message(sid, admin_msg, parse_mode="HTML", reply_markup=ikb)
        except Exception:
            pass

    # Mijozga tasdiq + 15 daqiqalik otmen + shaxsiy ichish tartibi
    if user_id:
        cancel_kb = types.InlineKeyboardMarkup()
        cancel_kb.add(types.InlineKeyboardButton("❌ Буюртмани бекор қилиш (15 дақиқа ичида)", callback_data=f"cancel_ord:{order_id}"))
        user_msg = (
            f"✅ <b>Буюртмангиз #{order_id} қабул қилинди!</b>\n\n"
            f"💵 Жами: <b>{total:,} сўм</b>\n"
            f"🎁 Кэшбэк ({old_tier['pct']}%): <b>+{cashback_earned:,} сўм</b>\n"
            f"💰 Баланс: <b>{new_bonus:,} сўм</b> ({new_tier[f'name_{lang}']})\n"
        )
        if payment_method in ("Click", "Payme"):
            user_msg += f"\n💳 Тўлов картаси: <code>{HUMO_CARD}</code>\n📸 Тўлов қилгач, чек расмини шу ботга ташланг!"
        try:
            bot.send_message(user_id, user_msg, parse_mode="HTML", reply_markup=cancel_kb)
            if dosage_lines:
                bot.send_message(user_id, f"📋 <b>ҚАБУЛ ҚИЛИШ ТАРТИБИ (#{order_id}):</b>\n\n" + "\n\n".join(dosage_lines), parse_mode="HTML")
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
