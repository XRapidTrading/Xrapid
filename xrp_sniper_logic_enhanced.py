import asyncio
import json
import websockets
import os
from xrpl.clients import JsonRpcClient
from xrpl.models import Payment, TrustSet, IssuedCurrencyAmount, OfferCreate
from xrpl.transaction import submit_and_wait
from xrpl.wallet import Wallet
import xrpl
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
JSON_RPC_URL = "https://s.altnet.rippletest.net:51234/"  # Using testnet for development
WEBSOCKET_URL = "wss://s.altnet.rippletest.net:51233/"  # Using testnet for development
client = JsonRpcClient(JSON_RPC_URL)

class XRPSniper:
    def __init__(self, data_file="sniper_data.json"):
        self.data_file = data_file
        self.wallets = {}
        self.sniper_configs = {}  # Structure: {user_id: {config_id: config_dict}}
        self.default_trade_settings = {}  # Default settings for manual trading
        self.mev_protection_settings = {} # MEV protection settings
        self.buy_presets = {} # Buy presets for each user
        self.sell_presets = {} # Sell presets for each user
        self.running = False
        self.sniper_task = None
        self.ws = None
        self.load_data()

    def load_data(self):
        """Load wallets, sniper configs, and settings from file."""
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r') as f:
                    data = json.load(f)
                    
                    # Reconstruct wallets from seeds
                    for user_id, wallet_data in data.get('wallets', {}).items():
                        self.wallets[int(user_id)] = Wallet(wallet_data['seed'], 0)
                    
                    # Load sniper configs
                    self.sniper_configs = {
                        int(user_id): configs 
                        for user_id, configs in data.get('sniper_configs', {}).items()
                    }
                    
                    # Load default trade settings
                    self.default_trade_settings = {
                        int(k): v for k, v in data.get('default_trade_settings', {}).items()
                    }
                    
                    # Load MEV protection settings
                    self.mev_protection_settings = {
                        int(k): v for k, v in data.get('mev_protection_settings', {}).items()
                    }

                    # Load buy presets
                    self.buy_presets = {
                        int(k): v for k, v in data.get('buy_presets', {}).items()
                    }

                    # Load sell presets
                    self.sell_presets = {
                        int(k): v for k, v in data.get('sell_presets', {}).items()
                    }
                    
                logger.info(f"Loaded data for {len(self.wallets)} users with {sum(len(configs) for configs in self.sniper_configs.values())} sniper configs")
            except Exception as e:
                logger.error(f"Error loading data: {e}")
    
    def save_data(self):
        """Save wallets, sniper configs, and settings to file."""
        try:
            data = {
                'wallets': {
                    str(user_id): {'seed': wallet.seed, 'address': wallet.classic_address}
                    for user_id, wallet in self.wallets.items()
                },
                'sniper_configs': {
                    str(user_id): configs 
                    for user_id, configs in self.sniper_configs.items()
                },
                'default_trade_settings': {
                    str(k): v for k, v in self.default_trade_settings.items()
                },
                'mev_protection_settings': {
                    str(k): v for k, v in self.mev_protection_settings.items()
                },
                'buy_presets': {
                    str(k): v for k, v in self.buy_presets.items()
                },
                'sell_presets': {
                    str(k): v for k, v in self.sell_presets.items()
                }
            }
            with open(self.data_file, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info("Data saved successfully")
        except Exception as e:
            logger.error(f"Error saving data: {e}")

    def add_wallet(self, user_id: int, wallet_data: dict):
        """Adds a wallet to the sniper bot for a specific user."""
        self.wallets[user_id] = Wallet(wallet_data["seed"], 0)
        self.save_data()
        logger.info(f"Wallet added for user {user_id}: {self.wallets[user_id].classic_address}")

    def get_user_sniper_configs(self, user_id: int) -> dict:
        """Get all sniper configs for a user."""
        return self.sniper_configs.get(user_id, {})

    def get_sniper_config(self, user_id: int, config_id: str) -> dict:
        """Get a specific sniper config."""
        return self.sniper_configs.get(user_id, {}).get(config_id)

    def save_sniper_config(self, user_id: int, config_id: str, config: dict):
        """Save or update a sniper config."""
        if user_id not in self.sniper_configs:
            self.sniper_configs[user_id] = {}
        
        self.sniper_configs[user_id][config_id] = config
        self.save_data()
        logger.info(f"Sniper config {config_id} saved for user {user_id}")

    def update_sniper_config_status(self, user_id: int, config_id: str, enabled: bool):
        """Update the enabled status of a sniper config."""
        if user_id in self.sniper_configs and config_id in self.sniper_configs[user_id]:
            self.sniper_configs[user_id][config_id]["enabled"] = enabled
            self.save_data()
            
            # Update running status
            self._update_running_status()
            
            logger.info(f"Sniper config {config_id} for user {user_id} {'enabled' if enabled else 'disabled'}")

    def delete_sniper_config(self, user_id: int, config_id: str):
        """Delete a sniper config."""
        if user_id in self.sniper_configs and config_id in self.sniper_configs[user_id]:
            del self.sniper_configs[user_id][config_id]
            self.save_data()
            
            # Update running status
            self._update_running_status()
            
            logger.info(f"Sniper config {config_id} deleted for user {user_id}")

    def _update_running_status(self):
        """Update the running status based on enabled configs."""
        # Check if any config is enabled
        has_enabled_configs = any(
            config.get("enabled", False)
            for user_configs in self.sniper_configs.values()
            for config in user_configs.values()
        )
        
        if has_enabled_configs and not self.running:
            self.running = True
        elif not has_enabled_configs and self.running:
            self.running = False

    def get_enabled_configs(self) -> list:
        """Get all enabled sniper configs across all users."""
        enabled_configs = []
        for user_id, configs in self.sniper_configs.items():
            for config_id, config in configs.items():
                if config.get("enabled", False):
                    enabled_configs.append({
                        "user_id": user_id,
                        "config_id": config_id,
                        "config": config
                    })
        return enabled_configs

    async def _keep_alive(self):
        """Sends periodic ping to keep WebSocket connection alive."""
        try:
            while self.running and self.ws:
                await asyncio.sleep(30)
                if self.ws and not self.ws.closed:
                    await self.ws.ping()
                    logger.debug("Sent WebSocket ping")
        except Exception as e:
            logger.error(f"Keep-alive error: {e}")

    async def _subscribe_to_transactions(self):
        """Subscribes to real-time transaction streams on the XRPL with auto-reconnect."""
        reconnect_delay = 5
        max_reconnect_delay = 60
        
        while self.running:
            try:
                logger.info(f"Connecting to WebSocket: {WEBSOCKET_URL}")
                async with websockets.connect(
                    WEBSOCKET_URL,
                    ping_interval=30,
                    ping_timeout=10,
                    close_timeout=10
                ) as ws:
                    self.ws = ws
                    
                    # Subscribe to all transactions and ledger streams
                    await ws.send(json.dumps({
                        "id": 1,
                        "command": "subscribe",
                        "streams": ["transactions", "ledger"]
                    }))
                    
                    response = await ws.recv()
                    logger.info(f"Subscription response: {response}")
                    
                    reconnect_delay = 5
                    
                    while self.running:
                        try:
                            message = await ws.recv()
                            await self._process_xrpl_message(json.loads(message))
                        except websockets.exceptions.ConnectionClosed:
                            logger.warning("WebSocket connection closed by server")
                            break
                        except json.JSONDecodeError as e:
                            logger.error(f"JSON decode error: {e}")
                            continue
                            
            except (websockets.exceptions.WebSocketException, 
                    ConnectionRefusedError,
                    OSError) as e:
                if self.running:
                    logger.error(f"WebSocket error: {e}. Reconnecting in {reconnect_delay}s...")
                    await asyncio.sleep(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)
                else:
                    logger.info("Sniper stopped, not reconnecting")
                    break
            except Exception as e:
                logger.error(f"Unexpected error in WebSocket connection: {e}")
                if self.running:
                    await asyncio.sleep(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)
                else:
                    break
            finally:
                self.ws = None
        
        logger.info("WebSocket subscription loop ended")

    async def _process_xrpl_message(self, message: dict):
        """Processes incoming WebSocket messages from the XRPL."""
        if message.get("type") == "transaction" and message.get("validated"):
            transaction = message.get("transaction")
            meta = message.get("meta")

            tx_type = transaction.get("TransactionType")

            # Monitor for OfferCreate transactions (new listings/liquidity)
            if tx_type == "OfferCreate":
                await self._handle_offer_create_transaction(transaction, meta)
            # Monitor for TrustSet transactions
            elif tx_type == "TrustSet":
                await self._handle_trustset_transaction(transaction, meta)

    async def _handle_offer_create_transaction(self, transaction: dict, meta: dict):
        """Handles OfferCreate transactions to detect new token listings/liquidity."""
        logger.info(f"Detected OfferCreate transaction: {transaction.get('hash')}")

        taker_gets = transaction.get("TakerGets")
        taker_pays = transaction.get("TakerPays")

        # Identify the token being offered and the currency being paid
        token_currency = None
        token_issuer = None
        payment_currency = None

        if isinstance(taker_gets, dict) and "currency" in taker_gets:
            token_currency = taker_gets["currency"]
            token_issuer = taker_gets["issuer"]
        elif isinstance(taker_gets, str):  # XRP
            payment_currency = "XRP"

        if isinstance(taker_pays, dict) and "currency" in taker_pays:
            payment_currency = taker_pays["currency"]
        elif isinstance(taker_pays, str):  # XRP
            payment_currency = "XRP"

        if token_currency and token_issuer and payment_currency == "XRP":
            logger.info(f"Potential new listing: {token_currency}.{token_issuer} against XRP")
            
            # Check all enabled configs
            enabled_configs = self.get_enabled_configs()
            for config_data in enabled_configs:
                user_id = config_data["user_id"]
                config = config_data["config"]
                
                if self._matches_snipe_criteria(config, token_currency, token_issuer, transaction):
                    logger.info(f"Attempting to snipe token {token_currency}.{token_issuer} for user {user_id}")
                    await self._execute_buy_order(
                        user_id, 
                        token_currency, 
                        token_issuer, 
                        config.get("buy_amount_xrp", 10),
                        config.get("slippage", 0.01),
                        mev_protect=self.mev_protection_settings.get(user_id, {}).get("enabled", False)
                    )

    async def _handle_trustset_transaction(self, transaction: dict, meta: dict):
        """Handles TrustSet transactions."""
        logger.info(f"Detected TrustSet transaction: {transaction.get('hash')}")

    def _matches_snipe_criteria(self, config: dict, currency: str, issuer: str, transaction: dict) -> bool:
        """Checks if the token matches the sniper config criteria."""
        
        # Criteria 1: Developer wallet
        dev_wallet_address = config.get("dev_wallet_address")
        if dev_wallet_address and transaction.get("Account") == dev_wallet_address:
            logger.info(f"Match by developer wallet: {dev_wallet_address}")
            return True

        # Criteria 2: Token name/ticker (currency code)
        target_currency = config.get("target_currency")
        if target_currency and target_currency.upper() == currency.upper():
            logger.info(f"Match by currency code: {target_currency}")
            return True

        # Criteria 3: Issuer address
        target_issuer = config.get("target_issuer")
        if target_issuer and target_issuer == issuer:
            logger.info(f"Match by target issuer: {target_issuer}")
            return True

        return False

    def get_order_book(self, taker_pays_currency, taker_pays_issuer, 
                       taker_gets_currency, taker_gets_issuer):
        """Query the order book for current prices."""
        try:
            taker_pays_obj = {
                "currency": taker_pays_currency,
                "issuer": taker_pays_issuer
            } if taker_pays_currency != "XRP" else "XRP"
            
            taker_gets_obj = {
                "currency": taker_gets_currency,
                "issuer": taker_gets_issuer
            } if taker_gets_currency != "XRP" else "XRP"
            
            request = xrpl.models.requests.BookOffers(
                taker_pays=taker_pays_obj,
                taker_gets=taker_gets_obj,
                limit=10
            )
            response = client.request(request)
            return response.result.get('offers', [])
        except Exception as e:
            logger.error(f"Error fetching order book: {e}")
            return []

    async def _execute_buy_order(self, user_id: int, currency: str, issuer: str, buy_amount_xrp: float, slippage: float, mev_protect: bool = False):
        """Executes a buy order for a token on the XRPL DEX."""
        if user_id not in self.wallets:
            logger.error(f"No wallet configured for user {user_id}. Cannot execute buy order.")
            return False

        wallet = self.wallets[user_id]
        
        # First, ensure a trustline exists for the token
        try:
            trust_set_tx = TrustSet(
                account=wallet.classic_address,
                limit_amount=IssuedCurrencyAmount(
                    currency=currency,
                    issuer=issuer,
                    value="10000000000000000"  # Large limit
                ),
            )
            response = submit_and_wait(trust_set_tx, client, wallet)

            if response.result['engine_result'] not in ['tesSUCCESS', 'tecNO_LINE', 'tecNO_LINE_INSUF_RESERVE']:
                logger.warning(f"TrustSet failed for {currency}.{issuer}: {response.result}")
            else:
                logger.info(f"Trustline set for {currency}.{issuer} for user {user_id}")
        except Exception as e:
            logger.error(f"Error setting trustline for {currency}.{issuer}: {e}")

        # Query order book to get realistic price
        offers = self.get_order_book("XRP", None, currency, issuer)
        
        if not offers:
            logger.warning(f"No offers found in order book for {currency}.{issuer}")
            estimated_token_amount = buy_amount_xrp * 1000 # Fallback estimation
        else:
            first_offer = offers[0]
            taker_gets = first_offer.get("TakerGets")
            taker_pays = first_offer.get("TakerPays")
            
            if isinstance(taker_gets, dict) and isinstance(taker_pays, str):
                token_amount = float(taker_gets.get("value", 0))
                xrp_amount = float(taker_pays) / 1_000_000
                
                if xrp_amount > 0:
                    rate = token_amount / xrp_amount
                    estimated_token_amount = buy_amount_xrp * rate * (1 - slippage)
                    logger.info(f"Calculated rate: {rate} {currency} per XRP, buying {estimated_token_amount} {currency}")
                else:
                    estimated_token_amount = buy_amount_xrp * 1000 # Fallback
            else:
                estimated_token_amount = buy_amount_xrp * 1000 # Fallback

        # Create OfferCreate transaction
        offer = OfferCreate(
            account=wallet.classic_address,
            taker_gets=IssuedCurrencyAmount(
                currency=currency,
                issuer=issuer,
                value=str(estimated_token_amount)
            ),
            taker_pays=str(xrpl.utils.xrp_to_drops(buy_amount_xrp)),
        )

        # MEV Protection (simplified: add a small delay or higher fee if enabled)
        if mev_protect:
            logger.info("MEV protection enabled: Adding a small delay before submission.")
            await asyncio.sleep(0.5) # Simulate a slight delay or other MEV protection strategy
            # For more advanced MEV protection, one might interact with a private transaction relay
            # or use specific transaction flags/hooks if XRPL supports them.

        try:
            response = submit_and_wait(offer, client, wallet)

            if response.result['engine_result'] == 'tesSUCCESS':
                logger.info(f"Successfully executed buy order for {buy_amount_xrp} XRP worth of {currency}.{issuer} for user {user_id}")
                return True
            else:
                logger.warning(f"Buy order failed for {currency}.{issuer}: {response.result}")
                return False
        except Exception as e:
            logger.error(f"Error executing buy order for {currency}.{issuer}: {e}")
            return False

    async def _execute_sell_order(self, user_id: int, currency: str, issuer: str, sell_percentage: float):
        """Executes a sell order for a token on the XRPL DEX based on a percentage of holdings."""
        if user_id not in self.wallets:
            logger.error(f"No wallet configured for user {user_id}. Cannot execute sell order.")
            return False

        wallet = self.wallets[user_id]
        account_info = self.get_account_info(wallet.classic_address)
        
        if "error" in account_info:
            logger.error(f"Could not retrieve account info for sell order: {account_info['error']}")
            return False

        balances = account_info.get("account_data", {}).get("balances", [])
        token_balance = 0.0
        for balance in balances:
            if isinstance(balance, dict) and balance.get("currency") == currency and balance.get("issuer") == issuer:
                token_balance = float(balance.get("value", 0))
                break
        
        if token_balance == 0:
            logger.warning(f"User {user_id} has no {currency}.{issuer} to sell.")
            return False

        amount_to_sell = token_balance * (sell_percentage / 100.0)
        if amount_to_sell <= 0:
            logger.warning(f"Calculated sell amount is zero or negative for user {user_id}, {currency}.{issuer}.")
            return False

        # Query order book to get realistic price for selling (token for XRP)
        offers = self.get_order_book(currency, issuer, "XRP", None)

        if not offers:
            logger.warning(f"No offers found in order book for selling {currency}.{issuer}")
            return False
        
        # Take the best offer to sell into
        first_offer = offers[0]
        taker_gets = first_offer.get("TakerGets") # XRP
        taker_pays = first_offer.get("TakerPays") # Token

        if isinstance(taker_gets, str) and isinstance(taker_pays, dict):
            # Calculate how much XRP we would get for the amount_to_sell
            offered_token_amount = float(taker_pays.get("value", 0))
            offered_xrp_amount = float(taker_gets) / 1_000_000

            if offered_token_amount > 0:
                xrp_per_token_rate = offered_xrp_amount / offered_token_amount
                estimated_xrp_gain = amount_to_sell * xrp_per_token_rate
            else:
                logger.warning("Offered token amount is zero, cannot calculate rate.")
                return False
        else:
            logger.warning("Unexpected offer format for sell order.")
            return False

        # Create OfferCreate transaction to sell tokens for XRP
        offer = OfferCreate(
            account=wallet.classic_address,
            taker_gets=str(xrpl.utils.xrp_to_drops(estimated_xrp_gain)), # Amount of XRP to get
            taker_pays=IssuedCurrencyAmount(
                currency=currency,
                issuer=issuer,
                value=str(amount_to_sell)
            ),
        )

        try:
            response = submit_and_wait(offer, client, wallet)

            if response.result['engine_result'] == 'tesSUCCESS':
                logger.info(f"Successfully executed sell order for {sell_percentage}% of {currency}.{issuer} for user {user_id}")
                return True
            else:
                logger.warning(f"Sell order failed for {currency}.{issuer}: {response.result}")
                return False
        except Exception as e:
            logger.error(f"Error executing sell order for {currency}.{issuer}: {e}")
            return False

    def get_account_info(self, address: str) -> dict:
        """Fetches account information from the XRPL."""
        try:
            acct_info = xrpl.models.requests.AccountInfo(account=address)
            response = client.request(acct_info)
            return response.result
        except Exception as e:
            logger.error(f"Error getting account info for {address}: {e}")
            return {"error": str(e)}

    def set_mev_protection(self, user_id: int, enabled: bool):
        """Sets the MEV protection status for a user."""
        if user_id not in self.mev_protection_settings:
            self.mev_protection_settings[user_id] = {}
        self.mev_protection_settings[user_id]["enabled"] = enabled
        self.save_data()
        logger.info(f"MEV protection for user {user_id} set to {enabled}")

    def get_mev_protection_status(self, user_id: int) -> bool:
        """Gets the MEV protection status for a user."""
        return self.mev_protection_settings.get(user_id, {}).get("enabled", False)

    def add_buy_preset(self, user_id: int, amount_xrp: float):
        """Adds a buy preset for a user."""
        if user_id not in self.buy_presets:
            self.buy_presets[user_id] = []
        if amount_xrp not in self.buy_presets[user_id]:
            self.buy_presets[user_id].append(amount_xrp)
            self.buy_presets[user_id].sort()
            self.save_data()
            logger.info(f"Buy preset {amount_xrp} XRP added for user {user_id}")

    def remove_buy_preset(self, user_id: int, amount_xrp: float):
        """Removes a buy preset for a user."""
        if user_id in self.buy_presets and amount_xrp in self.buy_presets[user_id]:
            self.buy_presets[user_id].remove(amount_xrp)
            self.save_data()
            logger.info(f"Buy preset {amount_xrp} XRP removed for user {user_id}")

    def get_buy_presets(self, user_id: int) -> list:
        """Gets all buy presets for a user."""
        return self.buy_presets.get(user_id, [])

    def add_sell_preset(self, user_id: int, percentage: int):
        """Adds a sell preset for a user."""
        if user_id not in self.sell_presets:
            self.sell_presets[user_id] = []
        if percentage not in self.sell_presets[user_id]:
            self.sell_presets[user_id].append(percentage)
            self.sell_presets[user_id].sort()
            self.save_data()
            logger.info(f"Sell preset {percentage}% added for user {user_id}")

    def remove_sell_preset(self, user_id: int, percentage: int):
        """Removes a sell preset for a user."""
        if user_id in self.sell_presets and percentage in self.sell_presets[user_id]:
            self.sell_presets[user_id].remove(percentage)
            self.save_data()
            logger.info(f"Sell preset {percentage}% removed for user {user_id}")

    def get_sell_presets(self, user_id: int) -> list:
        """Gets all sell presets for a user."""
        return self.sell_presets.get(user_id, [])

    async def start_sniper(self):
        """Starts the XRP Ledger monitoring for sniping."""
        if self.running:
            logger.warning("Sniper already running")
            return
        
        self.running = True
        logger.info("Starting XRP Sniper bot...")
        await self._subscribe_to_transactions()

    async def stop_sniper(self):
        """Stops the XRP Ledger monitoring."""
        logger.info("Stopping XRP Sniper bot...")
        self.running = False
        
        if self.ws and not self.ws.closed:
            await self.ws.close()
        
        if self.sniper_task and not self.sniper_task.done():
            self.sniper_task.cancel()
            try:
                await self.sniper_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Sniper stopped successfully")
