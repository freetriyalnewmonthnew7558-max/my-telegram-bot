# ============================================================
#  NUMBER PANEL BOT (V2.3 FINAL - Admin Delete Feature Added)
#  File: number_panel_v2_final.py
# ============================================================
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
import sqlite3, io, csv, os, sys
from datetime import datetime, timedelta

# ================= CONFIG (PLEASE CHECK THESE) =================
BOT_TOKEN = "8594708767:AAHR83LYAuEW1xKaDZjybbgPn2ln7C0FAI0"  # তোমার token
ADMIN_ID = 6580170122  # তোমার Telegram id
OTP_GROUP = "https://t.me/+1Zxobl56TBQyYTI1"
DB_FILE = "panel_v2.db"
# ===============================================================

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")
admin_flow = {}

# ========== DB helpers & init ==========
def db_connect():
    return sqlite3.connect(DB_FILE, timeout=30)

def init_db():
    conn = db_connect()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS countries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        dial TEXT,
        flag TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS numbers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        country_id INTEGER,
        phone TEXT,
        status TEXT DEFAULT 'available',
        meta TEXT,
        added_by INTEGER,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS assignments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        number_id INTEGER,
        user_id INTEGER,
        assigned_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.commit()
    conn.close()

init_db()

# ========== Utilities ==========
def get_countries():
    conn = db_connect(); c = conn.cursor()
    c.execute("""SELECT c.id, c.name, c.flag, c.dial,
                (SELECT COUNT(*) FROM numbers WHERE country_id=c.id AND status='available') as avail
                FROM countries c ORDER BY c.id""")
    rows = c.fetchall(); conn.close()
    return rows

def atomic_assign_number(country_id, user_id):
    conn = db_connect()
    c = conn.cursor()
    try:
        c.execute("BEGIN IMMEDIATE")
        c.execute("SELECT id, phone FROM numbers WHERE country_id=? AND status='available' LIMIT 1", (country_id,))
        row = c.fetchone()
        if not row:
            conn.commit(); conn.close(); return None
        number_id, phone = row
        c.execute("UPDATE numbers SET status='assigned' WHERE id=?", (number_id,))
        c.execute("INSERT INTO assignments (number_id, user_id) VALUES (?, ?)", (number_id, user_id))
        conn.commit()
        
        # FIX: Ensure '+' is prefixed for copyability (user requirement)
        if not phone.startswith('+'):
            phone = '+' + phone
            
        return {"id": number_id, "phone": phone}
    except Exception as e:
        conn.rollback(); print("assign err:", e); return None
    finally:
        conn.close()

def add_country_db(name, dial, flag):
    conn = db_connect(); c = conn.cursor()
    c.execute("INSERT INTO countries (name, dial, flag) VALUES (?, ?, ?)", (name, dial, flag))
    conn.commit(); cid = c.lastrowid; conn.close()
    return cid

def add_number_db(country_id, phone, meta, added_by):
    conn = db_connect(); c = conn.cursor()
    c.execute("INSERT INTO numbers (country_id, phone, meta, added_by) VALUES (?, ?, ?, ?)", (country_id, phone, meta, added_by))
    conn.commit(); nid = c.lastrowid; conn.close()
    return nid

def parse_numbers_from_bytes(content_bytes):
    # (Parsing function remains same, as it was robust)
    text = None
    try:
        text = content_bytes.decode('utf-8')
    except:
        try:
            text = content_bytes.decode('latin-1')
        except:
            text = content_bytes.decode('utf-8', errors='ignore')
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    results = []
    # detect csv (comma) vs pipe vs plain
    if lines and (',' in lines[0] and not '|' in lines[0]):
        reader = csv.reader(lines)
        for r in reader:
            if not r: continue
            num = r[0].strip()
            meta = r[1].strip() if len(r)>1 else ""
            results.append((num, meta))
    else:
        for ln in lines:
            if '|' in ln:
                parts = ln.split('|')
                num = parts[0].strip()
                meta = parts[1].strip() if len(parts)>1 else ""
                results.append((num, meta))
            elif ',' in ln:
                parts = ln.split(',',1)
                results.append((parts[0].strip(), parts[1].strip()))
            else:
                results.append((ln, ""))
    return results

# ========== Keyboards (MODIFIED) ==========

