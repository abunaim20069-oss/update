import json, re, sys
import telebot
from datetime import datetime
from telebot.types import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton, ForceReply
import time # For timestamp in orders

try:
    from telebot.apihelper import ApiTelegramException
except Exception:
    ApiTelegramException = Exception

# ========== CONFIG ==========
BOT_TOKEN = "7989043300:AAECZAXZ9ycCSBhfYujXQx5CyVW03bh0AUs" # আপনার বট টোকেন
ADMIN_ID  = 5830499612  # আপনার অ্যাডমিন টেলিগ্রাম ইউজার আইডি
DATA_FILE = "bot_data.json"

BOT_ID = int(BOT_TOKEN.split(":")[0]) # <--- এটিই সঠিক লাইন

# --- Define the file_id for your general welcome image here ---
WELCOME_PHOTO_FILE_ID = "AgACAgUAAxkBAANeaN16I-UxernNmUXW0ez9QUwQa78AAkXEMRvSaPFW29cLmQ1jtvIBAAMCAAN5AAM2BA" # Example file_id, replace with yours!

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

# ========== DATA ==========
def load_data():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {}
    data.setdefault("products", {}) # { "VPN_Name": [{"gmail": "...", "password": "..."}] }
    data.setdefault("balances", {})
    data.setdefault("pending_payments", {})
    data.setdefault("unmatched_payments", {})
    data.setdefault("orders", {})
    data.setdefault("total_sales", 0.0)
    data.setdefault("processed_transactions", [])
    return data

def save_data(d):
    d["processed_transactions"] = sorted(processed_transactions)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

data               = load_data()
products           = data["products"]
balances           = data["balances"]
pending_payments   = data["pending_payments"]
unmatched_payments = data["unmatched_payments"]
orders             = data["orders"]
total_sales        = data["total_sales"]
processed_transactions = set(trx.lower() for trx in data.get("processed_transactions", []))

# Keeps track of ongoing admin actions that require follow-up input.
admin_sessions = {}
user_sessions = {}

# Updated vpn_prices structure based on your provided list
vpn_prices = {
    "Express VPN": {"price": 30, "days": 7},
    "Nord VPN": {"price": 40, "days": 7},
    "PIA VPN": {"price": 30, "days": 7},
    "Surfshark": {"price": 30, "days": 7},
    "HotspotShield VPN": {"price": 30, "days": 7},
    "HMA VPN": {"price": 30, "days": 7},
    "IPVanish VPN": {"price": 30, "days": 7},
    "Cyberghost VPN": {"price": 15, "days": 3}, # Changed to 3 Days
    "Vypr VPN": {"price": 15, "days": 3},    # Changed to 3 Days
    "X VPN": {"price": 30, "days": 7},
    "Pure VPN": {"price": 30, "days": 7},
    "Panda VPN": {"price": 15, "days": 3},   # Changed to 3 Days
    "Turbo VPN": {"price": 30, "days": 7},
    "Sky VPN": {"price": 30, "days": 7},
    "Potato VPN": {"price": 30, "days": 7},
    "Zoog VPN": {"price": 15, "days": 3},    # Changed to 3 Days
    "Bitdefender VPN": {"price": 30, "days": 7}
}

# --- NEW: Define expected fields for each VPN type ---
# Keys are the exact keys from vpn_prices.
# Values are lists of required fields in the order they should appear in the input/output.
DEFAULT_PRODUCT_FIELDS = ["Gmail", "Password"]
MAX_PURCHASE_QUANTITY = 5

product_fields = {
    "Express VPN": ["Gmail", "Password", "PC Key"],
    "HMA VPN": ["Activation Key"], # HMA will only have an activation key
    # Default for others (if not specified here, it falls back to DEFAULT_PRODUCT_FIELDS)
}
# --- END NEW ---

# Payment gateway number (updated to your specified number)
PAYMENT_NUMBER = "01739089344" 
SUPPORT_CONTACT = "@Abdurrahman0999"

# Helper functions
def main_menu_markup():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("🛍️ Buy Products", "💳 Add Balance")
    kb.row("📦 My Orders", "💰 My Balance")
    return kb

def admin_menu_markup():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("📊 Total Sales", "📈 Current Stock")
    kb.row("🧾 Pending Payments", "👥 User Lookup")
    kb.row("➕ Add VPN Account", "⬅️ Main Menu (User)")
    return kb

def norm_text(s): return " ".join(s.strip().split()).lower() if isinstance(s, str) else ""
def ensure_user(uid): balances.setdefault(uid, 0.0); orders.setdefault(uid, [])


def support_footer():
    return f"\n\n📞 Support: {SUPPORT_CONTACT}"


def build_quantity_keyboard(vpn_name, max_qty, selected_qty=None, include_confirm=False):
    markup = InlineKeyboardMarkup(row_width=3)

    buttons = []
    for qty in range(1, max_qty + 1):
        label_prefix = "🔘 " if qty == selected_qty else ""
        buttons.append(InlineKeyboardButton(f"{label_prefix}{qty}", callback_data=f"select_qty|{vpn_name}|{qty}"))

    for i in range(0, len(buttons), 3):
        markup.add(*buttons[i:i+3])

    if include_confirm and selected_qty:
        markup.add(InlineKeyboardButton("✅ Confirm Purchase", callback_data=f"confirm_purchase|{vpn_name}|{selected_qty}"))

    markup.add(InlineKeyboardButton("❌ Cancel", callback_data="cancel_vpn_selection"))
    markup.add(InlineKeyboardButton("🏠 Main Menu", callback_data="back_to_main_menu"))

    return markup


def has_processed_trx(trx_id):
    return (trx_id or "").lower() in processed_transactions


def mark_trx_processed(trx_id):
    normalized = (trx_id or "").lower()
    if not normalized:
        return
    processed_transactions.add(normalized)


def format_user_summary(target_uid):
    ensure_user(target_uid)
    summary_lines = [
        "📋 *User Overview*",
        f"└👤 User ID: `{target_uid}`",
        f"└💳 Balance: {balances.get(target_uid, 0.0):.2f}৳",
        f"└🛍 Total Orders: {len(orders.get(target_uid, []))}"
    ]

    user_orders = orders.get(target_uid, [])
    if user_orders:
        last_order = user_orders[-1]
        summary_lines.append(
            f"└🕒 Last Order: {last_order.get('timestamp', 'N/A')} — {last_order.get('vpn_name', 'N/A')}"
        )

    pending_trx = [trx.upper() for trx, owner in pending_payments.items() if owner == target_uid]
    if pending_trx:
        summary_lines.append("└⏳ Pending TRX: " + ", ".join(pending_trx))

    return "\n".join(summary_lines) + support_footer()


