import os
import re
import json
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
WEBAPP_URL = "https://uzumseller41-jpg.github.io/vitora-shop/?v=8"
DB_FILE = "vitora.db"
BACKUP_STATE_FILE = "backup_meta.json"
HUMO_CARD = "9860 1501 1189 2918"
PHARMACY_ADDRESS_CYR = "Самарқанд шаҳар, Қозизода Румий 56 А уй"
PHARMACY_ADDRESS_LAT = "Samarqand shahar, Qozizoda Rumiy 56 A uy"
PHARMACY_ADDRESS_RU = "г. Самарканд, ул. Козизода Румий, дом 56 А"
PHARMACY_ADDRESS_EN = "56 A Qozizoda Rumiy Street, Samarkand"
WORK_HOURS = "08:00 – 24:00"
UZ_TZ = timezone(timedelta(hours=5))

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
app = Flask(__name__)
CORS(app)

waiting_support = set()
user_states = {}
ephemeral_msgs = {}


# ================= MA'LUMOTLAR BAZASI VA DOIMIY SAQLASH =================
def get_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def make_card_id(user_id):
    return "VTR-" + hex(abs(int(user_id or 1)))[2:].upper().zfill(8)[:8]


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
        "ALTER TABLE orders ADD COLUMN notified INTEGER DEFAULT 0"
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


# ================= CHATNI TOZA SAQLASH VA AQLLI PHARM-TAHLIL =================
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


def smart_pharma_analyze(raw_name):
    n = raw_name.strip()
    nl = n.lower()
    qty_match = re.search(r"(№\s*\d+|\d+\s*(капсул|таб|шт|дона|мл|мг))", nl)
    pack_info = qty_match.group(0).upper() if qty_match else "№60 капсула"

    brand = "Vitora"
    for b in ["Solgar", "Now Foods", "Doppelherz", "Evalar", "California Gold", "Nature's Bounty", "Vitrum", "Complivit", "Orthomol", "Bayer"]:
        if b.lower() in nl:
            brand = b
            break

    if "омега" in nl or "omega" in nl:
        return {
            "brand": brand,
            "category": "Омега и Жирные кислоты",
            "dosage": f"Катталарга кунига 1–2 капсуладан овқат вақтида сув билан ({pack_info}). Курс: 1–2 ой.",
            "description": f"{n} ({pack_info}) — юқори тозаланган EPA ва DHA политўйинмаган ёғ кислоталари манбаи.",
            "benefits": "Юрак-қон томир тизимини мустаҳкамлайди, холестеринни меъёрлаштиради, хотира ва кўриш қобилиятини яхшилайди.",
            "warnings": "Балиқ маҳсулотларига аллергия бўлса эҳтиёткорлик билан қабул қилинг. Оч қоринга ичманг.",
            "combine_with": "Витамин D3 2000 МЕ, Коэнзим Q10, Витамин E"
        }
    if "витамин d" in nl or "d3" in nl or "д3" in nl:
        return {
            "brand": brand,
            "category": "Витамины",
            "dosage": f"Кунига 1 тадан эрталаб ёғлироқ нонушта билан ({pack_info}).",
            "description": f"{n} ({pack_info}) — суяк тўқимаси ва иммунитет учун муҳим холекальциферол.",
            "benefits": "Кальций сўрилишини таъминлайди, иммунитетни кўтаради, сурункали чарчоқни камайтиради.",
            "warnings": "Кечқурун ичиш уйқуга таъсир қилиши мумкин — эрталаб ичган маъқул.",
            "combine_with": "Витамин K2 (MK-7), Омега-3, Магний цитрат"
        }
    if "магн" in nl or "magne" in nl:
        return {
            "brand": brand,
            "category": "Минералы",
            "dosage": f"Кечқурун ухлашдан 1 соат олдин 1–2 таблеткадан ({pack_info}).",
            "description": f"{n} ({pack_info}) — асаб тизими ва мушаклар бўшашиши учун минерал комплекс.",
            "benefits": "Стресс ва асабийликни камайтиради, уйқу сифатини яхшилайди, мушак тортишишини олади.",
            "warnings": "Буйрак етишмовчилигида шифокор маслаҳати зарур.",
            "combine_with": "Витамин B6, Витамин D3, Кальций"
        }
    if "коллаген" in nl or "collagen" in nl:
        return {
            "brand": brand,
            "category": "Красота и Здоровье",
            "dosage": f"Эрталаб овқатдан 30 дақиқа олдин 1–2 тадан сув билан ({pack_info}).",
            "description": f"{n} ({pack_info}) — гидролизланган пептид коллаген комплекси.",
            "benefits": "Тери эластиклигини оширади, соч ва тирноқларни мустаҳкамлайди, бўғимлар ҳаракатчанлигини сақлайди.",
            "warnings": "Самараси сезилиши учун камида 6–8 ҳафта узлуксиз қабул қилиш тавсия этилади.",
            "combine_with": "Витамин C, Гиалурон кислота, Биотин"
        }
    if "цинк" in nl or "zinc" in nl or "иммун" in nl:
        return {
            "brand": brand,
            "category": "Иммунитет",
            "dosage": f"Кунига 1 таблеткадан овқатдан кейин ({pack_info}).",
            "description": f"{n} ({pack_info}) — вирусларга қарши ҳимоя ва ҳужайра регенерацияси учун.",
            "benefits": "Шамоллаш даврида тез соғайишга ёрдам беради, тери ва соч саломатлигини қўллаб-қувватлайди.",
            "warnings": "Оч қоринга ичилса кўнгил айниши мумкин — фақат тўқ қоринга ичинг.",
            "combine_with": "Витамин C, Витамин D3, Селен"
        }

    return {
        "brand": brand,
        "category": "БАДы",
        "dosage": f"Катталарга кунига 1–2 маҳал овқат вақтида сув билан ({pack_info}).",
        "description": f"{n} ({pack_info}) — организмнинг умумий тонуси ва саломатлигини қўллаб-қувватловчи комплекс.",
        "benefits": "Моддалар алмашинувини яхшилайди, кун давомида қувват ва иммунитетни қўллаб-қувватлайди.",
        "warnings": "Шахсий таъсирчанлик бўлса қабулни тўхтатинг. Сақлаш ҳарорати +25°C гача.",
        "combine_with": "Мультивитаминлар, Омега-3"
    }


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


