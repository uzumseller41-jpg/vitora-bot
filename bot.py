import os
import re
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
WEBAPP_URL = "https://uzumseller41-jpg.github.io/vitora-shop/?v=4"
DB_FILE = "vitora.db"
HUMO_CARD = "9860 1501 1189 2918"
PHARMACY_ADDRESS = "Самарқанд шаҳар, Қозизода Румий 56 А уй"
WORK_HOURS = "08:00 – 24:00 (ҳар куни)"
UZ_TZ = timezone(timedelta(hours=5))

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
app = Flask(__name__)
CORS(app)

waiting_support = set()
admin_states = {}  # prixod, edit, news, discount, staff bosqichlari


# ================= MA'LUMOTLAR BAZASI =================
def get_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def make_card_id(user_id):
    return "VTR-" + hex(abs(int(user_id or 1)))[2:].upper().zfill(8)[:8]


def get_tier_info(total_spent):
    spent = int(total_spent or 0)
    if spent >= 3000000:
        return {"name": "💎 Бриллиант Содиқ Мижоз", "rate": 0.10, "pct": 10, "next": None}
    elif spent >= 1500000:
        return {"name": "🥇 Олтин", "rate": 0.07, "pct": 7, "next": 3000000}
    elif spent >= 500000:
        return {"name": "🥈 Кумуш", "rate": 0.05, "pct": 5, "next": 1500000}
    else:
        return {"name": "🥉 Бронза", "rate": 0.03, "pct": 3, "next": 500000}