def build_sales_report_for_date(target_date_str):
    vpn_counts = {}
    order_details = []

    for uid, user_orders in orders.items():
        for order in user_orders:
            timestamp = order.get("timestamp", "")
            if not timestamp:
                continue
            order_date = timestamp.split(" ")[0]
            if order_date == target_date_str:
                vpn_name = order.get("vpn_name", "Unknown VPN")
                vpn_counts[vpn_name] = vpn_counts.get(vpn_name, 0) + 1
                order_details.append({
                    "vpn_name": vpn_name,
                    "timestamp": timestamp,
                    "user_id": uid
                })

    if not order_details:
        return False, f"ℹ️ `{target_date_str}` তারিখে কোনো বিক্রয় রেকর্ড নেই।" + support_footer()

    total_sold = len(order_details)
    vpn_breakdown = "\n".join(
        [f"   • {vpn_name}: {count}" for vpn_name, count in sorted(vpn_counts.items(), key=lambda kv: kv[0].lower())]
    ) or "   • (No VPN data)"

    orders_section = "\n".join(
        [f"   {idx:02d}. {detail['timestamp']} — {detail['vpn_name']} (User `{detail['user_id']}`)" for idx, detail in enumerate(order_details, start=1)]
    )

    report = (
        f"🗓 *Sales Summary* ─ `{target_date_str}`\n"
        "════════════════════════════\n"
        f"*Total Sold:* {total_sold} VPN{'s' if total_sold != 1 else ''}\n"
        "\n"
        "📦 *By VPN*\n"
        f"{vpn_breakdown}\n"
        "\n"
        "📋 *Order Details*\n"
        f"{orders_section}"
    )

    return True, report + support_footer()


def safe_answer_callback(query_id, text=None, show_alert=False, url=None, cache_time=None):
    try:
        bot.answer_callback_query(
            query_id,
            text=text,
            show_alert=show_alert,
            url=url,
            cache_time=cache_time
        )
    except ApiTelegramException as exc:
        message = str(exc).lower()
        if "query is too old" in message or "timeout" in message or "query id is invalid" in message:
            print(f"[WARN] Ignored callback query error: {exc}")
        else:
            raise

def parse_trx_id(text): 
    m_bkash = re.search(r'TrxID[:\s]+([A-Za-z0-9]+)', text, re.I)
    if m_bkash:
        return m_bkash.group(1).lower()
    
    m_nagad = re.search(r'TxnID[:\s]+([A-Za-z0-9]+)', text, re.I)
    if m_nagad:
        return m_nagad.group(1).lower()
        
    return None

def parse_amount(text): 
    m = re.search(r'\bTk\s?([0-9]+(?:\.[0-9]{1,2})?)\b', text.replace(",", ""), re.I)
    return float(m.group(1)) if m else None

# ========== START COMMANDS ==========
@bot.message_handler(commands=['start', 'admin'])
def start_or_admin(message):
    uid = str(message.from_user.id)
    ensure_user(uid)
    
    # Define your welcome message
    welcome_message = (
        "আসসালামু আলাইকুম ❤️‍🩹 *PremiumOne* এ আপনাকে স্বাগতম!\n"
        f"যে কোনও সাহায্যের জন্য যোগাযোগ করুন {SUPPORT_CONTACT}\n\n"
        "*কীভাবে ব্যালেন্স যোগ করবেন* 💳\n"
        "1️⃣ `💳 Add Balance` এ ক্লিক করুন\n"
        "2️⃣ `bKash` অথবা `Nagad` বেছে নিন\n"
        "3️⃣ নম্বরে সেন্ড মানি করে TrxID সংরক্ষণ করুন\n"
        "4️⃣ `Payment Done` চাপুন এবং TrxID পাঠান\n\n"
        "*কীভাবে VPN নিবেন* 🛍️\n"
        "1️⃣ `🛍️ Buy Products` এ যান\n"
        "2️⃣ পছন্দের VPN নির্বাচন করুন\n"
        "3️⃣ ব্যালেন্স যথেষ্ট হলে `Buy Now` চাপুন\n\n"
        f"✅ যে কোনও সময় সরাসরি এই চ্যাটে মেসেজ করুন অথবা {SUPPORT_CONTACT} এ পিং করুন।"
    )

    if uid == str(ADMIN_ID):
        bot.send_message(message.chat.id, "👋 Welcome Admin! Choose an option:", reply_markup=admin_menu_markup())
    else:
        if WELCOME_PHOTO_FILE_ID:
            try:
                bot.send_photo(message.chat.id, WELCOME_PHOTO_FILE_ID, caption=welcome_message, reply_markup=main_menu_markup(), parse_mode="Markdown")
            except Exception as e:
                print(f"Error sending welcome photo with file_id: {e}")
                bot.send_message(message.chat.id, "Error sending welcome image. " + welcome_message, reply_markup=main_menu_markup(), parse_mode="Markdown")
        else:
            bot.send_message(message.chat.id, welcome_message, reply_markup=main_menu_markup(), parse_mode="Markdown")


@bot.message_handler(func=lambda m: norm_text(m.text) == "💰 my balance")
def show_balance(message):
    uid = str(message.from_user.id)
    ensure_user(uid)
    bot.send_message(message.chat.id, f"💳 Your current balance: {balances.get(uid, 0.0):.2f}৳", reply_markup=main_menu_markup())

# ========== BUY PRODUCTS ==========
@bot.message_handler(func=lambda m: norm_text(m.text) == "🛍️ buy products")
def show_vpn_list(message):
    sorted_vpns = sorted(
        vpn_prices.items(),
        key=lambda item: (0 if len(products.get(item[0], [])) > 0 else 1, item[0].lower())
    )

    lines = [
        "🛍 *VPN Catalog*",
        "════════════════",
    ]

    buttons = []
    markup = InlineKeyboardMarkup(row_width=2)

    for name, data_item in sorted_vpns:
        price = data_item["price"]
        days = data_item["days"]
        stock_count = len(products.get(name, []))
        in_stock = stock_count > 0
        status_icon = "✅" if in_stock else "🔴"
        stock_note = f"{stock_count} left" if in_stock else "Out of stock"
        lines.append(f"{status_icon} *{name}* — {days}d · {price}৳ ({stock_note})")

        button_text = f"{status_icon} {name}" if in_stock else f"{status_icon} {name}"
        buttons.append(InlineKeyboardButton(button_text, callback_data=f"vpn|{name}"))

    if buttons:
        for i in range(0, len(buttons), 2):
            markup.add(*buttons[i:i+2])

    markup.add(InlineKeyboardButton("🏠 Main Menu", callback_data="back_to_main_menu"))

    catalog_text = "\n".join(lines) + support_footer()
    bot.send_message(message.chat.id, catalog_text, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data.startswith("vpn|"))
