import os
import json
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

# CORS ruxsati (Netlify saytidan buyurtma qabul qilish uchun)
@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS"
    return response

# SQLite baza
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

# WebApp sendData usuli orqali kelgan buyurtma
@bot.message_handler(content_types=["web_app_data"])
def handle_webapp_data(message):
    data = json.loads(message.web_app_data.data)
    uid = message.from_user.id
    cursor.execute("SELECT phone FROM users WHERE user_id = ?", (uid,))
    row = cursor.fetchone()
    phone = row[0] if row else "Ko'rsatilmagan"
    text = (
        f"🆕 <b>YANGI BUYURTMA (Telegram)!</b>\n\n"
        f"👤 Mijoz: <b>{message.from_user.first_name}</b> (@{message.from_user.username or 'yoq'})\n"
        f"📞 Tel: <code>{phone}</code>\n"
        f"💳 Karta: <code>{data.get('card')}</code>\n\n"
        f"💊 <b>Mahsulotlar:</b>\n{data.get('items')}\n\n"
        f"💰 <b>Jami: {int(data.get('total', 0)):,} so'm</b>"
    )
    bot.send_message(ADMIN_ID, text, parse_mode="HTML")
    bot.send_message(message.chat.id, "✅ Buyurtmangiz qabul qilindi! Tez orada operatorimiz bog'lanadi.")

# To'g'ridan-to'g'ri HTTP API orqali buyurtma (OPEN tugmasi va Instagram uchun)
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
