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
ADMIN_ID = int(os.environ.get("ADMIN_ID", "5055854613"))
RENDER_URL = "https://vitora-bot.onrender.com"
WEBAPP_URL = "https://uzumseller41-jpg.github.io/vitora-shop/?v=3"
EXCEL_FILE = "Vitora_Smart_Pharm_BAD_Tovarlar.xlsx"
DB_FILE = "vitora.db"
HUMO_CARD = "9860 1501 1189 2918"
UZ_TZ = timezone(timedelta(hours=5))

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
app = Flask(__name__)
CORS(app)

waiting_support = set()
prixod_states = {}  # Admin prixod bosqichlari


# ================= MA'LUMOTLAR BAZASI =================
def get_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def make_card_id(user_id):
    return "VTR-" + hex(abs(int(user_id or 1)))[2:].upper().zfill(8)[:8]


def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            name TEXT,
            username TEXT,
            phone TEXT,
            bonus INTEGER DEFAULT 5000
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT DEFAULT 'БАДы',
            price INTEGER NOT NULL,
            stock INTEGER DEFAULT 10,
            description TEXT DEFAULT '',
            image TEXT DEFAULT ''
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


def parse_number(val):
    s = str(val).strip().lower()
    if not s or s == "nan":
        return 0
    s = s.replace(" ", "").replace("\xa0", "").replace(",", ".").replace("сум", "").replace("сўм", "")
    cleaned = re.sub(r"[^\d.]", "", s)
    if not cleaned:
        return 0
    try:
        return int(float(cleaned))
    except Exception:
        return 0


def auto_seed_from_excel(force=False):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM products")
    count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM products WHERE price > 0")
    valid_prices = cur.fetchone()[0]

    if (count == 0 or valid_prices == 0 or force) and os.path.exists(EXCEL_FILE):
        try:
            cur.execute("DELETE FROM products")
            df = pd.read_excel(EXCEL_FILE)
            df.columns = [str(c).strip() for c in df.columns]

            for _, row in df.iterrows():
                vals = [str(v).strip() for v in row.values]
                text_cols = [v for v in vals if v and v.lower() != "nan" and not v.replace(".", "").isdigit()]
                if not text_cols:
                    continue

                name = text_cols[0]
                if "jami" in name.lower() or "итого" in name.lower() or "всего" in name.lower():
                    continue

                category = text_cols[1] if len(text_cols) > 1 else "БАДы"
                desc = " | ".join(text_cols[2:4]) if len(text_cols) > 2 else ""

                price = 0
                for v in reversed(vals):
                    num = parse_number(v)
                    if num >= 500:
                        price = num
                        break

                cur.execute(
                    "INSERT INTO products (name, category, price, stock, description, image) VALUES (?, ?, ?, ?, ?, ?)",
                    (name, category, price, 10, desc, "")
                )
            conn.commit()
        except Exception as e:
            print("Excel yuklashda xatolik:", e)
    conn.close()


init_db()
auto_seed_from_excel()


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
    if user_id == ADMIN_ID:
        kb.row(
            types.KeyboardButton(text="➕ Приход қилиш"),
            types.KeyboardButton(text="📊 Ҳафталик отчёт")
        )
    return kb