def vpn_selected(c):
    vpn_name = c.data.split("|")[1]
    vpn_info = vpn_prices.get(vpn_name)
    if not vpn_info:
        bot.edit_message_text("❌ VPN not found.", c.message.chat.id, c.message.message_id)
        safe_answer_callback(c.id, text="VPN not found.", show_alert=True)
        return

    price = vpn_info["price"]
    days = vpn_info["days"]
    uid = str(c.from_user.id)
    bal = balances.get(uid, 0.0)
    stock_count = len(products.get(vpn_name, []))

    if stock_count == 0:
        safe_answer_callback(c.id, text="This VPN is currently out of stock. Please choose another.", show_alert=True)
        message_text = (
            f"🛍 *{vpn_name}* ({days} Days)\n"
            f"Price: {price}৳\n"
            "🚫 This VPN is currently *Out of Stock*."
        )
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🏠 Main Menu", callback_data="back_to_main_menu"))
        bot.edit_message_text(message_text, c.message.chat.id, c.message.message_id, reply_markup=markup, parse_mode="Markdown")
        return

    affordable_qty = int(bal // price)
    max_qty = min(stock_count, affordable_qty, MAX_PURCHASE_QUANTITY)

    if max_qty <= 0:
        safe_answer_callback(c.id, text="Insufficient balance. Please add funds.", show_alert=True)
        message_text = (
            f"🛍 *{vpn_name}* ({days} Days)\n"
            f"Price: {price}৳\n"
            f"Available Stock: {stock_count}\n"
            f"Your Balance: {bal:.2f}৳\n\n"
            "💰 Your balance isn't enough for this VPN."
        )
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("➕ Add Balance", callback_data="add_balance_shortcut"))
        markup.add(InlineKeyboardButton("❌ Cancel", callback_data="cancel_vpn_selection"))
        markup.add(InlineKeyboardButton("🏠 Main Menu", callback_data="back_to_main_menu"))
        bot.edit_message_text(message_text, c.message.chat.id, c.message.message_id, reply_markup=markup, parse_mode="Markdown")
        return

    user_sessions[uid] = {
        "selected_vpn": vpn_name,
        "max_qty": max_qty
    }

    instruction_text = (
        f"🛍 *{vpn_name}* ({days} Days)\n"
        f"Price per VPN: {price}৳\n"
        f"Available Stock: {stock_count}\n"
        f"Your Balance: {bal:.2f}৳\n"
        f"Maximum you can buy now: {max_qty}\n\n"
        "🔢 Select how many you want to buy:"
    )

    markup = build_quantity_keyboard(vpn_name, max_qty)
    bot.edit_message_text(instruction_text, c.message.chat.id, c.message.message_id, reply_markup=markup, parse_mode="Markdown")


@bot.callback_query_handler(func=lambda c: c.data.startswith("select_qty|"))
def select_quantity(c):
    parts = c.data.split("|")
    if len(parts) != 3:
        safe_answer_callback(c.id, text="Invalid selection.", show_alert=True)
        return

    vpn_name = parts[1]
    try:
        selected_qty = int(parts[2])
    except ValueError:
        safe_answer_callback(c.id, text="Invalid quantity.", show_alert=True)
        return

    vpn_info = vpn_prices.get(vpn_name)
    if not vpn_info:
        safe_answer_callback(c.id, text="VPN not found.", show_alert=True)
        return

    uid = str(c.from_user.id)
    price = vpn_info["price"]
    days = vpn_info["days"]
    bal = balances.get(uid, 0.0)
    stock_count = len(products.get(vpn_name, []))

    if stock_count == 0:
        bot.edit_message_text("🚫 This VPN just went out of stock. Please choose another.", c.message.chat.id, c.message.message_id)
        safe_answer_callback(c.id, text="Out of stock.", show_alert=True)
        return

    affordable_qty = int(bal // price)
    max_qty = min(stock_count, affordable_qty, MAX_PURCHASE_QUANTITY)

    if max_qty <= 0:
        message_text = "💰 Your balance isn't enough for this VPN. Please add funds and try again."
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("➕ Add Balance", callback_data="add_balance_shortcut"))
        markup.add(InlineKeyboardButton("🏠 Main Menu", callback_data="back_to_main_menu"))
        bot.edit_message_text(message_text, c.message.chat.id, c.message.message_id, reply_markup=markup, parse_mode="Markdown")
        safe_answer_callback(c.id, text="Insufficient balance.", show_alert=True)
        return

    if selected_qty < 1 or selected_qty > max_qty:
        safe_answer_callback(c.id, text=f"Please choose between 1 and {max_qty}.", show_alert=True)
        markup = build_quantity_keyboard(vpn_name, max_qty)
        instruction_text = (
            f"🛍 *{vpn_name}* ({days} Days)\n"
            f"Price per VPN: {price}৳\n"
            f"Available Stock: {stock_count}\n"
            f"Your Balance: {bal:.2f}৳\n"
            f"Maximum you can buy now: {max_qty}\n\n"
            "🔢 Select how many you want to buy:"
        )
        bot.edit_message_text(instruction_text, c.message.chat.id, c.message.message_id, reply_markup=markup, parse_mode="Markdown")
        return

    total_cost = price * selected_qty
    remaining_balance = bal - total_cost
    remaining_stock = stock_count - selected_qty

    user_sessions[uid] = {
        "selected_vpn": vpn_name,
        "selected_qty": selected_qty,
        "max_qty": max_qty
    }

    summary_text = (
        f"🛍 *{vpn_name}* ({days} Days)\n"
        f"Selected Quantity: {selected_qty}\n"
        f"Total Cost: {total_cost:.2f}৳\n"
        f"Your Balance: {bal:.2f}৳ (after purchase: {remaining_balance:.2f}৳)\n"
        f"Stock remaining after purchase: {max(remaining_stock, 0)}\n\n"
        "✅ Tap *Confirm Purchase* to continue or pick another quantity."
    )

    markup = build_quantity_keyboard(vpn_name, max_qty, selected_qty=selected_qty, include_confirm=True)
    bot.edit_message_text(summary_text, c.message.chat.id, c.message.message_id, reply_markup=markup, parse_mode="Markdown")
    safe_answer_callback(c.id, text=f"Quantity set to {selected_qty}")

