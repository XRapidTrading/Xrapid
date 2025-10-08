import logging
import asyncio
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# Import functions from xrpl_client.py
from xrpl_client import generate_new_wallet_sync, import_wallet, get_account_info
# Import XRPSniper class
from xrp_sniper_logic_improved import XRPSniper

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Global sniper instance
sniper = XRPSniper()

# --- Bot Command Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a message with the main menu options."""
    user = update.effective_user
    keyboard = [
        [InlineKeyboardButton("📊 Positions", callback_data="positions_menu")],
        [InlineKeyboardButton("🎯 Sniper", callback_data="sniper_menu")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="settings_menu")],
        [InlineKeyboardButton("❓ Help", callback_data="help_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = f"Hi {user.mention_html()}! Welcome to your XRP Sniper Bot. Please choose an option:"

    if update.callback_query:
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode="HTML")
    else:
        await update.message.reply_html(message_text, reply_markup=reply_markup)

async def help_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays detailed help information."""
    message_text = (
        "**Bot Help & Detailed Information**\n\n"
        "This bot is a powerful tool to trade and snipe tokens on the XRP Ledger. Here’s how it works:\n\n"
        "**1. 🎯 Sniper**\n"
        "The core feature. You can create multiple, named \'sniper configurations\' to automatically buy tokens when they meet your criteria.\n"
        "- **Create a Config**: Go to `Sniper` -> `Create New Config`.\n"
        "- **Token Name (Ticker)**: The token\'s currency code (e.g., \'USD\', \'SOLO\').\n"
        "- **Token Issuer**: The address of the account that issued the token. This is crucial for identifying the correct token.\n"
        "- **Dev Wallet Address**: If you want to snipe a token as soon as a specific developer\'s wallet makes a transaction, enter it here.\n"
        "- **Sniper-Specific Settings**: Each config has its own `Buy Amount`, `Slippage`, `Fees`, `MEV Protection`, and `Tip`. These settings ONLY apply to this specific sniper config.\n"
        "- **Wallet Selection**: You\'ll be asked to choose which of your imported wallets will be used for this snipe.\n"
        "- **Naming**: Give your config a unique name to identify it.\n"
        "- **Activation**: Once created, you can see your list of configs in the `Sniper` menu. Each can be turned ON `🟢` or OFF `🔴` individually.\n\n"
        "**2. ⚙️ Settings**\n"
        "This section is for **general trading**, not for the sniper. These are your default settings for manual trades (e.g., when you paste a contract address).\n"
        "- **General Buy/Sell Settings**: Set your default `Buy Amount`, `Slippage`, `MEV Protection`, and `Fees` for all non-sniper trades.\n"
        "- **Wallet Settings**: Manage your wallets. You can generate a new one (currently under review) or import an existing one using its seed.\n\n"
        "**3. 📊 Positions**\n"
        "View your token balances for your active wallet. From here, you can perform manual trades.\n"
        "- **Sell Percentages**: Quickly sell a portion of your holdings with the `Sell 5%`, `25%`, `50%`, or `100%` buttons. (Note: This feature is in development).\n\n"
        "**Important Distinction:**\n"
        "Settings in a **Sniper Config** are for that specific automated snipe. **General Settings** are your defaults for everything else."
    )
    keyboard = [
        [InlineKeyboardButton("↩️ Back to Main Menu", callback_data="start")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode="MarkdownV2")

async def positions_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the positions menu."""
    keyboard = [
        [InlineKeyboardButton("💰 View My Positions", callback_data="view_positions")],
        [InlineKeyboardButton("↩️ Back to Main Menu", callback_data="start")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = "Here you can view and manage your token positions."
    await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup)

async def sniper_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays a list of sniper configs and an option to create a new one."""
    user_id = update.effective_user.id
    user_configs = sniper.snipe_settings.get(user_id, {})
    
    keyboard = []
    if user_configs:
        for name, config in user_configs.items():
            status_emoji = "🟢" if config.get("is_active", False) else "🔴"
            # Button to manage a specific config
            keyboard.append([InlineKeyboardButton(f"{status_emoji} {name}", callback_data=f"manage_config_{name}")])
    
    keyboard.append([InlineKeyboardButton("📝 Create New Config", callback_data="create_sniper_config_new")])
    keyboard.append([InlineKeyboardButton("↩️ Back to Main Menu", callback_data="start")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = "Your Sniper Configurations. Select one to manage or create a new one."
    await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup)

async def manage_sniper_config(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays management options for a specific sniper config."""
    query = update.callback_query
    config_name = query.data.replace("manage_config_", "")
    user_id = update.effective_user.id
    config = sniper.snipe_settings.get(user_id, {}).get(config_name)

    if not config:
        await query.edit_message_text("Error: Config not found.")
        return

    status_emoji = "🟢" if config.get("is_active", False) else "🔴"
    status_text = "Deactivate" if config.get("is_active", False) else "Activate"

    keyboard = [
        [InlineKeyboardButton(f"{status_emoji} {status_text}", callback_data=f"toggle_config_{config_name}")],
        [InlineKeyboardButton("✏️ Edit", callback_data=f"edit_config_{config_name}")],
        [InlineKeyboardButton("🗑️ Delete", callback_data=f"delete_config_{config_name}")],
        [InlineKeyboardButton("↩️ Back to Sniper Menu", callback_data="sniper_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = f"Managing Sniper Config: **{config_name}**\n\n`{config}`"
    await query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode="MarkdownV2")

async def toggle_sniper_config_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggles the active status of a single sniper config."""
    query = update.callback_query
    config_name = query.data.replace("toggle_config_", "")
    user_id = update.effective_user.id
    
    user_configs = sniper.snipe_settings.get(user_id, {})
    if config_name in user_configs:
        current_status = user_configs[config_name].get("is_active", False)
        user_configs[config_name]["is_active"] = not current_status
        sniper.update_snipe_settings(user_id, user_configs)
        await query.answer(f"Config \'{config_name}\' is now {\"OFF 🔴\" if current_status else \"ON 🟢\"}.")
        # Rerender the main sniper menu to show the updated list
        await sniper_menu(update, context)
    else:
        await query.answer("Error: Config not found.")

async def delete_sniper_config(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Deletes a sniper config."""
    query = update.callback_query
    config_name = query.data.replace("delete_config_", "")
    user_id = update.effective_user.id
    
    user_configs = sniper.snipe_settings.get(user_id, {})
    if config_name in user_configs:
        del user_configs[config_name]
        sniper.update_snipe_settings(user_id, user_configs)
        await query.answer(f"Config \'{config_name}\' has been deleted.")
        await sniper_menu(update, context)
    else:
        await query.answer("Error: Config not found.")

async def create_sniper_config_new(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Starts the process for creating a new sniper config."""
    # Clear any old temporary data
    context.user_data["temp_sniper_config"] = {}
    await create_sniper_config_editor(update, context, is_new=True)

async def edit_sniper_config(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Starts the process for editing an existing sniper config."""
    query = update.callback_query
    config_name = query.data.replace("edit_config_", "")
    user_id = update.effective_user.id
    config = sniper.snipe_settings.get(user_id, {}).get(config_name)

    if not config:
        await query.edit_message_text("Error: Config not found.")
        return

    # Load existing config into temporary data for editing
    context.user_data["temp_sniper_config"] = config.copy()
    context.user_data["editing_config_name"] = config_name
    await create_sniper_config_editor(update, context, is_new=False)

async def create_sniper_config_editor(update: Update, context: ContextTypes.DEFAULT_TYPE, is_new: bool) -> None:
    """The main editor menu for creating or editing a sniper config."""
    temp_config = context.user_data.get("temp_sniper_config", {})

    keyboard = [
        [InlineKeyboardButton(f"Token Name (Ticker): {temp_config.get("token_name", "Not Set")}", callback_data="set_sniper_token_name")],
        [InlineKeyboardButton(f"Token Issuer: {temp_config.get("token_issuer", "Not Set")}", callback_data="set_sniper_token_issuer")],
        [InlineKeyboardButton(f"Dev Wallet Address: {temp_config.get("dev_wallet_address", "Not Set")}", callback_data="set_sniper_dev_wallet_address")],
        [InlineKeyboardButton(f"💲 Buy Amount XRP: {temp_config.get("buy_amount_xrp", "Not Set")}", callback_data="set_sniper_buy_amount_xrp")],
        [InlineKeyboardButton(f"📉 Slippage: {temp_config.get("slippage", "Not Set")}", callback_data="set_sniper_slippage")],
        [InlineKeyboardButton(f"⛽ Fees: {temp_config.get("fees", "Not Set")}", callback_data="set_sniper_fees")],
        [InlineKeyboardButton(f"🛡️ MEV Protection: {temp_config.get("mev_protection", "Off")}", callback_data="toggle_sniper_mev_protection")],
        [InlineKeyboardButton(f"💡 Tip: {temp_config.get("tip", "Not Set")}", callback_data="set_sniper_tip")],
        [InlineKeyboardButton(f"💼 Wallet: {temp_config.get("wallet_address", "Not Set")}", callback_data="select_sniper_wallet")],
        [InlineKeyboardButton("✅ Save Config", callback_data="save_sniper_config")],
        [InlineKeyboardButton("↩️ Back to Sniper Menu", callback_data="sniper_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    title = "Creating New Sniper Config" if is_new else f"Editing Sniper Config: {context.user_data.get("editing_config_name")}"
    message_text = f"**{title}**\n\nUse the buttons to set the parameters for this config.\n\n`{temp_config}`"

    if update.callback_query:
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode="MarkdownV2")
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode="MarkdownV2")

async def select_sniper_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Allows the user to select a wallet for the sniper config."""
    user_id = update.effective_user.id
    user_wallets = sniper.wallets.get(user_id)

    if not user_wallets or not isinstance(user_wallets, dict):
        await update.callback_query.answer("You have no wallets. Please add one in Settings.", show_alert=True)
        return

    keyboard = []
    for address, wallet_obj in user_wallets.items():
        keyboard.append([InlineKeyboardButton(address, callback_data=f"set_wallet_{address}")])
    
    keyboard.append([InlineKeyboardButton("↩️ Back to Config Editor", callback_data="back_to_editor")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text("Select a wallet to use for this sniper config:", reply_markup=reply_markup)

async def set_sniper_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sets the selected wallet for the temporary sniper config."""
    query = update.callback_query
    wallet_address = query.data.replace("set_wallet_", "")
    
    temp_config = context.user_data.get("temp_sniper_config", {})
    temp_config["wallet_address"] = wallet_address
    context.user_data["temp_sniper_config"] = temp_config
    
    await query.answer(f"Wallet set to {wallet_address}")
    await create_sniper_config_editor(update, context, is_new="editing_config_name" not in context.user_data)

async def save_sniper_config(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompts the user to name and save the config."""
    temp_config = context.user_data.get("temp_sniper_config", {})
    if "wallet_address" not in temp_config or "token_name" not in temp_config or "token_issuer" not in temp_config:
        await update.callback_query.answer("Wallet, Token Name, and Token Issuer are required before saving.", show_alert=True)
        return

    if "editing_config_name" in context.user_data: # It's an existing config
        user_id = update.effective_user.id
        config_name = context.user_data["editing_config_name"]
        user_configs = sniper.snipe_settings.get(user_id, {})
        user_configs[config_name] = temp_config
        sniper.update_snipe_settings(user_id, user_configs)
        await update.callback_query.edit_message_text(f"✅ Config \'{config_name}\' updated successfully!")
        # Clean up
        del context.user_data["temp_sniper_config"]
        del context.user_data["editing_config_name"]
        await asyncio.sleep(2)
        await sniper_menu(update, context)
    else: # It's a new config
        await update.callback_query.edit_message_text("Please enter a name for this new sniper config:")
        context.user_data["awaiting_sniper_config_name"] = True

async def handle_sniper_config_name_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the input for the new sniper config name."""
    user_id = update.effective_user.id
    config_name = update.message.text.strip()
    temp_config = context.user_data.get("temp_sniper_config", {})

    if not config_name:
        await update.message.reply_text("Config name cannot be empty. Please try again.")
        return
    
    user_configs = sniper.snipe_settings.get(user_id, {})
    if config_name in user_configs:
        await update.message.reply_text(f"A config named \'{config_name}\' already exists. Please choose a different name.")
        return

    # Save the config
    temp_config["is_active"] = False # New configs start inactive
    user_configs[config_name] = temp_config
    sniper.update_snipe_settings(user_id, user_configs)

    await update.message.reply_text(f"✅ Sniper config \'{config_name}\' created successfully! It is currently OFF 🔴.")
    # Clean up
    del context.user_data["temp_sniper_config"]
    context.user_data["awaiting_sniper_config_name"] = False
    await asyncio.sleep(2)
    await sniper_menu(update, context) # Return to sniper menu

async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the settings menu."""
    keyboard = [
        [InlineKeyboardButton("💼 Wallet Settings", callback_data="wallet_settings")],
        [InlineKeyboardButton("🛒 General Buy/Sell Settings", callback_data="general_buy_sell_settings")],
        [InlineKeyboardButton("↩️ Back to Main Menu", callback_data="start")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = "Adjust over
(Content truncated due to size limit. Use page ranges or line ranges to read remaining content)