# ================= HAFTALIK OTCHOT GENERATORI =================
def build_weekly_report_text():
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
        LIMIT 10
    """, (since,)).fetchall()

    slow_items = conn.execute("""
        SELECT name, stock FROM products
        WHERE stock > 0 AND name NOT IN (
            SELECT DISTINCT product_name FROM order_items WHERE created_at >= ?
        )
        ORDER BY stock DESC
        LIMIT 5
    """, (since,)).fetchall()

    low_stock = conn.execute("""
        SELECT name, stock FROM products
        WHERE stock <= 3
        ORDER BY stock ASC
        LIMIT 7
    """).fetchall()

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
        f"📥 <b>Ҳафталик приход:</b> {prixod_cnt['cnt']} та партия ({prixod_cnt['total_qty']} дона)\n"
    ]

    if top_items:
        lines.append("🔥 <b>ХИТ ТОВАРЛАР (ТОП-10):</b>")
        for idx, it in enumerate(top_items, 1):
            lines.append(f"<b>{idx}.</b> {it['product_name']} — <b>{it['sold_qty']} дона</b> ({it['sold_sum']:,} сўм)")
    else:
        lines.append("🔥 <b>ХИТ ТОВАРЛАР:</b> Охирги 7 кунда ҳали сотув қайд этилмаган.")

    if slow_items:
        lines.append("\n🐢 <b>ҲАФТАДА СОТИЛМАГАН (СЕКИН) ТОВАРЛАР:</b>")
        for it in slow_items:
            lines.append(f"• {it['name']} (қолдиқ: {it['stock']} дона)")

    if low_stock:
        lines.append("\n⚠️ <b>ТУГАЁТГАН ТОВАРЛАР (ЗАКАЗ ҚИЛИШ КЕРАК):</b>")
        for it in low_stock:
            lines.append(f"• {it['name']} — <b>{it['stock']} дона</b> қолди")

    return "\n".join(lines)


def weekly_scheduler_loop():
    last_sent_week = None
    while True:
        try:
            now_uz = datetime.now(UZ_TZ)
            week_key = now_uz.strftime("%Y-%W")
            if now_uz.weekday() == 6 and now_uz.hour == 21 and last_sent_week != week_key:
                report = build_weekly_report_text()
                bot.send_message(ADMIN_ID, report, parse_mode="HTML")
                last_sent_week = week_key
        except Exception as e:
            print("Weekly scheduler xato:", e)
        time.sleep(60)


threading.Thread(target=weekly_scheduler_loop, daemon=True).start()


# ================= TELEGRAM BOT BUYRUQLARI =================
@bot.message_handler(commands=["start"])
def cmd_start(message):
    uid = message.from_user.id
    waiting_support.discard(uid)
    prixod_states.pop(uid, None)

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
    conn.execute(
        "INSERT OR REPLACE INTO users (user_id, name, username, phone, bonus) VALUES (?, ?, ?, ?, 5000)",
        (uid, message.from_user.first_name, message.from_user.username or "", phone)
    )
    conn.commit()
    conn.close()

    bot.send_message(
        message.chat.id,
        f"Раҳмат, <b>{message.from_user.first_name}</b>! ✅\n"
        f"Бонус картангиз: <b>{card}</b>\n\n"
        "Энди буюртма беришингиз мумкин — пастдаги «Буюртма бериш» тугмасини босинг.",
        parse_mode="HTML"
    )
    bot.send_message(
        message.chat.id,
        "Нима қиламиз? Пастдаги тугмалардан бирини танланг.",
        reply_markup=main_menu_keyboard(uid)
    )


# ================= PRIXOD (KIRIM) JARAYONI =================
def start_prixod_flow(chat_id, uid):
    prixod_states[uid] = {"step": "photo", "image": ""}
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(types.KeyboardButton("⏭ Расмсиз ўтиш"), types.KeyboardButton("❌ Бекор қилиш"))
    bot.send_message(
        chat_id,
        "📥 <b>ЯНГИ ПРИХОД (КИРИМ) ҚИЛИШ</b>\n\n"
        "1️⃣ Товар <b>расмини</b> юборинг (ёки «⏭ Расмсиз ўтиш» тугмасини босинг):",
        parse_mode="HTML",
        reply_markup=kb
    )


@bot.message_handler(commands=["prixod"])
def cmd_prixod(message):
    if message.from_user.id != ADMIN_ID:
        return
    start_prixod_flow(message.chat.id, message.from_user.id)


@bot.message_handler(func=lambda m: m.text == "➕ Приход қилиш" and m.from_user.id == ADMIN_ID)
def btn_prixod(message):
    start_prixod_flow(message.chat.id, message.from_user.id)


@bot.message_handler(commands=["otchot"])
def cmd_otchot(message):
    if message.from_user.id != ADMIN_ID:
        return
    bot.send_message(message.chat.id, build_weekly_report_text(), parse_mode="HTML", reply_markup=main_menu_keyboard(ADMIN_ID))


@bot.message_handler(func=lambda m: m.text == "📊 Ҳафталик отчёт" and m.from_user.id == ADMIN_ID)
def btn_otchot(message):
    bot.send_message(message.chat.id, build_weekly_report_text(), parse_mode="HTML", reply_markup=main_menu_keyboard(ADMIN_ID))


def send_category_step(chat_id):
    conn = get_db()
    rows = conn.execute("SELECT DISTINCT category FROM products WHERE category != '' LIMIT 12").fetchall()
    conn.close()

    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    cats = [r["category"] for r in rows] if rows else ["БАДы", "Витамины", "Фиточаи, травы и экстракты"]
    for i in range(0, len(cats), 2):
        kb.row(*[types.KeyboardButton(c) for c in cats[i:i+2]])
    kb.row(types.KeyboardButton("❌ Бекор қилиш"))

    bot.send_message(
        chat_id,
        "3️⃣ Қайси <b>категорияга</b> киради?\nПастдаги тугмалардан танланг ёки янги категория номини ёзинг:",
        parse_mode="HTML",
        reply_markup=kb
    )


@bot.message_handler(content_types=["photo"])
def handle_photo(message):
    uid = message.from_user.id
    if uid == ADMIN_ID and uid in prixod_states and prixod_states[uid]["step"] == "photo":
        file_id = message.photo[-1].file_id
        img_url = f"{RENDER_URL}/api/tg_photo/{file_id}"
        prixod_states[uid]["image"] = img_url
        prixod_states[uid]["step"] = "name"

        kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add(types.KeyboardButton("❌ Бекор қилиш"))
        bot.send_message(
            message.chat.id,
            "✅ Расм қабул қилинди!\n\n2️⃣ Энди товар <b>номини</b> ёзинг (масалан: <i>Омега-3 1000 мг №60</i>):",
            parse_mode="HTML",
            reply_markup=kb
        )
        return

    if uid != ADMIN_ID:
        caption = (
            f"🧾 <b>YANGI TO'LOV CHEKI!</b>\n"
            f"👤 Mijoz: {message.from_user.first_name} (@{message.from_user.username or 'yoq'})\n"
            f"🆔 ID: <code>{uid}</code>"
        )
        bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=caption, parse_mode="HTML")
        bot.reply_to(message, "✅ Тўлов чекингиз админга юборилди! Тез орада тасдиқланади.")


# ================= MIJOZ MENYULARI =================
@bot.message_handler(func=lambda m: m.text == "🎁 Бонусларим")
def menu_bonuses(message):
    uid = message.from_user.id
    card = make_card_id(uid)
    conn = get_db()
    user = conn.execute("SELECT bonus FROM users WHERE user_id = ?", (uid,)).fetchone()
    conn.close()
    bonus = user["bonus"] if user else 5000

    bot.send_message(
        message.chat.id,
        f"💳 <b>Бонус картангиз:</b> <code>{card}</code>\n"
        f"🎁 <b>Жорий баланс:</b> <b>{bonus:,} сўм</b>\n"
        f"🏅 <b>Даража:</b> Бронза\n\n"
        "Ҳар бир харидингиздан кэшбэк йиғилиб боради!",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(uid)
    )


@bot.message_handler(func=lambda m: m.text == "🧾 Харидларим")
def menu_orders(message):
    uid = message.from_user.id
    conn = get_db()
    rows = conn.execute(
        "SELECT id, items, total, payment_method FROM orders WHERE user_id = ? ORDER BY id DESC LIMIT 10",
        (uid,)
    ).fetchall()
    conn.close()

    if not rows:
        bot.send_message(
            message.chat.id,
            "Ҳали харид қайд этилмаган.\n"
            "Буюртма берганингиздан сўнг барча харидларингиз шу ерда кўринади.",
            reply_markup=main_menu_keyboard(uid)
        )
        return

    lines = ["🧾 <b>Сўнгги харидларингиз:</b>\n"]
    for r in rows:
        lines.append(f"🔹 <b>Буюртма #{r['id']}</b> — <b>{r['total']:,} сўм</b> ({r['payment_method']})\n{r['items']}\n")
    bot.send_message(message.chat.id, "\n".join(lines), parse_mode="HTML", reply_markup=main_menu_keyboard(uid))


@bot.message_handler(func=lambda m: m.text == "📍 Филиаллар")
def menu_branches(message):
    uid = message.from_user.id
    bot.send_message(
        message.chat.id,
        "🏥 <b>Vitora | Smart Pharm</b>\n\n"
        "📍 <b>Манзил:</b> Самарқанд шаҳри, асосий филиал.\n"
        "🕒 <b>Иш вақти:</b> 08:00 – 22:00 (дам олиш кунларисиз)\n"
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


# ================= ADMIN QO'SHIMCHA BUYRUQLAR =================
@bot.message_handler(commands=["products"])
def cmd_products(message):
    if message.from_user.id != ADMIN_ID:
        return
    conn = get_db()
    rows = conn.execute("SELECT id, name, price, stock FROM products ORDER BY id DESC LIMIT 50").fetchall()
    total = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    conn.close()

    if not rows:
        bot.reply_to(message, "Bazadagi mahsulotlar ro'yxati bo'sh.")
        return

    lines = [f"📦 <b>Jami mahsulotlar: {total} ta</b> (oxirgi 50 tasi):\n"]
    for r in rows:
        lines.append(f"<b>{r['id']}.</b> {r['name']} — {r['price']:,} so'm ({r['stock']} dona)")
    bot.send_message(message.chat.id, "\n".join(lines), parse_mode="HTML")


@bot.message_handler(commands=["del"])
def cmd_del(message):
    if message.from_user.id != ADMIN_ID:
        return
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        bot.reply_to(message, "Foydalanish: /del ID (masalan: /del 15)")
        return
    pid = int(parts[1])
    conn = get_db()
    conn.execute("DELETE FROM products WHERE id = ?", (pid,))
    conn.commit()
    conn.close()
    bot.reply_to(message, f"🗑 ID {pid} mahsulot o'chirildi.")


@bot.message_handler(commands=["photo"])
def cmd_photo(message):
    if message.from_user.id != ADMIN_ID:
        return
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3 or not parts[1].isdigit():
        bot.reply_to(message, "Foydalanish: /photo ID rasm_url")
        return
    pid = int(parts[1])
    url = parts[2].strip()
    conn = get_db()
    conn.execute("UPDATE products SET image = ? WHERE id = ?", (url, pid))
    conn.commit()
    conn.close()
    bot.reply_to(message, f"🖼 ID {pid} mahsulot rasmi yangilandi.")


@bot.message_handler(content_types=["document"])
def handle_excel_upload(message):
    if message.from_user.id != ADMIN_ID:
        return
    doc = message.document
    if not doc.file_name.endswith(".xlsx"):
        return

    file_info = bot.get_file(doc.file_id)
    downloaded = bot.download_file(file_info.file_path)
    with open(EXCEL_FILE, "wb") as f:
        f.write(downloaded)

    auto_seed_from_excel(force=True)
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    conn.close()
    bot.reply_to(message, f"📊 Excel fayl muvaffaqiyatli yuklandi!\n✅ Bazadagi tovarlar: {total} ta.")


# ================= MATNLI XABARLAR VA PRIXOD BOSQICHLARI =================
@bot.message_handler(func=lambda m: True)
def handle_all_text(message):
    uid = message.from_user.id
    txt = (message.text or "").strip()

    if uid == ADMIN_ID and uid in prixod_states:
        if txt == "❌ Бекор қилиш":
            prixod_states.pop(uid, None)
            bot.send_message(message.chat.id, "❌ Приход бекор қилинди.", reply_markup=main_menu_keyboard(uid))
            return

        st = prixod_states[uid]
        step = st["step"]

        if step == "photo":
            if txt == "⏭ Расмсиз ўтиш":
                st["image"] = ""
                st["step"] = "name"
                kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
                kb.add(types.KeyboardButton("❌ Бекор қилиш"))
                bot.send_message(
                    message.chat.id,
                    "2️⃣ Товар <b>номини</b> ёзинг (масалан: <i>Омега-3 1000 мг №60</i>):",
                    parse_mode="HTML",
                    reply_markup=kb
                )
            else:
                bot.send_message(message.chat.id, "Илтимос, товар <b>расмини</b> юборинг ёки «⏭ Расмсиз ўтиш» тугмасини босинг:", parse_mode="HTML")
            return

        if step == "name":
            if len(txt) < 2:
                bot.send_message(message.chat.id, "Товар номини тўлиқроқ ёзинг:")
                return
            st["name"] = txt
            st["step"] = "category"
            send_category_step(message.chat.id)
            return

        if step == "category":
            st["category"] = txt
            st["step"] = "price"
            kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
            kb.add(types.KeyboardButton("❌ Бекор қилиш"))
            bot.send_message(
                message.chat.id,
                "4️⃣ Товарнинг <b>сотув нархини</b> (сўмда, фақат рақам) ёзинг:\n<i>Масалан: 125000</i>",
                parse_mode="HTML",
                reply_markup=kb
            )
            return

        if step == "price":
            price = parse_number(txt)
            if price <= 0:
                bot.send_message(message.chat.id, "❌ Нотўғри нарх. Фақат рақам ёзинг (масалан: 85000):")
                return
            st["price"] = price
            st["step"] = "qty"
            kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
            kb.add(types.KeyboardButton("❌ Бекор қилиш"))
            bot.send_message(
                message.chat.id,
                "5️⃣ Неча <b>дона (сони)</b> келди? Фақат рақам ёзинг:\n<i>Масалан: 20</i>",
                parse_mode="HTML",
                reply_markup=kb
            )
            return

        if step == "qty":
            qty = parse_number(txt)
            if qty <= 0:
                bot.send_message(message.chat.id, "❌ Сонини тўғри киритинг (масалан: 15):")
                return

            name = st["name"]
            category = st["category"]
            price = st["price"]
            image = st["image"]

            conn = get_db()
            cur = conn.cursor()
            existing = cur.execute("SELECT id, stock, image FROM products WHERE LOWER(name) = LOWER(?)", (name,)).fetchone()

            if existing:
                pid = existing["id"]
                new_stock = existing["stock"] + qty
                final_img = image if image else existing["image"]
                cur.execute(
                    "UPDATE products SET category = ?, price = ?, stock = ?, image = ? WHERE id = ?",
                    (category, price, new_stock, final_img, pid)
                )
                action_note = f"Мавжуд товар янгиланди (жами қолдиқ: <b>{new_stock} дона</b>)"
            else:
                cur.execute(
                    "INSERT INTO products (name, category, price, stock, description, image) VALUES (?, ?, ?, ?, ?, ?)",
                    (name, category, price, qty, category, image)
                )
                pid = cur.lastrowid
                action_note = f"Янги товар базага қўшилди (ID: <b>#{pid}</b>)"

            cur.execute(
                "INSERT INTO stock_in (product_id, product_name, category, qty, price) VALUES (?, ?, ?, ?, ?)",
                (pid, name, category, qty, price)
            )
            conn.commit()
            conn.close()

            prixod_states.pop(uid, None)
            bot.send_message(
                message.chat.id,
                f"✅ <b>ПРИХОД МУВАФФАҚИЯТЛИ САҚЛАНДИ!</b>\n\n"
                f"💊 <b>Номи:</b> {name}\n"
                f"📂 <b>Категория:</b> {category}\n"
                f"💵 <b>Нархи:</b> {price:,} сўм\n"
                f"📦 <b>Келган сони:</b> +{qty} дона\n"
                f"🖼 <b>Расм:</b> {'Юкланди ✅' if image else 'Йўқ'}\n\n"
                f"ℹ️ {action_note}",
                parse_mode="HTML",
                reply_markup=main_menu_keyboard(uid)
            )
            return

    if uid in waiting_support:
        waiting_support.discard(uid)
        bot.send_message(
            ADMIN_ID,
            f"📩 <b>ЯНГИ МУРОЖААТ!</b>\n"
            f"👤 {message.from_user.first_name} (@{message.from_user.username or 'yoq'})\n"
            f"🆔 <code>{uid}</code>\n\n"
            f"💬 {txt}",
            parse_mode="HTML"
        )
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
    conn.close()
    return jsonify({"products": [dict(r) for r in rows]})


@app.route("/api/order", methods=["POST"])
def api_order():
    data = request.json or {}
    user_id = data.get("user_id", 0)
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

    cur.execute("""
        INSERT INTO orders (user_id, name, username, card, phone, delivery_type, address, payment_method, items, total)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (user_id, name, username, card, phone, delivery_type, address, payment_method, items_text, total))
    order_id = cur.lastrowid

    for item in cart_items:
        pid = int(item.get("id", 0))
        pname = str(item.get("name", ""))
        qty = int(item.get("qty", 0))
        price = int(item.get("price", 0))
        if pid and qty > 0:
            cur.execute("UPDATE products SET stock = MAX(0, stock - ?) WHERE id = ?", (qty, pid))
        if qty > 0:
            cur.execute("""
                INSERT INTO order_items (order_id, product_id, product_name, qty, price, subtotal)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (order_id, pid, pname, qty, price, qty * price))

    conn.commit()
    conn.close()

    admin_msg = (
        f"🆕 <b>YANGI BUYURTMA #{order_id}</b>\n\n"
        f"👤 <b>Mijoz:</b> {name} (@{username})\n"
        f"💳 <b>Bonus ID:</b> {card}\n"
        f"📞 <b>Telefon:</b> {phone}\n"
        f"🚚 <b>Usul:</b> {delivery_type}\n"
        f"📍 <b>Manzil:</b> {address or 'Kiritilmagan'}\n"
        f"💰 <b>To'lov:</b> {payment_method}\n\n"
        f"📦 <b>Mahsulotlar:</b>\n{items_text}\n\n"
        f"💵 <b>JAMI: {total:,} so'm</b>"
    )
    try:
        bot.send_message(ADMIN_ID, admin_msg, parse_mode="HTML")
    except Exception as e:
        print("Adminga xabar yuborishda xato:", e)

    if user_id:
        user_msg = (
            f"✅ <b>Буюртмангиз #{order_id} қабул қилинди!</b>\n\n"
            f"💵 Жами сумма: <b>{total:,} сўм</b>\n"
            f"💰 Тўлов тури: <b>{payment_method}</b>\n"
        )
        if payment_method in ("Click", "Payme"):
            user_msg += f"\n💳 Тўлов учун карта: <code>{HUMO_CARD}</code>\n📸 Тўлов қилгач, чек расмини шу ботга юборинг."
        try:
            bot.send_message(user_id, user_msg, parse_mode="HTML", reply_markup=main_menu_keyboard(user_id))
        except Exception:
            pass

    return jsonify({"ok": True, "order_id": order_id})


if __name__ == "__main__":
    try:
        bot.remove_webhook()
        time.sleep(0.5)
        bot.set_webhook(url=f"{RENDER_URL}/webhook")
    except Exception as e:
        print("Webhook ulashda xato:", e)
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