def parse_number(val):
    s = str(val).strip().lower().replace(" ", "").replace("\xa0", "").replace(",", ".").replace("сум", "").replace("сўм", "")
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
        return "🧬 Илмий асос: Омега-3 юрак ва мия фаолияти учун 1–3 ойлик курс талаб қилади. 💡 Ғоя: «2 та олсангиз +15% чегирма (Тўлиқ курс)» акциясини эълон қилинг."
    if "витамин" in n or "иммун" in n or "цинк" in n or "d3" in n:
        return "🧬 Илмий асос: Иммунитет ҳужайралари янгиланиши учун 30 кунлик қабул зарур. 💡 Ғоя: «Оилавий иммунитет пакети — 20% чегирма» номи остида тез сотиш мумкин."
    return "🧬 Илмий асос: БАДлар курс шаклида қабул қилинганда юқори самара беради. 💡 Ғоя: 3 ой олдин 15–25% чегирма билан курс харидини рағбатлантиринг."


# ================= ASOSIY MENYU KLAVIATURASI (MIJOZ VA XODIM UCHUN ALOHIDA!) =================
def main_menu_keyboard(user_id=0):
    role = get_role(user_id)
    lang = get_user_lang(user_id)
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)

    # 1. ODDIY MIJOZLAR UCHUN MENYU
    if role == "client":
        url = f"{WEBAPP_URL}&lang={lang}&role=client"
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
        elif lang == "en":
            kb.row(types.KeyboardButton(text="🛍 Order Now", web_app=types.WebAppInfo(url=url)))
            kb.row(types.KeyboardButton(text="🎁 My Bonuses"), types.KeyboardButton(text="🧾 My Orders"))
            kb.row(types.KeyboardButton(text="📍 Location"), types.KeyboardButton(text="💬 Support"))
            kb.row(types.KeyboardButton(text="🌐 Change Language"))
        else:
            kb.row(types.KeyboardButton(text="🛍 Буюртма бериш", web_app=types.WebAppInfo(url=url)))
            kb.row(types.KeyboardButton(text="🎁 Бонусларим"), types.KeyboardButton(text="🧾 Харидларим"))
            kb.row(types.KeyboardButton(text="📍 Жойлашув"), types.KeyboardButton(text="💬 Мурожаат"))
            kb.row(types.KeyboardButton(text="🌐 Тилни ўзгартириш"))
        return kb

    # 2. XODIMLAR, ADMIN VA SUPER ADMIN UCHUN TOZA ISHCHI MENYU (Bonuslarim / Joylashuv / Xaridlarim OLIB TASHLANDI!)
    staff_url = f"{WEBAPP_URL}&lang={lang}&role={role}&staff_id={user_id}"
    kb.row(types.KeyboardButton(text="🏪 Дўкон ва QR Сканер (Камера)", web_app=types.WebAppInfo(url=staff_url)))
    kb.row(
        types.KeyboardButton(text="🔍 Мижозни қидириш"),
        types.KeyboardButton(text="👷 Менинг профилим (KPI)")
    )

    if role in ("superadmin", "admin"):
        kb.row(
            types.KeyboardButton(text="📥 Приход"),
            types.KeyboardButton(text="✏️ Товарни таҳрирлаш")
        )
        kb.row(
            types.KeyboardButton(text="🏷 Скидка эълон қилиш"),
            types.KeyboardButton(text="📢 Янгилик тарқатиш")
        )

    if role == "superadmin":
        kb.row(
            types.KeyboardButton(text="🧾 Чеки ва Савдолар"),
            types.KeyboardButton(text="📊 Ҳафталик отчёт")
        )
        kb.row(
            types.KeyboardButton(text="👥 Ходим ва Админлар"),
            types.KeyboardButton(text="🌐 Тилни ўзгартириш")
        )
    else:
        kb.row(types.KeyboardButton(text="🌐 Тилни ўзгартириш"))

    return kb


# ================= HAFTALIK EXCEL OTCHOT =================
def generate_weekly_report_and_excel():
    conn = get_db()
    since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    summary = conn.execute("SELECT COUNT(*) as cnt, COALESCE(SUM(total), 0) as rev FROM orders WHERE created_at >= ?", (since,)).fetchone()
    top_items = conn.execute("SELECT product_name, SUM(qty) as sold_qty, SUM(subtotal) as sold_sum FROM order_items WHERE created_at >= ? GROUP BY product_name ORDER BY sold_qty DESC", (since,)).fetchall()
    staff_rows = conn.execute("SELECT user_id, role, name, served_count, total_stars, rating_count FROM staff").fetchall()
    all_prods = conn.execute("SELECT id, name, category, cost_price, price, discount_pct, stock, sold_count, expiry_date FROM products ORDER BY id DESC").fetchall()
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


# ================= FON TEKSHIRUVLARI =================
def background_monitor_loop():
    last_sent_week = None
    while True:
        try:
            conn = get_db()
            clean_expired_reservations(conn)
            conn.execute("DELETE FROM receipts WHERE created_ts < ?", (time.time() - (90 * 86400),))

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
    ask_language(message.chat.id)