def build_user_reply_kb():
    """
    Creates the permanent ReplyKeyboardMarkup buttons (Get Number, Available Country, Support).
    """
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
    kb.add(KeyboardButton("📲 Get Number"))
    kb.add(KeyboardButton("🌍 Available Country"), KeyboardButton("💬 Support"))
    return kb

def build_countries_kb():
    kb = InlineKeyboardMarkup()
    for cid, name, flag, dial, avail in get_countries():
        # FIX: Ensure flag/dial are present but number is not shown with '+'
        label = f"{flag or ''} {name} {dial or ''} — {avail} available"
        kb.add(InlineKeyboardButton(label, callback_data=f"country_{cid}"))
    return kb

def build_countries_for_delete_kb():
    """
    NEW: Creates an InlineKeyboardMarkup for the admin to select and delete countries.
    """
    kb = InlineKeyboardMarkup()
    rows = get_countries()
    if not rows:
        kb.add(InlineKeyboardButton("No Countries Found", callback_data="admin_no_op"))
        kb.add(InlineKeyboardButton("↩️ Back to Admin Panel", callback_data="admin_cancel"))
        return kb

    for cid, name, flag, dial, avail in rows:
        label = f"❌ {flag or ''} {name} — {avail} available"
        # The callback data is set for deletion
        kb.add(InlineKeyboardButton(label, callback_data=f"delete_country_{cid}"))
    
    kb.add(InlineKeyboardButton("❌ Cancel", callback_data="admin_cancel"))
    return kb

def build_number_buttons(country_id, phone):
    """
    Only contains Change Number, Change Country, OTP Group.
    """
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("🔁 Change Number", callback_data=f"change_{country_id}"))
    kb.add(InlineKeyboardButton("🌐 Change Country", callback_data="show_countries"))
    kb.add(InlineKeyboardButton("🔔 OTP Group", url=OTP_GROUP))
    return kb

def build_admin_panel_kb():
    """
    FIX: Simplified Admin Panel buttons + New 'Available Countries (Delete)'.
    """
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("➕ Add Country", callback_data="admin_add_country"))
    # NEW FEATURE: Button to see/delete countries
    kb.add(InlineKeyboardButton("🌍 Available Countries (Delete)", callback_data="admin_show_countries_for_delete"))
    kb.add(InlineKeyboardButton("🧹 Clear Assigned", callback_data="admin_clear_assigned"))
    kb.add(InlineKeyboardButton("📁 Export DB", callback_data="admin_export_db"))
    kb.add(InlineKeyboardButton("♻️ Restart Bot", callback_data="admin_restart"))
    return kb

def build_upload_choice_kb(country_id):
    """
    This KB is shown only after 'Add Country' now.
    """
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("📂 Upload File", callback_data=f"upload_choice_file:{country_id}"))
    kb.add(InlineKeyboardButton("📝 Paste Text", callback_data=f"upload_choice_text:{country_id}"))
    kb.add(InlineKeyboardButton("❌ Cancel", callback_data="admin_cancel"))
    return kb

# ========== Handlers (MODIFIED) ==========

@bot.message_handler(commands=['start', 'help'])
def handle_start(msg):
    # FIX: Send permanent Reply Keyboard and check for countries immediately
    kb_reply = build_user_reply_kb()
    
    bot.send_message(msg.chat.id, "👋 Welcome! Select an option below:", reply_markup=kb_reply)

    handle_get_number(msg) # Immediately show countries list/message

@bot.message_handler(func=lambda m: m.text and m.text.strip() in ("📲 Get Number", "🌍 Available Country"))
def handle_get_number(msg):
    """
    FIX: Handles both Get Number and Available Country buttons by showing the countries list.
    """
    rows = get_countries()
    if not rows:
        # FIX: Show no country message
        bot.send_message(msg.chat.id, "⚠️ **No country added by admin.**\nPlease ask the admin to add numbers.")
        return
    
    kb = build_countries_kb()
    bot.send_message(msg.chat.id, "🌍 *Select your country:*")
    bot.send_message(msg.chat.id, "Click on the country button below to get an assigned number.", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text and m.text.strip() == "💬 Support")
def handle_support(msg):
    bot.send_message(msg.chat.id, f"🚨 For support, please contact the bot owner or visit the OTP Group: {OTP_GROUP}")