def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            name TEXT,
            username TEXT,
            phone TEXT,
            bonus INTEGER DEFAULT 5000,
            total_spent INTEGER DEFAULT 0
        )
    """)
    for col_sql in [
        "ALTER TABLE users ADD COLUMN total_spent INTEGER DEFAULT 0"
    ]:
        try:
            cur.execute(col_sql)
        except Exception:
            pass

    cur.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT DEFAULT 'БАДы',
            price INTEGER NOT NULL,
            old_price INTEGER DEFAULT 0,
            discount_pct INTEGER DEFAULT 0,
            stock INTEGER DEFAULT 10,
            description TEXT DEFAULT '',
            dosage TEXT DEFAULT '',
            image TEXT DEFAULT ''
        )
    """)
    for col_sql in [
        "ALTER TABLE products ADD COLUMN old_price INTEGER DEFAULT 0",
        "ALTER TABLE products ADD COLUMN discount_pct INTEGER DEFAULT 0",
        "ALTER TABLE products ADD COLUMN dosage TEXT DEFAULT ''"
    ]:
        try:
            cur.execute(col_sql)
        except Exception:
            pass

    cur.execute("""
        CREATE TABLE IF NOT EXISTS staff (
            user_id INTEGER PRIMARY KEY,
            role TEXT NOT NULL,
            label TEXT DEFAULT '',
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
            items TEXT,
            total INTEGER,
            cashback_earned INTEGER DEFAULT 0,
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


init_db()


def is_admin(uid):
    if uid == SUPER_ADMIN_ID:
        return True
    conn = get_db()
    row = conn.execute("SELECT role FROM staff WHERE user_id = ? AND role = 'admin'", (uid,)).fetchone()
    conn.close()
    return bool(row)


def get_all_order_receivers():
    ids = {SUPER_ADMIN_ID}
    conn = get_db()
    rows = conn.execute("SELECT user_id FROM staff").fetchall()
    conn.close()
    for r in rows:
        ids.add(int(r["user_id"]))
    return list(ids)


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


# ================= ASOSIY MENYU KLAVIATURASI =================
def main_menu_keyboard(user_id=0):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(types.KeyboardButton(text="🛍 Буюртма бериш", web_app=types.WebAppInfo(url=WEBAPP_URL)))
    kb.row(
        types.KeyboardButton(text="🎁 Бонусларим"),
        types.KeyboardButton(text="🧾 Харидларим")
    )
    kb.row(
        types.KeyboardButton(text="📍 Филиаллар"),
        types.KeyboardButton(text="💬 Мурожаат")
    )
    kb.row(
        types.KeyboardButton(text="🚀 Кабинетим", web_app=types.WebAppInfo(url=WEBAPP_URL)),
        types.KeyboardButton(text="🌐 Сайт")
    )
    if is_admin(user_id):
        kb.row(
            types.KeyboardButton(text="➕ Приход қилиш"),
            types.KeyboardButton(text="✏️ Товарни таҳрирлаш")
        )
        kb.row(
            types.KeyboardButton(text="🏷 Скидка эълон қилиш"),
            types.KeyboardButton(text="📢 Янгилик тарқатиш")
        )
        kb.row(
            types.KeyboardButton(text="📊 Ҳафталик отчёт"),
            types.KeyboardButton(text="👥 Админ ва Ишчилар")
        )
    return kb


# ================= HAFTALIK EXCEL VA MATNLI OTCHOT =================
def generate_weekly_report_and_excel():
    conn = get_db()
    since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")

    summary = conn.execute(
        "SELECT COUNT(*) as cnt, COALESCE(SUM(total), 0) as rev FROM orders WHERE created_at >= ?",
        (since,)
    ).fetchone()

    top_items = conn.execute("""
        SELECT product_name, SUM(qty) as sold_qty, SUM(subtotal) as sold_sum
        FROM order_items
        WHERE created_at >= ?
        GROUP BY product_name
        ORDER BY sold_qty DESC, sold_sum DESC
    """, (since,)).fetchall()

    slow_items = conn.execute("""
        SELECT id, name, category, price, stock FROM products
        WHERE stock > 0 AND name NOT IN (
            SELECT DISTINCT product_name FROM order_items WHERE created_at >= ?
        )
        ORDER BY stock DESC
    """, (since,)).fetchall()

    low_stock = conn.execute("""
        SELECT id, name, category, price, stock FROM products
        WHERE stock <= 3
        ORDER BY stock ASC
    """).fetchall()

    all_prods = conn.execute("SELECT id, name, category, price, discount_pct, stock FROM products ORDER BY id DESC").fetchall()
    prixod_cnt = conn.execute(
        "SELECT COUNT(*) as cnt, COALESCE(SUM(qty), 0) as total_qty FROM stock_in WHERE created_at >= ?",
        (since,)
    ).fetchone()
    conn.close()

    uz_now = datetime.now(UZ_TZ).strftime("%d.%m.%Y %H:%M")
    lines = [
        f"📊 <b>VITORA | ҲАФТАЛИК САВДО ОТЧЁТИ</b>",
        f"🕒 Сана: <i>{uz_now}</i> (охирги 7 кун)\n",
        f"🛒 <b>Жами буюртмалар:</b> {summary['cnt']} та",
        f"💰 <b>Умумий тушум:</b> {summary['rev']:,} сўм",
        f"📥 <b>Ҳафталик приход:</b> {prixod_cnt['cnt']} та партия ({prixod_cnt['total_qty']} дона)"
    ]

    excel_path = f"Vitora_Otchot_{datetime.now(UZ_TZ).strftime('%Y%m%d_%H%M')}.xlsx"
    with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
        df_sum = pd.DataFrame([{
            "Ҳисобот санаси": uz_now,
            "Жами буюртмалар сони": summary["cnt"],
            "Умумий тушум (сўм)": summary["rev"],
            "Ҳафталик приход партиялар": prixod_cnt["cnt"],
            "Приход қилинган дона": prixod_cnt["total_qty"]
        }])
        df_sum.to_excel(writer, sheet_name="Умумий_натижа", index=False)

        df_top = pd.DataFrame([
            {"Маҳсулот номи": r["product_name"], "Сотилган сони": r["sold_qty"], "Жами сумма (сўм)": r["sold_sum"]}
            for r in top_items
        ]) if top_items else pd.DataFrame(columns=["Маҳсулот номи", "Сотилган сони", "Жами сумма (сўм)"])
        df_top.to_excel(writer, sheet_name="Хит_товарлар", index=False)

        df_slow = pd.DataFrame([
            {"ID": r["id"], "Маҳсулот номи": r["name"], "Категория": r["category"], "Нархи": r["price"], "Қолдиқ": r["stock"]}
            for r in slow_items
        ]) if slow_items else pd.DataFrame(columns=["ID", "Маҳсулот номи", "Категория", "Нархи", "Қолдиқ"])
        df_slow.to_excel(writer, sheet_name="Сотилмаганлар", index=False)

        df_low = pd.DataFrame([
            {"ID": r["id"], "Маҳсулот номи": r["name"], "Категория": r["category"], "Нархи": r["price"], "Қолдиқ": r["stock"]}
            for r in low_stock
        ]) if low_stock else pd.DataFrame(columns=["ID", "Маҳсулот номи", "Категория", "Нархи", "Қолдиқ"])
        df_low.to_excel(writer, sheet_name="Тугаётган_товарлар", index=False)

        df_all = pd.DataFrame([dict(r) for r in all_prods]) if all_prods else pd.DataFrame()
        df_all.to_excel(writer, sheet_name="Омбор_қолдиғи", index=False)

    return "\n".join(lines), excel_path


def weekly_scheduler_loop():
    last_sent_week = None
    while True:
        try:
            now_uz = datetime.now(UZ_TZ)
            week_key = now_uz.strftime("%Y-%W")
            if now_uz.weekday() == 6 and now_uz.hour == 21 and last_sent_week != week_key:
                text, path = generate_weekly_report_and_excel()
                bot.send_message(SUPER_ADMIN_ID, text, parse_mode="HTML")
                with open(path, "rb") as f:
                    bot.send_document(SUPER_ADMIN_ID, f, caption="📊 Ҳафталик Excel отчёт")
                if os.path.exists(path):
                    os.remove(path)
                last_sent_week = week_key
        except Exception as e:
            print("Weekly scheduler xato:", e)
        time.sleep(60)


threading.Thread(target=weekly_scheduler_loop, daemon=True).start()


# ================= START VA KONTAKT =================
@bot.message_handler(commands=["start"])
def cmd_start(message):
    uid = message.from_user.id
    waiting_support.discard(uid)
    admin_states.pop(uid, None)

    conn = get_db()
    user = conn.execute("SELECT phone FROM users WHERE user_id = ?", (uid,)).fetchone()
    conn.close()

    if user and user["phone"]:
        bot.send_message(
            message.chat.id,
            "Нима қиламиз? Пастдаги тугмалардан бирини танланг.",
            reply_markup=main_menu_keyboard(uid)
        )
    else:
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.add(types.KeyboardButton(text="📱 Рақамни юбориш", request_contact=True))
        bot.send_message(
            message.chat.id,
            f"Ассалому алайкум, <b>{message.from_user.first_name}</b>! 👋\n\n"
            "<b>Vitora | Smart Pharm</b> дорихонаси ботига хуш келибсиз.\n"
            "Бошлаш учун пастдаги тугмани босиб телефон рақамингизни юборинг 👇",
            parse_mode="HTML",
            reply_markup=kb
        )


@bot.message_handler(content_types=["contact"])
def handle_contact(message):
    if not message.contact:
        return
    phone = message.contact.phone_number
    if not phone.startswith("+"):
        phone = "+" + phone

    uid = message.from_user.id
    card = make_card_id(uid)

    conn = get_db()
    existing = conn.execute("SELECT bonus, total_spent FROM users WHERE user_id = ?", (uid,)).fetchone()
    bonus = existing["bonus"] if existing else 5000
    spent = existing["total_spent"] if existing else 0
    conn.execute(
        "INSERT OR REPLACE INTO users (user_id, name, username, phone, bonus, total_spent) VALUES (?, ?, ?, ?, ?, ?)",
        (uid, message.from_user.first_name, message.from_user.username or "", phone, bonus, spent)
    )
    conn.commit()
    conn.close()

    bot.send_message(
        message.chat.id,
        f"Раҳмат, <b>{message.from_user.first_name}</b>! ✅\n"
        f"Бонус картангиз: <b>{card}</b>\n"
        f"Бошланғич даража: <b>🥉 Бронза (3% кэшбэк)</b>\n\n"
        "Энди буюртма беришингиз мумкин — пастдаги «Буюртма бериш» тугмасини босинг.",
        parse_mode="HTML"
    )
    bot.send_message(
        message.chat.id,
        "Нима қиламиз? Пастдаги тугмалардан бирини танланг.",
        reply_markup=main_menu_keyboard(uid)
    )


# ================= PRIXOD (KIRIM) =================
@bot.message_handler(func=lambda m: m.text == "➕ Приход қилиш" and is_admin(m.from_user.id))
def btn_prixod(message):
    uid = message.from_user.id
    admin_states[uid] = {"mode": "prixod", "step": "photo", "image": ""}
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(types.KeyboardButton("⏭ Расмсиз ўтиш"), types.KeyboardButton("❌ Бекор қилиш"))
    bot.send_message(
        message.chat.id,
        "📥 <b>ЯНГИ ПРИХОД (КИРИМ) ҚИЛИШ</b>\n\n"
        "1️⃣ Товар <b>расмини</b> юборинг (ёки «⏭ Расмсиз ўтиш» тугмасини босинг):",
        parse_mode="HTML",
        reply_markup=kb
    )


def send_category_step(chat_id):
    conn = get_db()
    rows = conn.execute("SELECT DISTINCT category FROM products WHERE category != '' LIMIT 10").fetchall()
    conn.close()

    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    cats = [r["category"] for r in rows] if rows else ["Витамины", "БАДы", "Иммунитет", "Фиточаи и травы"]
    for i in range(0, len(cats), 2):
        kb.row(*[types.KeyboardButton(c) for c in cats[i:i+2]])
    kb.row(types.KeyboardButton("❌ Бекор қилиш"))

    bot.send_message(
        chat_id,
        "3️⃣ Қайси <b>категорияга</b> киради?\nТугмалардан танланг ёки янги категория номини ёзинг:",
        parse_mode="HTML",
        reply_markup=kb
    )


# ================= TOVARNI TAHRIRLASH / O'CHIRISH =================
@bot.message_handler(func=lambda m: m.text == "✏️ Товарни таҳрирлаш" and is_admin(m.from_user.id))
def btn_edit_products(message):
    conn = get_db()
    rows = conn.execute("SELECT id, name, price, stock FROM products ORDER BY id DESC LIMIT 30").fetchall()
    conn.close()

    if not rows:
        bot.send_message(message.chat.id, "📦 Ҳозирча базада товар йўқ. Аввал «➕ Приход қилиш» орқали товар қўшинг.", reply_markup=main_menu_keyboard(message.from_user.id))
        return

    ikb = types.InlineKeyboardMarkup()
    for r in rows:
        ikb.add(types.InlineKeyboardButton(
            text=f"#{r['id']} | {r['name'][:26]} ({r['price']:,} сўм)",
            callback_data=f"ed_pick:{r['id']}"
        ))
    bot.send_message(
        message.chat.id,
        "✏️ <b>Таҳрирлаш ёки ўчириш учун товарни танланг:</b>",
        parse_mode="HTML",
        reply_markup=ikb
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("ed_"))
def cb_edit_product(call):
    uid = call.from_user.id
    if not is_admin(uid):
        return
    parts = call.data.split(":")
    action = parts[0]
    pid = int(parts[1])

    conn = get_db()
    prod = conn.execute("SELECT * FROM products WHERE id = ?", (pid,)).fetchone()
    conn.close()

    if not prod:
        bot.answer_callback_query(call.id, "Товар топилмади")
        return

    if action == "ed_pick":
        ikb = types.InlineKeyboardMarkup()
        ikb.row(
            types.InlineKeyboardButton("💵 Нархни ўзгартириш", callback_data=f"ed_price:{pid}"),
            types.InlineKeyboardButton("🗑 Ўчириш", callback_data=f"ed_del:{pid}")
        )
        bot.edit_message_text(
            f"💊 <b>{prod['name']}</b>\n"
            f"💵 Ҳозирги нархи: <b>{prod['price']:,} сўм</b>\n"
            f"📦 Қолдиқ: <b>{prod['stock']} дона</b>\n\nНима қилмоқчисиз?",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="HTML",
            reply_markup=ikb
        )
    elif action == "ed_price":
        admin_states[uid] = {"mode": "edit_price", "pid": pid, "pname": prod["name"]}
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add(types.KeyboardButton("❌ Бекор қилиш"))
        bot.send_message(
            call.message.chat.id,
            f"💵 <b>{prod['name']}</b> учун янги нархни (сўмда, фақат рақам) ёзинг:",
            parse_mode="HTML",
            reply_markup=kb
        )
        bot.answer_callback_query(call.id)
    elif action == "ed_del":
        conn = get_db()
        conn.execute("DELETE FROM products WHERE id = ?", (pid,))
        conn.commit()
        conn.close()
        bot.edit_message_text(
            f"🗑 <b>{prod['name']}</b> базадан ва сайтдан ўчирилди!",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="HTML"
        )
        bot.answer_callback_query(call.id, "Ўчирилди!")


# ================= SKIDKA E'LON QILISH =================
@bot.message_handler(func=lambda m: m.text == "🏷 Скидка эълон қилиш" and is_admin(m.from_user.id))
def btn_discount(message):
    conn = get_db()
    rows = conn.execute("SELECT id, name, price, discount_pct FROM products ORDER BY id DESC LIMIT 30").fetchall()
    conn.close()

    if not rows:
        bot.send_message(message.chat.id, "📦 Скидка қўйиш учун аввал товар қўшинг.", reply_markup=main_menu_keyboard(message.from_user.id))
        return

    ikb = types.InlineKeyboardMarkup()
    for r in rows:
        tag = f" (-{r['discount_pct']}%)" if r["discount_pct"] else ""
        ikb.add(types.InlineKeyboardButton(
            text=f"#{r['id']} | {r['name'][:25]} — {r['price']:,}{tag}",
            callback_data=f"disc_pick:{r['id']}"
        ))
    bot.send_message(
        message.chat.id,
        "🏷 <b>Қайси товарга скидка эълон қиламиз?</b>",
        parse_mode="HTML",
        reply_markup=ikb
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("disc_pick:"))
def cb_discount_pick(call):
    uid = call.from_user.id
    if not is_admin(uid):
        return
    pid = int(call.data.split(":")[1])
    admin_states[uid] = {"mode": "discount", "pid": pid}
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(types.KeyboardButton("10"), types.KeyboardButton("15"), types.KeyboardButton("20"), types.KeyboardButton("30"))
    kb.row(types.KeyboardButton("0 (Скидкани олиб ташлаш)"), types.KeyboardButton("❌ Бекор қилиш"))
    bot.send_message(
        call.message.chat.id,
        "🏷 Неча <b>фоиз (%)</b> скидка қўямиз? Рақам ёзинг ёки тугмани босинг (masalan: <code>15</code>):",
        parse_mode="HTML",
        reply_markup=kb
    )
    bot.answer_callback_query(call.id)


# ================= YANGILIK TARQATISH =================
@bot.message_handler(func=lambda m: m.text == "📢 Янгилик тарқатиш" and is_admin(m.from_user.id))
def btn_news(message):
    uid = message.from_user.id
    admin_states[uid] = {"mode": "news"}
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton("❌ Бекор қилиш"))
    bot.send_message(
        message.chat.id,
        "📢 <b>ЯНГИЛИК ТАРҚАТИШ</b>\n\n"
        "Мижозларга юбормоқчи бўлган янгилик <b>матнини</b> ёзинг (ёки расм билан бирга юборинг):",
        parse_mode="HTML",
        reply_markup=kb
    )


# ================= ADMIN VA ISHCHILAR TAYINLASH =================
@bot.message_handler(func=lambda m: m.text == "👥 Админ ва Ишчилар" and is_admin(m.from_user.id))
def btn_staff(message):
    conn = get_db()
    rows = conn.execute("SELECT user_id, role, label FROM staff").fetchall()
    conn.close()

    lines = ["👥 <b>ЖАМОА ВА РУХСАТЛАР</b>\n", f"👑 <b>Бош админ:</b> <code>{SUPER_ADMIN_ID}</code>"]
    for r in rows:
        r_name = "🛡 Админ" if r["role"] == "admin" else "👷 Ишчи (Заказ қабул қилувчи)"
        lines.append(f"• {r_name}: <code>{r['user_id']}</code> ({r['label']})")

    ikb = types.InlineKeyboardMarkup()
    ikb.row(
        types.InlineKeyboardButton("🛡 Админ қўшиш", callback_data="st_add:admin"),
        types.InlineKeyboardButton("👷 Ишчи қўшиш", callback_data="st_add:worker")
    )
    if rows:
        ikb.add(types.InlineKeyboardButton("🗑 Ходимни ўчириш", callback_data="st_del_list"))

    bot.send_message(message.chat.id, "\n".join(lines), parse_mode="HTML", reply_markup=ikb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("st_"))
def cb_staff(call):
    uid = call.from_user.id
    if not is_admin(uid):
        return
    if call.data.startswith("st_add:"):
        role = call.data.split(":")[1]
        admin_states[uid] = {"mode": "add_staff", "role": role}
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add(types.KeyboardButton("❌ Бекор қилиш"))
        title = "Админ" if role == "admin" else "Ишчи"
        bot.send_message(
            call.message.chat.id,
            f"🆔 Тайинланадиган <b>{title}</b> нинг Telegram ID рақамини юборинг (масалан: <code>123456789</code>):\n"
            "<i>(У @userinfobot га кирса ўз ID рақамини кўради)</i>",
            parse_mode="HTML",
            reply_markup=kb
        )
        bot.answer_callback_query(call.id)
    elif call.data == "st_del_list":
        conn = get_db()
        rows = conn.execute("SELECT user_id, role FROM staff").fetchall()
        conn.close()
        ikb = types.InlineKeyboardMarkup()
        for r in rows:
            ikb.add(types.InlineKeyboardButton(f"❌ Ўчириш: {r['user_id']} ({r['role']})", callback_data=f"st_rm:{r['user_id']}"))
        bot.edit_message_text("Ўчириладиган ходимни танланг:", call.message.chat.id, call.message.message_id, reply_markup=ikb)
    elif call.data.startswith("st_rm:"):
        rm_id = int(call.data.split(":")[1])
        conn = get_db()
        conn.execute("DELETE FROM staff WHERE user_id = ?", (rm_id,))
        conn.commit()
        conn.close()
        bot.edit_message_text(f"✅ ID <code>{rm_id}</code> ходимлар рўйхатидан ўчирилди.", call.message.chat.id, call.message.message_id, parse_mode="HTML")


# ================= HAFTALIK OTCHOT TUGMASI =================
@bot.message_handler(func=lambda m: m.text == "📊 Ҳафталик отчёт" and is_admin(m.from_user.id))
def btn_otchot(message):
    text, path = generate_weekly_report_and_excel()
    bot.send_message(message.chat.id, text, parse_mode="HTML")
    with open(path, "rb") as f:
        bot.send_document(message.chat.id, f, caption="📊 Vitora Smart Pharm — Ҳафталик Excel ҳисобот", reply_markup=main_menu_keyboard(message.from_user.id))
    if os.path.exists(path):
        os.remove(path)


# ================= RASM QABUL QILISH =================
@bot.message_handler(content_types=["photo"])
def handle_photo(message):
    uid = message.from_user.id
    if is_admin(uid) and uid in admin_states:
        st = admin_states[uid]
        if st.get("mode") == "prixod" and st.get("step") == "photo":
            file_id = message.photo[-1].file_id
            st["image"] = f"{RENDER_URL}/api/tg_photo/{file_id}"
            st["step"] = "name"
            kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
            kb.add(types.KeyboardButton("❌ Бекор қилиш"))
            bot.send_message(
                message.chat.id,
                "✅ Расм қабул қилинди!\n\n2️⃣ Энди товар <b>номини</b> ёзинг (масалан: <i>Омега-3 1000 мг №60</i>):",
                parse_mode="HTML",
                reply_markup=kb
            )
            return
        elif st.get("mode") == "news":
            file_id = message.photo[-1].file_id
            caption = (message.caption or "").strip() or "Янгилик!"
            img_url = f"{RENDER_URL}/api/tg_photo/{file_id}"
            conn = get_db()
            conn.execute("INSERT INTO news (title, body, image) VALUES (?, ?, ?)", ("Янгилик", caption, img_url))
            conn.commit()
            conn.close()
            admin_states.pop(uid, None)
            cnt = broadcast_to_clients(f"📢 <b>VITORA | ЯНГИЛИК</b>\n\n{caption}", photo_file_id=file_id)
            bot.send_message(message.chat.id, f"✅ Янгилик сақланди ва <b>{cnt} та</b> мижозга юборилди!", parse_mode="HTML", reply_markup=main_menu_keyboard(uid))
            return

    if not is_admin(uid):
        caption = (
            f"🧾 <b>YANGI TO'LOV CHEKI!</b>\n"
            f"👤 Mijoz: {message.from_user.first_name} (@{message.from_user.username or 'yoq'})\n"
            f"🆔 ID: <code>{uid}</code>"
        )
        for rid in get_all_order_receivers():
            try:
                bot.send_photo(rid, message.photo[-1].file_id, caption=caption, parse_mode="HTML")
            except Exception:
                pass
        bot.reply_to(message, "✅ Тўлов чекингиз қабул қилинди! Тез орада тасдиқланади.")


# ================= MIJOZ MENYULARI =================
@bot.message_handler(func=lambda m: m.text == "🎁 Бонусларим")
def menu_bonuses(message):
    uid = message.from_user.id
    card = make_card_id(uid)
    conn = get_db()
    user = conn.execute("SELECT bonus, total_spent FROM users WHERE user_id = ?", (uid,)).fetchone()
    conn.close()
    bonus = user["bonus"] if user else 5000
    spent = user["total_spent"] if user else 0
    tier = get_tier_info(spent)
    next_txt = f"\n📈 Кейинги даражагача: <b>{(tier['next'] - spent):,} сўм</b> харид қолди" if tier["next"] else "\n👑 Сиз энг юқори даражадасиз!"

    bot.send_message(
        message.chat.id,
        f"💳 <b>Бонус картангиз:</b> <code>{card}</code>\n"
        f"🎁 <b>Жорий баланс:</b> <b>{bonus:,} сўм</b>\n"
        f"🏅 <b>Даражангиз:</b> <b>{tier['name']}</b>\n"
        f"💸 <b>Кэшбэк фоизи:</b> <b>{tier['pct']}%</b>\n"
        f"🛍 <b>Жами харидларингиз:</b> {spent:,} сўм"
        f"{next_txt}\n\n"
        "<i>Даражалар: Бронза (3%) → Кумуш (5%) → Олтин (7%) → Бриллиант (10%)</i>",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(uid)
    )


@bot.message_handler(func=lambda m: m.text == "🧾 Харидларим")
def menu_orders(message):
    uid = message.from_user.id
    conn = get_db()
    rows = conn.execute(
        "SELECT id, items, total, payment_method, cashback_earned FROM orders WHERE user_id = ? ORDER BY id DESC LIMIT 10",
        (uid,)
    ).fetchall()
    conn.close()

    if not rows:
        bot.send_message(
            message.chat.id,
            "Ҳали харид қайд этилмаган.\nБуюртма берганингиздан сўнг барча харидларингиз шу ерда кўринади.",
            reply_markup=main_menu_keyboard(uid)
        )
        return

    lines = ["🧾 <b>Сўнгги харидларингиз:</b>\n"]
    for r in rows:
        lines.append(
            f"🔹 <b>Буюртма #{r['id']}</b> — <b>{r['total']:,} сўм</b> ({r['payment_method']})\n"
            f"🎁 Кэшбэк: +{r['cashback_earned']:,} сўм\n{r['items']}\n"
        )
    bot.send_message(message.chat.id, "\n".join(lines), parse_mode="HTML", reply_markup=main_menu_keyboard(uid))


@bot.message_handler(func=lambda m: m.text == "📍 Филиаллар")
def menu_branches(message):
    uid = message.from_user.id
    bot.send_message(
        message.chat.id,
        "🏥 <b>Vitora | Smart Pharm</b>\n\n"
        f"📍 <b>Манзил:</b> {PHARMACY_ADDRESS}\n"
        f"🕒 <b>Иш вақти:</b> {WORK_HOURS}\n"
        "🚚 <b>Етказиб бериш:</b> Самарқанд шаҳри бўйлаб мавжуд.",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(uid)
    )


@bot.message_handler(func=lambda m: m.text == "🌐 Сайт")
def menu_site(message):
    ikb = types.InlineKeyboardMarkup()
    ikb.add(types.InlineKeyboardButton(text="🌐 Каталогни очиш", web_app=types.WebAppInfo(url=WEBAPP_URL)))
    bot.send_message(
        message.chat.id,
        "🌐 <b>Vitora | Smart Pharm</b> онлайн каталогига ўтиш учун пастдаги тугмани босинг 👇",
        parse_mode="HTML",
        reply_markup=ikb
    )


@bot.message_handler(func=lambda m: m.text == "💬 Мурожаат")
def menu_support(message):
    uid = message.from_user.id
    waiting_support.add(uid)
    bot.send_message(
        message.chat.id,
        "✍️ Саволингиз ёки мурожаатингизни ёзиб юборинг — операторларимиз тез орада жавоб беришади:",
        reply_markup=main_menu_keyboard(uid)
    )


# ================= BARCHA MATNLI BOSQICHLAR =================
@bot.message_handler(func=lambda m: True)
def handle_all_text(message):
    uid = message.from_user.id
    txt = (message.text or "").strip()

    if is_admin(uid) and uid in admin_states:
        if txt == "❌ Бекор қилиш":
            admin_states.pop(uid, None)
            bot.send_message(message.chat.id, "❌ Амал бекор қилинди.", reply_markup=main_menu_keyboard(uid))
            return

        st = admin_states[uid]
        mode = st.get("mode")

        # --- 1. PRIXOD ---
        if mode == "prixod":
            step = st["step"]
            if step == "photo":
                if txt == "⏭ Расмсиз ўтиш":
                    st["image"] = ""
                    st["step"] = "name"
                    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
                    kb.add(types.KeyboardButton("❌ Бекор қилиш"))
                    bot.send_message(message.chat.id, "2️⃣ Товар <b>номини</b> ёзинг:", parse_mode="HTML", reply_markup=kb)
                else:
                    bot.send_message(message.chat.id, "Илтимос, расм юборинг ёки «⏭ Расмсиз ўтиш» ни босинг.")
                return

            if step == "name":
                st["name"] = txt
                st["step"] = "category"
                send_category_step(message.chat.id)
                return

            if step == "category":
                st["category"] = txt
                st["step"] = "price"
                kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
                kb.add(types.KeyboardButton("❌ Бекор қилиш"))
                bot.send_message(message.chat.id, "4️⃣ Товарнинг <b>сотув нархини</b> (сўмда, фақат рақам) ёзинг:", parse_mode="HTML", reply_markup=kb)
                return

            if step == "price":
                price = parse_number(txt)
                if price <= 0:
                    bot.send_message(message.chat.id, "❌ Нотўғри нарх. Фақат рақам ёзинг:")
                    return
                st["price"] = price
                st["step"] = "qty"
                kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
                kb.add(types.KeyboardButton("❌ Бекор қилиш"))
                bot.send_message(message.chat.id, "5️⃣ Неча <b>дона</b> келди? Фақат рақам ёзинг:", parse_mode="HTML", reply_markup=kb)
                return

            if step == "qty":
                qty = parse_number(txt)
                if qty <= 0:
                    bot.send_message(message.chat.id, "❌ Сонини тўғри киритинг:")
                    return
                st["qty"] = qty
                st["step"] = "dosage"
                kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
                kb.row(types.KeyboardButton("Кунига 1 маҳал эрталаб 1 тадан"))
                kb.row(types.KeyboardButton("Тунда ухлашдан олдин 2 тадан"))
                kb.row(types.KeyboardButton("Кунига 2 маҳал овқат билан 1 тадан"), types.KeyboardButton("❌ Бекор қилиш"))
                bot.send_message(
                    message.chat.id,
                    "6️⃣ <b>Ичиш тартибини (инструкция)</b> ёзинг:\n"
                    "<i>Мижоз бу дорини сотиб олганида унга шу матн СМС бўлиб боради (масалан: Тунда 2 тадан сув билан ичиш керак)</i>:",
                    parse_mode="HTML",
                    reply_markup=kb
                )
                return

            if step == "dosage":
                dosage = txt
                name = st["name"]
                category = st["category"]
                price = st["price"]
                qty = st["qty"]
                image = st["image"]

                conn = get_db()
                cur = conn.cursor()
                existing = cur.execute("SELECT id, stock, image FROM products WHERE LOWER(name) = LOWER(?)", (name,)).fetchone()
                if existing:
                    pid = existing["id"]
                    new_stock = existing["stock"] + qty
                    final_img = image if image else existing["image"]
                    cur.execute(
                        "UPDATE products SET category = ?, price = ?, stock = ?, dosage = ?, description = ?, image = ? WHERE id = ?",
                        (category, price, new_stock, dosage, dosage, final_img, pid)
                    )
                else:
                    cur.execute(
                        "INSERT INTO products (name, category, price, old_price, discount_pct, stock, description, dosage, image) VALUES (?, ?, ?, 0, 0, ?, ?, ?, ?)",
                        (name, category, price, qty, dosage, dosage, image)
                    )
                    pid = cur.lastrowid

                cur.execute(
                    "INSERT INTO stock_in (product_id, product_name, category, qty, price) VALUES (?, ?, ?, ?, ?)",
                    (pid, name, category, qty, price)
                )
                conn.commit()
                conn.close()

                admin_states.pop(uid, None)
                notify_txt = (
                    f"🆕 <b>ДОРИХОНАГА ЯНГИ ТОВАР КЕЛДИ!</b>\n\n"
                    f"💊 <b>{name}</b>\n"
                    f"📂 Тоифа: {category}\n"
                    f"💵 Нархи: <b>{price:,} сўм</b>\n"
                    f"📋 Қўлланилиши: <i>{dosage}</i>\n\n"
                    f"🛍 Буюртма бериш учун «Буюртма бериш» тугмасини босинг!"
                )
                sent_cnt = broadcast_to_clients(notify_txt)
                bot.send_message(
                    message.chat.id,
                    f"✅ <b>ПРИХОД САҚЛАНДИ!</b>\n\n"
                    f"💊 <b>{name}</b> (+{qty} дона — {price:,} сўм)\n"
                    f"📋 Ичиш тартиби: <i>{dosage}</i>\n"
                    f"📣 <b>{sent_cnt} та</b> мижозга янги товар келгани ҳақида билдиришнома юборилди!",
                    parse_mode="HTML",
                    reply_markup=main_menu_keyboard(uid)
                )
                return

        # --- 2. NARXNI TAHRIRLASH ---
        if mode == "edit_price":
            new_price = parse_number(txt)
            if new_price <= 0:
                bot.send_message(message.chat.id, "❌ Нархни тўғри рақамда киритинг:")
                return
            pid = st["pid"]
            pname = st["pname"]
            conn = get_db()
            conn.execute("UPDATE products SET price = ?, old_price = 0, discount_pct = 0 WHERE id = ?", (new_price, pid))
            conn.commit()
            conn.close()
            admin_states.pop(uid, None)
            bot.send_message(
                message.chat.id,
                f"✅ <b>{pname}</b> нархи <b>{new_price:,} сўм</b> қилиб янгиланди!",
                parse_mode="HTML",
                reply_markup=main_menu_keyboard(uid)
            )
            return

        # --- 3. SKIDKA QO'YISH ---
        if mode == "discount":
            pid = st["pid"]
            conn = get_db()
            prod = conn.execute("SELECT * FROM products WHERE id = ?", (pid,)).fetchone()
            if not prod:
                conn.close()
                admin_states.pop(uid, None)
                return

            if txt.startswith("0"):
                orig = prod["old_price"] if prod["old_price"] > 0 else prod["price"]
                conn.execute("UPDATE products SET price = ?, old_price = 0, discount_pct = 0 WHERE id = ?", (orig, pid))
                conn.commit()
                conn.close()
                admin_states.pop(uid, None)
                bot.send_message(message.chat.id, f"✅ <b>{prod['name']}</b> учун скидка олиб ташланди.", parse_mode="HTML", reply_markup=main_menu_keyboard(uid))
                return

            pct = parse_number(txt)
            if pct <= 0 or pct >= 95:
                conn.close()
                bot.send_message(message.chat.id, "❌ Чегирма фоизини 1 дан 90 гача киритинг:")
                return

            base_price = prod["old_price"] if prod["old_price"] > 0 else prod["price"]
            new_price = int(round(base_price * (100 - pct) / 100.0))
            conn.execute(
                "UPDATE products SET price = ?, old_price = ?, discount_pct = ? WHERE id = ?",
                (new_price, base_price, pct, pid)
            )
            conn.commit()
            conn.close()
            admin_states.pop(uid, None)

            disc_msg = (
                f"🔥 <b>КАТТА СКИДКА ЭЪЛОН ҚИЛИНДИ (-{pct}%)!</b>\n\n"
                f"💊 <b>{prod['name']}</b>\n"
                f"❌ Эски нарх: <s>{base_price:,} сўм</s>\n"
                f"✅ Янги нарх: <b>{new_price:,} сўм</b>\n\n"
                f"⏳ Шотинг, маҳсулот сони чекланган!"
            )
            sent_cnt = broadcast_to_clients(disc_msg)
            bot.send_message(
                message.chat.id,
                f"✅ Скидка ўрнатилди ва <b>{sent_cnt} та</b> мижозга хабар юборилди!",
                parse_mode="HTML",
                reply_markup=main_menu_keyboard(uid)
            )
            return

        # --- 4. YANGILIK TARQATISH ---
        if mode == "news":
            conn = get_db()
            conn.execute("INSERT INTO news (title, body, image) VALUES (?, ?, ?)", ("Янгилик", txt, ""))
            conn.commit()
            conn.close()
            admin_states.pop(uid, None)
            sent_cnt = broadcast_to_clients(f"📢 <b>VITORA | ЯНГИЛИК</b>\n\n{txt}")
            bot.send_message(
                message.chat.id,
                f"✅ Янгилик сақланди ва <b>{sent_cnt} та</b> мижозга юборилди!",
                parse_mode="HTML",
                reply_markup=main_menu_keyboard(uid)
            )
            return

        # --- 5. ADMIN / ISHCHI QO'SHISH ---
        if mode == "add_staff":
            target_id = parse_number(txt)
            if target_id <= 10000:
                bot.send_message(message.chat.id, "❌ Тўғри Telegram ID рақам киритинг (масалан: 123456789):")
                return
            role = st["role"]
            label = "Админ" if role == "admin" else "Ишчи"
            conn = get_db()
            conn.execute("INSERT OR REPLACE INTO staff (user_id, role, label) VALUES (?, ?, ?)", (target_id, role, label))
            conn.commit()
            conn.close()
            admin_states.pop(uid, None)
            bot.send_message(
                message.chat.id,
                f"✅ ID <code>{target_id}</code> муваффақиятли <b>{label}</b> сифатида тайинланди!",
                parse_mode="HTML",
                reply_markup=main_menu_keyboard(uid)
            )
            try:
                bot.send_message(target_id, f"🎉 Сиз <b>Vitora | Smart Pharm</b> тизимида <b>{label}</b> этиб тайинландингиз! /start ни босинг.", parse_mode="HTML")
            except Exception:
                pass
            return

    if uid in waiting_support:
        waiting_support.discard(uid)
        for rid in get_all_order_receivers():
            try:
                bot.send_message(
                    rid,
                    f"📩 <b>ЯНГИ МУРОЖААТ!</b>\n"
                    f"👤 {message.from_user.first_name} (@{message.from_user.username or 'yoq'})\n"
                    f"🆔 <code>{uid}</code>\n\n💬 {txt}",
                    parse_mode="HTML"
                )
            except Exception:
                pass
        bot.send_message(
            message.chat.id,
            "✅ Мурожаатингиз қабул қилинди! Операторларимиз тез орада сиз билан боғланишади.",
            reply_markup=main_menu_keyboard(uid)
        )
        return

    bot.send_message(
        message.chat.id,
        "Нима қиламиз? Пастдаги тугмалардан бирини танланг.",
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
    return jsonify({"webhook_set": ok, "url": f"{RENDER_URL}/webhook"})


@app.route("/")
def home():
    return "Vitora Smart Pharm API ishlamoqda!"


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
    rows = conn.execute("SELECT * FROM products ORDER BY id DESC").fetchall()
    news_rows = conn.execute("SELECT * FROM news ORDER BY id DESC LIMIT 15").fetchall()
    conn.close()
    return jsonify({
        "products": [dict(r) for r in rows],
        "news": [dict(n) for n in news_rows]
    })


@app.route("/api/user/<int:uid>", methods=["GET"])
def api_user(uid):
    conn = get_db()
    u = conn.execute("SELECT bonus, total_spent FROM users WHERE user_id = ?", (uid,)).fetchone()
    conn.close()
    bonus = u["bonus"] if u else 5000
    spent = u["total_spent"] if u else 0
    tier = get_tier_info(spent)
    return jsonify({
        "bonus": bonus,
        "total_spent": spent,
        "tier": tier["name"],
        "cashback_pct": tier["pct"]
    })


@app.route("/api/order", methods=["POST"])
def api_order():
    data = request.json or {}
    user_id = int(data.get("user_id", 0) or 0)
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

    # Cashback va daraja hisoblash
    u_row = cur.execute("SELECT bonus, total_spent FROM users WHERE user_id = ?", (user_id,)).fetchone() if user_id else None
    old_spent = u_row["total_spent"] if u_row else 0
    old_bonus = u_row["bonus"] if u_row else 5000
    old_tier = get_tier_info(old_spent)

    cashback_earned = int(round(total * old_tier["rate"]))
    new_spent = old_spent + total
    new_bonus = old_bonus + cashback_earned
    new_tier = get_tier_info(new_spent)

    if user_id:
        if u_row:
            cur.execute("UPDATE users SET bonus = ?, total_spent = ?, phone = ? WHERE user_id = ?", (new_bonus, new_spent, phone, user_id))
        else:
            cur.execute(
                "INSERT INTO users (user_id, name, username, phone, bonus, total_spent) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, name, username, phone, new_bonus, new_spent)
            )

    cur.execute("""
        INSERT INTO orders (user_id, name, username, card, phone, delivery_type, address, payment_method, items, total, cashback_earned)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (user_id, name, username, card, phone, delivery_type, address, payment_method, items_text, total, cashback_earned))
    order_id = cur.lastrowid

    dosage_lines = []
    for item in cart_items:
        pid = int(item.get("id", 0))
        pname = str(item.get("name", ""))
        qty = int(item.get("qty", 0))
        price = int(item.get("price", 0))
        if pid and qty > 0:
            cur.execute("UPDATE products SET stock = MAX(0, stock - ?) WHERE id = ?", (qty, pid))
            p_info = cur.execute("SELECT dosage FROM products WHERE id = ?", (pid,)).fetchone()
            d_txt = (p_info["dosage"] if p_info and p_info["dosage"] else "Шифокор тавсиясига кўра қабул қилинг.")
            dosage_lines.append(f"💊 <b>{pname}</b> ({qty} дона):\n   └ 📋 <i>{d_txt}</i>")
        if qty > 0:
            cur.execute("""
                INSERT INTO order_items (order_id, product_id, product_name, qty, price, subtotal)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (order_id, pid, pname, qty, price, qty * price))

    conn.commit()
    conn.close()

    # Admin va barcha ishchilarga buyurtma xabari
    admin_msg = (
        f"🆕 <b>ЯНГИ БУЮРТМА #{order_id}</b>\n\n"
        f"👤 <b>Мижоз:</b> {name} (@{username})\n"
        f"🏅 <b>Даражаси:</b> {new_tier['name']}\n"
        f"💳 <b>Bonus ID:</b> {card}\n"
        f"📞 <b>Телефон:</b> {phone}\n"
        f"🚚 <b>Усул:</b> {delivery_type}\n"
        f"📍 <b>Манзил:</b> {address or 'Дорихонадан олиб кетиш'}\n"
        f"💰 <b>Тўлов:</b> {payment_method}\n\n"
        f"📦 <b>Маҳсулотлар:</b>\n{items_text}\n\n"
        f"💵 <b>ЖАМИ: {total:,} сўм</b>"
    )
    for rid in get_all_order_receivers():
        try:
            bot.send_message(rid, admin_msg, parse_mode="HTML")
        except Exception:
            pass

    # Mijozga buyurtma tasdig'i + individual ichish tartibi SMS
    if user_id:
        tier_up_note = ""
        if new_tier["name"] != old_tier["name"]:
            tier_up_note = f"\n🎊 <b>ТАБРИКЛАЙМИЗ!</b> Сизнинг даражангиз <b>{new_tier['name']}</b> ({new_tier['pct']}% кэшбэк) га кўтарилди!\n"

        user_msg = (
            f"✅ <b>Буюртмангиз #{order_id} қабул қилинди!</b>\n\n"
            f"💵 Жами сумма: <b>{total:,} сўм</b>\n"
            f"🎁 Ҳисобланган кэшбэк ({old_tier['pct']}%): <b>+{cashback_earned:,} сўм</b>\n"
            f"💰 Жами бонусингиз: <b>{new_bonus:,} сўм</b> ({new_tier['name']})\n"
            f"{tier_up_note}"
        )
        if payment_method in ("Click", "Payme"):
            user_msg += f"\n💳 Тўлов учун карта: <code>{HUMO_CARD}</code>\n📸 Тўлов қилгач, чек расмини шу ботга юборинг."
        try:
            bot.send_message(user_id, user_msg, parse_mode="HTML", reply_markup=main_menu_keyboard(user_id))
            if dosage_lines:
                indiv_sms = (
                    f"📋 <b>ШАХСИЙ ҚАБУЛ ҚИЛИШ ТАРТИБИ (Буюртма #{order_id}):</b>\n\n"
                    + "\n\n".join(dosage_lines)
                    + "\n\n<i>Соғлиғингиз биз учун муҳим! — Vitora | Smart Pharm</i>"
                )
                bot.send_message(user_id, indiv_sms, parse_mode="HTML")
        except Exception:
            pass

    return jsonify({"ok": True, "order_id": order_id, "cashback": cashback_earned, "tier": new_tier["name"]})


if __name__ == "__main__":
    try:
        bot.remove_webhook()
        time.sleep(0.5)
        bot.set_webhook(url=f"{RENDER_URL}/webhook")
    except Exception as e:
        print("Webhook ulashda xato:", e)
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