@bot.callback_query_handler(func=lambda c: c.data == "cancel_vpn_selection")
def cancel_vpn_selection(c):
    user_sessions.pop(str(c.from_user.id), None)
    bot.edit_message_text("Selection cancelled. Returning to main menu.", c.message.chat.id, c.message.message_id)
    bot.send_message(c.message.chat.id, "Choose an option:", reply_markup=main_menu_markup())
    safe_answer_callback(c.id, text="Cancelled.")

@bot.callback_query_handler(func=lambda c: c.data == "back_to_main_menu")
def back_to_main_menu_callback(c):
    user_sessions.pop(str(c.from_user.id), None)
    bot.edit_message_text("Returning to main menu.", c.message.chat.id, c.message.message_id)
    bot.send_message(c.message.chat.id, "Choose an option:", reply_markup=main_menu_markup())
    safe_answer_callback(c.id, text="Back to main menu.")


@bot.callback_query_handler(func=lambda c: c.data.startswith("confirm_purchase|") or c.data.startswith("buy|"))
def confirm_purchase_callback(c):
    if c.data.startswith("buy|"):
        # Legacy fallback: treat as quantity 1 confirmation
        vpn_name = c.data.split("|")[1]
        qty = 1
    else:
        parts = c.data.split("|")
        if len(parts) != 3:
            safe_answer_callback(c.id, text="Invalid confirmation.", show_alert=True)
            return
        vpn_name = parts[1]
        try:
            qty = int(parts[2])
        except ValueError:
            safe_answer_callback(c.id, text="Invalid quantity.", show_alert=True)
            return

    vpn_info = vpn_prices.get(vpn_name)
    if not vpn_info:
        bot.edit_message_text("❌ VPN not found.", c.message.chat.id, c.message.message_id)
        bot.send_message(c.message.chat.id, "⬅️ Back to menu:", reply_markup=main_menu_markup())
        safe_answer_callback(c.id, text="VPN not found.", show_alert=True)
        return

    uid = str(c.from_user.id)
    price = vpn_info["price"]
    days = vpn_info["days"]
    bal = balances.get(uid, 0.0)

    if qty < 1 or qty > MAX_PURCHASE_QUANTITY:
        safe_answer_callback(c.id, text="Invalid quantity.", show_alert=True)
        return

    vpn_stock = products.get(vpn_name, [])

    if len(vpn_stock) < qty:
        stock_count = len(vpn_stock)
        affordable_qty = int(bal // price)
        max_qty = min(stock_count, affordable_qty, MAX_PURCHASE_QUANTITY)

        if max_qty > 0:
            message_text = (
                f"🛍 *{vpn_name}* ({days} Days)\n"
                f"Price per VPN: {price}৳\n"
                f"Available Stock: {stock_count}\n"
                f"Your Balance: {bal:.2f}৳\n"
                f"Maximum you can buy now: {max_qty}\n\n"
                f"🚫 Only {stock_count} account(s) left. Please choose up to {max_qty}."
            )
            markup = build_quantity_keyboard(vpn_name, max_qty)
            user_sessions[uid] = {
                "selected_vpn": vpn_name,
                "max_qty": max_qty
            }
        else:
            message_text = (
                "🚫 This VPN is currently unavailable for your balance/stock."
            )
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🏠 Main Menu", callback_data="back_to_main_menu"))

        bot.edit_message_text(message_text, c.message.chat.id, c.message.message_id, reply_markup=markup, parse_mode="Markdown")
        safe_answer_callback(c.id, text="Insufficient stock.", show_alert=True)
        return

    total_cost = price * qty
    if bal < total_cost:
        message_text = (
            f"💰 You need {total_cost:.2f}৳ but only have {bal:.2f}৳.\n"
            "Add balance and try again."
        )
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("➕ Add Balance", callback_data="add_balance_shortcut"))
        markup.add(InlineKeyboardButton("🏠 Main Menu", callback_data="back_to_main_menu"))
        bot.edit_message_text(message_text, c.message.chat.id, c.message.message_id, reply_markup=markup, parse_mode="Markdown")
        safe_answer_callback(c.id, text="Insufficient balance.", show_alert=True)
        return

    selected_items = [vpn_stock.pop(0) for _ in range(qty)]
    balances[uid] = round(bal - total_cost, 2)

    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    for item in selected_items:
        orders.setdefault(uid, []).append({
            "vpn_name": vpn_name,
            "item": item,
            "timestamp": timestamp
        })

    global total_sales
    total_sales += total_cost

    data["products"], data["balances"], data["orders"], data["total_sales"] = products, balances, orders, total_sales
    save_data(data)

    fields_to_display = product_fields.get(vpn_name, DEFAULT_PRODUCT_FIELDS)

    detail_lines = [
        f"🛍 *{vpn_name}* {days} Days ✅",
        f"Quantity: {qty}",
        f"Total Cost: {total_cost:.2f}৳",
        ""
    ]

    for idx, item in enumerate(selected_items, start=1):
        detail_lines.append(f"*Item {idx}*")
        for field_name in fields_to_display:
            item_key = field_name.replace(" ", "_").lower()
            detail_lines.append(f"└ *{field_name}* ➡ `{item.get(item_key, 'N/A')}`")
        detail_lines.append("")

    detail_message = "\n".join(detail_lines).strip() + support_footer()

    bot.edit_message_text(detail_message, c.message.chat.id, c.message.message_id, parse_mode="Markdown")
    bot.send_message(c.message.chat.id, "✅ Purchase successful! Check '📦 My Orders' for your VPN details.", reply_markup=main_menu_markup())
    safe_answer_callback(c.id, text="Purchase successful!", show_alert=True)

    user_sessions.pop(uid, None)