@bot.message_handler(func=lambda m: m.text in ("🌐 Тилни ўзгартириш", "🌐 Tilni o'zgartirish", "🌐 Сменить язык", "🌐 Change Language"))
def btn_change_lang(message):
    safe_del_msg(message.chat.id, message.message_id)
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
    safe_del_msg(call.message.chat.id, call.message.message_id)

    # Xodimlarga telefon raqam so'rash shart emas, to'g'ridan-to'g'ri ishchi menyu ochiladi!
    if is_staff_any(uid) or (row and row["phone"]):
        greet = {"cyr": "✅ Тил ўзгартирилди!", "lat": "✅ Til o'zgartirildi!", "ru": "✅ Язык изменён!", "en": "✅ Language updated!"}[lang]
        bot.send_message(call.message.chat.id, greet, reply_markup=main_menu_keyboard(uid))
    else:
        btn_txt = {"cyr": "📱 Рақамни юбориш", "lat": "📱 Raqamni yuborish", "ru": "📱 Отправить номер", "en": "📱 Share Phone Number"}[lang]
        ask_txt = {
            "cyr": "Давом этиш учун телефон рақамингизни юборинг 👇",
            "lat": "Davom etish uchun telefon raqamingizni yuboring 👇",
            "ru": "Для продолжения отправьте ваш номер телефона 👇",
            "en": "Please share your phone number to continue 👇"
        }[lang]
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.add(types.KeyboardButton(text=btn_txt, request_contact=True))
        m = bot.send_message(call.message.chat.id, ask_txt, reply_markup=kb)
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
    card = make_card_id(uid)
    clear_ephemeral(message.chat.id)

    conn = get_db()
    conn.execute("UPDATE users SET phone = ?, name = ?, username = ? WHERE user_id = ?",
                 (phone, message.from_user.first_name, message.from_user.username or "", uid))
    conn.commit()
    conn.close()
    threading.Thread(target=backup_db_to_telegram, daemon=True).start()

    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=260x260&data={card}"
    caption = {
        "cyr": f"✅ Рўйхатдан ўтдингиз!\n💳 Шахсий кодингиз: <b>{card}</b>\nДўконга келганингизда ушбу QR-кодни кўрсатинг!",
        "lat": f"✅ Ro'yxatdan o'tdingiz!\n💳 Shaxsiy kodingiz: <b>{card}</b>\nDo'konga kelganingizda ushbu QR-kodni ko'rsating!",
        "ru": f"✅ Вы зарегистрированы!\n💳 Ваш личный код: <b>{card}</b>\nПокажите этот QR-код в аптеке!",
        "en": f"✅ Registration complete!\n💳 Your personal ID: <b>{card}</b>\nShow this QR code when visiting our pharmacy!"
    }[lang]
    try:
        bot.send_photo(message.chat.id, qr_url, caption=caption, parse_mode="HTML", reply_markup=main_menu_keyboard(uid))
    except Exception:
        bot.send_message(message.chat.id, caption, parse_mode="HTML", reply_markup=main_menu_keyboard(uid))


# ================= 1 TA YAGONA "📥 ПРИХОД" VA UZLUKSIZ PARTIYA (BATCH) REJIMI =================
@bot.message_handler(func=lambda m: m.text == "📥 Приход" and is_admin_or_super(m.from_user.id))
def btn_unified_prixod(message):
    uid = message.from_user.id
    safe_del_msg(message.chat.id, message.message_id)
    clear_ephemeral(message.chat.id)

    user_states[uid] = {"mode": "prixod_choose_method", "batch": []}
    ikb = types.InlineKeyboardMarkup()
    ikb.add(types.InlineKeyboardButton("🧠 1. Ақлли Приход (Нархни қўлда қўйиш)", callback_data="px_m:manual"))
    if get_role(uid) == "superadmin":
        ikb.add(types.InlineKeyboardButton("🤖 2. Авто-приход (Келган нарх + % устама)", callback_data="px_m:auto"))
    ikb.add(types.InlineKeyboardButton("♻️ 3. Эски (базадаги) товарни тўлдириш", callback_data="px_m:old"))
    ikb.add(types.InlineKeyboardButton("❌ Ёпиш", callback_data="px_cancel"))

    m = bot.send_message(
        message.chat.id,
        "📥 <b>ПРИХОД БЎЛИМИ</b>\n\n"
        "Қайси усулда товар киритасиз?\n"
        "<i>(Бир нечта товарни кетма-кет киритишингиз мумкин — охирида «Приходни якунлаш» ни боссангиз мижозларга 1 та умумий хабар боради)</i>:",
        parse_mode="HTML",
        reply_markup=ikb
    )
    track_msg(message.chat.id, m.message_id)


