import hashlib
import os
import sqlite3
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import telebot
from telebot import types

BOT_TOKEN = "9250053752:AAHW1tI5OZAXio-fcbnIy-wF24yOxIEQGCk"
WEBAPP_URL = "https://relaxed-meerkat-9b9fbb.netlify.app"

bot = telebot.TeleBot(BOT_TOKEN)

conn = sqlite3.connect("vitora.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        full_name TEXT,
        phone TEXT,
        card_id TEXT,
        bonus INTEGER DEFAULT 5000
    )
""")
conn.commit()

def generate_card_id(user_id: int) -> str:
    hash_str = hashlib.md5(str(user_id).encode()).hexdigest()[:8].upper()
    return f"VTR-{hash_str}"

def get_main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(types.KeyboardButton(text="🛍 Buyurtma berish", web_app=types.WebAppInfo(url=WEBAPP_URL)))
    markup.row(types.KeyboardButton(text="🎁 Bonuslarim"), types.KeyboardButton(text="📋 Xaridlarim"))
    markup.row(types.KeyboardButton(text="📍 Filiallar"), types.KeyboardButton(text="💬 Murojaat"))
    markup.row(types.KeyboardButton(text="🚀 Kabinetim"), types.KeyboardButton(text="🌐 Sayt"))
    return markup

@bot.message_handler(commands=['start'])
def cmd_start(message):
    user_id = message.from_user.id
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()

    if user and user[2]:
        bot.send_message(
            message.chat.id,
            f"Xush kelibsiz, {user[1]}! 👋\n"
            f"Bonus kartangiz: <b>{user[3]}</b>\n\n"
            "Nima qilamiz? Pastdagi tugmalardan birini tanlang.",
            reply_markup=get_main_menu(),
            parse_mode="HTML"
        )
        return

    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton(text="O'zbekcha 🇺🇿", callback_data="lang_uz"),
        types.InlineKeyboardButton(text="Русский 🇷🇺", callback_data="lang_ru")
    )
    bot.send_message(message.chat.id, "Тилни танланг · Выберите язык", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("lang_"))
def select_lang(call):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(types.KeyboardButton(text="📱 Raqamimni yuborish", request_contact=True))
    
    bot.send_message(
        call.message.chat.id,
        "Salom! 👋\n\n"
        "Bu <b>Smart Pharm | Vitora</b> dorixonasi boti. Bu yerda dori va vitaminlarga buyurtma berasiz, bonuslaringizni ko'rasiz.\n\n"
        "Boshlash uchun pastdagi tugmani bosing — telefon raqamingiz bizga keladi.\n\n"
        "Filial yoki xodim bo'lsangiz: /xodim",
        reply_markup=markup,
        parse_mode="HTML"
    )
    bot.answer_callback_query(call.id)

@bot.message_handler(content_types=['contact'])
def handle_contact(message):
    user_id = message.from_user.id
    full_name = message.from_user.first_name or "Mijoz"
    phone = message.contact.phone_number
    card_id = generate_card_id(user_id)

    cursor.execute(
        "INSERT OR REPLACE INTO users (user_id, full_name, phone, card_id, bonus) VALUES (?, ?, ?, ?, ?)",
        (user_id, full_name, phone, card_id, 5000)
    )
    conn.commit()

    bot.send_message(
        message.chat.id,
        f"Rahmat, {full_name}! ✅\n"
        f"Bonus kartangiz: <b>{card_id}</b>\n"
        f"Sizga xush kelibsiz bonusi sifatida <b>5 000 so'm</b> taqdim etildi! 🎁\n\n"
        "Endi buyurtma berishingiz mumkin — pastdagi «🛍 Buyurtma berish» tugmasini bosing.",
        reply_markup=get_main_menu(),
        parse_mode="HTML"
    )

@bot.message_handler(commands=['xodim'])
def staff_mode(message):
    bot.send_message(
        message.chat.id,
        "🔐 <b>Xodimlar bo'limi</b>\n\nMijozning bonus kartasini tekshirish yoki ball qo'shish uchun karta raqamini kiriting (masalan: <code>VTR-13C57D75</code>):",
        parse_mode="HTML"
    )

@bot.message_handler(func=lambda message: True)
def handle_buttons(message):
    text = message.text
    user_id = message.from_user.id

    if text == "🎁 Bonuslarim":
        cursor.execute("SELECT card_id, bonus FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row:
            bot.send_message(
                message.chat.id,
                f"💳 <b>Bonus kartangiz:</b> <code>{row[0]}</code>\n"
                f"💰 <b>Joriy balansingiz:</b> {row[1]:,} so'm\n\n"
                "<i>Har bir xariddan 3% keshbek yig'iladi!</i>",
                parse_mode="HTML"
            )
    elif text == "📋 Xaridlarim":
        bot.send_message(message.chat.id, "📋 Barcha buyurtmalaringiz tarixini «🛍 Buyurtma berish» tugmasi ichidagi <b>Buyurtmalar</b> bo'limida ko'rishingiz mumkin.", parse_mode="HTML")
    elif text == "📍 Filiallar":
        bot.send_message(
            message.chat.id,
            "📍 <b>Smart Pharm | Vitora</b>\n\n"
            "• Samarqand shahri, asosiy filial\n"
            "• Ish vaqti: 08:00 – 22:00 (dam olish kunlarisiz)\n"
            "• Yetkazib berish: Samarqand bo'ylab 1–2 soat ichida",
            parse_mode="HTML"
        )
    elif text == "💬 Murojaat":
        bot.send_message(message.chat.id, "💬 Savol va takliflaringiz bo'lsa, shu yerga yozib qoldiring — farmatsevt operatorimiz tez orada javob beradi.")
    elif text == "🚀 Kabinetim":
        cursor.execute("SELECT full_name, phone, card_id, bonus FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row:
            bot.send_message(
                message.chat.id,
                f"👤 <b>Shaxsiy kabinet</b>\n\n"
                f"• Ism: {row[0]}\n"
                f"• Telefon: {row[1]}\n"
                f"• Karta ID: <code>{row[2]}</code>\n"
                f"• Bonus: {row[3]:,} so'm",
                parse_mode="HTML"
            )
    elif text == "🌐 Sayt":
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(text="🌐 Do'konni brauzerda ochish", url=WEBAPP_URL))
        bot.send_message(message.chat.id, "Onlayn katalogimizga havola:", reply_markup=markup)

# Render.com bepul tarifi uchun veb-port ochib turish
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Vitora Bot is running!")

def run_web():
    port = int(os.environ.get("PORT", 10000))
    HTTPServer(("0.0.0.0", port), DummyHandler).serve_forever()

threading.Thread(target=run_web, daemon=True).start()
print("Bot ishga tushdi...")
bot.infinity_polling()