@bot.message_handler(func=lambda m: (m.text and m.text.strip().lower() == "/admin") or (m.text and m.text.strip().lower() == "admin"))
def handle_admin_cmd(m):
    uid = m.from_user.id
    if uid != ADMIN_ID:
        bot.reply_to(m, "⛔ You are not the admin.")
        return
    
    # Send Reply Keyboard for user convenience, but use Inline Keyboard for Admin actions
    kb_reply = build_user_reply_kb()
    bot.send_message(uid, "🛠️ Admin Panel access granted.", reply_markup=kb_reply)
    
    kb = build_admin_panel_kb()
    bot.send_message(uid, "--- *Admin Actions* ---", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: True)
def handle_callback(c):
    uid = c.from_user.id
    data = c.data

    # cancel
    if data == "admin_cancel":
        admin_flow.pop(uid, None)
        bot.answer_callback_query(c.id, "Cancelled.")
        # Reload admin panel after cancellation
        kb_admin = build_admin_panel_kb()
        try:
            bot.edit_message_text("❌ Cancelled. --- *Admin Actions* ---", chat_id=c.message.chat.id, message_id=c.message.message_id, reply_markup=kb_admin)
        except:
            pass
        return

    # show countries (FIX: Edit message instead of sending new one)
    if data == "show_countries":
        kb = build_countries_kb()
        try:
            bot.edit_message_text("🌍 *Select your country:*", chat_id=c.message.chat.id, message_id=c.message.message_id, reply_markup=kb)
        except Exception:
            # Fallback if the message is too old to edit
            bot.send_message(c.message.chat.id, "🌍 *Select your country:*", reply_markup=kb)
        return

    # NEW: Admin show countries for deletion
    if data == "admin_show_countries_for_delete":
        if uid != ADMIN_ID:
            bot.answer_callback_query(c.id, "⛔ Only admin.")
            return
        kb = build_countries_for_delete_kb()
        try:
            bot.edit_message_text("🌍 *Select a country to delete (This will delete ALL associated numbers too):*", 
                                  chat_id=c.message.chat.id, message_id=c.message.message_id, reply_markup=kb)
        except Exception:
            bot.send_message(c.message.chat.id, "🌍 *Select a country to delete (This will delete ALL associated numbers too):*", reply_markup=kb)
        bot.answer_callback_query(c.id, "Showing countries for deletion.")
        return

    # NEW: Admin delete country action
    if data.startswith("delete_country_"):
        if uid != ADMIN_ID:
            bot.answer_callback_query(c.id, "⛔ Only admin.")
            return
        
        try:
            cid = int(data.split("_", 2)[2])
        except ValueError:
            bot.answer_callback_query(c.id, "❌ Invalid country ID.")
            return

        conn = db_connect(); c2 = conn.cursor()
        
        # Get country name before deleting (for response)
        c2.execute("SELECT name FROM countries WHERE id=?", (cid,))
        country_name_row = c2.fetchone()
        
        # Delete numbers and country
        c2.execute("DELETE FROM assignments WHERE number_id IN (SELECT id FROM numbers WHERE country_id=?)", (cid,))
        c2.execute("DELETE FROM numbers WHERE country_id=?", (cid,))
        deleted_numbers = c2.rowcount
        c2.execute("DELETE FROM countries WHERE id=?", (cid,))
        conn.commit(); conn.close()
        
        country_name = country_name_row[0] if country_name_row else 'Unknown'
        msg_text = f"✅ Country *{country_name}* (ID={cid}) and **{deleted_numbers}** associated numbers have been permanently deleted."
        
        # Reload the deletion list
        kb = build_countries_for_delete_kb()
        try:
            bot.edit_message_text(f"{msg_text}\n\n🌍 *Remaining Countries (Select to delete or Cancel):*", 
                                  chat_id=c.message.chat.id, message_id=c.message.message_id, reply_markup=kb)
        except Exception:
            bot.send_message(c.message.chat.id, f"{msg_text}\n\n🌍 *Remaining Countries (Select to delete or Cancel):*", reply_markup=kb)
        bot.answer_callback_query(c.id, "Country deleted.")
        return


    # country select & assign
    if data.startswith("country_"):
        cid = int(data.split("_",1)[1])
        bot.answer_callback_query(c.id, "Assigning number...")
        res = atomic_assign_number(cid, uid)
        if not res:
            bot.answer_callback_query(c.id, "❌ Sorry, no available number for this country.")
            return
        phone = res["phone"] # This includes '+' prefix now
        kb = build_number_buttons(cid, phone)
        
        # Edit the country list message to show the assigned number
        try:
            bot.edit_message_text(f"📞 **Assigned Number:**\n`{phone}`\n\n_Wait for the OTP in the group._", 
                                  chat_id=c.message.chat.id, message_id=c.message.message_id, reply_markup=kb)
        except Exception:
             bot.send_message(c.message.chat.id, f"📞 **Assigned Number:**\n`{phone}`\n\n_Wait for the OTP in the group._", reply_markup=kb)
        return

    # change number
    if data.startswith("change_"):
        cid = int(data.split("_",1)[1])
        try:
            bot.edit_message_text("🔄 Changing number… Please wait.", chat_id=c.message.chat.id, message_id=c.message.message_id)
        except Exception:
            bot.send_message(c.message.chat.id, "🔄 Changing number…")
            
        res = atomic_assign_number(cid, uid)
        if not res:
            try:
                bot.edit_message_text("❌ Sorry, no more available numbers for this country.", chat_id=c.message.chat.id, message_id=c.message.message_id)
            except:
                bot.send_message(c.message.chat.id, "❌ Sorry, no more available numbers for this country.")
            return
        
        phone = res["phone"]
        kb = build_number_buttons(cid, phone)
        try:
            bot.edit_message_text(f"📞 **New Assigned Number:**\n`{phone}`\n\n_Wait for the OTP in the group._", 
                                  chat_id=c.message.chat.id, message_id=c.message.message_id, reply_markup=kb)
        except Exception:
            bot.send_message(c.message.chat.id, f"📞 **New Assigned Number:**\n`{phone}`\n\n_Wait for the OTP in the group._", reply_markup=kb)
        return

    # Admin callbacks (simplified actions)
    if data.startswith("admin_"):
        if uid != ADMIN_ID:
            bot.answer_callback_query(c.id, "⛔ Only admin.")
            return
        action = data.split("admin_")[1]
        bot.answer_callback_query(c.id, f"🛠️ Running {action}...")

        if action == "add_country":
            admin_flow[uid] = {"action":"await_country_info"}
            bot.send_message(uid, "➕ *Add Country*\nSend country as:\n`Country Name|+Code|🇫🇷`\n(Example: `Saudi Arabia|+966|🇸🇦`)\nSend `cancel` anytime to cancel.")
            return

        if action == "clear_assigned":
            conn = db_connect(); c2 = conn.cursor()
            c2.execute("UPDATE numbers SET status='available' WHERE status='assigned'")
            conn.commit(); conn.close()
            bot.send_message(uid, "✅ All assigned numbers restored to available.")
            return

        if action == "export_db":
            try:
                with open(DB_FILE, "rb") as f:
                    bot.send_document(uid, f, caption="Number Panel Database")
            except Exception as e:
                bot.send_message(uid, f"Error sending DB: {e}")
            return
            
        if action == "restart":
            bot.send_message(uid, "♻️ Restarting...")
            try:
                python = sys.executable
                os.execv(python, [python] + sys.argv)
            except Exception as e:
                bot.send_message(uid, f"Restart failed: {e}")
            return

    # Upload choice callbacks (only called after add_country flow is completed)
    if data.startswith("upload_choice_file:") or data.startswith("upload_choice_text:"):
        parts = data.split(":",1)
        action_key = parts[0]
        try:
            cid = int(parts[1])
        except:
            bot.answer_callback_query(c.id, "Invalid country info. Start again.")
            return
        if uid != ADMIN_ID:
            bot.answer_callback_query(c.id, "⛔ Only admin.")
            return
        if action_key == "upload_choice_file":
            admin_flow[uid] = {"action":"await_file_for_country", "country_id": cid}
            bot.answer_callback_query(c.id, "Upload mode selected.")
            # FIX: Clear message on upload/paste flow initiation
            bot.send_message(uid, f"📂 *Upload File*\n**Please send the file now.** (For country ID: {cid})")
        else:
            admin_flow[uid] = {"action":"await_text_for_country", "country_id": cid}
            bot.answer_callback_query(c.id, "Paste mode selected.")
            # FIX: Clear message on upload/paste flow initiation
            bot.send_message(uid, f"📝 *Paste Text*\n**Please paste the numbers now.** (For country ID: {cid})")
        return

    bot.answer_callback_query(c.id, "Unknown action.")