@bot.callback_query_handler(func=lambda c: c.data.startswith("px_"))
def cb_prixod_controls(call):
    uid = call.from_user.id
    if not is_admin_or_super(uid):
        return
    st = user_states.get(uid) or {"batch": []}
    batch = st.get("batch", [])
    action = call.data

    if action == "px_cancel":
        user_states.pop(uid, None)
        clear_ephemeral(call.message.chat.id)
        safe_del_msg(call.message.chat.id, call.message.message_id)
        bot.send_message(call.message.chat.id, "❌ Приход ёпилди.", reply_markup=main_menu_keyboard(uid))
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
        lines.append("\n🛍 Онлайн буюртма бериш учун «Буюртма бериш» тугмасини босинг!")
        cnt = broadcast_to_clients("\n".join(lines))

        threading.Thread(target=backup_db_to_telegram, daemon=True).start()
        bot.send_message(
            call.message.chat.id,
            f"🎉 <b>ПРИХОД ТЎЛИҚ ЯКУНЛАНДИ!</b>\n📦 Жами <b>{len(batch)} та</b> позиция базага сақланди.\n📨 Мижозларга <b>1 та умумий хабар</b> ({cnt} кишига) юборилди!",
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
        kb.row(types.KeyboardButton("⏭ Расмсиз ўтиш"), types.KeyboardButton("✅ Приходни якунлаш"))
        m = bot.send_message(
            call.message.chat.id,
            f"1️⃣ Товар <b>расмини</b> юборинг (тагига номини ҳам ёзсангиз бот ўзи автоматик таҳлил қилади):",
            parse_mode="HTML",
            reply_markup=kb
        )
        track_msg(call.message.chat.id, m.message_id)
        return

    if action == "px_back_menu":
        safe_del_msg(call.message.chat.id, call.message.message_id)
        user_states[uid] = {"mode": "prixod_choose_method", "batch": batch}
        ikb = types.InlineKeyboardMarkup()
        ikb.add(types.InlineKeyboardButton("🧠 1. Ақлли Приход (Нархни қўлда қўйиш)", callback_data="px_m:manual"))
        if get_role(uid) == "superadmin":
            ikb.add(types.InlineKeyboardButton("🤖 2. Авто-приход (Келган нарх + % устама)", callback_data="px_m:auto"))
        ikb.add(types.InlineKeyboardButton("♻️ 3. Эски (базадаги) товарни тўлдириш", callback_data="px_m:old"))
        if batch:
            ikb.add(types.InlineKeyboardButton(f"✅ Приходни якунлаш ({len(batch)} та товар)", callback_data="px_finish"))
        else:
            ikb.add(types.InlineKeyboardButton("❌ Ёпиш", callback_data="px_cancel"))
        m = bot.send_message(call.message.chat.id, f"📥 <b>ПРИХОД ОЙНАСИ</b> (Саватда: {len(batch)} та товар)\nКейинги товар учун усулни танланг ёки якунланг:", parse_mode="HTML", reply_markup=ikb)
        track_msg(call.message.chat.id, m.message_id)


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
    kb.add(types.KeyboardButton("✅ Приходни якунлаш"))
    m = bot.send_message(call.message.chat.id, f"♻️ <b>{prod['name']}</b>\nНеча <b>дона</b> келди?", parse_mode="HTML", reply_markup=kb)
    track_msg(call.message.chat.id, m.message_id)
    bot.answer_callback_query(call.id)


# ================= CHEKLAR VA KUNLIK SAVDO ARXIVI =================
@bot.message_handler(func=lambda m: m.text == "🧾 Чеки ва Савдолар" and get_role(m.from_user.id) == "superadmin")
def btn_receipts_days(message):
    safe_del_msg(message.chat.id, message.message_id)
    conn = get_db()
    days = conn.execute("SELECT day_str, COUNT(*) as cnt, COALESCE(SUM(final_paid), 0) as s FROM receipts GROUP BY day_str ORDER BY day_str DESC LIMIT 30").fetchall()
    conn.close()

    if not days:
        m = bot.send_message(message.chat.id, "🧾 Ҳозирча сақланган тўлов чеклари йўқ (чек базада 3 ой сақланади).", reply_markup=main_menu_keyboard(message.from_user.id))
        track_msg(message.chat.id, m.message_id)
        return

    ikb = types.InlineKeyboardMarkup()
    for d in days:
        ikb.add(types.InlineKeyboardButton(
            text=f"📅 {d['day_str']}  |  {d['cnt']} та чек  |  {d['s']:,} сўм",
            callback_data=f"rcp_day:{d['day_str']}"
        ))
    ikb.add(types.InlineKeyboardButton("❌ Ёпиш", callback_data="close_msg"))
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
    ikb.add(types.InlineKeyboardButton("❌ Ёпиш", callback_data="close_msg"))
    bot.edit_message_text("\n".join(lines), call.message.chat.id, call.message.message_id, parse_mode="HTML", reply_markup=ikb)


@bot.callback_query_handler(func=lambda c: c.data == "close_msg")
def cb_close_msg(call):
    safe_del_msg(call.message.chat.id, call.message.message_id)
    bot.answer_callback_query(call.id)


# ================= TOLOV TASDIQLASH VA TOPSHIRISH =================
@bot.callback_query_handler(func=lambda c: c.data.startswith("pay_ok:"))
def cb_confirm_payment(call):
    if not is_staff_any(call.from_user.id):
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
    if not is_staff_any(staff_uid):
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


# ================= BUYURTMA STATUS TUGMALARI =================
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
    conn.execute("UPDATE orders SET order_status = ?, served_by = ? WHERE id = ?", (st_label, staff_uid, oid))
    conn.commit()
    conn.close()
    bot.answer_callback_query(call.id, st_label)
    if code == "done":
        safe_del_msg(call.message.chat.id, call.message.message_id)

    if order["user_id"]:
        try:
            ckb = None
            if code in ("sent", "done"):
                ckb = types.InlineKeyboardMarkup()
                ckb.add(types.InlineKeyboardButton("📦 Қабул қилиб олдим (Сифатни баҳолаш)", callback_data=f"client_recv:{oid}"))
            bot.send_message(order["user_id"], client_txt, parse_mode="HTML", reply_markup=ckb)
        except Exception:
            pass


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
@bot.message_handler(func=lambda m: m.text == "✏️ Товарни таҳрирлаш" and is_admin_or_super(m.from_user.id))
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
    ikb.add(types.InlineKeyboardButton("❌ Ёпиш", callback_data="close_msg"))
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
        bot.edit_message_text(f"💊 <b>{prod['name']}</b> — {prod['price']:,} сўм ({prod['stock']} дона)", call.message.chat.id, call.message.message_id, parse_mode="HTML", reply_markup=ikb)
    elif act == "ed_price":
        safe_del_msg(call.message.chat.id, call.message.message_id)
        user_states[uid] = {"mode": "edit_price", "pid": pid}
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add(types.KeyboardButton("❌ Бекор қилиш"))
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


@bot.message_handler(func=lambda m: m.text == "🏷 Скидка эълон қилиш" and is_admin_or_super(m.from_user.id))
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
    ikb.add(types.InlineKeyboardButton("❌ Ёпиш", callback_data="close_msg"))
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
    kb.row(types.KeyboardButton("0 (Скидкани бекор қилиш)"), types.KeyboardButton("❌ Бекор қилиш"))
    m = bot.send_message(call.message.chat.id, "🏷 Чегирма фоизини (%) ёзинг ёки танланг:", reply_markup=kb)
    track_msg(call.message.chat.id, m.message_id)


@bot.message_handler(func=lambda m: m.text == "📢 Янгилик тарқатиш" and is_admin_or_super(m.from_user.id))
def btn_news(message):
    uid = message.from_user.id
    safe_del_msg(message.chat.id, message.message_id)
    user_states[uid] = {"mode": "news"}
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton("❌ Бекор қилиш"))
    m = bot.send_message(message.chat.id, "📢 Янгилик матни ёки расмини юборинг:", reply_markup=kb)
    track_msg(message.chat.id, m.message_id)


