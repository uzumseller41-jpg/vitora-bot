import os
import io
import base64
import sqlite3
import threading
import time
import openpyxl
from flask import Flask, request, jsonify
import telebot
from telebot import types

TOKEN = "9250053752:AAHW1tI5OZAXio-fcbnIy-wF24yOxIEQGCk"
ADMIN_ID = 5055854613
WEBAPP_URL = "https://relaxed-meerkat-9b9fbb.netlify.app"
RENDER_URL = "https://vitora-bot.onrender.com"
PAYMENT_CARD = "9860 1501 1189 2918"

bot = telebot.TeleBot(TOKEN, threaded=False)
app = Flask(__name__)
admin_drafts = {}
pending_photo_pid = {}

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
    stock INTEGER DEFAULT 0,
    description TEXT DEFAULT '',
    image_data TEXT DEFAULT ''
)
""")
conn.commit()

try:
    cursor.execute("ALTER TABLE products ADD COLUMN stock INTEGER DEFAULT 0")
    conn.commit()
except Exception:
    pass

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

# ================= EXCEL (.XLSX) ORQALI TOVAR YUKLASH =================
@bot.message_handler(content_types=["document"], func=lambda m: m.from_user.id == ADMIN_ID)
def admin_upload_excel(message):
    doc = message.document
    if not doc.file_name.lower().endswith(".xlsx"):
        bot.send_message(message.chat.id, "⚠️ Iltimos, faqat <b>.xlsx</b> formatidagi Excel fayl yuboring.", parse_mode="HTML")
        return

    file_info = bot.get_file(doc.file_id)
    downloaded = bot.download_file(file_info.file_path)
    wb = openpyxl.load_workbook(io.BytesIO(downloaded), data_only=True)
    ws = wb["Tovarlar"] if "Tovarlar" in wb.sheetnames else wb.active

    added_count = 0
    for row in ws.iter_rows(min_row=5, values_only=True):
        if not row or len(row) < 4:
            continue
        name = str(row[1] or "").strip()
        if not name or name.startswith("JAMI"):
            continue
        category = str(row[2] or "Витамины").strip()
        try:
            price = int(float(row[3] or 0))
        except Exception:
            price = 0
        try:
            stock = int(float(row[4] or 0)) if len(row) > 4 and row[4] is not None else 0
        except Exception:
            stock = 0
        description = str(row[6] or "").strip() if len(row) > 6 else ""
        image_url = str(row[7] or "").strip() if len(row) > 7 else ""

        if price > 0:
            cursor.execute(
                "INSERT INTO products (name, category, price, stock, description, image_data) VALUES (?, ?, ?, ?, ?, ?)",
                (name, category, price, stock, description, image_url)
            )
            added_count += 1

    conn.commit()
    bot.send_message(
        message.chat.id,
        f"📊 <b>Excel fayl muvaffaqiyatli yuklandi!</b>\n\n"
        f"✅ Qo‘shilgan tovarlar soni: <b>{added_count} ta</b>\n\n"
        f"📋 Barchasini ko‘rish: <code>/products</code>\n"
        f"🖼 Biror tovarga rasm biriktirish uchun: <code>/photo ID</code> (masalan: <code>/photo 1</code>)",
        parse_mode="HTML"
    )

@bot.message_handler(commands=["photo"])
def admin_attach_photo_cmd(message):
    if message.from_user.id != ADMIN_ID:
        return
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        bot.send_message(message.chat.id, "⚠️ To‘g‘ri format: <code>/photo 1</code> (ID raqamini yozing)", parse_mode="HTML")
        return
    pid = int(parts[1])
    cursor.execute("SELECT name FROM products WHERE id = ?", (pid,))
    row = cursor.fetchone()
    if not row:
        bot.send_message(message.chat.id, "⚠️ Bunday ID raqamli tovar topilmadi.")
        return
    pending_photo_pid[ADMIN_ID] = pid
    bot.send_message(
        message.chat.id,
        f"📸 <b>{row[0]}</b> (ID: <code>{pid}</code>) uchun rasm yuboring:",
        parse_mode="HTML"
    )

# ================= YAKKA TARTIBDA ADMIN BUYRUQLARI =================
@bot.message_handler(commands=["add"])
def admin_add_start(message):
    if message.from_user.id != ADMIN_ID:
        return
    admin_drafts[ADMIN_ID] = {"step": "photo"}
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(types.KeyboardButton("⏭ Rasmsiz davom etish"), types.KeyboardButton("❌ Bekor qilish"))
    bot.send_message(
        message.chat.id,
        "📸 <b>1/6-qadam:</b> Tovar rasmini yuboring (yoki «Rasmsiz davom etish» tugmasini bosing):",
        parse_mode="HTML",
        reply_markup=kb
    )

@bot.message_handler(commands=["products"])
def admin_list_products(message):
    if message.from_user.id != ADMIN_ID:
        return
    cursor.execute("SELECT id, name, price, stock, category FROM products ORDER BY id DESC")
    rows = cursor.fetchall()
    if not rows:
        bot.send_message(message.chat.id, "📭 Hozircha bazada qo‘shilgan tovarlar yo‘q. Excel (.xlsx) yuboring yoki /add yozing.")
        return
    lines = ["📦 <b>Do‘kondagi tovarlar va qoldiqlar:</b>\n"]
    for r in rows[:50]:
        lines.append(f"🆔 <code>{r[0]}</code> | <b>{r[1]}</b> ({r[4]})\n    💰 {r[2]:,} so‘m | 📦 Qoldiq: <b>{r[3]} dona</b>")
    if len(rows) > 50:
        lines.append(f"\n... va yana {len(rows) - 50} ta tovar")
    lines.append("\n🖼 Rasm qo‘shish: <code>/photo ID</code>\n➕ Qoldiq qo‘shish: <code>/stock ID SON</code>\n🗑 O‘chirish: <code>/del ID</code>")
    bot.send_message(message.chat.id, "\n".join(lines), parse_mode="HTML")

@bot.message_handler(commands=["stock"])
def admin_update_stock(message):
    if message.from_user.id != ADMIN_ID:
        return
    parts = message.text.split()
    if len(parts) < 3 or not parts[1].isdigit() or not parts[2].lstrip("+-").isdigit():
        bot.send_message(message.chat.id, "⚠️ To‘g‘ri format: <code>/stock 1 25</code>", parse_mode="HTML")
        return
    pid = int(parts[1])
    qty = int(parts[2])
    cursor.execute("UPDATE products SET stock = MAX(0, stock + ?) WHERE id = ?", (qty, pid))
    conn.commit()
    cursor.execute("SELECT name, stock FROM products WHERE id = ?", (pid,))
    row = cursor.fetchone()
    if row:
        bot.send_message(message.chat.id, f"✅ <b>{row[0]}</b> yangi qoldig‘i: <b>{row[1]} dona</b>", parse_mode="HTML")
    else:
        bot.send_message(message.chat.id, "⚠️ Bunday ID topilmadi.")

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

@bot.message_handler(content_types=["photo"], func=lambda m: m.from_user.id == ADMIN_ID)
def admin_receive_photo(message):
    file_id = message.photo[-1].file_id
    file_info = bot.get_file(file_id)
    downloaded = bot.download_file(file_info.file_path)
    b64_img = "data:image/jpeg;base64," + base64.b64encode(downloaded).decode("utf-8")

    if ADMIN_ID in pending_photo_pid:
        pid = pending_photo_pid.pop(ADMIN_ID)
        cursor.execute("UPDATE products SET image_data = ? WHERE id = ?", (b64_img, pid))
        conn.commit()
        bot.send_message(message.chat.id, f"✅ ID <code>{pid}</code> raqamli tovarga rasm muvaffaqiyatli biriktirildi!", parse_mode="HTML")
        return

    if ADMIN_ID in admin_drafts and admin_drafts[ADMIN_ID].get("step") == "photo":
        draft = admin_drafts[ADMIN_ID]
        draft["image_data"] = b64_img
        draft["step"] = "name"
        bot.send_message(
            message.chat.id,
            "✅ Rasm qabul qilindi!\n\n✍️ <b>2/6-qadam:</b> Tovar nomini yozing:",
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
            "✍️ <b>2/6-qadam:</b> Tovar nomini yozing:",
            parse_mode="HTML",
            reply_markup=types.ReplyKeyboardRemove()
        )
    elif step == "name":
        draft["name"] = text
        draft["step"] = "category"
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True, row_width=2)
        kb.add("Витамины и комплексы", "Омега-3 и рыбий жир", "Минералы и микроэлементы", "Для детей", "Для суставов и костей", "Фиточаи, травы и экстракты")
        bot.send_message(
            message.chat.id,
            "📂 <b>3/6-qadam:</b> Kategoriyani tanlang yoki yozing:",
            parse_mode="HTML",
            reply_markup=kb
        )
    elif step == "category":
        draft["category"] = text
        draft["step"] = "price"
        bot.send_message(
            message.chat.id,
            "💰 <b>4/6-qadam:</b> Sotuv narxini faqat raqamda yozing (masalan: <code>145000</code>):",
            parse_mode="HTML",
            reply_markup=types.ReplyKeyboardRemove()
        )
    elif step == "price":
        digits = "".join(c for c in text if c.isdigit())
        if not digits:
            bot.send_message(message.chat.id, "⚠️ Iltimos, narxni faqat raqamda yozing:")
            return
        draft["price"] = int(digits)
        draft["step"] = "stock"
        bot.send_message(
            message.chat.id,
            "📦 <b>5/6-qadam:</b> Omborga nechta keldi? (sonini yozing, masalan: <code>30</code>):",
            parse_mode="HTML"
        )
    elif step == "stock":
        digits = "".join(c for c in text if c.isdigit())
        if not digits:
            bot.send_message(message.chat.id, "⚠️ Iltimos, kelgan sonini faqat raqamda yozing:")
            return
        draft["stock"] = int(digits)
        draft["step"] = "description"
        bot.send_message(
            message.chat.id,
            "📝 <b>6/6-qadam:</b> Qisqa tavsif / tarkibini yozing:",
            parse_mode="HTML"
        )
    elif step == "description":
        draft["description"] = text
        cursor.execute(
            "INSERT INTO products (name, category, price, stock, description, image_data) VALUES (?, ?, ?, ?, ?, ?)",
            (draft["name"], draft["category"], draft["price"], draft["stock"], draft["description"], draft.get("image_data", ""))
        )
        conn.commit()
        new_id = cursor.lastrowid
        admin_drafts.pop(ADMIN_ID, None)
        bot.send_message(
            message.chat.id,
            f"🎉 <b>Tovar qo‘shildi!</b>\n🆔 ID: <code>{new_id}</code> | <b>{draft['name']}</b> — {draft['price']:,} so‘m ({draft['stock']} dona)",
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

# ================= WEBHOOK & MINI APP API =================
@app.route("/webhook", methods=["POST"])
def telegram_webhook():
    json_str = request.get_data().decode("utf-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "OK", 200

@app.route("/api/config", methods=["GET"])
def api_config():
    return jsonify({"ok": True, "payment_card": PAYMENT_CARD}), 200

@app.route("/api/products", methods=["GET"])
def api_products():
    cursor.execute("SELECT id, name, category, price, stock, description, image_data FROM products ORDER BY id DESC")
    rows = cursor.fetchall()
    items = [
        {"id": r[0], "name": r[1], "category": r[2], "price": r[3], "stock": r[4], "description": r[5], "image": r[6]}
        for r in rows
    ]
    return jsonify({"ok": True, "products": items, "payment_card": PAYMENT_CARD}), 200

@app.route("/api/order", methods=["POST", "OPTIONS"])
def api_order():
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200
    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id")
    phone = (data.get("phone") or "").strip()
    if not phone and user_id:
        cursor.execute("SELECT phone FROM users WHERE user_id = ?", (int(user_id),))
        row = cursor.fetchone()
        if row and row[0]:
            phone = row[0]
    if not phone:
        phone = "Ko'rsatilmagan"

    delivery_type = data.get("delivery_type", "Yetkazib berish")
    address = (data.get("address") or "").strip() or "Dorixonadan olib ketish"
    payment_method = data.get("payment_method", "Naqd pul")

    cart_items = data.get("cart", [])
    if isinstance(cart_items, list):
        for item in cart_items:
            pid = item.get("id")
            qty = int(item.get("qty", 1))
            if pid:
                cursor.execute("UPDATE products SET stock = MAX(0, stock - ?) WHERE id = ?", (qty, int(pid)))
        conn.commit()

    text = (
        f"🆕 <b>YANGI BUYURTMA!</b>\n\n"
        f"👤 Mijoz: <b>{data.get('name', 'Mijoz')}</b> (@{data.get('username', 'yoq')})\n"
        f"📞 Tel: <code>{phone}</code>\n"
        f"💳 To‘lov: <b>{payment_method}</b> (Karta: <code>{PAYMENT_CARD}</code>)\n"
        f"🚚 Usul: <b>{delivery_type}</b>\n"
        f"📍 Manzil: <i>{address}</i>\n"
        f"🆔 Karta ID: <code>{data.get('card', '—')}</code>\n\n"
        f"💊 <b>Mahsulotlar:</b>\n{data.get('items', '')}\n\n"
        f"💰 <b>Jami: {int(data.get('total', 0)):,} so'm</b>"
    )
    try:
        bot.send_message(ADMIN_ID, text, parse_mode="HTML")
        return jsonify({"ok": True, "payment_card": PAYMENT_CARD}), 200
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/")
def index():
    return "Vitora Bot Webhook is running 24/7!"

def setup_webhook():
    time.sleep(3)
    bot.remove_webhook()
    time.sleep(1)
    bot.set_webhook(url=f"{RENDER_URL}/webhook")

if __name__ == "__main__":
    threading.Thread(target=setup_webhook, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