# ========== MY ORDERS ==========
@bot.message_handler(func=lambda m: norm_text(m.text) == "📦 my orders")
def show_my_orders(message):
    uid = str(message.from_user.id)
    user_orders = orders.get(uid)
    
    if not user_orders:
        bot.send_message(message.chat.id, "You haven't purchased any VPNs yet! Tap '🛍️ Buy Products' to get started.", reply_markup=main_menu_markup())
        return
    
    order_list_text = "🛍 Your Recent Orders:\n\n"
    # Show last 5 orders, or fewer if less than 5
    for i, order_item in enumerate(user_orders[-5:]): 
        vpn_name = order_item.get("vpn_name", "N/A")
        item_details = order_item.get("item", {})
        timestamp = order_item.get("timestamp", "N/A")
        
        order_list_text += f"*{i+1}. {vpn_name}* (Purchased: {timestamp})\n"
        
        # --- MODIFIED: Display VPN details in orders based on product_fields ---
        fields_to_display = product_fields.get(vpn_name, DEFAULT_PRODUCT_FIELDS)
        for field_name in fields_to_display:
            item_key = field_name.replace(" ", "_").lower()
            order_list_text += f"  *{field_name}:* `{item_details.get(item_key, 'N/A')}`\n"
        order_list_text += "\n"
        # --- END MODIFIED ---
        
    bot.send_message(message.chat.id, order_list_text, parse_mode="Markdown", reply_markup=main_menu_markup())

# ========== ADD BALANCE ==========
@bot.message_handler(func=lambda m: norm_text(m.text) == "💳 add balance")
def add_balance_ui(message):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🟣 Bkash", callback_data="add_balance_bkash"))
    kb.add(InlineKeyboardButton("🟠 Nagad", callback_data="add_balance_nagad"))
    bot.send_message(message.chat.id, "Choose your payment method:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "add_balance_shortcut")
def add_balance_shortcut(c):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🟣 Bkash", callback_data="add_balance_bkash"))
    kb.add(InlineKeyboardButton("🟠 Nagad", callback_data="add_balance_nagad"))
    bot.edit_message_text("Choose your payment method:", c.message.chat.id, c.message.message_id, reply_markup=kb)
    safe_answer_callback(c.id, text="Redirecting to Add Balance section.")

@bot.callback_query_handler(func=lambda c: c.data.startswith("add_balance_"))
def show_payment_details(c):
    method = c.data.split("_")[2].capitalize() # "Bkash" or "Nagad"
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("Payment Done ✅", callback_data="send_trx"))
    
    bot.edit_message_text(
        f"নিচের দেওয়া {method} নাম্বারে এ সেন্ড মানি করবেন 👇\n\n`{PAYMENT_NUMBER}`\n\n"
        "Trx Id কপি করে রাখবেন\n\nটাকা পাঠানোর পর Payment Done ✅ এ ক্লিক করুন\n └ TRX ID দিন",
        c.message.chat.id, c.message.message_id, parse_mode="Markdown", reply_markup=kb
    )
    safe_answer_callback(c.id, text=f"Showing {method} payment details.")

@bot.callback_query_handler(func=lambda c: c.data == "send_trx")
def ask_trx(c):
    msg = bot.send_message(c.message.chat.id, "📥 TRX ID দিন", reply_markup=ForceReply())
    bot.register_next_step_handler(msg, save_trx_id)
    safe_answer_callback(c.id, text="Please send your TRX ID.")

def save_trx_id(message):
    uid = str(message.from_user.id)
    trx = (message.text or "").strip().lower()

    if not re.fullmatch(r"[A-Za-z0-9]+", trx):
        bot.reply_to(message, "❌ Invalid TRX ID format. Please enter a valid Transaction ID.")
        bot.send_message(message.chat.id, "⬅️ Back to menu:", reply_markup=main_menu_markup())
        return

    if has_processed_trx(trx):
        bot.reply_to(message, "❌ এই TRX ID ইতোমধ্যে কনফার্ম হয়েছে। অনুগ্রহ করে নতুন ট্রান্স্যাকশন আইডি ব্যবহার করুন।")
        bot.send_message(message.chat.id, "⬅️ Back to menu:", reply_markup=main_menu_markup())
        return
    
    if trx in pending_payments:
        bot.reply_to(message, "⏳ This TRX ID is already pending admin confirmation.")
        bot.send_message(message.chat.id, "⬅️ Back to menu:", reply_markup=main_menu_markup())
        return
    # This check for existing TRX in orders might be redundant or could cause issues if a user
    # tries to use the same TRX for multiple payments (which they shouldn't).
    # if any(trx == order_item.get("trx_id", "").lower() for user_orders in orders.values() for order_item in user_orders):
    #    pass 

    pending_payments[trx] = uid
    data["pending_payments"] = pending_payments

    if trx in unmatched_payments:
        amt = unmatched_payments.pop(trx)
        balances[uid] = round(balances.get(uid, 0.0) + amt, 2)
        data["balances"], data["unmatched_payments"] = balances, unmatched_payments
        mark_trx_processed(trx)
        save_data(data)
        bot.reply_to(message, f"আপনার ব্যালেন্স সফলভাবে যুক্ত হয়েছে! 🎉\n \t└{amt} TK\n\t└ধন্যবাদ! 💖")
        bot.send_message(ADMIN_ID, f"✅ Auto-confirmed TRX `{trx.upper()}` for user `{uid}`. Amount: {amt} TK", parse_mode="Markdown")
    else:
        save_data(data)
        bot.reply_to(message, "✅ TRX ID received. Awaiting admin confirmation.")
        bot.send_message(ADMIN_ID, f"💳 *Payment Request*\nTRX ID: `{trx.upper()}`\nUser ID: `{uid}`\n\nForward the bKash/Nagad SMS here to confirm.", parse_mode="Markdown")
    
    bot.send_message(message.chat.id, "⬅️ Back to menu:", reply_markup=main_menu_markup())


@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text and 
                                     (("trxid" in m.text.lower() or "txnid" in m.text.lower() or "trnx id" in m.text.lower()) and 
                                      "tk" in m.text.lower() and 
                                      ("received" in m.text.lower() or "prepaid" in m.text.lower() or "cash in" in m.text.lower())))