@bot.message_handler(func=lambda m: m.text == "🔍 Мижозни қидириш" and is_staff_any(m.from_user.id))
def btn_search_client(message):
    uid = message.from_user.id
    safe_del_msg(message.chat.id, message.message_id)
    user_states[uid] = {"mode": "search_client"}
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton("❌ Бекор қилиш"))
    m = bot.send_message(message.chat.id, "🔍 Мижознинг <code>VTR-...</code> кодини ёки телефонини ёзинг:", parse_mode="HTML", reply_markup=kb)
    track_msg(message.chat.id, m.message_id)


@bot.message_handler(func=lambda m: m.text == "👷 Менинг профилим (KPI)" and is_staff_any(m.from_user.id))
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
    ikb.add(types.InlineKeyboardButton("❌ Ёпиш", callback_data="close_msg"))
    bot.send_message(message.chat.id, "\n".join(lines), parse_mode="HTML", reply_markup=ikb)


@bot.message_handler(func=lambda m: m.text == "👥 Ходим ва Админлар" and get_role(m.from_user.id) == "superadmin")
def btn_manage_staff(message):
    safe_del_msg(message.chat.id, message.message_id)
    conn = get_db()
    rows = conn.execute("SELECT * FROM staff").fetchall()
    conn.close()
    lines = ["👥 <b>ХОДИМЛАР ВА АДМИНЛАР</b>\n"]
    for r in rows:
        avg = round(r["total_stars"] / r["rating_count"], 2) if r["rating_count"] else 0
        lines.append(f"• {r['role']} | <code>{r['user_id']}</code> | {r['served_count']} та | ⭐ {avg}")
    ikb = types.InlineKeyboardMarkup()
    ikb.row(types.InlineKeyboardButton("🛡 Админ қўшиш", callback_data="st_add:admin"), types.InlineKeyboardButton("👷 Ишчи қўшиш", callback_data="st_add:worker"))
    if rows:
        ikb.add(types.InlineKeyboardButton("🗑 Ходимни чиқариш", callback_data="st_del_list"))
    ikb.add(types.InlineKeyboardButton("❌ Ёпиш", callback_data="close_msg"))
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
        kb.add(types.KeyboardButton("❌ Бекор қилиш"))
        m = bot.send_message(call.message.chat.id, "🆔 Ходимнинг Telegram ID рақамини юборинг:", reply_markup=kb)
        track_msg(call.message.chat.id, m.message_id)
    elif call.data == "st_del_list":
        conn = get_db()
        rows = conn.execute("SELECT user_id, role FROM staff").fetchall()
        conn.close()
        ikb = types.InlineKeyboardMarkup()
        for r in rows:
            ikb.add(types.InlineKeyboardButton(f"❌ Чиқариш: {r['user_id']}", callback_data=f"st_rm:{r['user_id']}"))
        bot.edit_message_text("Танланг:", call.message.chat.id, call.message.message_id, reply_markup=ikb)
    elif call.data.startswith("st_rm:"):
        conn = get_db()
        conn.execute("DELETE FROM staff WHERE user_id = ?", (int(call.data.split(":")[1]),))
        conn.commit()
        conn.close()
        safe_del_msg(call.message.chat.id, call.message.message_id)
        threading.Thread(target=backup_db_to_telegram, daemon=True).start()


@bot.message_handler(func=lambda m: m.text == "📊 Ҳафталик отчёт" and get_role(m.from_user.id) == "superadmin")
def btn_otchot(message):
    safe_del_msg(message.chat.id, message.message_id)
    text, path = generate_weekly_report_and_excel()
    bot.send_message(message.chat.id, text, parse_mode="HTML")
    with open(path, "rb") as f:
        bot.send_document(message.chat.id, f, reply_markup=main_menu_keyboard(message.from_user.id))
    if os.path.exists(path):
        os.remove(path)


