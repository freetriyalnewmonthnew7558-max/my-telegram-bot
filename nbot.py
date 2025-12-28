# ============================================================
#  NUMBER PANEL BOT (V2.13 FINAL - ALL FIXES APPLIED)
# ============================================================
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
import sqlite3, io, csv, os, sys
from datetime import datetime, timedelta
# --- NEW IMPORTS for XLSX Handling ---
import pandas as pd
# --- END NEW IMPORTS ---

# *** BOT_TOKEN Configuration ***
BOT_TOKEN = "8594708767:AAHR83LYAuEW1xKaDZjybbgPn2ln7C0FAI0" 

# ================= CONFIG (PLEASE CHECK THESE) =================
ADMIN_ID = 6580170122
OTP_GROUP = "https://t.me/+1Zxobl56TBQyYTI1"
DB_FILE = "panel_v2.db"
# FIX: Use Zero-Width Space for stealthy loading of Reply Keyboard
INVISIBLE_MESSAGE = "\u200b" 
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
    # OPTIMIZATION: Added UNIQUE constraint to phone to prevent duplicates
    c.execute("""CREATE TABLE IF NOT EXISTS numbers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        country_id INTEGER,
        phone TEXT UNIQUE, 
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
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        first_name TEXT,
        username TEXT,
        last_activity TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.commit()
    conn.close()

def reset_all_data():
    conn = db_connect(); c = conn.cursor()
    try:
        c.execute("DELETE FROM assignments")
        c.execute("DELETE FROM numbers")
        c.execute("DELETE FROM countries")
        c.execute("DELETE FROM users")
        
        c.execute("DELETE FROM sqlite_sequence WHERE name='countries'")
        c.execute("DELETE FROM sqlite_sequence WHERE name='numbers'")
        c.execute("DELETE FROM sqlite_sequence WHERE name='users'")

        conn.commit()
        return True
    except Exception as e:
        print(f"Error resetting data: {e}")
        return False
    finally:
        conn.close()

init_db()

# ========== Core Utilities ==========

def register_user(user):
    conn = db_connect(); c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users (user_id, first_name, username, last_activity) VALUES (?, ?, ?, CURRENT_TIMESTAMP)", 
              (user.id, user.first_name, user.username, ))
    conn.commit(); conn.close()

def get_countries():
    conn = db_connect(); c = conn.cursor()
    c.execute("""SELECT c.id, c.name, c.flag, c.dial,
                (SELECT COUNT(*) FROM numbers WHERE country_id=c.id AND status='available') as avail
                FROM countries c ORDER BY c.id""")
    rows = c.fetchall(); conn.close()
    return rows

def get_country_details(country_id):
    conn = db_connect(); c = conn.cursor()
    c.execute("SELECT name, flag FROM countries WHERE id=?", (country_id,))
    row = c.fetchone()
    conn.close()
    return row

def atomic_assign_number(country_id, user_id):
    conn = db_connect()
    c = conn.cursor()
    try:
        c.execute("BEGIN IMMEDIATE")
        
        c.execute("""SELECT id, phone, meta 
                     FROM numbers 
                     WHERE country_id=? AND status='available' 
                     ORDER BY RANDOM() 
                     LIMIT 1""", (country_id,))
                     
        row = c.fetchone()
        
        if not row:
            conn.commit(); conn.close(); return None
            
        number_id, phone, meta = row
        
        c.execute("UPDATE numbers SET status='assigned' WHERE id=?", (number_id,))
        c.execute("INSERT INTO assignments (number_id, user_id) VALUES (?, ?)", (number_id, user_id))
        
        conn.commit()
        
        if not phone.startswith('+'):
            phone = '+' + phone
            
        return {"id": number_id, "phone": phone, "meta": meta}
    except Exception as e:
        conn.rollback(); print("assign err:", e); return None
    finally:
        conn.close()

def add_country_db(name, dial, flag):
    conn = db_connect(); c = conn.cursor()
    c.execute("INSERT INTO countries (name, dial, flag) VALUES (?, ?, ?)", (name, dial, flag))
    conn.commit(); cid = c.lastrowid; conn.close()
    return cid

# --- MODIFIED: Handles TXT/CSV and XLSX (Reads column D as number, column E as meta) ---
def parse_numbers_from_bytes(content_bytes, file_type='txt'):
    results = []

    if file_type == 'xlsx':
        try:
            df = pd.read_excel(io.BytesIO(content_bytes), engine='openpyxl')
            
            # Column D (Index 3) for the phone number
            phone_col_index = 3 
            # Column E (Index 4) for meta data (Monthly price, etc.)
            meta_col_index = 4

            if phone_col_index < len(df.columns):
                phone_column_data = df.iloc[:, phone_col_index]

                for index, value in phone_column_data.items():
                    if pd.isna(value):
                        continue

                    num_raw = str(value).strip()
                    meta = ""
                    
                    if meta_col_index < len(df.columns):
                        meta_raw = str(df.iloc[index, meta_col_index]).strip()
                        if meta_raw.lower() not in ('', 'nan', 'none'):
                             meta = meta_raw

                    # Basic number extraction and validation (Keeps only digits)
                    num_part = ''.join(filter(str.isdigit, num_raw))
                    
                    if len(num_part) >= 5: 
                        final_num = num_part.replace('+', '').strip()
                        results.append((final_num, meta.strip()))
                        
            return results
            
        except Exception as e:
            print(f"Error parsing XLSX: {e}")
            return []

    # --- Original TXT/CSV Parsing Logic ---
    else: 
        text = None
        try:
            text = content_bytes.decode('utf-8')
        except:
            text = content_bytes.decode('utf-8', errors='ignore')
            
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        
        for ln in lines:
            num = None
            meta = ""
            ln_cleaned = ln.replace('"', '').strip()

            if '|' in ln_cleaned:
                parts = ln_cleaned.split('|')
                num = parts[0].strip()
                meta = parts[1].strip() if len(parts) > 1 else ""
            elif ',' in ln_cleaned:
                parts = ln_cleaned.split(',', 1)
                num = parts[0].strip()
                meta = parts[1].strip() if len(parts) > 1 else ""
            else:
                num = ln_cleaned
                
            if num:
                num_part = ''.join(filter(str.isdigit, num))
                non_digit_ratio = (len(num) - len(num_part)) / max(1, len(num))
                
                if len(num_part) >= 5 and non_digit_ratio < 0.5:
                    final_num = num_part.replace('+', '').strip() 
                    results.append((final_num, meta.strip()))
                    
        return results

def send_message_to_all_users(message, admin_id):
    conn = db_connect(); c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE user_id != ?", (admin_id,))
    users = [row[0] for row in c.fetchall()]
    conn.close()
    
    sent_count = 0
    total_users = len(users)
    
    for user_id in users:
        try:
            bot.send_message(user_id, message)
            sent_count += 1
        except telebot.apihelper.ApiTelegramException as e:
            if 'bot was blocked by the user' in str(e) or 'user is deactivated' in str(e):
                pass
            else:
                print(f"Error sending message to {user_id}: {e}")
        except Exception as e:
            print(f"General error sending message to {user_id}: {e}")
    
    return sent_count, total_users

# ========== Keyboards ==========

def build_user_reply_kb():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
    kb.add(KeyboardButton("📲 Get Number"))
    kb.add(KeyboardButton("🌍 Available Country"), KeyboardButton("💬 Support"))
    return kb

def build_countries_kb(prefix="country"):
    kb = InlineKeyboardMarkup()
    for cid, name, flag, dial, avail in get_countries():
        label = f"{flag or ''} {name} {dial or ''} — {avail} available"
        kb.add(InlineKeyboardButton(label, callback_data=f"{prefix}_{cid}"))
    return kb

def build_countries_for_delete_kb():
    kb = InlineKeyboardMarkup()
    rows = get_countries()
    if not rows:
        kb.add(InlineKeyboardButton("No Countries Found", callback_data="admin_no_op"))
        kb.add(InlineKeyboardButton("↩️ Back to Admin Panel", callback_data="admin_cmd"))
        return kb

    for cid, name, flag, dial, avail in rows:
        label = f"❌ {flag or ''} {name} — {avail} available (ID:{cid})"
        kb.add(InlineKeyboardButton(label, callback_data=f"delete_country_{cid}"))
    
    kb.add(InlineKeyboardButton("❌ Cancel", callback_data="admin_cmd"))
    return kb

def build_number_buttons(country_id):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("🌍 Change Country", callback_data="show_countries"),
           InlineKeyboardButton("📩 View OTP", url=OTP_GROUP))
    kb.add(InlineKeyboardButton("🔄 Change Number", callback_data=f"change_{country_id}"))
    return kb

def build_admin_panel_kb():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("➕ Add New Country", callback_data="admin_add_country"))
    kb.add(InlineKeyboardButton("➕ Add Numbers to Existing", callback_data="admin_show_countries_for_add")) 
    kb.add(InlineKeyboardButton("🌍 Available Countries (Delete)", callback_data="admin_show_countries_for_delete"))
    kb.add(InlineKeyboardButton("📣 Send Announcement", callback_data="admin_custom_announce"))
    kb.add(InlineKeyboardButton("🧹 Clear Assigned", callback_data="admin_clear_assigned"))
    kb.add(InlineKeyboardButton("💣 Clear All Data & Reset", callback_data="admin_reset_all_data")) 
    kb.add(InlineKeyboardButton("📁 Export DB", callback_data="admin_export_db"))
    kb.add(InlineKeyboardButton("♻️ Restart Bot", callback_data="admin_restart"))
    return kb

def build_upload_choice_kb(country_id):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("📂 Upload File (TXT/CSV/XLSX)", callback_data=f"upload_choice_file:{country_id}"))
    kb.add(InlineKeyboardButton("📝 Paste Text", callback_data=f"upload_choice_text:{country_id}"))
    kb.add(InlineKeyboardButton("❌ Cancel", callback_data="admin_cancel"))
    return kb

def build_announcement_choice_kb(cid, inserted):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("✅ Send Auto Announce", callback_data=f"announce_auto:{cid}:{inserted}"))
    kb.add(InlineKeyboardButton("📝 Send Custom Msg", callback_data=f"announce_custom:{cid}:{inserted}"))
    kb.add(InlineKeyboardButton("❌ Don't Announce", callback_data="admin_cancel"))
    return kb

# ========== Handlers ==========

@bot.message_handler(commands=['start', 'help'])
def handle_start(msg):
    register_user(msg.from_user)
    kb_reply = build_user_reply_kb()
    
    first_name = msg.from_user.first_name if msg.from_user.first_name else 'User'
    
    welcome_message = (
        f"👋 Welcome {first_name}!\n\n"
        f"🌟 This bot provides virtual phone numbers for verification.\n\n"
        f"Available features:\n"
        f"📱Get Number - Get a virtual number\n"
        f"💬 Support 24 Hours For You\n"
        f"🌍 Available Country - See available countries"
    )

    try:
        bot.send_message(msg.chat.id, welcome_message, reply_markup=kb_reply)
    except Exception as e:
        print(f"Error sending welcome message with Reply KB: {e}")
            

@bot.message_handler(func=lambda m: m.text and m.text.strip() in ("📲 Get Number", "🌍 Available Country"))
def handle_get_number(msg):
    register_user(msg.from_user)
    rows = get_countries()
    if not rows:
        bot.send_message(msg.chat.id, "⚠️ **No country added by admin.**\nPlease ask the admin to add numbers.")
        return
    
    kb = build_countries_kb()
    bot.send_message(msg.chat.id, "🌍 *Select your country:*", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text and m.text.strip() == "💬 Support")
def handle_support(msg):
    bot.send_message(msg.chat.id, f"🚨 For support, please contact the bot owner or visit the OTP Group: {OTP_GROUP}")

@bot.message_handler(func=lambda m: (m.text and m.text.strip().lower() == "/admin") or (m.text and m.text.strip().lower() == "admin"))
def handle_admin_cmd(m):
    uid = m.from_user.id
    if uid != ADMIN_ID:
        bot.reply_to(m, "⛔ You are not the admin.")
        return
    
    kb_reply = build_user_reply_kb()
    bot.send_message(uid, "🛠️ Admin Panel access granted.", reply_markup=kb_reply)
    
    kb = build_admin_panel_kb()
    bot.send_message(uid, "--- *Admin Actions* ---", reply_markup=kb)

# --- MODIFIED: Removed meta from display text ---
def assigned_number_text(country_flag, country_name, meta, phone):
    # meta is stored in DB but not displayed to the user
    meta_display = "" 
    return (
        f"{country_flag} **{country_name}{meta_display} Number Assigned:**\n"
        f"`{phone}`\n\n" 
        f"Wait for the OTP in the group..."
    )
# --------------------------------------------------

@bot.callback_query_handler(func=lambda c: True)
def handle_callback(c):
    uid = c.from_user.id
    data = c.data

    # --- Cancel / Reload Admin Panel ---
    if data == "admin_cancel" or data == "admin_cmd":
        admin_flow.pop(uid, None)
        bot.answer_callback_query(c.id, "Cancelled.")
        kb_admin = build_admin_panel_kb()
        try:
            bot.edit_message_text("❌ Action Cancelled. --- *Admin Actions* ---", chat_id=c.message.chat.id, message_id=c.message.message_id, reply_markup=kb_admin)
        except:
            bot.send_message(uid, "--- *Admin Actions* ---", reply_markup=kb_admin)
        return
    
    # --- Country Select & Assign (User Action) ---
    if data.startswith("country_"):
        cid = int(data.split("_",1)[1])
        bot.answer_callback_query(c.id, "Assigning number... Please wait.") 
        
        try:
            bot.edit_message_text("⌛ Assigning number... Please wait.", chat_id=c.message.chat.id, message_id=c.message.message_id)
        except Exception:
            pass 
            
        res = atomic_assign_number(cid, uid)
        if not res:
            try:
                bot.edit_message_text("❌ Sorry, no available number for this country.", chat_id=c.message.chat.id, message_id=c.message.message_id)
            except:
                bot.send_message(c.message.chat.id, "❌ Sorry, no available number for this country.")
            return
            
        phone = res["phone"]
        meta = res["meta"]
        country_name, country_flag = get_country_details(cid)
        
        kb = build_number_buttons(cid) 
        text = assigned_number_text(country_flag, country_name, meta, phone)
        
        try:
            bot.edit_message_text(text, chat_id=c.message.chat.id, message_id=c.message.message_id, reply_markup=kb)
        except Exception:
             bot.send_message(c.message.chat.id, text, reply_markup=kb)
        return

    # --- Change Number (User Action) ---
    if data.startswith("change_"):
        cid = int(data.split("_",1)[1])
        bot.answer_callback_query(c.id, "🔄 Changing number… Please wait.")
        
        try:
            bot.edit_message_text("🔄 Changing number… Please wait.", chat_id=c.message.chat.id, message_id=c.message.message_id)
        except Exception:
            pass 
            
        res = atomic_assign_number(cid, uid)
        if not res:
            try:
                bot.edit_message_text("❌ Sorry, no more available numbers for this country.", chat_id=c.message.chat.id, message_id=c.message.message_id)
            except:
                bot.send_message(c.message.chat.id, "❌ Sorry, no more available numbers for this country.")
            return
        
        phone = res["phone"]
        meta = res["meta"]
        country_name, country_flag = get_country_details(cid)
        
        kb = build_number_buttons(cid) 
        text = assigned_number_text(country_flag, country_name, meta, phone)
        
        try:
            bot.edit_message_text(text, chat_id=c.message.chat.id, message_id=c.message.message_id, reply_markup=kb)
        except Exception:
            bot.send_message(c.message.chat.id, text, reply_markup=kb)
        return

    if data == "show_countries":
        kb = build_countries_kb()
        try:
            bot.edit_message_text("🌍 *Select your country:*", chat_id=c.message.chat.id, message_id=c.message.message_id, reply_markup=kb)
        except Exception:
            bot.send_message(c.message.chat.id, "🌍 *Select your country:*", reply_markup=kb)
        return

    # --- Admin Callbacks (Unchanged logic) ---
    if data.startswith("admin_") and uid == ADMIN_ID:
        action = data.split("admin_")[1]
        bot.answer_callback_query(c.id, f"🛠️ Running {action}...")

        if action == "add_country":
            admin_flow[uid] = {"action":"await_country_info"}
            bot.send_message(uid, "➕ *Add New Country*\nSend country as:\n`Country Name|Dial Code|🇫🇷`\n(Example: `Saudi Arabia|+966|🇸🇦`)\nSend `cancel` anytime to cancel.")
            return
        
        if action == "show_countries_for_add":
            kb = build_countries_kb(prefix="add_to_country")
            try:
                bot.edit_message_text("➕ *Select a country to add more numbers to:*", 
                                  chat_id=c.message.chat.id, message_id=c.message.message_id, reply_markup=kb)
            except Exception:
                bot.send_message(c.message.chat.id, "➕ *Select a country to add more numbers to:*", reply_markup=kb)
            return

        if action == "show_countries_for_delete":
            kb = build_countries_for_delete_kb()
            try:
                bot.edit_message_text("🌍 *Select a country to delete (This will delete ALL associated numbers too):*", 
                                      chat_id=c.message.chat.id, message_id=c.message.message_id, reply_markup=kb)
            except Exception:
                bot.send_message(c.message.chat.id, "🌍 *Select a country to delete (This will delete ALL associated numbers too):*", reply_markup=kb)
            bot.answer_callback_query(c.id, "Showing countries for deletion.")
            return

        # Custom Announcement Start
        if action == "custom_announce":
            admin_flow[uid] = {"action":"await_custom_announcement_text"}
            bot.send_message(uid, "📣 *Send Custom Announcement*\nPlease send the message you want to broadcast to all users.\nSend `cancel` to stop.")
            return
        
        if action == "reset_all_data":
            success = reset_all_data()
            if success:
                msg_text = "💣 **SUCCESS!** All user data, numbers, countries, and database counters have been permanently wiped and reset to 0."
            else:
                msg_text = "❌ **ERROR!** Could not reset database. Check logs."
            
            kb = build_admin_panel_kb()
            try:
                bot.edit_message_text(msg_text + "\n\n--- *Admin Actions* ---", chat_id=c.message.chat.id, message_id=c.message.message_id, reply_markup=kb)
            except:
                bot.send_message(uid, msg_text, reply_markup=kb)
            return
        
        if action == "clear_assigned":
            conn = db_connect(); c2 = conn.cursor()
            try:
                c2.execute("UPDATE numbers SET status='available' WHERE status='assigned'")
                updated_count = c2.rowcount
                c2.execute("DELETE FROM assignments")
                conn.commit()
                msg_text = f"✅ **SUCCESS!** **{updated_count}** assigned numbers have been cleared and set back to 'available'. All assignments records deleted."
            except Exception as e:
                conn.rollback()
                msg_text = f"❌ **ERROR!** Could not clear assigned numbers: {e}"
            finally:
                conn.close()

            kb = build_admin_panel_kb()
            try:
                bot.edit_message_text(msg_text + "\n\n--- *Admin Actions* ---", chat_id=c.message.chat.id, message_id=c.message.message_id, reply_markup=kb)
            except:
                bot.send_message(uid, msg_text, reply_markup=kb)
            return

        if action == "export_db":
            try:
                with open(DB_FILE, 'rb') as f:
                    bot.send_document(uid, f, caption="📁 Database Export")
                kb = build_admin_panel_kb()
                bot.edit_message_text("✅ Database file sent.\n\n--- *Admin Actions* ---", chat_id=c.message.chat.id, message_id=c.message.message_id, reply_markup=kb)
            except Exception as e:
                bot.send_message(uid, f"❌ Error exporting DB: {e}")
            return
        
        if action == "restart":
            kb = build_admin_panel_kb()
            try:
                bot.edit_message_text("♻️ Bot is restarting... (May take a moment)", chat_id=c.message.chat.id, message_id=c.message.message_id, reply_markup=kb)
            except:
                bot.send_message(uid, "♻️ Bot is restarting... (May take a moment)", reply_markup=kb)

            bot.stop_polling()
            os.execv(sys.executable, ['python'] + sys.argv)
            return

    if data.startswith("delete_country_") and uid == ADMIN_ID:
        try:
            cid = int(data.split("_", 2)[2])
        except ValueError:
            bot.answer_callback_query(c.id, "❌ Invalid country ID.")
            return

        bot.answer_callback_query(c.id, "Deleting country and numbers...")

        conn = db_connect(); c2 = conn.cursor()
        
        c2.execute("SELECT name FROM countries WHERE id=?", (cid,))
        country_name_row = c2.fetchone()
        
        try:
            c2.execute("DELETE FROM assignments WHERE number_id IN (SELECT id FROM numbers WHERE country_id=?)", (cid,))
            c2.execute("DELETE FROM numbers WHERE country_id=?", (cid,))
            deleted_numbers = c2.rowcount
            c2.execute("DELETE FROM countries WHERE id=?", (cid,))
            conn.commit()
            
            country_name = country_name_row[0] if country_name_row else 'Unknown'
            msg_text = f"✅ Country *{country_name}* (ID={cid}) and **{deleted_numbers}** associated numbers have been permanently deleted."
            
            kb = build_countries_for_delete_kb()
            try:
                bot.edit_message_text(f"{msg_text}\n\n🌍 *Remaining Countries (Select to delete or Cancel):*", 
                                      chat_id=c.message.chat.id, message_id=c.message.message_id, reply_markup=kb)
            except Exception:
                bot.send_message(c.message.chat.id, f"{msg_text}\n\n🌍 *Remaining Countries (Select to delete or Cancel):*", reply_markup=kb)
                
        except Exception as e:
            conn.rollback()
            bot.send_message(uid, f"❌ Database Error during deletion: {e}")
            
        finally:
            conn.close()
        return

    # Select existing country for number addition
    if data.startswith("add_to_country_") and uid == ADMIN_ID:
        try:
            cid = int(data.split("_")[-1]) 
        except ValueError:
            bot.answer_callback_query(c.id, "❌ Invalid country ID.")
            return
            
        admin_flow[uid] = {"action":"await_upload_choice", "country_id": cid}
        bot.answer_callback_query(c.id, "Country selected. Choose upload method.")
        
        country_name, country_flag = get_country_details(cid)
        kb = build_upload_choice_kb(cid)
        bot.send_message(uid, f"➕ *Add Numbers to {country_flag} {country_name} (ID: {cid})*\nChoose upload method:", reply_markup=kb)
        return

    # --- Upload Choice Handlers (Unchanged logic) ---
    if data.startswith("upload_choice_file:") or data.startswith("upload_choice_text:") and uid == ADMIN_ID:
        parts = data.split(":",1)
        action_key = parts[0]
        try:
            cid = int(parts[1])
        except:
            bot.answer_callback_query(c.id, "Invalid country info. Start again.")
            return
        if action_key == "upload_choice_file":
            admin_flow[uid] = {"action":"await_file_for_country", "country_id": cid}
            bot.answer_callback_query(c.id, "Upload mode selected.")
            # Updated file type instruction
            bot.send_message(uid, f"📂 *Upload File*\n**Please send a TXT, CSV, or XLSX file now.** (For country ID: {cid})")
        else:
            admin_flow[uid] = {"action":"await_text_for_country", "country_id": cid}
            bot.answer_callback_query(c.id, "Paste mode selected.")
            bot.send_message(uid, f"📝 *Paste Text*\n**Please paste the numbers now.** (For country ID: {cid})")
        return


    # --- Announcement Choices (Unchanged logic) ---
    if data.startswith("announce_auto:") and uid == ADMIN_ID:
        try:
            parts = data.split(":")
            cid = int(parts[1]); inserted = int(parts[2])
            country_name, country_flag = get_country_details(cid)
            
            message = (
                f"📣 **New Numbers Added!** 🚀\n\n"
                f"We've just added **{inserted}** new numbers for {country_flag} **{country_name}**!\n"
                f"Tap '📲 Get Number' to receive one.\n"
                f"Happy verification! 😊"
            )
            sent_count, total_users = send_message_to_all_users(message, uid)
            
            bot.answer_callback_query(c.id, f"✅ Auto Announce sent to {sent_count}/{total_users} users.")
            bot.edit_message_text(f"✅ Auto Announcement sent to **{sent_count}** out of **{total_users}** users.", chat_id=c.message.chat.id, message_id=c.message.message_id)
            admin_flow.pop(uid, None)
        except Exception as e:
            bot.send_message(uid, f"❌ Error during auto announcement: {e}")
        return

    if data.startswith("announce_custom:") and uid == ADMIN_ID:
        try:
            parts = data.split(":")
            cid = int(parts[1]); inserted = int(parts[2])
            admin_flow[uid] = {"action": "await_custom_announcement_after_add", "country_id": cid, "inserted_count": inserted}
            
            bot.answer_callback_query(c.id, "Custom message mode selected.")
            bot.edit_message_text(f"📝 *Send Custom Message*\nNumbers added: **{inserted}**.\n\n**Now, please type the message** you want to send to all users:", 
                                  chat_id=c.message.chat.id, message_id=c.message.message_id)
        except:
             bot.answer_callback_query(c.id, "Error in flow.")
        return

    bot.answer_callback_query(c.id, "Unknown action.")


@bot.message_handler(content_types=['text'])
def handle_text(msg):
    uid = msg.from_user.id
    text = msg.text.strip()
    register_user(msg.from_user)

    # Admin Flow handling
    if uid == ADMIN_ID and uid in admin_flow:
        f = admin_flow[uid]
        act = f.get("action")

        if text.lower() == "cancel":
            admin_flow.pop(uid, None)
            bot.reply_to(msg, "✅ Cancelled current admin operation.")
            return

        if act == "await_country_info":
            try:
                name, dial, flag = [p.strip() for p in text.split("|",2)]
                cid = add_country_db(name, dial, flag)
                
                admin_flow.pop(uid, None)
                admin_flow[uid] = {"action":"await_upload_choice", "country_id": cid}
                bot.send_message(uid, f"✅ Country added: {flag} {name} (ID={cid})\nChoose upload method:", reply_markup=build_upload_choice_kb(cid))
            except ValueError:
                bot.send_message(uid, "❌ Invalid format. Expected: `Country Name|Dial Code|Flag`\n(e.g., `Saudi Arabia|+966|🇸🇦`). Please try again or send `cancel`.")
            except Exception as e:
                bot.send_message(uid, f"❌ An unexpected error occurred: {e}")
            return

        if act == "await_text_for_country":
            cid = f.get("country_id")
            content = text.encode('utf-8')
            # Changed parse_numbers_from_bytes call to use file_type='txt' for consistency
            pairs = parse_numbers_from_bytes(content, file_type='txt')
            inserted = 0
            
            conn = db_connect(); c = conn.cursor()
            for number, meta in pairs:
                try:
                    # Use INSERT OR IGNORE to handle UNIQUE constraint (duplicates) quietly
                    c.execute("INSERT OR IGNORE INTO numbers (country_id, phone, meta, added_by) VALUES (?, ?, ?, ?)", (cid, number, meta, uid))
                    # Check if a row was actually inserted (not just ignored)
                    if c.rowcount > 0:
                        inserted += 1
                except Exception as e:
                    # Catch other potential database errors
                    print(f"DB Error inserting text number {number}: {e}")
                    pass
            conn.commit(); conn.close()
            
            if inserted > 0:
                kb = build_announcement_choice_kb(cid, inserted)
                bot.send_message(uid, f"✅ Success! **{inserted}** unique numbers added to country ID {cid}.\n\n*Would you like to send an announcement?*", reply_markup=kb)
            else:
                bot.send_message(uid, f"⚠️ **0** unique numbers added to country ID {cid}. Please check your format or if all numbers were duplicates.")
                admin_flow.pop(uid, None)
            return

        # Admin Custom Announcement Handlers
        if act == "await_custom_announcement_text":
            sent_count, total_users = send_message_to_all_users(text, uid)
            bot.send_message(uid, f"✅ Custom announcement sent to **{sent_count}** out of **{total_users}** users.")
            admin_flow.pop(uid, None)
            return
            
        if act == "await_custom_announcement_after_add":
            sent_count, total_users = send_message_to_all_users(text, uid)
            inserted = f.get("inserted_count")
            bot.send_message(uid, f"✅ **{inserted}** numbers added. Custom announcement sent to **{sent_count}** out of **{total_users}** users.")
            admin_flow.pop(uid, None)
            return
        
    # Regular message handlers
    if text.lower() in ("help", "/help"):
        handle_start(msg)
        return
    
    if text.strip() == "💬 Support":
        handle_support(msg)
    elif text.strip() in ("📲 Get Number", "🌍 Available Country"):
        handle_get_number(msg)
    # If a random text is sent (not a menu button or admin command), show countries
    else:
        # Prevent showing countries if user is in an active admin flow
        if uid != ADMIN_ID or uid not in admin_flow:
            handle_get_number(msg)


# ========== Document handler for admin file upload (MODIFIED) ==========
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
    
    # Determine file type based on MIME or extension
    mime_type = msg.document.mime_type
    file_type = 'txt'
    
    # Check for Excel file types
    if 'excel' in mime_type or 'spreadsheet' in mime_type or msg.document.file_name.lower().endswith(('.xlsx', '.xls')):
        file_type = 'xlsx'
        
    try:
        bot.reply_to(msg, f"Processing file (Type: **{file_type}**)... Please wait.")
        file_info = bot.get_file(msg.document.file_id)
        file_bytes = bot.download_file(file_info.file_path)
    except Exception as e:
        bot.reply_to(msg, f"❌ File download failed: {e}")
        return
        
    # Pass the determined file type to the parsing function
    pairs = parse_numbers_from_bytes(file_bytes, file_type)
    inserted = 0
    
    conn = db_connect(); c = conn.cursor()
    for number, meta in pairs:
        try:
            # Use INSERT OR IGNORE to handle UNIQUE constraint (duplicates) quietly
            c.execute("INSERT OR IGNORE INTO numbers (country_id, phone, meta, added_by) VALUES (?, ?, ?, ?)", (cid, number, meta, uid))
            # Check if a row was actually inserted (not just ignored)
            if c.rowcount > 0:
                inserted += 1
        except Exception as e:
            # Catch other potential database errors
            print(f"DB Error inserting file number {number}: {e}")
            pass
    conn.commit(); conn.close()
    
    if inserted > 0:
        kb = build_announcement_choice_kb(cid, inserted)
        bot.send_message(uid, f"✅ Success! **{inserted}** unique numbers added to country ID {cid}.\n\n*Would you like to send an announcement?*", reply_markup=kb)
    else:
        bot.send_message(uid, f"⚠️ **0** unique numbers added to country ID {cid}. Please check your file format or if all numbers were duplicates.")
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

    print("Bot started (v2.13 Final - ALL FIXES APPLIED).")
    bot.infinity_polling(timeout=20, long_polling_timeout=10)
