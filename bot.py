import os
import re
import time
import sqlite3
import pandas as pd
import telebot
from telebot import types
from flask import Flask, request, jsonify
from flask_cors import CORS

# ================= SOZLAMALAR =================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "9250053752:AAHW1tI5OZAXio-fcbnIy-wF24yOxIEQGCk")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "5055854613"))
RENDER_URL = "https://vitora-bot.onrender.com"
WEBAPP_URL = "https://uzumseller41-jpg.github.io/vitora-shop/?v=2"
EXCEL_FILE = "Vitora_Smart_Pharm_BAD_Tovarlar.xlsx"
DB_FILE = "vitora.db"
HUMO_CARD = "9860 1501 1189 2918"

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
app = Flask(__name__)
CORS(app)


# ================= MA'LUMOTLAR BAZASI =================
def get_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            name TEXT,
            username TEXT,
            phone TEXT
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
    conn.commit()
    conn.close()


def find_col(df, keywords):
    for col in df.columns:
        c_low = str(col).strip().lower()
        for kw in keywords:
            if kw in c_low:
                return col
    return None


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

            col_name = find_col(df, ["наимен", "товар", "препарат", "nomi", "name", "назван"])
            col_cat = find_col(df, ["катег", "групп", "kategoriya", "category", "тип"])
            col_price = find_col(df, ["цен", "narx", "price", "сумм", "стоим", "розм", "розн"])
            col_stock = find_col(df, ["остат", "кол", "qoldiq", "stock", "наличи"])
            col_desc = find_col(df, ["опис", "производ", "страна", "срок", "tavsif", "desc"])
            col_img = find_col(df, ["фото", "картин", "rasm", "image", "img", "url"])

            for _, row in df.iterrows():
                if col_name:
                    name = str(row[col_name]).strip()
                else:
                    name = ""
                    for val in row.values:
                        s = str(val).strip()
                        if s and s.lower() != "nan" and not s.replace(".", "").isdigit():
                            name = s
                            break

                if not name or name.lower() == "nan" or name.isdigit():
                    continue

                category = str(row[col_cat]).strip() if col_cat else "БАДы"
                if not category or category.lower() == "nan":
                    category = "БАДы"

                price = 0
                if col_price:
                    raw_p = str(row[col_price]).replace(" ", "").replace(",", ".").replace("сум", "").replace("сўм", "")
                    try:
                        price = int(float(re.sub(r"[^\d.]", "", raw_p)))
                    except Exception:
                        price = 0

                stock = 10
                if col_stock:
                    raw_s = str(row[col_stock]).replace(" ", "").replace(",", ".")
                    try:
                        stock = int(float(re.sub(r"[^\d.]", "", raw_s)))
                    except Exception:
                        stock = 10

                desc = ""
                if col_desc:
                    desc = str(row[col_desc]).strip()
                    if desc.lower() == "nan":
                        desc = ""
                else:
                    extra = []
                    for c in df.columns:
                        if c in (col_name, col_cat, col_price, col_stock, col_img):
                            continue
                        val = str(row[c]).strip()
                        if val and val.lower() != "nan" and not val.isdigit() and len(val) > 2:
                            extra.append(val)
                    desc = " | ".join(extra[:2])

                img = str(row[col_img]).strip() if col_img else ""
                if img.lower() == "nan":
                    img = ""

                cur.execute(
                    "INSERT INTO products (name, category, price, stock, description, image) VALUES (?, ?, ?, ?, ?, ?)",
                    (name, category, price, stock, desc, img)
                )
            conn.commit()
        except Exception as e:
            print("Excel yuklashda xatolik:", e)
    conn.close()


init_db()
auto_seed_from_excel()


# ================= TELEGRAM BOT BUYRUQLARI =================
def shop_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton(text="🛍 Do'konni ochish", web_app=types.WebAppInfo(url=WEBAPP_URL)))
    return kb


@bot.message_handler(commands=["start"])
def cmd_start(message):
    conn = get_db()
    user = conn.execute("SELECT phone FROM users WHERE user_id = ?", (message.from_user.id,)).fetchone()
    conn.close()

    if user and user["phone"]:
        bot.send_message(
            message.chat.id,
            f"Assalomu alaykum, <b>{message.from_user.first_name}</b>!\n\n"
            "🏥 <b>Vitora | Smart Pharm</b> dorixonasiga xush kelibsiz.\n"
            "Buyurtma berish uchun pastdagi tugmani bosing 👇",
            parse_mode="HTML",
            reply_markup=shop_keyboard()
        )
    else:
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.add(types.KeyboardButton(text="📱 Telefon raqamni yuborish", request_contact=True))
        bot.send_message(
            message.chat.id,
            f"Assalomu alaykum, <b>{message.from_user.first_name}</b>!\n\n"
            "🏥 <b>Vitora | Smart Pharm</b> dorixonasi botiga xush kelibsiz.\n"
            "Ro'yxatdan o'tish va bonus kartangizni faollashtirish uchun telefon raqamingizni yuboring 👇",
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

    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO users (user_id, name, username, phone) VALUES (?, ?, ?, ?)",
        (message.from_user.id, message.from_user.first_name, message.from_user.username or "", phone)
    )
    conn.commit()
    conn.close()

    bot.send_message(
        message.chat.id,
        f"✅ Raqamingiz tasdiqlandi: <b>{phone}</b>\n"
        "🎁 Sizga <b>5 000 so'm</b> bonus berildi!\n\n"
        "Endi do'konni ochishingiz mumkin 👇",
        parse_mode="HTML",
        reply_markup=shop_keyboard()
    )


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


@bot.message_handler(content_types=["photo"])
def handle_receipt_photo(message):
    if message.from_user.id == ADMIN_ID:
        return
    caption = (
        f"🧾 <b>YANGI TO'LOV CHEKI!</b>\n"
        f"👤 Mijoz: {message.from_user.first_name} (@{message.from_user.username or 'yoq'})\n"
        f"🆔 ID: <code>{message.from_user.id}</code>"
    )
    bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=caption, parse_mode="HTML")
    bot.reply_to(message, "✅ To'lov chekingiz adminga yuborildi! Tez orada tasdiqlanadi.")


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

    for item in cart_items:
        pid = int(item.get("id", 0))
        qty = int(item.get("qty", 0))
        if pid and qty > 0:
            cur.execute("UPDATE products SET stock = MAX(0, stock - ?) WHERE id = ?", (qty, pid))

    cur.execute("""
        INSERT INTO orders (user_id, name, username, card, phone, delivery_type, address, payment_method, items, total)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (user_id, name, username, card, phone, delivery_type, address, payment_method, items_text, total))
    order_id = cur.lastrowid
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
            f"✅ <b>Buyurtmangiz #{order_id} qabul qilindi!</b>\n\n"
            f"💵 Jami summa: <b>{total:,} so'm</b>\n"
            f"💰 To'lov turi: <b>{payment_method}</b>\n"
        )
        if payment_method in ("Click", "Payme"):
            user_msg += f"\n💳 To'lov uchun karta: <code>{HUMO_CARD}</code>\n📸 To'lov qilgach, chek rasmini shu botga yuboring."
        try:
            bot.send_message(user_id, user_msg, parse_mode="HTML")
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