def admin_bkash_nagad_parser(m):
    txt = (m.text or "").strip()
    trx = parse_trx_id(txt)
    amt = parse_amount(txt)

    if not trx or amt is None:
        bot.reply_to(m, "❌ Could not extract TRX ID or amount from the SMS.")
        return
    
    if has_processed_trx(trx):
        bot.reply_to(m, f"⚠️ TRX `{trx.upper()}` ইতোমধ্যে প্রসেস করা হয়েছে।", parse_mode="Markdown")
        return
    
    if trx in pending_payments:
        uid = pending_payments.pop(trx)
        balances[uid] = round(balances.get(uid, 0.0) + amt, 2)
        mark_trx_processed(trx)
        data["balances"], data["pending_payments"] = balances, pending_payments
        save_data(data)
        bot.send_message(int(uid), f"আপনার ব্যালেন্স সফলভাবে যুক্ত হয়েছে! 🎉:\n\t└ {amt} TK\n\t└Transaction ID: `{trx.upper()}`\n\t└ধন্যবাদ! 💖", parse_mode="Markdown")
        bot.reply_to(m, f"✅ Auto-confirmed.\nUser: `{uid}`\nAmount: {amt} TK\nTRX: `{trx.upper()}`", parse_mode="Markdown")
    elif trx not in unmatched_payments:
        unmatched_payments[trx] = amt
        data["unmatched_payments"] = unmatched_payments
        save_data(data)
        bot.reply_to(m, f"⚠ SMS saved. No pending user request found for TRX ID: `{trx.upper()}`. Will auto-confirm when user provides TRX ID.\nAmount: {amt} TK", parse_mode="Markdown")
    else:
        bot.reply_to(m, f"ℹ️ This TRX ID `{trx.upper()}` is already in unmatched payments.", parse_mode="Markdown")


# ========== ADMIN FEATURES ==========
@bot.message_handler(func=lambda m: norm_text(m.text) == "⬅️ main menu (user)" and str(m.from_user.id) == str(ADMIN_ID))
def back_to_main_menu_admin(message):
    bot.send_message(message.chat.id, "Returning to main user menu.", reply_markup=main_menu_markup())

@bot.message_handler(func=lambda m: norm_text(m.text) == "📊 total sales" and str(m.from_user.id) == str(ADMIN_ID))
def prompt_sales_report_date(message):
    admin_sessions[message.from_user.id] = {"type": "sales_report"}
    prompt = bot.send_message(
        message.chat.id,
        "🗓 কোন দিনের সেল রিপোর্ট দেখতে চান?\n`YYYY-MM-DD` ফরম্যাটে তারিখ পাঠান অথবা `today` লিখুন।",
        reply_markup=ForceReply()
    )
    bot.register_next_step_handler(prompt, process_sales_report_request)

@bot.message_handler(func=lambda m: norm_text(m.text) == "📈 current stock" and str(m.from_user.id) == str(ADMIN_ID))
def show_current_stock(message):
    lines = [
        "📦 *Current VPN Stock*",
        "════════════════════"
    ]
    has_stock = False
    for vpn_name in sorted(vpn_prices.keys()): # Sort for consistent display
        stock_list = products.get(vpn_name, [])
        count = len(stock_list)
        lines.append(f"• {vpn_name}: {count} available")
        if count > 0:
            has_stock = True
    
    if not has_stock:
        lines.append("• No VPNs currently in stock.")
    
    stock_report = "\n".join(lines) + support_footer()
    bot.send_message(message.chat.id, stock_report, parse_mode="Markdown", reply_markup=admin_menu_markup())


def process_sales_report_request(message):
    if str(message.from_user.id) != str(ADMIN_ID):
        bot.reply_to(message, "Unauthorized.")
        return

    session = admin_sessions.get(message.from_user.id)
    if not session or session.get("type") != "sales_report":
        bot.reply_to(message, "❌ এই মুহূর্তে কোনো সেল রিপোর্ট অনুরোধ নেই।", reply_markup=admin_menu_markup())
        return

    raw_text = (message.text or "").strip()
    if not raw_text:
        retry = bot.reply_to(message, "❌ সঠিক তারিখ লিখুন (উদাহরণ: 2025-10-30) অথবা `today` লিখুন।", reply_markup=ForceReply())
        bot.register_next_step_handler(retry, process_sales_report_request)
        return

    raw_lower = raw_text.lower()

    if raw_lower == "today":
        target_date_str = datetime.now().strftime("%Y-%m-%d")
    else:
        try:
            parsed_date = datetime.strptime(raw_text, "%Y-%m-%d")
            target_date_str = parsed_date.strftime("%Y-%m-%d")
        except ValueError:
            retry = bot.reply_to(message, "❌ ভুল ফরম্যাট। অনুগ্রহ করে `YYYY-MM-DD` ফরম্যাটে তারিখ দিন অথবা `today` লিখুন।", reply_markup=ForceReply())
            bot.register_next_step_handler(retry, process_sales_report_request)
            return

    admin_sessions.pop(message.from_user.id, None)

    _, report_text = build_sales_report_for_date(target_date_str)
    bot.reply_to(message, report_text, parse_mode="Markdown")
    bot.send_message(message.chat.id, "⬅️ Back to Admin Menu:", reply_markup=admin_menu_markup())


@bot.message_handler(func=lambda m: norm_text(m.text) == "🧾 pending payments" and str(m.from_user.id) == str(ADMIN_ID))
def show_pending_payments(message):
    if not pending_payments:
        bot.send_message(message.chat.id, "✅ বর্তমানে কোনো পেন্ডিং পেমেন্ট নেই।" + support_footer(), reply_markup=admin_menu_markup(), parse_mode="Markdown")
        return

    intro_text = (
        "🧾 *Pending Payment Requests*\n"
        "কনফার্ম বা রিজেক্ট করতে নীচের বোতাম ব্যবহার করুন।"
    ) + support_footer()
    bot.send_message(message.chat.id, intro_text, reply_markup=admin_menu_markup(), parse_mode="Markdown")

    shown = 0
    for trx, uid in list(pending_payments.items()):
        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton("✅ Confirm", callback_data=f"admin_confirm_trx|{trx}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"admin_reject_trx|{trx}")
        )
        markup.row(InlineKeyboardButton("👤 User Profile", callback_data=f"admin_lookup_user|{uid}"))

        message_text = (
            "💳 *Pending Payment*\n"
            f"└Trx ID: `{trx.upper()}`\n"
            f"└User ID: `{uid}`\n"
            f"└Current Balance: {balances.get(uid, 0.0):.2f}৳"
        ) + support_footer()

        bot.send_message(message.chat.id, message_text, reply_markup=markup, parse_mode="Markdown")

        shown += 1
        if shown >= 10:
            remaining = len(pending_payments) - shown
            if remaining > 0:
                bot.send_message(message.chat.id, f"ℹ️ আরও {remaining} টি রিকুয়েস্ট রয়েছে। পুরোনো রিকুয়েস্টগুলো দেখার জন্য কমান্ডটি আবার ব্যবহার করুন।" + support_footer(), parse_mode="Markdown")
            break