# ================= RASM QABUL QILISH =================
@bot.message_handler(content_types=["photo"])
def handle_photo(message):
    uid = message.from_user.id
    st = user_states.get(uid)
    track_msg(message.chat.id, message.message_id)

    if is_admin_or_super(uid) and st and st.get("mode") == "prixod" and st.get("step") == "photo":
        file_id = message.photo[-1].file_id
        st["image"] = f"{RENDER_URL}/api/tg_photo/{file_id}"
        cap = (message.caption or "").strip()
        if cap:
            ai_info = smart_pharma_analyze(cap)
            st.update(ai_info)
            st["name"] = cap
            st["step"] = "qty"
            kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
            kb.add(types.KeyboardButton("✅ Приходни якунлаш"))
            m = bot.send_message(message.chat.id, f"🧠 <b>АҚЛЛИ ТАҲЛИЛ:</b> {cap}\n📋 <i>{ai_info['dosage']}</i>\n\n2️⃣ Неча <b>дона</b> келди?", parse_mode="HTML", reply_markup=kb)
            track_msg(message.chat.id, m.message_id)
        else:
            st["step"] = "name"
            kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
            kb.add(types.KeyboardButton("✅ Приходни якунлаш"))
            m = bot.send_message(message.chat.id, "✅ Расм олинди!\n2️⃣ Товар <b>номини ва сонини</b> ёзинг (масалан: <i>Solgar Omega-3 №50</i>):", parse_mode="HTML", reply_markup=kb)
            track_msg(message.chat.id, m.message_id)
        return

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

    if not is_staff_any(uid):
        conn = get_db()
        last_ord = conn.execute("SELECT id, final_payable, total FROM orders WHERE user_id = ? ORDER BY id DESC LIMIT 1", (uid,)).fetchone()
        conn.close()
        oid = last_ord["id"] if last_ord else 0
        amt = (last_ord["final_payable"] or last_ord["total"]) if last_ord else 0
        ikb = types.InlineKeyboardMarkup()
        if oid:
            ikb.add(types.InlineKeyboardButton("✅ Тўловни тасдиқлаш", callback_data=f"pay_ok:{oid}"))
        for sid in get_all_staff_ids():
            try:
                bot.send_photo(sid, message.photo[-1].file_id, caption=f"🧾 <b>ТЎЛОВ ЧЕКИ</b> | #{oid} | <b>{amt:,} сўм</b>", parse_mode="HTML", reply_markup=ikb)
            except Exception:
                pass
        bot.reply_to(message, "✅ Чек қабул қилинди!")


# ================= MIJOZ MENYULARI =================
@bot.message_handler(func=lambda m: m.text in ("🎁 Бонусларим", "🎁 Bonuslarim", "🎁 Мои бонусы", "🎁 My Bonuses") and get_role(m.from_user.id) == "client")
def menu_bonuses(message):
    uid = message.from_user.id
    lang = get_user_lang(uid)
    conn = get_db()
    user = conn.execute("SELECT bonus, total_spent FROM users WHERE user_id = ?", (uid,)).fetchone()
    conn.close()
    bonus = user["bonus"] if user else 2000
    spent = user["total_spent"] if user else 0
    tier = get_tier_info(spent)
    bot.send_message(message.chat.id, f"💳 <b>ID:</b> <code>{make_card_id(uid)}</code>\n🎁 <b>Бонус:</b> <b>{bonus:,} сўм</b>\n🏅 <b>Даража:</b> <b>{tier[f'name_{lang}']} ({tier['pct']}%)</b>", parse_mode="HTML", reply_markup=main_menu_keyboard(uid))


@bot.message_handler(func=lambda m: m.text in ("🧾 Харидларим", "🧾 Xaridlarim", "🧾 Мои покупки", "🧾 My Orders") and get_role(m.from_user.id) == "client")
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


@bot.message_handler(func=lambda m: m.text in ("📍 Жойлашув", "📍 Joylashuv", "📍 Локация", "📍 Location") and get_role(m.from_user.id) == "client")
def menu_location(message):
    uid = message.from_user.id
    lang = get_user_lang(uid)
    addr = {"cyr": PHARMACY_ADDRESS_CYR, "lat": PHARMACY_ADDRESS_LAT, "ru": PHARMACY_ADDRESS_RU, "en": PHARMACY_ADDRESS_EN}[lang]
    bot.send_message(message.chat.id, f"🏥 <b>Vitora | Smart Pharm</b>\n\n📍 <b>Манзил:</b> {addr}\n🕒 <b>Иш вақти:</b> {WORK_HOURS}", parse_mode="HTML", reply_markup=main_menu_keyboard(uid))


@bot.message_handler(func=lambda m: m.text in ("💬 Мурожаат", "💬 Murojaat", "💬 Обращение", "💬 Support") and get_role(m.from_user.id) == "client")
def menu_support(message):
    waiting_support.add(message.from_user.id)
    bot.send_message(message.chat.id, "✍️ Саволингизни ёзинг:", reply_markup=main_menu_keyboard(message.from_user.id))


