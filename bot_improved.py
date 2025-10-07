import logging
import asyncio
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from xrpl_client import generate_new_wallet, import_wallet, get_account_info
from xrp_sniper_logic_improved import XRPSniper

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx" ).setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Global sniper instance
sniper = XRPSniper()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued, displaying a main menu."""
    user = update.effective_user
    keyboard = [
        [InlineKeyboardButton("Setup Wallet", callback_data="setup_wallet")],
        [InlineKeyboardButton("Snipe Settings", callback_data="snipe_settings")],
        [InlineKeyboardButton("Start Snipe", callback_data="start_snipe")],
        [InlineKeyboardButton("Stop Snipe", callback_data="stop_snipe")],
        [InlineKeyboardButton("My Wallet", callback_data="my_wallet")],
        [InlineKeyboardButton("My Settings", callback_data="my_settings")],
        [InlineKeyboardButton("My Positions", callback_data="my_positions")],
        [InlineKeyboardButton("Help", callback_data="help")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = f"Hi {user.mention_html()}! I am your XRP Sniper Bot. Please choose an option:"

    if update.callback_query:
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode="HTML")
    else:
        await update.message.reply_html(message_text, reply_markup=reply_markup)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    help_text = (
        "Available commands:\n"
        "/start - Start the bot\n"
        "/help - Show this help message\n"
        "/setup_wallet - Set up your XRP Ledger wallet\n"
        "/snipe_settings - Configure your token sniping settings\n"
        "/start_snipe - Start the automated sniping process\n"
        "/stop_snipe - Stop the automated sniping process\n"
        "/my_wallet - View your connected wallet details\n"
        "/my_settings - View your current sniping settings"
    )
    if update.callback_query:
        await update.callback_query.edit_message_text(help_text)
    else:
        await update.message.reply_text(help_text)

async def setup_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Allows the user to set up their XRP Ledger wallet with inline buttons."""
    keyboard = [
        [InlineKeyboardButton("Generate New Wallet", callback_data="generate_wallet")],
        [InlineKeyboardButton("Import Existing Wallet (Seed)", callback_data="import_wallet")],
        [InlineKeyboardButton("Back to Main Menu", callback_data="start")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = "How would you like to set up your wallet?"
    if update.callback_query:
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup)


async def snipe_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Allows the user to configure token sniping settings with inline buttons."""
    user_id = update.effective_user.id
    current_settings = sniper.snipe_settings.get(user_id, {})

    keyboard = [
        [InlineKeyboardButton(f"Buy Amount XRP: {current_settings.get("buy_amount_xrp", "Not Set")}", callback_data="set_buy_amount_xrp")],
        [InlineKeyboardButton(f"Slippage: {current_settings.get("slippage", "Not Set")}", callback_data="set_slippage")],
        [InlineKeyboardButton(f"Target Issuer: {current_settings.get("target_issuer", "Not Set")}", callback_data="set_target_issuer")],
        [InlineKeyboardButton(f"Target Currency: {current_settings.get("target_currency", "Not Set")}", callback_data="set_target_currency")],
        [InlineKeyboardButton(f"Dev Wallet Address: {current_settings.get("dev_wallet_address", "Not Set")}", callback_data="set_dev_wallet_address")],
        [InlineKeyboardButton(f"AFK Mode: {"Active" if current_settings.get("afk_mode") else "Inactive"}", callback_data="toggle_afk_mode")],
        [InlineKeyboardButton("Back to Main Menu", callback_data="start")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    message_text = "Configure your sniping settings:\n\n" \
                   f"Current settings: `{current_settings}`"

    if update.callback_query:
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode="MarkdownV2")
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode="MarkdownV2")


async def handle_specific_snipe_setting_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles user input for a specific snipe setting."""
    user_id = update.effective_user.id
    setting_key = context.user_data.get("awaiting_specific_snipe_setting")
    if not setting_key:
        return

    value = update.message.text.strip()
    current_settings = sniper.snipe_settings.get(user_id, {})

    try:
        if value.lower() == 'none':
            current_settings[setting_key] = None
        elif setting_key == 'buy_amount_xrp' or setting_key == 'slippage':
            current_settings[setting_key] = float(value)
        elif setting_key == 'afk_mode':
            current_settings[setting_key] = value.lower() == 'true'
        else:
            current_settings[setting_key] = value
        
        sniper.update_snipe_settings(user_id, current_settings)
        await update.message.reply_text(f"{setting_key.replace('_', ' ').title()} updated successfully!")
    except ValueError:
        await update.message.reply_text(f"Invalid value for {setting_key.replace('_', ' ').title()}. Please enter a valid number or 'None'.")
    except Exception as e:
        await update.message.reply_text(f"Error updating {setting_key.replace('_', ' ').title()}: {e}")
    finally:
        context.user_data["awaiting_specific_snipe_setting"] = None
        await snipe_settings(update, context)

async def start_snipe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Starts the automated sniping process."""
    user_id = update.effective_user.id
    if user_id not in sniper.wallets:
        message = "Please set up your wallet first using /setup_wallet."
        if update.callback_query:
            await update.callback_query.edit_message_text(message)
        else:
            await update.message.reply_text(message)
        return
    if not sniper.snipe_settings.get(user_id, {}).get("afk_mode"):
        message = "AFK mode is not enabled in your settings. Please configure it using /snipe_settings."
        if update.callback_query:
            await update.callback_query.edit_message_text(message)
        else:
            await update.message.reply_text(message)
        return
    
    # Check if sniper is already running
    if sniper.running:
        message = "Sniper is already running!"
        if update.callback_query:
            await update.callback_query.edit_message_text(message)
        else:
            await update.message.reply_text(message)
        return
    
    # Start sniper in background task
    sniper.sniper_task = context.application.create_task(sniper.start_sniper())
    
    message = "Automated sniping started! I will notify you of any snipes."
    if update.callback_query:
        await update.callback_query.edit_message_text(message)
    else:
        await update.message.reply_text(message)

async def stop_snipe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Stops the automated sniping process."""
    if not sniper.running:
        message = "Sniper is not currently running."
        if update.callback_query:
            await update.callback_query.edit_message_text(message)
        else:
            await update.message.reply_text(message)
        return
    
    # Stop the sniper
    await sniper.stop_sniper()
    
    message = "Automated sniping stopped successfully."
    if update.callback_query:
        await update.callback_query.edit_message_text(message)
    else:
        await update.message.reply_text(message)

async def my_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the user's connected wallet details."""
    user_id = update.effective_user.id
    wallet = sniper.wallets.get(user_id)
    if wallet:
        account_info = get_account_info(wallet.classic_address)
        if "error" not in account_info:
            message = (
                f"Your Wallet Address: `{wallet.classic_address}`\n"
                f"XRP Balance: `{account_info.get('account_data', {}).get('Balance')} drops`\n"
                f"(Seed is kept confidential)"
            )
        else:
            message = f"Could not retrieve account info: {account_info['error']}"
    else:
        message = "No wallet configured. Use /setup_wallet to add one."

    if update.callback_query:
        await update.callback_query.edit_message_text(message, parse_mode="MarkdownV2")
    else:
        await update.message.reply_text(message, parse_mode="MarkdownV2")

async def my_positions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the user's current token holdings and provides options to buy/sell."""
    user_id = update.effective_user.id
    wallet = sniper.wallets.get(user_id)
    if not wallet:
        message = "No wallet configured. Use /setup_wallet to add one."
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
    message_text = f"Your current positions for wallet `{wallet.classic_address}`:\n\n"

    if not balances:
        message_text += "No tokens held yet."
    else:
        for balance in balances:
            if isinstance(balance, dict) and "currency" in balance and "value" in balance:
                currency = balance["currency"]
                value = balance["value"]
                issuer = balance.get("issuer", "")
                if currency == "XRP":
                    message_text += f"- XRP: `{value}` drops\n"
                else:
                    message_text += f"- {currency} ({issuer}): `{value}`\n"

    keyboard = [
        [InlineKeyboardButton("Buy Token", callback_data="positions_buy")],
        [InlineKeyboardButton("Sell Token", callback_data="positions_sell")],
        [InlineKeyboardButton("Refresh", callback_data="my_positions")],
        [InlineKeyboardButton("Back to Main Menu", callback_data="start")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode="MarkdownV2")
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode="MarkdownV2")


async def buy_token(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompts the user for details to buy a token."""
    message_text = "Please enter the details for the token you want to buy in the format: `CURRENCY, ISSUER, AMOUNT` (e.g., `USD, rPEPPER7gfohRMQA9rEPFuZQhQ5U2qP4L, 100`)."
    if update.callback_query:
        await update.callback_query.edit_message_text(message_text, parse_mode="MarkdownV2")
    else:
        await update.message.reply_text(message_text, parse_mode="MarkdownV2")
    context.user_data["awaiting_buy_token_input"] = True

async def sell_token(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompts the user for details to sell a token."""
    message_text = "Please enter the details for the token you want to sell in the format: `CURRENCY, ISSUER, AMOUNT` (e.g., `USD, rPEPPER7gfohRMQA9rEPFuZQhQ5U2qP4L, 100`)."
    if update.callback_query:
        await update.callback_query.edit_message_text(message_text, parse_mode="MarkdownV2")
    else:
        await update.message.reply_text(message_text, parse_mode="MarkdownV2")
    context.user_data["awaiting_sell_token_input"] = True

async def my_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the user's current sniping settings."""
    user_id = update.effective_user.id
    settings = sniper.snipe_settings.get(user_id)
    if settings:
        message = f"Your current sniping settings: `{settings}`"
    else:
        message = "No sniping settings configured. Use /snipe_settings to add them."

    if update.callback_query:
        await update.callback_query.edit_message_text(message, parse_mode="MarkdownV2")
    else:
        await update.message.reply_text(message, parse_mode="MarkdownV2")

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles button presses from inline keyboards."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id

    if query.data == "start":
        await start(update, context)
    elif query.data == "generate_wallet":
        new_wallet_data = await generate_new_wallet()
        if "error" not in new_wallet_data:
            sniper.add_wallet(user_id, new_wallet_data)
            await query.edit_message_text(
                f"New wallet generated and funded (Testnet):\n"
                f"Address: `{new_wallet_data['address']}`\n"
                f"Seed: `{new_wallet_data['seed']}` (SAVE THIS SAFELY!)\""
                f"\n\nYour wallet is now set up. Use /my_wallet to view details.", parse_mode="MarkdownV2"
            )
        else:
            await query.edit_message_text(f"Error generating wallet: {new_wallet_data['error']}")
    elif query.data == "import_wallet":
        await query.edit_message_text(
            "Please reply with your wallet seed (sEd...) to import it. "
            "**WARNING: Sharing your seed is risky. Only do this if you understand the risks.**"
        )
        context.user_data["awaiting_seed_input"] = True
    elif query.data.startswith("set_"):
        setting_key = query.data[len("set_"):]
        await query.edit_message_text(f"Please enter the new value for {setting_key.replace('_', ' ')}: (Type 'None' to clear)")
        context.user_data["awaiting_specific_snipe_setting"] = setting_key
    elif query.data == "toggle_afk_mode":
        current_settings = sniper.snipe_settings.get(user_id, {})
        new_afk_mode = not current_settings.get("afk_mode", False)
        current_settings["afk_mode"] = new_afk_mode
        sniper.update_snipe_settings(user_id, current_settings)
        await query.answer(f"AFK Mode set to {new_afk_mode}")
        await snipe_settings(update, context) # Refresh settings menu
    elif query.data == "setup_wallet":
        await setup_wallet(update, context)
    elif query.data == "snipe_settings":
        await snipe_settings(update, context)
    elif query.data == "start_snipe":
        await start_snipe(update, context)
    elif query.data == "stop_snipe":
        await stop_snipe(update, context)
    elif query.data == "my_wallet":
        await my_wallet(update, context)
    elif query.data == "my_settings":
        await my_settings(update, context)
    elif query.data == "my_positions":
        await my_positions(update, context)
    elif query.data == "positions_buy":
        await buy_token(update, context)
    elif query.data == "positions_sell":
        await sell_token(update, context)
    elif query.data == "help":
        await help_command(update, context)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle regular text messages for various inputs."""
    user_id = update.effective_user.id
    message_text = update.message.text

    if context.user_data.get("awaiting_seed_input"):
        seed = message_text.strip()
        try:
            imported_wallet = await import_wallet(seed)
            if "error" not in imported_wallet:
                sniper.add_wallet(user_id, imported_wallet)
                await update.message.reply_text(
                    f"Wallet imported successfully! Address: `{imported_wallet['address']}`",
                    parse_mode="MarkdownV2"
                )
            else:
                await update.message.reply_text(f"Error importing wallet: {imported_wallet['error']}")
        except Exception as e:
            await update.message.reply_text(f"An unexpected error occurred: {e}")
        finally:
            context.user_data["awaiting_seed_input"] = False

    elif context.user_data.get("awaiting_specific_snipe_setting"):
        await handle_specific_snipe_setting_input(update, context)

    elif context.user_data.get("awaiting_buy_token_input"):
        # Logic to handle buy token input
        # Example: parse message_text and execute buy
        await update.message.reply_text("Buy functionality is being processed...")
        context.user_data["awaiting_buy_token_input"] = False

    elif context.user_data.get("awaiting_sell_token_input"):
        # Logic to handle sell token input
        # Example: parse message_text and execute sell
        await update.message.reply_text("Sell functionality is being processed...")
        context.user_data["awaiting_sell_token_input"] = False
    else:
        await update.message.reply_text("I'm not sure what you mean. Use the menu to see available actions.")

async def post_init(application: Application) -> None:
    """Runs once after the bot is started and before polling starts."""
    await application.bot.set_my_commands([
        ("start", "Start the bot and show the main menu"),
        ("help", "Show the help message"),
        ("setup_wallet", "Set up your XRP Ledger wallet"),
        ("snipe_settings", "Configure your token sniping settings"),
        ("start_snipe", "Start the automated sniping process"),
        ("stop_snipe", "Stop the automated sniping process"),
        ("my_wallet", "View your connected wallet details"),
        ("my_settings", "View your current sniping settings"),
        ("my_positions", "View your current token holdings"),
    ])
    logger.info("Bot commands set successfully!")

def main() -> None:
    """Start the bot."""
    # Get the bot token from environment variables
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN environment variable not set!")
        return

    # Create the Application and pass it your bot's token.
    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("setup_wallet", setup_wallet))
    application.add_handler(CommandHandler("snipe_settings", snipe_settings))
    application.add_handler(CommandHandler("start_snipe", start_snipe))
    application.add_handler(CommandHandler("stop_snipe", stop_snipe))
    application.add_handler(CommandHandler("my_wallet", my_wallet))
    application.add_handler(CommandHandler("my_settings", my_settings))
    application.add_handler(CommandHandler("my_positions", my_positions))

    # Callback query handler for inline buttons
    application.add_handler(CallbackQueryHandler(button))

    # Message handler for text inputs
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
