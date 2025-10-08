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
    """Displays help information."""
    message_text = (
        "**Help & Information**\n\n"
        "This bot allows you to manage your XRPL wallets, configure a sniper for token launches, "
        "and view your token positions.\n\n"
        "**Main Features:**\n"
        "- **Positions**: View your current token holdings and manage them.\n"
        "- **Sniper**: Set up and monitor automated token sniping configurations.\n"
        "- **Settings**: Adjust general bot parameters, wallet settings, and buy/sell defaults.\n\n"
        "If you encounter any issues or have questions, please refer to the documentation or contact support."
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
    """Displays the sniper menu."""
    user_id = update.effective_user.id
    sniper_status_emoji = "🟢" if sniper.running else "🔴"
    sniper_status_text = "ON" if sniper.running else "OFF"

    keyboard = [
        [InlineKeyboardButton("📝 Create/Edit Config", callback_data="create_sniper_config")],
        [InlineKeyboardButton(f"{sniper_status_emoji} Sniper Status: {sniper_status_text}", callback_data="toggle_sniper_status")],
        [InlineKeyboardButton("↩️ Back to Main Menu", callback_data="start")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = "Manage your sniping configurations and status."
    await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup)

async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the settings menu."""
    keyboard = [
        [InlineKeyboardButton("💼 Wallet Settings", callback_data="wallet_settings")],
        [InlineKeyboardButton("🛒 General Buy/Sell Settings", callback_data="general_buy_sell_settings")],
        [InlineKeyboardButton("↩️ Back to Main Menu", callback_data="start")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = "Adjust overall bot settings."
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
    message_text = "Manage your XRP Ledger wallets."
    await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup)

async def general_buy_sell_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays general buy/sell configuration options."""
    user_id = update.effective_user.id
    # These settings are general, not sniper-specific
    general_settings = context.user_data.get("general_settings", {})

    keyboard = [
        [InlineKeyboardButton(f"💲 Default Buy Amount XRP: {general_settings.get("default_buy_amount_xrp", "Not Set")}", callback_data="set_default_buy_amount_xrp")],
        [InlineKeyboardButton(f"📉 Default Slippage: {general_settings.get("default_slippage", "Not Set")}", callback_data="set_default_slippage")],
        [InlineKeyboardButton(f"🛡️ MEV Protection: {general_settings.get("mev_protection", "Off")}", callback_data="toggle_mev_protection")],
        [InlineKeyboardButton(f"⛽ Default Fees: {general_settings.get("default_fees", "Not Set")}", callback_data="set_default_fees")],
        [InlineKeyboardButton("↩️ Back to Settings", callback_data="settings_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = "Configure your general buying and selling parameters."
    await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup)

async def create_sniper_config(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Allows the user to configure token sniping settings with inline buttons."""
    user_id = update.effective_user.id
    current_sniper_settings = sniper.snipe_settings.get(user_id, {})

    keyboard = [
        [InlineKeyboardButton(f"Target Issuer: {current_sniper_settings.get("target_issuer", "Not Set")}", callback_data="set_sniper_target_issuer")],
        [InlineKeyboardButton(f"Target Currency: {current_sniper_settings.get("target_currency", "Not Set")}", callback_data="set_sniper_target_currency")],
        [InlineKeyboardButton(f"Dev Wallet Address: {current_sniper_settings.get("dev_wallet_address", "Not Set")}", callback_data="set_sniper_dev_wallet_address")],
        [InlineKeyboardButton(f"💲 Buy Amount XRP: {current_sniper_settings.get("buy_amount_xrp", "Not Set")}", callback_data="set_sniper_buy_amount_xrp")],
        [InlineKeyboardButton(f"📉 Slippage: {current_sniper_settings.get("slippage", "Not Set")}", callback_data="set_sniper_slippage")],
        [InlineKeyboardButton(f"⛽ Fees: {current_sniper_settings.get("fees", "Not Set")}", callback_data="set_sniper_fees")],
        [InlineKeyboardButton(f"🛡️ MEV Protection: {current_sniper_settings.get("mev_protection", "Off")}", callback_data="toggle_sniper_mev_protection")],
        [InlineKeyboardButton(f"💡 Tip: {current_sniper_settings.get("tip", "Not Set")}", callback_data="set_sniper_tip")],
        [InlineKeyboardButton("↩️ Back to Sniper Menu", callback_data="sniper_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    message_text = "Configure your sniping settings:\n\n" \
                   f"Current settings: `{current_sniper_settings}`"

    if update.callback_query:
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode="MarkdownV2")
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode="MarkdownV2")

async def toggle_sniper_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggles the sniper's running status."""
    user_id = update.effective_user.id
    if sniper.running:
        await sniper.stop_sniper()
        message = "Sniper is now OFF 🔴."
    else:
        # Ensure sniper is started as a background task
        if not sniper.sniper_task or sniper.sniper_task.done():
            sniper.sniper_task = context.application.create_task(sniper.start_sniper())
        message = "Sniper is now ON 🟢."
    await update.callback_query.answer(message)
    await sniper_menu(update, context) # Refresh the sniper menu

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
        message = f"Could not retrieve account info: {account_info["error"]}"
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
        [InlineKeyboardButton("Sell 5%", callback_data="sell_5_percent"),
         InlineKeyboardButton("Sell 25%", callback_data="sell_25_percent")],
        [InlineKeyboardButton("Sell 50%", callback_data="sell_50_percent"),
         InlineKeyboardButton("Sell 100%", callback_data="sell_100_percent")],
        [InlineKeyboardButton("Refresh", callback_data="view_positions")],
        [InlineKeyboardButton("↩️ Back to Positions Menu", callback_data="positions_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode="MarkdownV2")
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode="MarkdownV2")


async def generate_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles generating a new wallet."""
    await update.callback_query.edit_message_text("Generating new wallet... This may take a moment.")
    # Call the synchronous generate_new_wallet_sync in a separate thread
    new_wallet_data = await context.application.loop.run_in_executor(None, generate_new_wallet_sync)
    if "error" not in new_wallet_data:
        sniper.add_wallet(update.effective_user.id, new_wallet_data)
        await update.callback_query.edit_message_text(
            f"New wallet generated and funded (Testnet):\n"
            f"Address: `{new_wallet_data["address"]}`\n"
            f"Seed: `{new_wallet_data["seed"]}` (SAVE THIS SAFELY!)"
            f"\n\nYour wallet is now set up. Use the menu to view details.", parse_mode="MarkdownV2"
        )
    else:
        await update.callback_query.edit_message_text(f"Error generating wallet: {new_wallet_data["error"]}")

async def import_wallet_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompts the user to enter their wallet seed."""
    await update.callback_query.edit_message_text(
        "Please reply with your wallet seed (sEd...) to import it. "
        "**WARNING: Sharing your seed is risky. Only do this if you understand the risks.**"
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
                f"Your Wallet Address: `{wallet.classic_address}`\n"
                f"XRP Balance: `{account_info.get("account_data", {}).get("Balance")} drops`\n"
                f"(Seed is kept confidential)"
            )
        else:
            message = f"Could not retrieve account info: {account_info["error"]}"
    else:
        message = "No wallet configured. Use the menu to add one."

    if update.callback_query:
        await update.callback_query.edit_message_text(message, parse_mode="MarkdownV2")
    else:
        await update.message.reply_text(message, parse_mode="MarkdownV2")

# --- General Buy/Sell Settings Handlers ---
async def set_default_buy_amount_xrp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.edit_message_text("Please enter the **default** amount of XRP to use for buying tokens:")
    context.user_data["awaiting_default_buy_amount_xrp"] = True

async def set_default_slippage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.edit_message_text("Please enter the **default** slippage percentage (e.g., 0.5 for 0.5%):")
    context.user_data["awaiting_default_slippage"] = True

async def toggle_mev_protection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    general_settings = context.user_data.get("general_settings", {})
    current_mev_status = general_settings.get("mev_protection", "Off")
    new_mev_status = "On" if current_mev_status == "Off" else "Off"
    general_settings["mev_protection"] = new_mev_status
    context.user_data["general_settings"] = general_settings
    await update.callback_query.answer(f"MEV Protection toggled to {new_mev_status}")
    await general_buy_sell_settings(update, context) # Refresh menu

async def set_default_fees(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.edit_message_text("Please enter the **default** transaction fees (e.g., 0.00001 XRP):")
    context.user_data["awaiting_default_fees"] = True

# --- Sniper-Specific Settings Handlers ---
async def set_sniper_buy_amount_xrp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.edit_message_text("Please enter the **sniper-specific** amount of XRP to use for buying tokens:")
    context.user_data["awaiting_sniper_buy_amount_xrp"] = True

async def set_sniper_slippage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.edit_message_text("Please enter the **sniper-specific** slippage percentage (e.g., 0.5 for 0.5%):")
    context.user_data["awaiting_sniper_slippage"] = True

async def set_sniper_fees(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.edit_message_text("Please enter the **sniper-specific** transaction fees (e.g., 0.00001 XRP):")
    context.user_data["awaiting_sniper_fees"] = True

async def toggle_sniper_mev_protection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    current_sniper_settings = sniper.snipe_settings.get(user_id, {})
    current_mev_status = current_sniper_settings.get("mev_protection", "Off")
    new_mev_status = "On" if current_mev_status == "Off" else "Off"
    current_sniper_settings["mev_protection"] = new_mev_status
    sniper.update_snipe_settings(user_id, current_sniper_settings)
    await update.callback_query.answer(f"Sniper MEV Protection toggled to {new_mev_status}")
    await create_sniper_config(update, context) # Refresh menu

async def set_sniper_tip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.edit_message_text("Please enter the **sniper-specific** tip amount (e.g., 0.001 XRP):")
    context.user_data["awaiting_sniper_tip"] = True

async def set_sniper_target_issuer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.edit_message_text("Please enter the **sniper-specific** target issuer address:")
    context.user_data["awaiting_sniper_target_issuer"] = True

async def set_sniper_target_currency(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.edit_message_text("Please enter the **sniper-specific** target currency code (e.g., USD):")
    context.user_data["awaiting_sniper_target_currency"] = True

async def set_sniper_dev_wallet_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.edit_message_text("Please enter the **sniper-specific** developer wallet address:")
    context.user_data["awaiting_sniper_dev_wallet_address"] = True

# --- Sell Percentage Handlers (Placeholder) ---
async def sell_percentage(update: Update, context: ContextTypes.DEFAULT_TYPE, percentage: int) -> None:
    user_id = update.effective_user.id
    wallet = sniper.wallets.get(user_id)
    if not wallet:
        await update.callback_query.edit_message_text("No wallet configured to sell from.")
        return
    
    # In a real implementation, you would fetch the user's token balances
    # and execute a sell order for the specified percentage of a chosen token.
    # For now, this is a placeholder.
    await update.callback_query.edit_message_text(f"Selling {percentage}% of a token (functionality under development).")

async def sell_5_percent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await sell_percentage(update, context, 5)

async def sell_25_percent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await sell_percentage(update, context, 25)

async def sell_50_percent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await sell_percentage(update, context, 50)

async def sell_100_percent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await sell_percentage(update, context, 100)


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles button presses from inline keyboards."""
    query = update.callback_query
    await query.answer()

    if query.data == "start":
        await start(update, context)
    elif query.data == "help_menu":
        await help_menu(update, context)
    elif query.data == "positions_menu":
        await positions_menu(update, context)
    elif query.data == "sniper_menu":
        await sniper_menu(update, context)
    elif query.data == "settings_menu":
        await settings_menu(update, context)
    elif query.data == "wallet_settings":
        await wallet_settings(update, context)
    elif query.data == "general_buy_sell_settings":
        await general_buy_sell_settings(update, context)
    elif query.data == "generate_wallet":
        await generate_wallet(update, context)
    elif query.data == "import_wallet":
        await import_wallet_prompt(update, context)
    elif query.data == "my_wallet":
        await my_wallet(update, context)
    elif query.data == "create_sniper_config":
        await create_sniper_config(update, context)
    elif query.data == "toggle_sniper_status":
        await toggle_sniper_status(update, context)
    elif query.data == "view_positions":
        await view_positions(update, context)
    
    # General Buy/Sell Settings Callbacks
    elif query.data == "set_default_buy_amount_xrp":
        await set_default_buy_amount_xrp(update, context)
    elif query.data == "set_default_slippage":
        await set_default_slippage(update, context)
    elif query.data == "toggle_mev_protection":
        await toggle_mev_protection(update, context)
    elif query.data == "set_default_fees":
        await set_default_fees(update, context)

    # Sniper-Specific Settings Callbacks
    elif query.data == "set_sniper_buy_amount_xrp":
        await set_sniper_buy_amount_xrp(update, context)
    elif query.data == "set_sniper_slippage":
        await set_sniper_slippage(update, context)
    elif query.data == "set_sniper_fees":
        await set_sniper_fees(update, context)
    elif query.data == "toggle_sniper_mev_protection":
        await toggle_sniper_mev_protection(update, context)
    elif query.data == "set_sniper_tip":
        await set_sniper_tip(update, context)
    elif query.data == "set_sniper_target_issuer":
        await set_sniper_target_issuer(update, context)
    elif query.data == "set_sniper_target_currency":
        await set_sniper_target_currency(update, context)
    elif query.data == "set_sniper_dev_wallet_address":
        await set_sniper_dev_wallet_address(update, context)

    # Sell Percentage Callbacks
    elif query.data == "sell_5_percent":
        await sell_5_percent(update, context)
    elif query.data == "sell_25_percent":
        await sell_25_percent(update, context)
    elif query.data == "sell_50_percent":
        await sell_50_percent(update, context)
    elif query.data == "sell_100_percent":
        await sell_100_percent(update, context)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle regular text messages for various inputs."""
    user_id = update.effective_user.id
    message_text = update.message.text

    # --- General Settings Input Handlers ---
    if context.user_data.get("awaiting_seed_input"):
        seed = message_text.strip()
        try:
            imported_wallet = import_wallet(seed)
            if "error" not in imported_wallet:
                sniper.add_wallet(user_id, imported_wallet)
                await update.message.reply_text(
                    f"Wallet imported successfully! Address: `{imported_wallet["address"]}`",
                    parse_mode="MarkdownV2"
                )
            else:
                await update.message.reply_text(f"Error importing wallet: {imported_wallet["error"]}")
        except Exception as e:
            await update.message.reply_text(f"An unexpected error occurred: {e}")
        finally:
            context.user_data["awaiting_seed_input"] = False
            await wallet_settings(update, context) # Return to wallet settings menu

    elif context.user_data.get("awaiting_default_buy_amount_xrp"):
        try:
            buy_amount = float(message_text.strip())
            general_settings = context.user_data.get("general_settings", {})
            general_settings["default_buy_amount_xrp"] = buy_amount
            context.user_data["general_settings"] = general_settings
            await update.message.reply_text(f"Default buy amount set to: {buy_amount} XRP")
        except ValueError:
            await update.message.reply_text("Invalid amount. Please enter a number.")
        finally:
            context.user_data["awaiting_default_buy_amount_xrp"] = False
            await general_buy_sell_settings(update, context) # Return to general buy/sell settings menu

    elif context.user_data.get("awaiting_default_slippage"):
        try:
            slippage = float(message_text.strip())
            general_settings = context.user_data.get("general_settings", {})
            general_settings["default_slippage"] = slippage
            context.user_data["general_settings"] = general_settings
            await update.message.reply_text(f"Default slippage set to: {slippage}%")
        except ValueError:
            await update.message.reply_text("Invalid value. Please enter a number.")
        finally:
            context.user_data["awaiting_default_slippage"] = False
            await general_buy_sell_settings(update, context) # Return to general buy/sell settings menu

    elif context.user_data.get("awaiting_default_fees"):
        try:
            fees = float(message_text.strip())
            general_settings = context.user_data.get("general_settings", {})
            general_settings["default_fees"] = fees
            context.user_data["general_settings"] = general_settings
            await update.message.reply_text(f"Default fees set to: {fees} XRP")
        except ValueError:
            await update.message.reply_text("Invalid value. Please enter a number.")
        finally:
            context.user_data["awaiting_default_fees"] = False
            await general_buy_sell_settings(update, context) # Return to general buy/sell settings menu

    # --- Sniper Settings Input Handlers ---
    elif context.user_data.get("awaiting_sniper_buy_amount_xrp"):
        try:
            buy_amount = float(message_text.strip())
            current_settings = sniper.snipe_settings.get(user_id, {})
            current_settings["buy_amount_xrp"] = buy_amount
            sniper.update_snipe_settings(user_id, current_settings)
            await update.message.reply_text(f"Sniper buy amount set to: {buy_amount} XRP")
        except ValueError:
            await update.message.reply_text("Invalid amount. Please enter a number.")
        finally:
            context.user_data["awaiting_sniper_buy_amount_xrp"] = False
            await create_sniper_config(update, context) # Return to sniper config menu

    elif context.user_data.get("awaiting_sniper_slippage"):
        try:
            slippage = float(message_text.strip())
            current_settings = sniper.snipe_settings.get(user_id, {})
            current_settings["slippage"] = slippage
            sniper.update_snipe_settings(user_id, current_settings)
            await update.message.reply_text(f"Sniper slippage set to: {slippage}%")
        except ValueError:
            await update.message.reply_text("Invalid value. Please enter a number.")
        finally:
            context.user_data["awaiting_sniper_slippage"] = False
            await create_sniper_config(update, context) # Return to sniper config menu

    elif context.user_data.get("awaiting_sniper_fees"):
        try:
            fees = float(message_text.strip())
            current_settings = sniper.snipe_settings.get(user_id, {})
            current_settings["fees"] = fees
            sniper.update_snipe_settings(user_id, current_settings)
            await update.message.reply_text(f"Sniper fees set to: {fees} XRP")
        except ValueError:
            await update.message.reply_text("Invalid value. Please enter a number.")
        finally:
            context.user_data["awaiting_sniper_fees"] = False
            await create_sniper_config(update, context) # Return to sniper config menu

    elif context.user_data.get("awaiting_sniper_tip"):
        try:
            tip = float(message_text.strip())
            current_settings = sniper.snipe_settings.get(user_id, {})
            current_settings["tip"] = tip
            sniper.update_snipe_settings(user_id, current_settings)
            await update.message.reply_text(f"Sniper tip set to: {tip} XRP")
        except ValueError:
            await update.message.reply_text("Invalid value. Please enter a number.")
        finally:
            context.user_data["awaiting_sniper_tip"] = False
            await create_sniper_config(update, context) # Return to sniper config menu

    elif context.user_data.get("awaiting_sniper_target_issuer"):
        current_settings = sniper.snipe_settings.get(user_id, {})
        current_settings["target_issuer"] = message_text.strip()
        sniper.update_snipe_settings(user_id, current_settings)
        await update.message.reply_text(f"Sniper target issuer set to: {message_text.strip()}")
        context.user_data["awaiting_sniper_target_issuer"] = False
        await create_sniper_config(update, context) # Return to sniper config menu

    elif context.user_data.get("awaiting_sniper_target_currency"):
        current_settings = sniper.snipe_settings.get(user_id, {})
        current_settings["target_currency"] = message_text.strip()
        sniper.update_snipe_settings(user_id, current_settings)
        await update.message.reply_text(f"Sniper target currency set to: {message_text.strip()}")
        context.user_data["awaiting_sniper_target_currency"] = False
        await create_sniper_config(update, context) # Return to sniper config menu

    elif context.user_data.get("awaiting_sniper_dev_wallet_address"):
        current_settings = sniper.snipe_settings.get(user_id, {})
        current_settings["dev_wallet_address"] = message_text.strip()
        sniper.update_snipe_settings(user_id, current_settings)
        await update.message.reply_text(f"Sniper dev wallet address set to: {message_text.strip()}")
        context.user_data["awaiting_sniper_dev_wallet_address"] = False
        await create_sniper_config(update, context) # Return to sniper config menu

    else:
        # Handle pasted contract addresses
        # This is a simplified example. You might want to add more robust CA validation.
        if len(message_text.strip()) > 30: # Simple check for a potential contract address
            # Here you would add logic to display buy/sell options for the pasted CA
            await update.message.reply_text(f"Pasted address detected: {message_text.strip()}\n(Buy/Sell functionality for pasted addresses is under development)")
        else:
            await update.message.reply_text("I'm not sure what you mean. Use the menu to see available actions.")

async def post_init(application: Application) -> None:
    """Runs once after the bot is started and before polling starts."""
    await application.bot.set_my_commands([
        ("start", "Start the bot and show the main menu"),
        ("help", "Show help information"),
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
    application.add_handler(CommandHandler("help", help_menu)) # Add handler for /help command
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Application started")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
