import os
import json
import base64
import sqlite3
import threading
from flask import Flask, request, jsonify
import telebot
from telebot import types

TOKEN = "9250053752:AAHW1tI5OZAXio-fcbnIy-wF24yOxIEQGCk"
ADMIN_ID = 5055854613
WEBAPP_URL = "https://relaxed-meerkat-9b9fbb.netlify.app"

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)
admin_drafts = {}

@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS"
    return response

conn = sqlite3.connect("vitora.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    full_name TEXT,
    phone TEXT,
    card_id TEXT,
    bonus INTEGER DEFAULT 5000,
    lang TEXT DEFAULT 'uz'
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    category TEXT DEFAULT 'Витамины',
    price INTEGER NOT NULL,
    description TEXT DEFAULT '',
    image_data TEXT DEFAULT ''
)
""")
conn.commit()

def get_card_id(user_id: int) -> str:
    return "VTR-" + hex(abs(user_id))[2:].upper().zfill(8)[:8]

def main_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(types.KeyboardButton("🛍 Buyurtma berish", web_app=types.WebAppInfo(url=WEBAPP_URL)))
    kb.add(
        types.KeyboardButton("💳 Mening kartam"),
        types.KeyboardButton("🎁 Bonuslarim"),
        types.KeyboardButton("📦 Buyurtmalarim"),
        types.KeyboardButton("📍 Filiallarimiz"),
        types.KeyboardButton("💬 Operator bilan aloqa"),
        types.KeyboardButton("⚙️ Sozlamalar")
    )
    return kb

# ================= ADMIN BUYRUQLARI =================
@bot.message_handler(commands=["add"])
def admin_add_start(message):
    if message.from_user.id != ADMIN_ID:
        return
    admin_drafts[ADMIN_ID] = {"step": "photo"}
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(types.KeyboardButton("⏭ Rasmsiz davom etish"), types.KeyboardButton("❌ Bekor qilish"))
    bot.send_message(
        message.chat.id,
        "📸 <b>1/5-qadam:</b> Tovar rasmini yuboring (yoki «Rasmsiz davom etish» tugmasini bosing):",
        parse_mode="HTML",
        reply_markup=kb
    )

@bot.message_handler(commands=["products"])
def admin_list_products(message):
    if message.from_user.id != ADMIN_ID:
        return
    cursor.execute("SELECT id, name, price, category FROM products ORDER BY id DESC")
    rows = cursor.fetchall()
    if not rows:
        bot.send_message(message.chat.id, "📭 Hozircha bazada qo‘shilgan tovarlar yo‘q. Qo‘shish uchun /add yozing.")
        return
    lines = ["📦 <b>Do‘kondagi tovarlar ro‘yxati:</b>\n"]
    for r in rows:
        lines.append(f"🆔 <code>{r[0]}</code> | <b>{r[1]}</b> ({r[3]}) — {r[2]:,} so‘m")
    lines.append("\n🗑 O‘chirish uchun: <code>/del ID</code> (masalan: <code>/del 1</code>)")
    bot.send_message(message.chat.id, "\n".join(lines), parse_mode="HTML")

@bot.message_handler(commands=["del"])
def admin_delete_product(message):
    if message.from_user.id != ADMIN_ID:
        return
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        bot.send_message(message.chat.id, "⚠️ To‘g‘ri format: <code>/del 1</code>", parse_mode="HTML")
        return
    pid = int(parts[1])
    cursor.execute("DELETE FROM products WHERE id = ?", (pid,))
    conn.commit()
    bot.send_message(message.chat.id, f"🗑 ID <code>{pid}</code> raqamli tovar o‘chirildi.", parse_mode="HTML")

@bot.message_handler(content_types=["photo"], func=lambda m: m.from_user.id == ADMIN_ID and ADMIN_ID in admin_drafts)
def admin_receive_photo(message):
    draft = admin_drafts[ADMIN_ID]
    if draft.get("step") != "photo":
        return
    file_id = message.photo[-1].file_id
    file_info = bot.get_file(file_id)
    downloaded = bot.download_file(file_info.file_path)
    b64_img = "data:image/jpeg;base64," + base64.b64encode(downloaded).decode("utf-8")
    draft["image_data"] = b64_img
    draft["step"] = "name"
    bot.send_message(
        message.chat.id,
        "✅ Rasm qabul qilindi!\n\n✍️ <b>2/5-qadam:</b> Tovar nomini yozing (masalan: <i>Витамин D3 5000 МЕ</i>):",
        parse_mode="HTML",
        reply_markup=types.ReplyKeyboardRemove()
    )

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and ADMIN_ID in admin_drafts)
def admin_receive_steps(message):
    text = (message.text or "").strip()
    if text == "❌ Bekor qilish":
        admin_drafts.pop(ADMIN_ID, None)
        bot.send_message(message.chat.id, "❌ Tovar qo‘shish bekor qilindi.", reply_markup=main_menu())
        return

    draft = admin_drafts[ADMIN_ID]
    step = draft.get("step")

    if step == "photo" and text == "⏭ Rasmsiz davom etish":
        draft["image_data"] = ""
        draft["step"] = "name"
        bot.send_message(
            message.chat.id,
            "✍️ <b>2/5-qadam:</b> Tovar nomini yozing:",
            parse_mode="HTML",
            reply_markup=types.ReplyKeyboardRemove()
        )
    elif step == "name":
        draft["name"] = text
        draft["step"] = "category"
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True, row_width=2)
        kb.add("Витамины", "Омега-3", "Минералы", "Иммунитет", "Для детей", "БАДы")
        bot.send_message(
            message.chat.id,
            "📂 <b>3/5-qadam:</b> Kategoriyani tanlang yoki yozing:",
            parse_mode="HTML",
            reply_markup=kb
        )
    elif step == "category":
        draft["category"] = text
        draft["step"] = "price"
        bot.send_message(
            message.chat.id,
            "💰 <b>4/5-qadam:</b> Narxini faqat raqamda yozing (masalan: <code>145000</code>):",
            parse_mode="HTML",
            reply_markup=types.ReplyKeyboardRemove()
        )
    elif step == "price":
        digits = "".join(c for c in text if c.isdigit())
        if not digits:
            bot.send_message(message.chat.id, "⚠️ Iltimos, narxni faqat raqamda yozing (masalan: 145000):")
            return
        draft["price"] = int(digits)
        draft["step"] = "description"
        bot.send_message(
            message.chat.id,
            "📝 <b>5/5-qadam:</b> Qisqa tavsif / tarkibini yozing (masalan: <i>60 капсул, для костей и иммунитета</i>):",
            parse_mode="HTML"
        )
    elif step == "description":
        draft["description"] = text
        cursor.execute(
            "INSERT INTO products (name, category, price, description, image_data) VALUES (?, ?, ?, ?, ?)",
            (draft["name"], draft["category"], draft["price"], draft["description"], draft.get("image_data", ""))
        )
        conn.commit()
        new_id = cursor.lastrowid
        admin_drafts.pop(ADMIN_ID, None)
        bot.send_message(
            message.chat.id,
            f"🎉 <b>Tovar muvaffaqiyatli qo‘shildi!</b>\n\n"
            f"🆔 ID: <code>{new_id}</code>\n"
            f"💊 Nomi: <b>{draft['name']}</b>\n"
            f"📂 Kategoriya: {draft['category']}\n"
            f"💰 Narxi: <b>{draft['price']:,} so‘m</b>\n"
            f"📝 Tavsif: {draft['description']}\n\n"
            f"Endi Mini App’da darhol ko‘rinadi!",
            parse_mode="HTML",
            reply_markup=main_menu()
        )

# ================= FOYDALANUVCHI BUYRUQLARI =================
@bot.message_handler(commands=["start"])
def start_cmd(message):
    uid = message.from_user.id
    cursor.execute("SELECT phone, card_id FROM users WHERE user_id = ?", (uid,))
    row = cursor.fetchone()
    if row and row[0]:
        bot.send_message(
            message.chat.id,
            f"👋 Xush kelibsiz, <b>{message.from_user.first_name}</b>!\n"
            f"💳 Karta ID: <code>{row[1]}</code>\n\nQuyidagi tugmalardan birini tanlang:",
            parse_mode="HTML",
            reply_markup=main_menu()
        )
    else:
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.add(types.KeyboardButton("📱 Telefon raqamni yuborish", request_contact=True))
        bot.send_message(
            message.chat.id,
            "Assalomu alaykum! <b>Vitora | Smart Pharm</b> dorixonasi botiga xush kelibsiz.\n\n"
            "Ro'yxatdan o'tish va <b>5 000 so'm</b> bonus olish uchun telefon raqamingizni yuboring:",
            parse_mode="HTML",
            reply_markup=kb
        )

@bot.message_handler(content_types=["contact"])
def handle_contact(message):
    uid = message.from_user.id
    phone = message.contact.phone_number
    name = message.from_user.first_name or "Mijoz"
    card_id = get_card_id(uid)
    cursor.execute(
        "INSERT OR REPLACE INTO users (user_id, full_name, phone, card_id, bonus) VALUES (?, ?, ?, ?, 5000)",
        (uid, name, phone, card_id)
    )
    conn.commit()
    bot.send_message(
        message.chat.id,
        f"✅ Tabriklaymiz, <b>{name}</b>! Siz muvaffaqiyatli ro'yxatdan o'tdingiz.\n"
        f"💳 Karta raqamingiz: <code>{card_id}</code>\n"
        f"🎁 Hisobingizga <b>5 000 so'm</b> bonus qo'shildi!",
        parse_mode="HTML",
        reply_markup=main_menu()
    )

@bot.message_handler(func=lambda m: m.text == "💳 Mening kartam")
def my_card(message):
    uid = message.from_user.id
    card_id = get_card_id(uid)
    cursor.execute("SELECT bonus FROM users WHERE user_id = ?", (uid,))
    row = cursor.fetchone()
    bonus = row[0] if row else 5000
    bot.send_message(
        message.chat.id,
        f"💳 <b>Vitora Loyalty Karta</b>\n\n"
        f"🆔 Karta ID: <code>{card_id}</code>\n"
        f"💰 Bonus: <b>{bonus:,} so'm</b>\n"
        f"🏅 Daraja: <b>Bronza</b>",
        parse_mode="HTML"
    )

@bot.message_handler(func=lambda m: m.text == "🎁 Bonuslarim")
def my_bonus(message):
    uid = message.from_user.id
    cursor.execute("SELECT bonus FROM users WHERE user_id = ?", (uid,))
    row = cursor.fetchone()
    bonus = row[0] if row else 5000
    bot.send_message(message.chat.id, f"🎁 Sizning joriy bonusingiz: <b>{bonus:,} so'm</b>", parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "📍 Filiallarimiz")
def branches(message):
    bot.send_message(
        message.chat.id,
        "📍 <b>Vitora | Smart Pharm</b>\nSamarqand shahri, asosiy filial.\n🕒 Ish vaqti: 08:00 – 22:00",
        parse_mode="HTML"
    )

@bot.message_handler(func=lambda m: m.text == "💬 Operator bilan aloqa")
def contact_op(message):
    bot.send_message(message.chat.id, "✍️ Savolingizni shu yerga yozing — operatorimiz tez orada javob beradi.")

@bot.message_handler(func=lambda m: m.text == "📦 Buyurtmalarim")
def my_orders(message):
    bot.send_message(message.chat.id, "📦 Buyurtmalaringizni do'kon menyusidagi «Буюртмалар» bo'limidan kuzatishingiz mumkin.")

@bot.message_handler(func=lambda m: m.text == "⚙️ Sozlamalar")
def settings(message):
    bot.send_message(message.chat.id, "⚙️ Til: O'zbekcha\n🔔 Bildirishnomalar: Yoqilgan")

# ================= MINI APP API =================
@app.route("/api/products", methods=["GET"])
def api_products():
    cursor.execute("SELECT id, name, category, price, description, image_data FROM products ORDER BY id DESC")
    rows = cursor.fetchall()
    items = []
    for r in rows:
        items.append({
            "id": r[0],
            "name": r[1],
            "category": r[2],
            "price": r[3],
            "description": r[4],
            "image": r[5]
        })
    return jsonify({"ok": True, "products": items}), 200

@app.route("/api/order", methods=["POST", "OPTIONS"])
def api_order():
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200
    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id")
    phone = "Ko'rsatilmagan"
    if user_id:
        cursor.execute("SELECT phone FROM users WHERE user_id = ?", (int(user_id),))
        row = cursor.fetchone()
        if row and row[0]:
            phone = row[0]
    text = (
        f"🆕 <b>YANGI BUYURTMA!</b>\n\n"
        f"👤 Mijoz: <b>{data.get('name', 'Mijoz')}</b> (@{data.get('username', 'yoq')})\n"
        f"📞 Tel: <code>{phone}</code>\n"
        f"💳 Karta: <code>{data.get('card', '—')}</code>\n\n"
        f"💊 <b>Mahsulotlar:</b>\n{data.get('items', '')}\n\n"
        f"💰 <b>Jami: {int(data.get('total', 0)):,} so'm</b>"
    )
    try:
        bot.send_message(ADMIN_ID, text, parse_mode="HTML")
        return jsonify({"ok": True}), 200
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/")
def index():
    return "Vitora Bot is running 24/7!"

def run_bot():
    bot.infinity_polling(skip_pending=True)

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