# ========== Message handlers ==========
@bot.message_handler(content_types=['text'])
def handle_text(msg):
    uid = msg.from_user.id
    text = msg.text.strip()

    # Admin Flow handling
    if uid == ADMIN_ID and uid in admin_flow:
        f = admin_flow[uid]
        act = f.get("action")

        # cancel support
        if text.lower() == "cancel":
            admin_flow.pop(uid, None)
            bot.reply_to(msg, "✅ Cancelled current admin operation.")
            return

        # await_country_info: expecting "Name|+Code|flag"
        if act == "await_country_info":
            try:
                name, dial, flag = [p.strip() for p in text.split("|",2)]
                cid = add_country_db(name, dial, flag)
                
                # Send upload choice buttons (with cid encoded)
                admin_flow.pop(uid, None) # Clear flow first
                admin_flow[uid] = {"action":"await_upload_choice", "country_id": cid}
                bot.send_message(uid, f"✅ Country added: {name} (ID={cid})\nChoose upload method:", reply_markup=build_upload_choice_kb(cid))
            except Exception:
                bot.send_message(uid, "❌ Invalid format. Use: Country Name|+Code|🇧🇩\nTry again or send 'cancel'.")
            return

        # await_text_for_country (admin pasted text)
        if act == "await_text_for_country":
            cid = f.get("country_id")
            content = text
            pairs = parse_numbers_from_bytes(content.encode('utf-8'))
            inserted = 0
            
            # Simplified insertion logic assuming country_id is known from flow (cid != 0)
            conn = db_connect(); c = conn.cursor()
            for number, meta in pairs:
                try:
                    c.execute("INSERT INTO numbers (country_id, phone, meta, added_by) VALUES (?, ?, ?, ?)", (cid, number, meta, uid))
                    inserted += 1
                except Exception:
                    pass
            conn.commit(); conn.close()
            
            # FIX: Send clear success message
            bot.send_message(uid, f"✅ Success! **{inserted}** numbers added to country ID {cid}.")
            admin_flow.pop(uid, None)
            return

    # Regular message handlers (if not in admin flow)
    if text.lower() in ("help", "/help"):
        handle_start(msg)
        return