@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_confirm_trx|"))
def admin_confirm_trx(c):
    if str(c.from_user.id) != str(ADMIN_ID):
        safe_answer_callback(c.id, text="Unauthorized", show_alert=True)
        return

    trx = c.data.split("|")[1]

    if has_processed_trx(trx):
        safe_answer_callback(c.id, text="এই TRX ইতোমধ্যে প্রসেস করা হয়েছে।", show_alert=True)
        bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id, reply_markup=None)
        return

    if trx not in pending_payments:
        safe_answer_callback(c.id, text="এই TRX ইতোমধ্যে প্রসেস করা হয়েছে।", show_alert=True)
        bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id, reply_markup=None)
        return

    admin_sessions[c.from_user.id] = {
        "type": "confirm_trx",
        "trx": trx,
        "chat_id": c.message.chat.id,
        "message_id": c.message.message_id
    }

    prompt = bot.send_message(
        c.message.chat.id,
        f"✅ TRX `{trx.upper()}` নির্বাচিত হয়েছে। অনুগ্রহ করে প্রাপ্ত টাকার পরিমাণ লিখুন (শুধু সংখ্যা)।",
        reply_markup=ForceReply()
    )
    bot.register_next_step_handler(prompt, handle_admin_confirm_amount, trx)
    safe_answer_callback(c.id, text=f"Enter amount for {trx.upper()}")


def handle_admin_confirm_amount(message, trx):
    if str(message.from_user.id) != str(ADMIN_ID):
        bot.reply_to(message, "Unauthorized.")
        return

    session = admin_sessions.get(message.from_user.id)
    if not session or session.get("type") != "confirm_trx" or session.get("trx") != trx:
        bot.reply_to(message, "❌ This confirmation session is no longer active.")
        bot.send_message(message.chat.id, "⬅️ Back to Admin Menu:", reply_markup=admin_menu_markup())
        return

    if has_processed_trx(trx):
        admin_sessions.pop(message.from_user.id, None)
        bot.reply_to(message, "⚠️ এই TRX ইতোমধ্যে প্রসেস করা হয়েছে।", reply_markup=admin_menu_markup())
        return

    amount_text = (message.text or "").strip().replace("৳", "").replace(",", "").lower().replace("tk", "")

    try:
        amount = float(amount_text)
    except ValueError:
        retry = bot.reply_to(message, "❌ সঠিক সংখ্যার পরিমাণ লিখুন (উদাহরণ: 150)।", reply_markup=ForceReply())
        bot.register_next_step_handler(retry, handle_admin_confirm_amount, trx)
        return

    if amount <= 0:
        retry = bot.reply_to(message, "❌ পরিমাণ শূন্য হতে পারে না। আবার লিখুন।", reply_markup=ForceReply())
        bot.register_next_step_handler(retry, handle_admin_confirm_amount, trx)
        return

    uid = pending_payments.pop(trx, None)
    if not uid:
        admin_sessions.pop(message.from_user.id, None)
        bot.reply_to(message, "⚠️ এই TRX আর পাওয়া যাচ্ছে না। হয়তো ইতোমধ্যে প্রসেস হয়েছে।")
        bot.send_message(message.chat.id, "⬅️ Back to Admin Menu:", reply_markup=admin_menu_markup())
        return

    balances[uid] = round(balances.get(uid, 0.0) + amount, 2)
    mark_trx_processed(trx)
    data["balances"], data["pending_payments"] = balances, pending_payments
    save_data(data)

    try:
        bot.send_message(int(uid), f"আপনার ব্যালেন্স সফলভাবে যুক্ত হয়েছে! 🎉\n└ {amount:.2f} TK\n└ Transaction ID: `{trx.upper()}`\n└ধন্যবাদ! 💖")
    except Exception as notify_err:
        bot.send_message(message.chat.id, f"⚠️ ব্যবহারকারীকে মেসেজ পাঠানো যায়নি: {notify_err}")

    bot.reply_to(message, f"✅ User `{uid}` এর অ্যাকাউন্টে {amount:.2f} TK যোগ করা হয়েছে।", parse_mode="Markdown")

    session_info = admin_sessions.pop(message.from_user.id, None)
    if session_info:
        updated_text = (
            f"✅ Confirmed TRX `{trx.upper()}`\n"
            f"• User: `{uid}`\n"
            f"• Amount: {amount:.2f} TK"
        )
        bot.edit_message_text(
            updated_text,
            session_info["chat_id"],
            session_info["message_id"],
            reply_markup=None
        )

    bot.send_message(message.chat.id, "⬅️ Back to Admin Menu:", reply_markup=admin_menu_markup())


@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_reject_trx|"))
def admin_reject_trx(c):
    if str(c.from_user.id) != str(ADMIN_ID):
        safe_answer_callback(c.id, text="Unauthorized", show_alert=True)
        return

    trx = c.data.split("|")[1]
    uid = pending_payments.pop(trx, None)

    if uid:
        data["pending_payments"] = pending_payments
        save_data(data)
        try:
            bot.send_message(int(uid), f"❌ আপনার পেমেন্টটি যাচাই করা যায়নি। TRX `{trx.upper()}` পুনরায় চেক করে আবার পাঠান অথবা {SUPPORT_CONTACT} এ যোগাযোগ করুন।")
        except Exception as notify_err:
            bot.send_message(c.message.chat.id, f"⚠️ ব্যবহারকারীকে মেসেজ পাঠানো যায়নি: {notify_err}")

        bot.edit_message_text(
            f"❌ Rejected TRX `{trx.upper()}` (User `{uid}`)",
            c.message.chat.id,
            c.message.message_id,
            reply_markup=None
        )
        safe_answer_callback(c.id, text=f"Rejected {trx.upper()}.")
    else:
        safe_answer_callback(c.id, text="TRX আর পাওয়া যাচ্ছে না।", show_alert=True)
        bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id, reply_markup=None)