# ================= BARCHA MATNLI BOSQICHLAR =================
@bot.message_handler(func=lambda m: True)
def handle_all_text(message):
    uid = message.from_user.id
    txt = (message.text or "").strip()
    st = user_states.get(uid)

    if st:
        track_msg(message.chat.id, message.message_id)

        if txt == "✅ Приходни якунлаш" and is_admin_or_super(uid):
            batch = st.get("batch", [])
            user_states.pop(uid, None)
            clear_ephemeral(message.chat.id)
            if batch:
                lines = ["🆕 <b>ДОРИХОНАМИЗГА ЯНГИ МАҲСУЛОТЛАР КЕЛДИ!</b>\n"]
                for idx, b in enumerate(batch, 1):
                    lines.append(f"{idx}. 💊 <b>{b['name']}</b> — <b>{b['price']:,} сўм</b>")
                lines.append("\n🛍 Онлайн буюртма бериш учун «Буюртма бериш» тугмасини босинг!")
                cnt = broadcast_to_clients("\n".join(lines))
                threading.Thread(target=backup_db_to_telegram, daemon=True).start()
                bot.send_message(message.chat.id, f"🎉 <b>ПРИХОД ЯКУНЛАНДИ!</b>\n📦 {len(batch)} та товар сақланди ва мижозларга <b>1 та умумий хабар</b> ({cnt} кишига) юборилди!", parse_mode="HTML", reply_markup=main_menu_keyboard(uid))
            else:
                bot.send_message(message.chat.id, "✅ Приход ойнаси ёпилди.", reply_markup=main_menu_keyboard(uid))
            return

        if txt == "❌ Бекор қилиш":
            user_states.pop(uid, None)
            clear_ephemeral(message.chat.id)
            bot.send_message(message.chat.id, "❌ Бекор қилинди.", reply_markup=main_menu_keyboard(uid))
            return

        mode = st.get("mode")

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
            conn = get_db()
            u = conn.execute("SELECT * FROM users").fetchall()
            found = next((r for r in u if make_card_id(r["user_id"]) == q or (r["phone"] and q in r["phone"])), None)
            conn.close()
            clear_ephemeral(message.chat.id)
            if not found:
                user_states.pop(uid, None)
                bot.send_message(message.chat.id, "❌ Мижоз топилмади.", reply_markup=main_menu_keyboard(uid))
                return
            user_states[uid] = {"mode": "custom_order_msg", "target_uid": found["user_id"], "oid": 0}
            m = bot.send_message(message.chat.id, f"✅ Топилди: <b>{found['name']}</b>\n✍️ Юбориладиган хабарни ёзинг:", parse_mode="HTML")
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
            if step == "photo" and txt == "⏭ Расмсиз ўтиш":
                st["image"] = ""
                st["step"] = "name"
                kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
                kb.add(types.KeyboardButton("✅ Приходни якунлаш"))
                m = bot.send_message(message.chat.id, "2️⃣ Товар <b>номини ва сонини</b> ёзинг (масалан: <i>Solgar Omega-3 №50</i>):", parse_mode="HTML", reply_markup=kb)
                track_msg(message.chat.id, m.message_id)
                return

            if step == "name":
                ai_info = smart_pharma_analyze(txt)
                st.update(ai_info)
                st["name"] = txt
                st["step"] = "qty"
                kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
                kb.add(types.KeyboardButton("✅ Приходни якунлаш"))
                m = bot.send_message(
                    message.chat.id,
                    f"🧠 <b>Таҳлил:</b> {ai_info['brand']} | {ai_info['category']}\n📋 <i>{ai_info['dosage']}</i>\n\n3️⃣ Неча <b>дона</b> келди?",
                    parse_mode="HTML",
                    reply_markup=kb
                )
                track_msg(message.chat.id, m.message_id)
                return

            if step == "qty":
                qty = parse_number(txt)
                if qty <= 0:
                    return
                st["qty"] = qty
                st["step"] = "expiry"
                kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
                kb.row(types.KeyboardButton("⏭ Муддатсиз"), types.KeyboardButton("✅ Приходни якунлаш"))
                m = bot.send_message(message.chat.id, "4️⃣ Яроқлилик муддатини (<b>ЙЙЙЙ-ОО-КК</b>, масалан: <code>2027-06-01</code>) ёзинг:", parse_mode="HTML", reply_markup=kb)
                track_msg(message.chat.id, m.message_id)
                return

            if step == "expiry":
                st["expiry"] = "" if txt == "⏭ Муддатсиз" else txt
                if st.get("is_old"):
                    st["step"] = "ask_price_change"
                    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
                    kb.row(types.KeyboardButton("✅ Ҳа, нархи ўзгарди"), types.KeyboardButton("❌ Йўқ, ўша нархда"))
                    m = bot.send_message(message.chat.id, f"5️⃣ Нархи ўзгардими? (Ҳозирги: <b>{st['price']:,} сўм</b>)", parse_mode="HTML", reply_markup=kb)
                    track_msg(message.chat.id, m.message_id)
                else:
                    st["step"] = "price_input"
                    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
                    kb.add(types.KeyboardButton("✅ Приходни якунлаш"))
                    prompt = "5️⃣ Келган (тан) нархини ёзинг (сўмда):" if st.get("is_auto") else "5️⃣ Сотув нархини ёзинг (сўмда):"
                    m = bot.send_message(message.chat.id, prompt, reply_markup=kb)
                    track_msg(message.chat.id, m.message_id)
                return

            if step == "ask_price_change":
                if "Ҳа" in txt:
                    st["step"] = "price_input"
                    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
                    kb.add(types.KeyboardButton("✅ Приходни якунлаш"))
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
        for sid in get_all_staff_ids():
            try:
                bot.send_message(sid, f"📩 <b>Мурожаат ({make_card_id(uid)}):</b>\n{txt}", parse_mode="HTML")
            except Exception:
                pass
        bot.send_message(message.chat.id, "✅ Мурожаатингиз юборилди!", reply_markup=main_menu_keyboard(uid))
        return

    bot.send_message(message.chat.id, "Пастдаги менюдан фойдаланинг 👇", reply_markup=main_menu_keyboard(uid))


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
            VALUES (?, ?, ?, ?, ?, 0, 0, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            st["name"], st.get("brand", "Vitora"), st.get("category", "БАДы"), st["price"], st.get("cost_price", 0),
            st["qty"], st.get("expiry", ""), st.get("description", ""), st.get("dosage", ""),
            st.get("benefits", ""), st.get("warnings", ""), st.get("combine_with", ""), st.get("image", "")
        ))
        pid = cur.lastrowid

    cur.execute("INSERT INTO stock_in (product_id, product_name, category, qty, price) VALUES (?, ?, ?, ?, ?)",
                (pid, st["name"], st.get("category", "БАДы"), st["qty"], st["price"]))
    conn.commit()
    conn.close()

    batch = st.get("batch", [])
    batch.append({"name": st["name"], "qty": st["qty"], "price": st["price"]})
    clear_ephemeral(chat_id)

    user_states[uid] = {"mode": "prixod_choose_method", "batch": batch}

    ikb = types.InlineKeyboardMarkup()
    ikb.add(types.InlineKeyboardButton("🧠 + Яна Ақлли Приход (Қўлда нарх)", callback_data="px_m:manual"))
    if get_role(uid) == "superadmin":
        ikb.add(types.InlineKeyboardButton("🤖 + Яна Авто-приход (Устама %)", callback_data="px_m:auto"))
    ikb.add(types.InlineKeyboardButton("♻️ + Эски товарни тўлдириш", callback_data="px_m:old"))
    ikb.add(types.InlineKeyboardButton(f"✅ Приходни якунлаш ({len(batch)} та товар — 1 та СМС)", callback_data="px_finish"))

    summary_lines = "\n".join([f"  {i}. <b>{b['name']}</b> (+{b['qty']} дона) — {b['price']:,} сўм" for i, b in enumerate(batch, 1)])
    m = bot.send_message(
        chat_id,
        f"✅ <b>Базага қўшилди!</b>\n\n"
        f"📋 <b>Жорий приход рўйхати ({len(batch)} та):</b>\n{summary_lines}\n\n"
        f"Яна товар қўшасизми ёки якунлайсизми?",
        parse_mode="HTML",
        reply_markup=ikb
    )
    track_msg(chat_id, m.message_id)


