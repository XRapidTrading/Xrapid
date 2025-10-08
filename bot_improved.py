import logging
import asyncio
import os
import uuid
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# Import functions from xrpl_client.py
from xrpl_client import generate_new_wallet_sync, import_wallet, get_account_info
# Import XRPSniper class
from xrp_sniper_logic_enhanced import XRPSniper

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
        [InlineKeyboardButton("💰 Buy", callback_data="buy_menu")],
        [InlineKeyboardButton("🎯 Sniper", callback_data="sniper_menu")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="settings_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = f"Hi {user.mention_html()}! Welcome to your XRP Sniper Bot. Please choose an option:"

    if update.callback_query:
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode="HTML")
    else:
        await update.message.reply_html(message_text, reply_markup=reply_markup)

async def positions_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the positions menu."""
    keyboard = [
        [InlineKeyboardButton("💰 View My Positions", callback_data="view_positions")],
        [InlineKeyboardButton("↩️ Back to Main Menu", callback_data="start")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = "Here you can view and manage your token positions."
    await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup)

async def buy_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the buy menu and prompts for contract address."""
    keyboard = [
        [InlineKeyboardButton("↩️ Back to Main Menu", callback_data="start")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = "💰 **Buy Token**\n\nPlease paste the token's **Contract Address (CA)** or **Issuer Address** to view details and buy.\n\n_Format: Issuer Address_"
    
    # Set the awaiting input flag
    context.user_data["awaiting_input"] = "buy_token_ca"
    
    await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode="Markdown")

async def process_buy_token_ca(update: Update, context: ContextTypes.DEFAULT_TYPE, ca: str) -> None:
    """Process the contract address and automatically detect issued currencies."""
    user_id = update.effective_user.id
    
    # Validate the address format (basic check)
    if not ca or len(ca) < 25:
        await update.message.reply_text("❌ Invalid address format. Please provide a valid XRPL issuer address.")
        return
    
    # Show loading message
    loading_msg = await update.message.reply_text(f"🔍 Analyzing issuer address...\n`{ca}`\n\nPlease wait...", parse_mode="Markdown")
    
    # Get all currencies issued by this address
    currencies = sniper.get_issued_currencies(ca)
    
    if not currencies or len(currencies) == 0:
        await loading_msg.edit_text(
            f"❌ **No tokens found**\n\n"
            f"The address `{ca}` doesn't appear to have issued any tokens, or the server couldn't retrieve the information.\n\n"
            f"Please verify the issuer address and try again.",
            parse_mode="Markdown"
        )
        context.user_data.pop("awaiting_input", None)
        return
    
    # If only one currency, show buy options directly
    if len(currencies) == 1:
        currency = currencies[0]
        await loading_msg.delete()
        await show_token_buy_options(update, context, currency, ca)
    else:
        # Multiple currencies - let user choose
        keyboard = []
        for currency in sorted(currencies):
            keyboard.append([InlineKeyboardButton(
                f"💰 {currency}", 
                callback_data=f"select_currency_{currency}_{ca}"
            )])
        keyboard.append([InlineKeyboardButton("↩️ Back to Buy Menu", callback_data="buy_menu")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        message_text = f"✅ **Found {len(currencies)} token(s)**\n\n"
        message_text += f"🏦 Issuer: `{ca}`\n\n"
        message_text += "Select a token to buy:"
        
        await loading_msg.edit_text(message_text, reply_markup=reply_markup, parse_mode="Markdown")
    
    context.user_data.pop("awaiting_input", None)

async def show_token_buy_options(update: Update, context: ContextTypes.DEFAULT_TYPE, currency: str, issuer: str) -> None:
    """Show token details and buy preset buttons."""
    user_id = update.effective_user.id
    
    # Get token info from order book
    try:
        offers = sniper.get_order_book("XRP", None, currency, issuer)
        
        if offers:
            first_offer = offers[0]
            taker_gets = first_offer.get("TakerGets")
            taker_pays = first_offer.get("TakerPays")
            
            if isinstance(taker_gets, dict) and isinstance(taker_pays, str):
                token_amount = float(taker_gets.get("value", 0))
                xrp_amount = float(taker_pays) / 1_000_000
                
                if xrp_amount > 0:
                    rate = token_amount / xrp_amount
                    price_info = f"💱 **Price:** {rate:.6f} {currency} per XRP\n"
                    price_info += f"📊 **Available:** {token_amount:.2f} {currency} for {xrp_amount:.2f} XRP\n\n"
                else:
                    price_info = "⚠️ Unable to determine price from order book.\n\n"
            else:
                price_info = "⚠️ Unable to determine price from order book.\n\n"
        else:
            price_info = "⚠️ No active offers found in order book.\n\n"
    except Exception as e:
        logger.error(f"Error fetching token info: {e}")
        price_info = "⚠️ Error fetching token information.\n\n"
    
    # Create buy preset buttons
    keyboard = [
        [InlineKeyboardButton("25 XRP", callback_data=f"execute_buy_{currency}_{issuer}_25")],
        [InlineKeyboardButton("50 XRP", callback_data=f"execute_buy_{currency}_{issuer}_50")],
        [InlineKeyboardButton("100 XRP", callback_data=f"execute_buy_{currency}_{issuer}_100")],
        [InlineKeyboardButton("250 XRP", callback_data=f"execute_buy_{currency}_{issuer}_250")],
        [InlineKeyboardButton("500 XRP", callback_data=f"execute_buy_{currency}_{issuer}_500")],
        [InlineKeyboardButton("🔢 Custom Amount", callback_data=f"custom_buy_{currency}_{issuer}")],
        [InlineKeyboardButton("↩️ Back to Buy Menu", callback_data="buy_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_text = f"💰 **Token Details**\n\n"
    message_text += f"🏷️ **Currency:** {currency}\n"
    message_text += f"🏦 **Issuer:** `{issuer}`\n\n"
    message_text += price_info
    message_text += "Select an amount to buy:"
    
    # Handle both message and callback_query updates
    if update.callback_query:
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode="Markdown")

async def execute_buy_from_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, currency: str, issuer: str, amount_xrp: float) -> None:
    """Execute a buy order from the buy menu."""
    user_id = update.effective_user.id
    
    # Check if user has a wallet
    if user_id not in sniper.wallets:
        await update.callback_query.answer("❌ No wallet configured! Please set up a wallet in Settings first.", show_alert=True)
        return
    
    await update.callback_query.answer(f"🔄 Buying {amount_xrp} XRP worth of {currency}...")
    await update.callback_query.edit_message_text(f"⏳ Processing buy order for {amount_xrp} XRP worth of {currency}...\n\nPlease wait...")
    
    # Get default slippage or use 1%
    default_settings = sniper.default_trade_settings.get(user_id, {})
    slippage = default_settings.get("slippage", 1.0) / 100  # Convert to decimal
    mev_protect = sniper.get_mev_protection_status(user_id)
    
    # Execute the buy order
    success = await sniper._execute_buy_order(user_id, currency, issuer, amount_xrp, slippage, mev_protect)
    
    if success:
        message_text = f"✅ **Buy Order Successful!**\n\n"
        message_text += f"💰 Bought {amount_xrp} XRP worth of {currency}\n"
        message_text += f"🏦 Issuer: `{issuer}`\n\n"
        message_text += "Check your positions to see your new balance!"
    else:
        message_text = f"❌ **Buy Order Failed**\n\n"
        message_text += f"Could not complete the purchase of {currency}.\n"
        message_text += "Please check your wallet balance and try again."
    
    keyboard = [
        [InlineKeyboardButton("💰 View Positions", callback_data="view_positions")],
        [InlineKeyboardButton("🔄 Buy More", callback_data="buy_menu")],
        [InlineKeyboardButton("↩️ Main Menu", callback_data="start")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode="Markdown")

async def custom_buy_amount_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE, currency: str, issuer: str) -> None:
    """Prompt user to enter a custom buy amount."""
    context.user_data["awaiting_input"] = f"custom_buy_amount_{currency}_{issuer}"
    await update.callback_query.edit_message_text(
        f"Please send the amount of XRP you want to spend on {currency}.\n\n_Example: 75, 150, 1000_",
        parse_mode="Markdown"
    )

async def sniper_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the sniper menu with list of saved configs."""
    user_id = update.effective_user.id
    user_configs = sniper.get_user_sniper_configs(user_id)
    
    keyboard = []
    
    # Show saved sniper configs
    if user_configs:
        keyboard.append([InlineKeyboardButton("📋 Your Sniper Configs:", callback_data="noop")])
        for config_id, config in user_configs.items():
            status_emoji = "🟢" if config.get("enabled", False) else "🔴"
            config_name = config.get("name", "Unnamed Config")
            keyboard.append([
                InlineKeyboardButton(
                    f"{status_emoji} {config_name}", 
                    callback_data=f"view_sniper_config_{config_id}"
                )
            ])
    
    # Add new config button
    keyboard.append([InlineKeyboardButton("➕ Create New Sniper Config", callback_data="create_new_sniper_config")])
    keyboard.append([InlineKeyboardButton("↩️ Back to Main Menu", callback_data="start")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = "🎯 Sniper Management\n\nCreate and manage your token sniping configurations."
    await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup)

async def create_new_sniper_config(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start creating a new sniper configuration."""
    user_id = update.effective_user.id
    
    # Generate a new config ID
    config_id = str(uuid.uuid4())[:8]
    
    # Initialize empty config in context
    context.user_data["creating_sniper_config"] = {
        "config_id": config_id,
        "name": "New Sniper Config",
        "ticker": None,
        "coin_name": None,
        "dev_wallet_address": None,
        "buy_amount_xrp": None,
        "slippage": None,
        "max_gas_fee": None,
        "enabled": False
    }
    
    await show_sniper_config_editor(update, context)

async def show_sniper_config_editor(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Shows the sniper configuration editor with all settings."""
    config = context.user_data.get("creating_sniper_config", {})
    
    keyboard = [
        [InlineKeyboardButton(f"📝 Config Name: {config.get('name', 'Not Set')}", callback_data="edit_sniper_name")],
        [InlineKeyboardButton(f"🎯 Ticker: {config.get('ticker', 'Not Set')}", callback_data="edit_ticker")],
        [InlineKeyboardButton(f"🏦 Coin Name: {config.get('coin_name', 'Not Set')[:20] + '...' if config.get('coin_name') else 'Not Set'}", callback_data="edit_coin_name")],
        [InlineKeyboardButton(f"👤 Dev Wallet: {config.get('dev_wallet_address', 'Not Set')[:20] + '...' if config.get('dev_wallet_address') else 'Not Set'}", callback_data="edit_dev_wallet")],
        [InlineKeyboardButton(f"💰 Buy Amount: {config.get('buy_amount_xrp', 'Not Set')} XRP", callback_data="edit_buy_amount")],
        [InlineKeyboardButton(f"📉 Slippage: {config.get('slippage', 'Not Set')}%", callback_data="edit_slippage")],
        [InlineKeyboardButton(f"⛽ Max Gas Fee: {config.get('max_gas_fee', 'Not Set')} XRP", callback_data="edit_max_gas_fee")],
        [InlineKeyboardButton("✅ Save Config", callback_data="save_sniper_config")],
        [InlineKeyboardButton("❌ Cancel", callback_data="sniper_menu")],
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_text = "⚙️ Configure Your Sniper\n\n"
    message_text += f"Name: {config.get('name', 'Not Set')}\n"
    message_text += f"Ticker: {config.get('ticker', 'Not Set')}\n"
    message_text += f"Coin Name: {config.get('coin_name', 'Not Set')}\n"
    message_text += f"Dev Wallet: {config.get('dev_wallet_address', 'Not Set')}\n"
    message_text += f"Buy Amount: {config.get('buy_amount_xrp', 'Not Set')} XRP\n"
    message_text += f"Slippage: {config.get('slippage', 'Not Set')}%\n"
    message_text += f"Max Gas Fee: {config.get('max_gas_fee', 'Not Set')} XRP\n\n"
    message_text += "Click on any field to edit it."
    
    if update.callback_query:
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup)

async def view_sniper_config(update: Update, context: ContextTypes.DEFAULT_TYPE, config_id: str) -> None:
    """View and manage a specific sniper config."""
    user_id = update.effective_user.id
    config = sniper.get_sniper_config(user_id, config_id)
    
    if not config:
        await update.callback_query.answer("Config not found!")
        await sniper_menu(update, context)
        return
    
    status_emoji = "🟢 ON" if config.get("enabled", False) else "🔴 OFF"
    toggle_text = "🔴 Disable" if config.get("enabled", False) else "🟢 Enable"
    
    keyboard = [
        [InlineKeyboardButton(f"{toggle_text}", callback_data=f"toggle_sniper_{config_id}")],
        [InlineKeyboardButton("✏️ Edit Config", callback_data=f"edit_sniper_config_{config_id}")],
        [InlineKeyboardButton("🗑️ Delete Config", callback_data=f"delete_sniper_config_{config_id}")],
        [InlineKeyboardButton("↩️ Back to Sniper Menu", callback_data="sniper_menu")],
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = f"🎯 Sniper Config: {config.get('name', 'Unnamed')}\n\n"
    message_text += f"Status: {status_emoji}\n\n"
    message_text += f"📋 Configuration:\n"
    message_text += f"  • Ticker: {config.get('ticker', 'Not Set')}\n"
    message_text += f"  • Coin Name: {config.get('coin_name', 'Not Set')}\n"
    message_text += f"  • Dev Wallet: {config.get('dev_wallet_address', 'Not Set')}\n"
    message_text += f"  • Buy Amount: {config.get('buy_amount_xrp', 'Not Set')} XRP\n"
    message_text += f"  • Slippage: {config.get('slippage', 'Not Set')}%\n"
    message_text += f"  • Max Gas Fee: {config.get('max_gas_fee', 'Not Set')} XRP\n"
    await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup)

async def toggle_sniper_config(update: Update, context: ContextTypes.DEFAULT_TYPE, config_id: str) -> None:
    """Toggle a sniper config on/off."""
    user_id = update.effective_user.id
    config = sniper.get_sniper_config(user_id, config_id)
    
    if not config:
        await update.callback_query.answer("Config not found!")
        return
    
    # Toggle the enabled status
    new_status = not config.get("enabled", False)
    sniper.update_sniper_config_status(user_id, config_id, new_status)
    
    # If enabling, start the sniper task if not already running
    if new_status and (not sniper.sniper_task or sniper.sniper_task.done()):
        sniper.sniper_task = context.application.create_task(sniper.start_sniper())
    
    status_text = "enabled" if new_status else "disabled"
    await update.callback_query.answer(f"Sniper config {status_text}!")
    
    # Refresh the view
    await view_sniper_config(update, context, config_id)

async def save_sniper_config(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Save the sniper config being created/edited."""
    user_id = update.effective_user.id
    config = context.user_data.get("creating_sniper_config")
    
    if not config:
        await update.callback_query.answer("No config to save!")
        return
    
    # Validate required fields
    required_fields = ["ticker", "coin_name", "buy_amount_xrp", "slippage"]
    missing_fields = [field for field in required_fields if not config.get(field)]
    
    if missing_fields:
        await update.callback_query.answer(f"Please set: {', '.join(missing_fields)}", show_alert=True)
        return
    
    # Save the config
    config_id = config.get("config_id")
    sniper.save_sniper_config(user_id, config_id, config)
    
    # Clear the creation context
    context.user_data.pop("creating_sniper_config", None)
    
    await update.callback_query.answer("Sniper config saved!")
    await sniper_menu(update, context)

async def delete_sniper_config(update: Update, context: ContextTypes.DEFAULT_TYPE, config_id: str) -> None:
    """Delete a sniper config."""
    user_id = update.effective_user.id
    sniper.delete_sniper_config(user_id, config_id)
    
    await update.callback_query.answer("Config deleted!")
    await sniper_menu(update, context)

async def edit_sniper_config(update: Update, context: ContextTypes.DEFAULT_TYPE, config_id: str) -> None:
    """Load a config for editing."""
    user_id = update.effective_user.id
    config = sniper.get_sniper_config(user_id, config_id)
    
    if not config:
        await update.callback_query.answer("Config not found!")
        return
    
    # Load config into context for editing
    context.user_data["creating_sniper_config"] = config.copy()
    await show_sniper_config_editor(update, context)

async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the settings menu."""
    keyboard = [
        [InlineKeyboardButton("💼 Wallet Settings", callback_data="wallet_settings")],
        [InlineKeyboardButton("🛒 Default Buy/Sell Settings", callback_data="buy_sell_settings")],
        [InlineKeyboardButton("🛡️ MEV Protection", callback_data="mev_protection_settings")],
        [InlineKeyboardButton("➕ Buy Presets (XRP)", callback_data="buy_presets_menu")],
        [InlineKeyboardButton("➖ Sell Presets (%)", callback_data="sell_presets_menu")],
        [InlineKeyboardButton("↩️ Back to Main Menu", callback_data="start")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = "⚙️ Settings\n\nAdjust your wallet and default trading settings."
    await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup)

async def wallet_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays wallet management options."""
    keyboard = [
        [InlineKeyboardButton("✨ Generate New Wallet", callback_data="generate_wallet")],
        [InlineKeyboardButton("📥 Import Existing Wallet", callback_data="import_wallet")],
        [InlineKeyboardButton("👁️ View My Wallet", callback_data="my_wallet")],
        [InlineKeyboardButton("↩️ Back to Settings", callback_data="settings_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = "💼 Wallet Management\n\nManage your XRP Ledger wallets."
    await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup)

async def buy_sell_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays default buy/sell configuration options."""
    user_id = update.effective_user.id
    current_settings = sniper.default_trade_settings.get(user_id, {})

    keyboard = [
        [InlineKeyboardButton(f"💲 Default Buy Amount: {current_settings.get('buy_amount_xrp', 'Not Set')} XRP", callback_data="set_default_buy_amount")],
        [InlineKeyboardButton(f"📉 Default Slippage: {current_settings.get('slippage', 'Not Set')}%", callback_data="set_default_slippage")],
        [InlineKeyboardButton(f"⛽ Default Gas Fee: {current_settings.get('max_gas_fee', 'Not Set')} XRP", callback_data="set_default_gas_fee")],
        [InlineKeyboardButton("↩️ Back to Settings", callback_data="settings_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = "🛒 Default Buy/Sell Settings\n\nThese are your default settings for manual trading.\n(Sniper configs have their own separate settings)"
    await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup)

async def mev_protection_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays MEV protection settings."""
    user_id = update.effective_user.id
    mev_enabled = sniper.get_mev_protection_status(user_id)
    status_text = "✅ Enabled" if mev_enabled else "❌ Disabled"
    toggle_text = "❌ Disable MEV Protection" if mev_enabled else "✅ Enable MEV Protection"

    keyboard = [
        [InlineKeyboardButton(f"MEV Protection Status: {status_text}", callback_data="noop")],
        [InlineKeyboardButton(toggle_text, callback_data="toggle_mev_protection")],
        [InlineKeyboardButton("↩️ Back to Settings", callback_data="settings_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = "🛡️ MEV Protection\n\nMinimize front-running and sandwich attacks. Enabling this may slightly increase transaction latency."
    await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup)

async def toggle_mev_protection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggles MEV protection on/off."""
    user_id = update.effective_user.id
    current_status = sniper.get_mev_protection_status(user_id)
    sniper.set_mev_protection(user_id, not current_status)
    await update.callback_query.answer(f"MEV Protection {'enabled' if not current_status else 'disabled'}.")
    await mev_protection_settings(update, context)

async def buy_presets_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays buy presets and options to add/remove them."""
    user_id = update.effective_user.id
    presets = sniper.get_buy_presets(user_id)

    keyboard = []
    if presets:
        keyboard.append([InlineKeyboardButton("Your Buy Presets (XRP):", callback_data="noop")])
        for preset in presets:
            keyboard.append([InlineKeyboardButton(f"{preset} XRP", callback_data=f"remove_buy_preset_{preset}")])
    
    keyboard.append([InlineKeyboardButton("➕ Add New Buy Preset", callback_data="add_buy_preset")],)
    keyboard.append([InlineKeyboardButton("↩️ Back to Settings", callback_data="settings_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = "➕ Buy Presets\n\nTap a preset to remove it. Add new presets in XRP amounts."
    await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup)

async def add_buy_preset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompts user to add a new buy preset."""
    context.user_data["awaiting_input"] = "add_buy_preset"
    await update.callback_query.edit_message_text("Please send the XRP amount for the new buy preset (e.g., 100, 500).")

async def remove_buy_preset(update: Update, context: ContextTypes.DEFAULT_TYPE, amount_xrp: float) -> None:
    """Removes a buy preset."""
    user_id = update.effective_user.id
    sniper.remove_buy_preset(user_id, amount_xrp)
    await update.callback_query.answer(f"Buy preset {amount_xrp} XRP removed.")
    await buy_presets_menu(update, context)

async def sell_presets_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays sell presets and options to add/remove them."""
    user_id = update.effective_user.id
    presets = sniper.get_sell_presets(user_id)

    keyboard = []
    if presets:
        keyboard.append([InlineKeyboardButton("Your Sell Presets (%):", callback_data="noop")])
        for preset in presets:
            keyboard.append([InlineKeyboardButton(f"{preset}%", callback_data=f"remove_sell_preset_{preset}")])
    
    keyboard.append([InlineKeyboardButton("➕ Add New Sell Preset", callback_data="add_sell_preset")])
    keyboard.append([InlineKeyboardButton("↩️ Back to Settings", callback_data="settings_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = "➖ Sell Presets\n\nTap a preset to remove it. Add new presets in percentage amounts."
    await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup)

async def add_sell_preset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompts user to add a new sell preset."""
    context.user_data["awaiting_input"] = "add_sell_preset"
    await update.callback_query.edit_message_text("Please send the percentage for the new sell preset (e.g., 25, 50, 100).")

async def remove_sell_preset(update: Update, context: ContextTypes.DEFAULT_TYPE, percentage: int) -> None:
    """Removes a sell preset."""
    user_id = update.effective_user.id
    sniper.remove_sell_preset(user_id, percentage)
    await update.callback_query.answer(f"Sell preset {percentage}% removed.")
    await sell_presets_menu(update, context)

async def view_positions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the user's current token holdings and provides options to buy/sell."""
    user_id = update.effective_user.id
    wallet = sniper.wallets.get(user_id)
    if not wallet:
        message = "No wallet configured. Please generate or import a wallet in Settings -> Wallet Settings."
        if update.callback_query:
            await update.callback_query.edit_message_text(message)
        else:
            await update.message.reply_text(message)
        return

    account_info = sniper.get_account_info(wallet.classic_address)
    if "error" in account_info:
        message = f"Could not retrieve account info: {account_info['error']}"
        if update.callback_query:
            await update.callback_query.edit_message_text(message)
        else:
            await update.message.reply_text(message)
        return

    balances = account_info.get("account_data", {}).get("balances", [])
    message_text = f"💰 Your Positions\n\nWallet: {wallet.classic_address}\n\n"

    keyboard = []
    if not balances:
        message_text += "No tokens held yet."
    else:
        for balance in balances:
            if isinstance(balance, dict) and "currency" in balance and "value" in balance:
                currency = balance["currency"]
                value = balance["value"]
                issuer = balance.get("issuer", "")
                if currency == "XRP":
                    message_text += f"- XRP: {float(value) / 1_000_000} XRP\n"
                else:
                    message_text += f"- {currency} ({issuer[:4]}...{issuer[-4:]}): {value}\n"
                    # Add buy/sell buttons for each token
                    keyboard.append([
                        InlineKeyboardButton(f"Buy {currency}", callback_data=f"buy_token_{currency}_{issuer}"),
                        InlineKeyboardButton(f"Sell {currency}", callback_data=f"sell_token_{currency}_{issuer}")
                    ])

    keyboard.append([InlineKeyboardButton("🔄 Refresh", callback_data="view_positions")],)
    keyboard.append([InlineKeyboardButton("↩️ Back to Positions Menu", callback_data="positions_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup)

async def buy_token_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, currency: str, issuer: str) -> None:
    """Displays buy options for a specific token."""
    user_id = update.effective_user.id
    buy_presets = sniper.get_buy_presets(user_id)
    default_buy_amount = sniper.default_trade_settings.get(user_id, {}).get("buy_amount_xrp", "Not Set")

    keyboard = []
    if buy_presets:
        keyboard.append([InlineKeyboardButton("Buy Presets (XRP):", callback_data="noop")])
        for preset in buy_presets:
            keyboard.append([InlineKeyboardButton(f"{preset} XRP", callback_data=f"execute_buy_{currency}_{issuer}_{preset}")])
    
    keyboard.append([InlineKeyboardButton(f"Default Buy Amount ({default_buy_amount} XRP)", callback_data=f"execute_buy_{currency}_{issuer}_{default_buy_amount}")])
    keyboard.append([InlineKeyboardButton("Custom Amount", callback_data=f"custom_buy_amount_{currency}_{issuer}")])
    keyboard.append([InlineKeyboardButton("↩️ Back to Positions", callback_data="view_positions")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = f"💰 Buy {currency} ({issuer[:4]}...{issuer[-4:]})\n\nChoose an amount to buy:"
    await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup)

async def custom_buy_amount(update: Update, context: ContextTypes.DEFAULT_TYPE, currency: str, issuer: str) -> None:
    """Prompts user for a custom buy amount."""
    context.user_data["awaiting_input"] = f"custom_buy_amount_{currency}_{issuer}"
    await update.callback_query.edit_message_text(f"Please send the custom XRP amount to buy {currency} ({issuer[:4]}...{issuer[-4:]}).")

async def execute_buy_order(update: Update, context: ContextTypes.DEFAULT_TYPE, currency: str, issuer: str, amount_xrp: float) -> None:
    """Executes a buy order."""
    user_id = update.effective_user.id
    slippage = sniper.default_trade_settings.get(user_id, {}).get("slippage", 0.01) # Default slippage
    mev_protect = sniper.get_mev_protection_status(user_id)

    await update.callback_query.edit_message_text(f"Attempting to buy {amount_xrp} XRP worth of {currency}...")
    success = await sniper._execute_buy_order(user_id, currency, issuer, amount_xrp, slippage, mev_protect)
    
    if success:
        await update.callback_query.edit_message_text(f"✅ Successfully bought {currency}!")
    else:
        await update.callback_query.edit_message_text(f"❌ Failed to buy {currency}. Check logs for details.")
    await asyncio.sleep(2) # Give user time to read message
    await view_positions(update, context)

async def sell_token_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, currency: str, issuer: str) -> None:
    """Displays sell options for a specific token."""
    user_id = update.effective_user.id
    sell_presets = sniper.get_sell_presets(user_id)

    keyboard = []
    if sell_presets:
        keyboard.append([InlineKeyboardButton("Sell Presets (% of holdings):", callback_data="noop")])
        for preset in sell_presets:
            keyboard.append([InlineKeyboardButton(f"{preset}%", callback_data=f"remove_sell_preset_{preset}")])
    
    keyboard.append([InlineKeyboardButton("Custom Percentage", callback_data=f"custom_sell_percentage_{currency}_{issuer}")])
    keyboard.append([InlineKeyboardButton("↩️ Back to Positions", callback_data="view_positions")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = f"➖ Sell {currency} ({issuer[:4]}...{issuer[-4:]})\n\nChoose a percentage of your holdings to sell:"
    await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup)

async def custom_sell_percentage(update: Update, context: ContextTypes.DEFAULT_TYPE, currency: str, issuer: str) -> None:
    """Prompts user for a custom sell percentage."""
    context.user_data["awaiting_input"] = f"custom_sell_percentage_{currency}_{issuer}"
    await update.callback_query.edit_message_text(f"Please send the custom percentage (1-100) of {currency} ({issuer[:4]}...{issuer[-4:]}) to sell.")

async def execute_sell_order(update: Update, context: ContextTypes.DEFAULT_TYPE, currency: str, issuer: str, percentage: int) -> None:
    """Executes a sell order."""
    user_id = update.effective_user.id

    await update.callback_query.edit_message_text(f"Attempting to sell {percentage}% of {currency}...")
    success = await sniper._execute_sell_order(user_id, currency, issuer, percentage)
    
    if success:
        await update.callback_query.edit_message_text(f"✅ Successfully sold {percentage}% of {currency}!")
    else:
        await update.callback_query.edit_message_text(f"❌ Failed to sell {currency}. Check logs for details.")
    await asyncio.sleep(2) # Give user time to read message
    await view_positions(update, context)

async def my_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the user's wallet address and current XRP balance."""
    user_id = update.effective_user.id
    wallet = sniper.wallets.get(user_id)

    if not wallet:
        message = "No wallet configured. Please generate or import a wallet in Settings -> Wallet Settings."
        if update.callback_query:
            await update.callback_query.edit_message_text(message)
        else:
            await update.message.reply_text(message)
        return

    account_info = sniper.get_account_info(wallet.classic_address)
    if "error" in account_info:
        message = f"Could not retrieve account info: {account_info['error']}"
        if update.callback_query:
            await update.callback_query.edit_message_text(message)
        else:
            await update.message.reply_text(message)
        return

    xrp_balance = float(account_info.get("account_data", {}).get("Balance", 0)) / 1_000_000
    message_text = f"💼 Your Wallet\n\nAddress: `{wallet.classic_address}`\nSeed: `{wallet.seed}`\n\nXRP Balance: {xrp_balance} XRP\n\n⚠️ Keep your seed safe! Do not share it with anyone."

    keyboard = [
        [InlineKeyboardButton("↩️ Back to Wallet Settings", callback_data="wallet_settings")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode="MarkdownV2")
    else:
        await update.message.reply_markdown_v2(message_text, reply_markup=reply_markup)

async def generate_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generates a new XRP Ledger wallet for the user."""
    user_id = update.effective_user.id
    
    # Show loading message
    if update.callback_query:
        await update.callback_query.edit_message_text("⏳ Generating wallet... This may take up to 3 minutes if using the faucet.\n\nPlease wait...")
    
    # Generate wallet (tries faucet, falls back to local generation)
    wallet_data = generate_new_wallet_sync()
    
    if "error" in wallet_data:
        error_message = f"❌ Failed to generate wallet: {wallet_data['error']}"
        if update.callback_query:
            await update.callback_query.edit_message_text(error_message)
        else:
            await update.message.reply_text(error_message)
        return
    
    # Store wallet in sniper
    sniper.set_wallet(user_id, wallet_data['seed'])
    
    # Prepare success message
    funded_status = "✅ Funded" if wallet_data.get('funded', False) else "⚠️ Unfunded (please fund manually)"
    message_text = f"✨ **Wallet Generated Successfully!**\n\n"
    message_text += f"📍 **Address:** `{wallet_data['address']}`\n"
    message_text += f"🔑 **Seed:** `{wallet_data['seed']}`\n"
    message_text += f"💰 **Status:** {funded_status}\n\n"
    message_text += f"ℹ️ {wallet_data.get('message', '')}\n\n"
    message_text += f"⚠️ **Keep your seed safe! Do not share it with anyone.**"
    
    keyboard = [
        [InlineKeyboardButton("👁️ View My Wallet", callback_data="my_wallet")],
        [InlineKeyboardButton("↩️ Back to Wallet Settings", callback_data="wallet_settings")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode="Markdown")

async def import_wallet_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompts user to send their wallet seed for import."""
    context.user_data["awaiting_input"] = "import_wallet_seed"
    
    message_text = "📥 **Import Wallet**\n\nPlease send your XRP Ledger wallet seed (secret key).\n\n⚠️ Make sure you're in a private chat and delete the message after importing!"
    
    keyboard = [
        [InlineKeyboardButton("↩️ Cancel", callback_data="wallet_settings")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode="Markdown")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles incoming text messages, especially for awaiting input."""
    user_id = update.effective_user.id
    message_text = update.message.text if update.message else None
    awaiting_input = context.user_data.get("awaiting_input")

    if awaiting_input and message_text:
        try:
            if awaiting_input == "buy_token_ca":
                # Process the contract address (issuer) - auto-detects currencies
                await process_buy_token_ca(update, context, message_text.strip())
            elif awaiting_input == "import_wallet_seed":
                # Import wallet from seed
                seed = message_text.strip()
                wallet_data = import_wallet(seed)
                
                if "error" in wallet_data:
                    await update.message.reply_text(f"❌ Failed to import wallet: {wallet_data['error']}")
                else:
                    # Store wallet in sniper
                    sniper.set_wallet(user_id, seed)
                    
                    message_text = f"✅ **Wallet Imported Successfully!**\n\n"
                    message_text += f"📍 **Address:** `{wallet_data['address']}`\n\n"
                    message_text += f"⚠️ **Please delete your seed message above for security!**"
                    
                    keyboard = [
                        [InlineKeyboardButton("👁️ View My Wallet", callback_data="my_wallet")],
                        [InlineKeyboardButton("↩️ Back to Wallet Settings", callback_data="wallet_settings")],
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode="Markdown")
                
                context.user_data.pop("awaiting_input", None)
            elif awaiting_input.startswith("custom_buy_amount_"):
                # Handle custom buy amount from buy menu
                parts = awaiting_input.replace("custom_buy_amount_", "").split("_", 1)
                if len(parts) == 2:
                    currency = parts[0]
                    issuer = parts[1]
                    amount = float(message_text)
                    if amount <= 0:
                        await update.message.reply_text("Amount must be positive.")
                        return
                    context.user_data.pop("awaiting_input", None)
                    await update.message.reply_text(f"⏳ Processing buy order for {amount} XRP worth of {currency}...")
                    
                    # Get default slippage or use 1%
                    default_settings = sniper.default_trade_settings.get(user_id, {})
                    slippage = default_settings.get("slippage", 1.0) / 100
                    mev_protect = sniper.get_mev_protection_status(user_id)
                    
                    # Execute the buy order
                    success = await sniper._execute_buy_order(user_id, currency, issuer, amount, slippage, mev_protect)
                    
                    if success:
                        await update.message.reply_text(f"✅ Successfully bought {amount} XRP worth of {currency}!")
                    else:
                        await update.message.reply_text(f"❌ Failed to buy {currency}. Check your wallet balance and try again.")
            elif awaiting_input == "add_buy_preset":
                amount = float(message_text)
                if amount <= 0:
                    await update.message.reply_text("Amount must be positive.")
                    return
                sniper.add_buy_preset(user_id, amount)
                await update.message.reply_text(f"✅ Buy preset {amount} XRP added!")
                await buy_presets_menu(update, context)
            elif awaiting_input == "add_sell_preset":
                percentage = int(message_text)
                if not (1 <= percentage <= 100):
                    await update.message.reply_text("Percentage must be between 1 and 100.")
                    return
                sniper.add_sell_preset(user_id, percentage)
                await update.message.reply_text(f"✅ Sell preset {percentage}% added!")
                await sell_presets_menu(update, context)
            elif awaiting_input.startswith("custom_buy_amount_"):
                parts = awaiting_input.split("_")
                currency = parts[2]
                issuer = parts[3]
                amount = float(message_text)
                if amount <= 0:
                    await update.message.reply_text("Amount must be positive.")
                    return
                await update.message.reply_text(f"Buying {amount} XRP worth of {currency}...")
                await execute_buy_order(update, context, currency, issuer, amount)
            elif awaiting_input.startswith("custom_sell_percentage_"):
                parts = awaiting_input.split("_")
                currency = parts[2]
                issuer = parts[3]
                percentage = int(message_text)
                if not (1 <= percentage <= 100):
                    await update.message.reply_text("Percentage must be between 1 and 100.")
                    return
                await update.message.reply_text(f"Selling {percentage}% of {currency}...")
                await execute_sell_order(update, context, currency, issuer, percentage)
            elif awaiting_input == "edit_sniper_name":
                config = context.user_data.get("creating_sniper_config")
                if config:
                    config["name"] = message_text.strip()
                    await update.message.reply_text("✅ Config name set!")
                    await show_sniper_config_editor(update, context)
            elif awaiting_input == "edit_ticker":
                config = context.user_data.get("creating_sniper_config")
                if config:
                    config["ticker"] = message_text.strip().upper()
                    await update.message.reply_text("✅ Ticker set!")
                    await show_sniper_config_editor(update, context)
            elif awaiting_input == "edit_coin_name":
                config = context.user_data.get("creating_sniper_config")
                if config:
                    config["coin_name"] = message_text.strip()
                    await update.message.reply_text("✅ Coin name set!")
                    await show_sniper_config_editor(update, context)

            elif awaiting_input == "edit_dev_wallet":
                config = context.user_data.get("creating_sniper_config")
                if config:
                    config["dev_wallet_address"] = message_text.strip()
                    await update.message.reply_text("✅ Dev wallet set!")
                    await show_sniper_config_editor(update, context)
            elif awaiting_input == "edit_buy_amount":
                config = context.user_data.get("creating_sniper_config")
                if config:
                    amount = float(message_text)
                    if amount <= 0:
                        await update.message.reply_text("Buy amount must be positive.")
                        return
                    config["buy_amount_xrp"] = amount
                    await update.message.reply_text("✅ Buy amount set!")
                    await show_sniper_config_editor(update, context)
            elif awaiting_input == "edit_slippage":
                config = context.user_data.get("creating_sniper_config")
                if config:
                    slippage = float(message_text)
                    if not (0 <= slippage <= 100):
                        await update.message.reply_text("Slippage must be between 0 and 100.")
                        return
                    config["slippage"] = slippage
                    await update.message.reply_text("✅ Slippage set!")
                    await show_sniper_config_editor(update, context)
            elif awaiting_input == "edit_max_gas_fee":
                config = context.user_data.get("creating_sniper_config")
                if config:
                    gas_fee = float(message_text)
                    if gas_fee < 0:
                        await update.message.reply_text("Gas fee cannot be negative.")
                        return
                    config["max_gas_fee"] = gas_fee
                    await update.message.reply_text("✅ Max Gas Fee set!")
                    await show_sniper_config_editor(update, context)
            elif awaiting_input.startswith("set_default_"):
                field_name = awaiting_input.replace("set_default_", "")
                value = float(message_text)
                if field_name == "buy_amount":
                    if value <= 0:
                        await update.message.reply_text("Buy amount must be positive.")
                        return
                    sniper.default_trade_settings.setdefault(user_id, {})["buy_amount_xrp"] = value
                elif field_name == "slippage":
                    if not (0 <= value <= 100):
                        await update.message.reply_text("Slippage must be between 0 and 100.")
                        return
                    sniper.default_trade_settings.setdefault(user_id, {})["slippage"] = value
                elif field_name == "gas_fee":
                    if value < 0:
                        await update.message.reply_text("Gas fee cannot be negative.")
                        return
                    sniper.default_trade_settings.setdefault(user_id, {})["max_gas_fee"] = value
                sniper.save_data()
                await update.message.reply_text(f"✅ Default {field_name.replace('_', ' ')} set!")
                await buy_sell_settings(update, context)
        except ValueError:
            await update.message.reply_text("❌ Invalid input. Please enter a valid number.")
        finally:
            context.user_data.pop("awaiting_input", None)
        return

    # Handle callback queries for dynamic buttons
    if update.callback_query:
        query = update.callback_query
        await query.answer()  # Answer immediately to remove loading state
        data = query.data
        
        if data == "start":
            await start(update, context)
        elif data == "positions_menu":
            await positions_menu(update, context)
        elif data == "buy_menu":
            await buy_menu(update, context)
        elif data.startswith("execute_buy_") and not data.startswith("execute_buy_amount"):
            # Handle execute_buy_{currency}_{issuer}_{amount}
            parts = data.replace("execute_buy_", "").rsplit("_", 1)
            if len(parts) == 2:
                currency_issuer = parts[0]
                amount = float(parts[1])
                # Split currency and issuer
                currency_issuer_parts = currency_issuer.split("_", 1)
                if len(currency_issuer_parts) == 2:
                    currency = currency_issuer_parts[0]
                    issuer = currency_issuer_parts[1]
                    await execute_buy_from_menu(update, context, currency, issuer, amount)
        elif data.startswith("custom_buy_"):
            # Handle custom_buy_{currency}_{issuer}
            parts = data.replace("custom_buy_", "").split("_", 1)
            if len(parts) == 2:
                currency = parts[0]
                issuer = parts[1]
                await custom_buy_amount_prompt(update, context, currency, issuer)
        elif data.startswith("select_currency_"):
            # Handle select_currency_{currency}_{issuer}
            parts = data.replace("select_currency_", "").split("_", 1)
            if len(parts) == 2:
                currency = parts[0]
                issuer = parts[1]
                await show_token_buy_options(update, context, currency, issuer)
        elif data == "sniper_menu":
            await sniper_menu(update, context)
        elif data == "settings_menu":
            await settings_menu(update, context)
        elif data == "wallet_settings":
            await wallet_settings(update, context)
        elif data == "buy_sell_settings":
            await buy_sell_settings(update, context)
        elif data == "mev_protection_settings":
            await mev_protection_settings(update, context)
        elif data == "toggle_mev_protection":
            await toggle_mev_protection(update, context)
        elif data == "buy_presets_menu":
            await buy_presets_menu(update, context)
        elif data == "add_buy_preset":
            await add_buy_preset(update, context)
        elif data.startswith("remove_buy_preset_"):
            amount = float(data.replace("remove_buy_preset_", ""))
            await remove_buy_preset(update, context, amount)
        elif data == "sell_presets_menu":
            await sell_presets_menu(update, context)
        elif data == "add_sell_preset":
            await add_sell_preset(update, context)
        elif data.startswith("remove_sell_preset_"):
            percentage = int(data.replace("remove_sell_preset_", ""))
            await remove_sell_preset(update, context, percentage)
        elif data == "generate_wallet":
            await generate_wallet(update, context)
        elif data == "import_wallet":
            await import_wallet_start(update, context)
        elif data == "my_wallet":
            await my_wallet(update, context)
        elif data == "view_positions":
            await view_positions(update, context)
        elif data.startswith("buy_token_"):
            parts = data.split("_")
            currency = parts[2]
            issuer = parts[3]
            await buy_token_menu(update, context, currency, issuer)
        elif data.startswith("sell_token_"):
            parts = data.split("_")
            currency = parts[2]
            issuer = parts[3]
            await sell_token_menu(update, context, currency, issuer)
        elif data.startswith("execute_buy_"):
            parts = data.split("_")
            currency = parts[2]
            issuer = parts[3]
            amount_xrp = float(parts[4])
            await execute_buy_order(update, context, currency, issuer, amount_xrp)
        elif data.startswith("custom_buy_amount_"):
            parts = data.split("_")
            currency = parts[2]
            issuer = parts[3]
            await custom_buy_amount(update, context, currency, issuer)
        elif data.startswith("execute_sell_"):
            parts = data.split("_")
            currency = parts[2]
            issuer = parts[3]
            percentage = int(parts[4])
            await execute_sell_order(update, context, currency, issuer, percentage)
        elif data.startswith("custom_sell_percentage_"):
            parts = data.split("_")
            currency = parts[2]
            issuer = parts[3]
            await custom_sell_percentage(update, context, currency, issuer)
        elif data == "create_new_sniper_config":
            await create_new_sniper_config(update, context)
        elif data.startswith("view_sniper_config_"):
            config_id = data.replace("view_sniper_config_", "")
            await view_sniper_config(update, context, config_id)
        elif data.startswith("toggle_sniper_"):
            config_id = data.replace("toggle_sniper_", "")
            await toggle_sniper_config(update, context, config_id)
        elif data.startswith("edit_sniper_config_"):
            config_id = data.replace("edit_sniper_config_", "")
            await edit_sniper_config(update, context, config_id)
        elif data.startswith("delete_sniper_config_"):
            config_id = data.replace("delete_sniper_config_", "")
            await delete_sniper_config(update, context, config_id)
        elif data == "save_sniper_config":
            await save_sniper_config(update, context)
        elif data == "edit_sniper_name":
            context.user_data["awaiting_input"] = "edit_sniper_name"
            await query.edit_message_text("Please send the new name for this sniper config.")
        elif data == "edit_ticker":
            context.user_data["awaiting_input"] = "edit_ticker"
            await query.edit_message_text("Please send the ticker (e.g., USD, BTC, MYTOKEN).")
        elif data == "edit_coin_name":
            context.user_data["awaiting_input"] = "edit_coin_name"
            await query.edit_message_text("Please send the coin name (e.g., USD, BTC, MYTOKEN) or the issuer address if it's a custom token.")
        elif data == "edit_dev_wallet":
            context.user_data["awaiting_input"] = "edit_dev_wallet"
            await query.edit_message_text("Please send the developer wallet address to monitor.")
        elif data == "edit_buy_amount":
            context.user_data["awaiting_input"] = "edit_buy_amount"
            await query.edit_message_text("Please send the buy amount in XRP (e.g., 100, 500).")
        elif data == "edit_slippage":
            context.user_data["awaiting_input"] = "edit_slippage"
            await query.edit_message_text("Please send the slippage percentage (e.g., 1, 5).")
        elif data == "edit_max_gas_fee":
            context.user_data["awaiting_input"] = "edit_max_gas_fee"
            await query.edit_message_text("Please send the maximum gas fee in XRP (e.g., 0.1, 0.5).")
        elif data == "set_default_buy_amount":
            context.user_data["awaiting_input"] = "set_default_buy_amount"
            await query.edit_message_text("Please send the default buy amount in XRP (e.g., 100, 500).")
        elif data == "set_default_slippage":
            context.user_data["awaiting_input"] = "set_default_slippage"
            await query.edit_message_text("Please send the default slippage percentage (e.g., 1, 5).")
        elif data == "set_default_gas_fee":
            context.user_data["awaiting_input"] = "set_default_gas_fee"
            await query.edit_message_text("Please send the default max gas fee in XRP (e.g., 0.1, 0.5).")

    # Default message handler
    # await update.message.reply_text("I\\'m not sure what you mean. Use /start to see the menu.")

async def post_init(application: Application) -> None:
    """Runs once after the bot is started and before polling starts."""
    await application.bot.set_my_commands([
        ("start", "Start the bot and show the main menu"),
    ])
    logger.info("Bot commands set successfully!")

def main() -> None:
    """Start the bot."""
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN environment variable not set!")
        return

    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_message))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Application started")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
