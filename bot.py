import os
import sqlite3
import threading
import pandas as pd
import telebot
from telebot import types
from flask import Flask, request, jsonify
from flask_cors import CORS

# ================= SOZLAMALAR =================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "9250053752:AAH-YourTokenHere")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "5055854613"))
WEBAPP_URL = "https://uzumseller41-jpg.github.io/vitora-shop/?v=2"
EXCEL_FILE = "Vitora_Smart_Pharm_BAD_Tovarlar.xlsx"
DB_FILE = "vitora.db"
HUMO_CARD = "9860 1501 1189 2918"

bot = telebot.TeleBot(BOT_TOKEN)
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


def auto_seed_from_excel():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM products")
    count = cur.fetchone()[0]

    if count == 0 and os.path.exists(EXCEL_FILE):
        try:
            df = pd.read_excel(EXCEL_FILE)
            df.columns = [str(c).strip() for c in df.columns]
            added = 0
            for _, row in df.iterrows():
                name = str(row.get("Nomi", row.get("Наименование", row.iloc[0]))).strip()
                if not name or name.lower() == "nan":
                    continue
                category = str(row.get("Kategoriya", row.get("Категория", "БАДы"))).strip()
                if category.lower() == "nan":
                    category = "БАДы"

                raw_price = row.get("Narxi", row.get("Цена", 0))
                try:
                    price = int(float(str(raw_price).replace(" ", "").replace(",", "")))
                except Exception:
                    price = 0

                raw_stock = row.get("Qoldiq", row.get("Остаток", 10))
                try:
                    stock = int(float(str(raw_stock).replace(" ", "").replace(",", "")))
                except Exception:
                    stock = 10

                desc = str(row.get("Tavsif", row.get("Описание", ""))).strip()
                if desc.lower() == "nan":
                    desc = ""

                img = str(row.get("Rasm", row.get("Фото", ""))).strip()
                if img.lower() == "nan":
                    img = ""

                cur.execute(
                    "INSERT INTO products (name, category, price, stock, description, image) VALUES (?, ?, ?, ?, ?, ?)",
                    (name, category, price, stock, desc, img)
                )
                added += 1
            conn.commit()
            print(f"Excel fayldan {added} ta mahsulot bazaga yuklandi.")
        except Exception as e:
            print("Excel yuklashda xatolik:", e)
    conn.close()


init_db()
auto_seed_from_excel()


# ================= TELEGRAM BOT BUYRUQLARI =================
@bot.message_handler(commands=["start"])
def cmd_start(message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn_shop = types.KeyboardButton(
        text="🛍 Do'konni ochish",
        web_app=types.WebAppInfo(url=WEBAPP_URL)
    )
    kb.add(btn_shop)

    text = (
        f"Assalomu alaykum, <b>{message.from_user.first_name}</b>!\n\n"
        "🏥 <b>Vitora | Smart Pharm</b> dorixonasi botiga xush kelibsiz.\n"
        "Kerakli dori va BAD mahsulotlarini onlayn buyurtma qilish uchun pastdagi tugmani bosing 👇"
    )
    bot.send_message(message.chat.id, text, parse_mode="HTML", reply_markup=kb)


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

    conn = get_db()
    conn.execute("DELETE FROM products")
    conn.commit()
    conn.close()

    auto_seed_from_excel()
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


# ================= FLASK API (MINI APP UCHUN) =================
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


def run_bot():
    bot.infinity_polling(skip_pending=True)


if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