# ========== Document handler for admin file upload ==========
@bot.message_handler(content_types=['document'])
def handle_document(msg):
    uid = msg.from_user.id
    if uid != ADMIN_ID:
        bot.reply_to(msg, "This bot only allows admin for batch uploads.")
        return
    f = admin_flow.get(uid)
    if not f or f.get("action") != "await_file_for_country":
        bot.reply_to(msg, "❌ Error: Not in file upload state. Start from Admin Panel → Add Country first.")
        return
    
    cid = f.get("country_id")
    try:
        file_info = bot.get_file(msg.document.file_id)
        file_bytes = bot.download_file(file_info.file_path)
    except Exception as e:
        bot.reply_to(msg, f"❌ File download failed: {e}")
        return
        
    pairs = parse_numbers_from_bytes(file_bytes)
    inserted = 0
    
    # Simplified insertion logic assuming country_id is known from flow (cid != 0)
    conn = db_connect(); c = conn.cursor()
    for number, meta in pairs:
        try:
            c.execute("INSERT INTO numbers (country_id, phone, meta, added_by) VALUES (?, ?, ?, ?)", (cid, number, meta, uid))
            inserted += 1
        except Exception:
            pass
    conn.commit(); conn.close()
    
    # FIX: Send clear success message
    bot.send_message(uid, f"✅ Success! **{inserted}** numbers added to country ID {cid}.")
    admin_flow.pop(uid, None)
    return

# ================= Start polling =================
if __name__ == "__main__":
    try:
        bot.set_my_commands([
            telebot.types.BotCommand("/start", "Start / Menu"),
            telebot.types.BotCommand("/admin", "Open admin panel (admin only)")
        ])
    except Exception:
        pass

    print("Bot started (v2.3 fully fixed).")
    bot.infinity_polling()
