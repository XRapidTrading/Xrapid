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
        "target_currency": None,
        "target_issuer": None,
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
        [InlineKeyboardButton(f"🎯 Target Currency: {config.get('target_currency', 'Not Set')}", callback_data="edit_target_currency")],
        [InlineKeyboardButton(f"🏦 Target Issuer: {config.get('target_issuer', 'Not Set')[:20] + '...' if config.get('target_issuer') else 'Not Set'}", callback_data="edit_target_issuer")],
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
    message_text += f"Target Currency: {config.get('target_currency', 'Not Set')}\n"
    message_text += f"Target Issuer: {config.get('target_issuer', 'Not Set')}\n"
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
    message_text += f"  • Target Currency: {config.get('target_currency', 'Not Set')}\n"
    message_text += f"  • Target Issuer: {config.get('target_issuer', 'Not Set')}\n"
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
    required_fields = ["target_currency", "buy_amount_xrp", "slippage"]
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

    account_info = get_account_info(wallet.classic_address)
    if "error" in account_info:
        message = f"Could not retrieve account info: {account_info['error']}"
        if update.callback_query:
            await update.callback_query.edit_message_text(message)
        else:
            await update.message.reply_text(message)
        return

    balances = account_info.get("account_data", {}).get("balances", [])
    message_text = f"💰 Your Positions\n\nWallet: {wallet.classic_address}\n\n"

    if not balances:
        message_text += "No tokens held yet."
    else:
        for balance in balances:
            if isinstance(balance, dict) and "currency" in balance and "value" in balance:
                currency = balance["currency"]
                value = balance["value"]
                issuer = balance.get("issuer", "")
                if currency == "XRP":
                    message_text += f"- XRP: {value} drops\n"
                else:
                    message_text += f"- {currency} ({issuer[:10]}...): {value}\n"

    keyboard = [
        [InlineKeyboardButton("🔄 Refresh", callback_data="view_positions")],
        [InlineKeyboardButton("↩️ Back to Positions Menu", callback_data="positions_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup)

async def generate_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles generating a new wallet."""
    await update.callback_query.edit_message_text("Generating new wallet... This may take a moment.")
    new_wallet_data = await context.application.loop.run_in_executor(None, generate_new_wallet_sync)
    if "error" not in new_wallet_data:
        sniper.add_wallet(update.effective_user.id, new_wallet_data)
        await update.callback_query.edit_message_text(
            f"✅ New wallet generated and funded (Testnet):\n\n"
            f"Address: {new_wallet_data['address']}\n"
            f"Seed: {new_wallet_data['seed']}\n\n"
            f"⚠️ SAVE THIS SEED SAFELY!\n\n"
            f"Your wallet is now set up. Use the menu to view details."
        )
    else:
        await update.callback_query.edit_message_text(f"❌ Error generating wallet: {new_wallet_data['error']}")

async def import_wallet_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompts the user to enter their wallet seed."""
    await update.callback_query.edit_message_text(
        "Please reply with your wallet seed (sEd...) to import it.\n\n"
        "⚠️ WARNING: Sharing your seed is risky. Only do this if you understand the risks."
    )
    context.user_data["awaiting_seed_input"] = True

async def my_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the user's connected wallet details."""
    user_id = update.effective_user.id
    wallet = sniper.wallets.get(user_id)
    if wallet:
        account_info = get_account_info(wallet.classic_address)
        if "error" not in account_info:
            message = (
                f"💼 Your Wallet\n\n"
                f"Address: {wallet.classic_address}\n"
                f"XRP Balance: {account_info.get('account_data', {}).get('Balance')} drops\n\n"
                f"(Seed is kept confidential)"
            )
        else:
            message = f"Could not retrieve account info: {account_info['error']}"
    else:
        message = "No wallet configured. Use the menu to add one."

    if update.callback_query:
        await update.callback_query.edit_message_text(message)
    else:
        await update.message.reply_text(message)

# Prompt handlers for editing sniper config fields
async def prompt_edit_field(update: Update, context: ContextTypes.DEFAULT_TYPE, field_name: str, prompt_text: str) -> None:
    """Generic function to prompt user for field input."""
    await update.callback_query.edit_message_text(prompt_text)
    context.user_data["editing_field"] = field_name

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles button presses from inline keyboards."""
    query = update.callback_query
    await query.answer()

    if query.data == "start":
        await start(update, context)
    elif query.data == "positions_menu":
        await positions_menu(update, context)
    elif query.data == "sniper_menu":
        await sniper_menu(update, context)
    elif query.data == "settings_menu":
        await settings_menu(update, context)
    elif query.data == "wallet_settings":
        await wallet_settings(update, context)
    elif query.data == "buy_sell_settings":
        await buy_sell_settings(update, context)
    elif query.data == "generate_wallet":
        await generate_wallet(update, context)
    elif query.data == "import_wallet":
        await import_wallet_prompt(update, context)
    elif query.data == "my_wallet":
        await my_wallet(update, context)
    elif query.data == "view_positions":
        await view_positions(update, context)
    elif query.data == "create_new_sniper_config":
        await create_new_sniper_config(update, context)
    elif query.data == "save_sniper_config":
        await save_sniper_config(update, context)
    elif query.data.startswith("view_sniper_config_"):
        config_id = query.data.replace("view_sniper_config_", "")
        await view_sniper_config(update, context, config_id)
    elif query.data.startswith("toggle_sniper_"):
        config_id = query.data.replace("toggle_sniper_", "")
        await toggle_sniper_config(update, context, config_id)
    elif query.data.startswith("delete_sniper_config_"):
        config_id = query.data.replace("delete_sniper_config_", "")
        await delete_sniper_config(update, context, config_id)
    elif query.data.startswith("edit_sniper_config_"):
        config_id = query.data.replace("edit_sniper_config_", "")
        await edit_sniper_config(update, context, config_id)
    elif query.data == "edit_sniper_name":
        await prompt_edit_field(update, context, "name", "Enter a name for this sniper config:")
    elif query.data == "edit_target_currency":
        await prompt_edit_field(update, context, "target_currency", "Enter the target currency code (e.g., USD, BTC):")
    elif query.data == "edit_target_issuer":
        await prompt_edit_field(update, context, "target_issuer", "Enter the target issuer address:")
    elif query.data == "edit_dev_wallet":
        await prompt_edit_field(update, context, "dev_wallet_address", "Enter the developer wallet address:")
    elif query.data == "edit_buy_amount":
        await prompt_edit_field(update, context, "buy_amount_xrp", "Enter the buy amount in XRP:")
    elif query.data == "edit_slippage":
        await prompt_edit_field(update, context, "slippage", "Enter the slippage percentage (e.g., 0.5 for 0.5%):")
    elif query.data == "edit_max_gas_fee":
        await prompt_edit_field(update, context, "max_gas_fee", "Enter the maximum gas fee in XRP:")
    elif query.data == "set_default_buy_amount":
        await prompt_edit_field(update, context, "default_buy_amount_xrp", "Enter the default buy amount in XRP:")
    elif query.data == "set_default_slippage":
        await prompt_edit_field(update, context, "default_slippage", "Enter the default slippage percentage:")
    elif query.data == "set_default_gas_fee":
        await prompt_edit_field(update, context, "default_max_gas_fee", "Enter the default max gas fee in XRP:")
    elif query.data == "noop":
        pass  # Do nothing for header buttons

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle regular text messages for various inputs."""
    user_id = update.effective_user.id
    message_text = update.message.text

    # Handle wallet seed import
    if context.user_data.get("awaiting_seed_input"):
        seed = message_text.strip()
        try:
            imported_wallet = import_wallet(seed)
            if "error" not in imported_wallet:
                sniper.add_wallet(user_id, imported_wallet)
                await update.message.reply_text(
                    f"✅ Wallet imported successfully!\n\nAddress: {imported_wallet['address']}"
                )
            else:
                await update.message.reply_text(f"❌ Error importing wallet: {imported_wallet['error']}")
        except Exception as e:
            await update.message.reply_text(f"❌ An unexpected error occurred: {e}")
        finally:
            context.user_data["awaiting_seed_input"] = False
        return

    # Handle sniper config field editing
    if context.user_data.get("editing_field"):
        field_name = context.user_data["editing_field"]
        config = context.user_data.get("creating_sniper_config")
        
        if not config:
            await update.message.reply_text("❌ No config being edited. Please start over.")
            context.user_data.pop("editing_field", None)
            return
        
        # Process the input based on field type
        try:
            if field_name in ["buy_amount_xrp", "slippage", "max_gas_fee", "default_buy_amount_xrp", "default_slippage", "default_max_gas_fee"]:
                # Numeric fields
                value = float(message_text.strip())
                
                if field_name.startswith("default_"):
                    # Update default settings
                    actual_field = field_name.replace("default_", "")
                    if user_id not in sniper.default_trade_settings:
                        sniper.default_trade_settings[user_id] = {}
                    sniper.default_trade_settings[user_id][actual_field] = value
                    sniper.save_data()
                    await update.message.reply_text(f"✅ Default {actual_field} set to: {value}")
                    # Return to settings menu
                    keyboard = [[InlineKeyboardButton("↩️ Back to Settings", callback_data="buy_sell_settings")]]
                    await update.message.reply_text("Done!", reply_markup=InlineKeyboardMarkup(keyboard))
                else:
                    config[field_name] = value
                    await update.message.reply_text(f"✅ {field_name} set to: {value}")
                    await show_sniper_config_editor(update, context)
            else:
                # Text fields
                if field_name.startswith("default_"):
                    await update.message.reply_text("❌ Invalid field for text input")
                else:
                    config[field_name] = message_text.strip()
                    await update.message.reply_text(f"✅ {field_name} set!")
                    await show_sniper_config_editor(update, context)
        except ValueError:
            await update.message.reply_text("❌ Invalid input. Please enter a valid number.")
            return
        finally:
            context.user_data.pop("editing_field", None)
        return

    # Default message handler
    await update.message.reply_text("I'm not sure what you mean. Use /start to see the menu.")

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
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Application started")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