# ================= WEBHOOK VA FLASK API (XODIM QR-SKANER API BILAN) =================
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
    return "Vitora Smart Pharm API v8 ishlamoqda!"


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


# XODIMLAR UCHUN WEBAPP ICHIDAN MIJOZNI QR YOKI VTR KOD ORQALI TEKSHIRISH API
@app.route("/api/staff/scan_lookup", methods=["GET"])
def api_staff_scan_lookup():
    q = (request.args.get("q") or "").strip().upper()
    if not q:
        return jsonify({"ok": False, "error": "Код киритилмади"})

    conn = get_db()
    users = conn.execute("SELECT * FROM users").fetchall()
    client = None
    for u in users:
        cid = make_card_id(u["user_id"])
        if cid == q or (u["phone"] and q in u["phone"].upper()):
            client = dict(u)
            client["card_id"] = cid
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


# XODIMLAR UCHUN WEBAPP ICHIDAN TO'LOVNI TASDIQLASH VA TOPSHIRISH API
@app.route("/api/staff/order_action", methods=["POST"])
def api_staff_order_action():
    data = request.json or {}
    staff_id = int(data.get("staff_id") or SUPER_ADMIN_ID)
    if not is_staff_any(staff_id):
        return jsonify({"ok": False, "error": "Рухсат йўқ"})

    oid = int(data.get("order_id") or 0)
    action = data.get("action")  # 'pay_ok' yoki 'handover'
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
    card = data.get("card", "")
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
            cur.execute("UPDATE users SET bonus = ?, total_spent = ?, phone = ? WHERE user_id = ?", (new_bonus, new_spent, phone, user_id))
        else:
            cur.execute("INSERT INTO users (user_id, name, username, phone, lang, bonus, total_spent) VALUES (?, ?, ?, ?, 'cyr', ?, ?)",
                        (user_id, name, username, phone, new_bonus, new_spent))

    cur.execute("""
        INSERT INTO orders (user_id, name, username, card, phone, delivery_type, address, payment_method, items, cart_json, total, discount_used, final_payable, cashback_earned, notified, created_ts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
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

    conn.commit()
    conn.close()
    threading.Thread(target=backup_db_to_telegram, daemon=True).start()

    for sname in sold_out_names:
        try:
            bot.send_message(SUPER_ADMIN_ID, f"⚠️ <b>ТОВАР ТУГАДИ (0 ДОНА)!</b>\n💊 <b>{sname}</b> дўкондан олинди.", parse_mode="HTML")
        except Exception:
            pass

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
        types.InlineKeyboardButton("✍️ Бошқа", callback_data=f"ost:custom:{order_id}"),
        types.InlineKeyboardButton("🏁 Эгасига берилди", callback_data=f"handover:{order_id}")
    )

    admin_msg = (
        f"🆕 <b>БУЮРТМА #{order_id}</b> | <code>{card}</code>\n"
        f"👤 {name} ({phone}) | {delivery_type}\n"
        f"💰 Тўлов: <b>{payment_method}</b>\n"
        f"📦 {items_text}\n"
        f"💵 <b>Олинади: {final_payable:,} сўм</b>" + (f" (Скидка: -{discount_used:,})" if discount_used else "")
    )
    for sid in set(get_all_staff_ids()):
        try:
            bot.send_message(sid, admin_msg, parse_mode="HTML", reply_markup=ikb)
        except Exception:
            pass

    if user_id:
        cancel_kb = types.InlineKeyboardMarkup()
        cancel_kb.add(types.InlineKeyboardButton("❌ Буюртмани бекор қилиш (15 дақиқа)", callback_data=f"cancel_ord:{order_id}"))
        user_msg = (
            f"✅ <b>Буюртмангиз #{order_id} қабул қилинди!</b>\n"
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