@bot.message_handler(func=lambda m: norm_text(m.text) == "👥 user lookup" and str(m.from_user.id) == str(ADMIN_ID))
def prompt_admin_user_lookup(message):
    admin_sessions[message.from_user.id] = {"type": "user_lookup", "last_lookup": None}
    prompt = bot.send_message(
        message.chat.id,
        "🔍 যেই ব্যবহারকারীর তথ্য চান তার ইউজার আইডি লিখুন।\n`me` লিখলে নিজের তথ্য পাবেন, `exit` লিখলে ফিরে যাবেন।",
        reply_markup=ForceReply()
    )
    bot.register_next_step_handler(prompt, process_admin_user_lookup)


def process_admin_user_lookup(message):
    if str(message.from_user.id) != str(ADMIN_ID):
        bot.reply_to(message, "Unauthorized.")
        return

    session = admin_sessions.get(message.from_user.id)
    if not session or session.get("type") != "user_lookup":
        bot.reply_to(message, "❌ এই মুহূর্তে কোনো লুকআপ সেশন চালু নেই।", reply_markup=admin_menu_markup())
        return

    raw_input = (message.text or "").strip()
    lower_input = raw_input.lower()

    if lower_input in {"exit", "back", "close"}:
        admin_sessions.pop(message.from_user.id, None)
        bot.reply_to(message, "✅ ব্যবহারকারী লুকআপ থেকে বেরিয়ে এসেছেন।", reply_markup=admin_menu_markup())
        return

    if lower_input in {"me", "self", "admin"}:
        target_uid = str(ADMIN_ID)
    elif raw_input == "" and session.get("last_lookup"):
        target_uid = session["last_lookup"]
    else:
        if not raw_input.isdigit():
            retry = bot.reply_to(message, "❌ শুধুমাত্র সংখ্যায় টেলিগ্রাম ইউজার আইডি লিখুন অথবা `me`/`exit` ব্যবহার করুন।", reply_markup=ForceReply())
            bot.register_next_step_handler(retry, process_admin_user_lookup)
            return
        target_uid = raw_input

    summary = format_user_summary(target_uid)
    admin_sessions[message.from_user.id]["last_lookup"] = target_uid

    bot.reply_to(message, summary, parse_mode="Markdown")

    prompt = bot.send_message(
        message.chat.id,
        "আরও কোনো ইউজারের আইডি চাইলে এখনই লিখুন। বের হতে `exit` লিখুন।",
        reply_markup=ForceReply()
    )
    bot.register_next_step_handler(prompt, process_admin_user_lookup)


@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_lookup_user|"))
def admin_lookup_user_callback(c):
    if str(c.from_user.id) != str(ADMIN_ID):
        safe_answer_callback(c.id, text="Unauthorized", show_alert=True)
        return

    target_uid = c.data.split("|")[1]
    summary = format_user_summary(target_uid)
    safe_answer_callback(c.id, text=f"Showing user {target_uid}")
    bot.send_message(c.message.chat.id, summary, reply_markup=admin_menu_markup())


@bot.message_handler(func=lambda m: norm_text(m.text) == "➕ add vpn account" and str(m.from_user.id) == str(ADMIN_ID))
def ask_add_vpn_account(message):
    markup = InlineKeyboardMarkup()
    for name in sorted(vpn_prices.keys()): # Sort for consistent display
        markup.add(InlineKeyboardButton(name, callback_data=f"admin_add_vpn|{name}"))
    msg = bot.send_message(message.chat.id, "Which VPN account do you want to add stock for?", reply_markup=markup)
    
@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_add_vpn|"))
def admin_selected_vpn_to_add(c):
    vpn_name = c.data.split("|")[1]
    
    # --- MODIFIED: Adjust prompt based on product_fields ---
    prompt_fields = product_fields.get(vpn_name, DEFAULT_PRODUCT_FIELDS) # Default to Gmail/Password
    
    prompt_text = f"You selected *{vpn_name}*.\n\nPlease send the VPN account details in the following format:\n\n"
    format_example = ""
    for field in prompt_fields:
        format_example += f"*{field}*:your_{field.lower().replace(' ', '_')}_value\n"
    
    prompt_text += f"`{format_example.strip()}`"

    msg = bot.send_message(c.message.chat.id, prompt_text, parse_mode="Markdown", reply_markup=ForceReply())
    bot.register_next_step_handler(msg, process_add_vpn_account, vpn_name)
    safe_answer_callback(c.id, text=f"Ready to add {vpn_name} account.")


def process_add_vpn_account(message, vpn_name):
    txt = (message.text or "").strip()
    details = {}
    lines = txt.split('\n')
    
    # --- MODIFIED: Parse input based on expected fields ---
    required_fields_for_vpn = product_fields.get(vpn_name, DEFAULT_PRODUCT_FIELDS) # Default to Gmail/Password
    
    parsed_count = 0
    for line in lines:
        if ':' in line:
            key, value = line.split(':', 1)
            # Standardize key to lowercase and replace spaces with underscores for storage
            standardized_key = key.strip().lower().replace(" ", "_")
            details[standardized_key] = value.strip()
            parsed_count += 1
    
    # Check if all required fields are present
    missing_fields = []
    for field in required_fields_for_vpn:
        standardized_field_key = field.lower().replace(" ", "_")
        if standardized_field_key not in details or not details[standardized_field_key]:
            missing_fields.append(field)

    if missing_fields:
        bot.reply_to(message, f"❌ Invalid format. The following fields are required: {', '.join(missing_fields)}. Please try again.")
        bot.send_message(message.chat.id, "⬅️ Back to Admin Menu:", reply_markup=admin_menu_markup())
        return

    # If all required fields are present, add to products
    products.setdefault(vpn_name, []).append(details) # Store the details dictionary as is
    data["products"] = products
    save_data(data)
    
    bot.reply_to(message, f"✅ Successfully added 1 account for *{vpn_name}* to stock. Current stock: {len(products[vpn_name])}", parse_mode="Markdown")
    bot.send_message(message.chat.id, "⬅️ Back to Admin Menu:", reply_markup=admin_menu_markup())


# ========== ERROR HANDLER ==========
@bot.message_handler(func=lambda message: True)
def echo_all(message):
    uid = str(message.from_user.id)
    if uid == str(ADMIN_ID):
        bot.send_message(message.chat.id, "Did not understand that admin command. Please use the admin menu buttons.", reply_markup=admin_menu_markup())
    else:
        bot.send_message(message.chat.id, "I didn't catch that. Please choose an option from the menu অথবা সরাসরি আমাদের বার্তা পাঠান।", reply_markup=main_menu_markup())


print("Bot polling...")
bot.infinity_polling()