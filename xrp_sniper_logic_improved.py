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
JSON_RPC_URL = "https://s.altnet.rippletest.net:51234/" # Using testnet for development
WEBSOCKET_URL = "wss://s.altnet.rippletest.net:51233/" # Using testnet for development
client = JsonRpcClient(JSON_RPC_URL)

class XRPSniper:
    def __init__(self, data_file="sniper_data.json"):
        self.data_file = data_file
        self.wallets = {}
        self.snipe_settings = {}
        self.active_snipes = {}
        self.running = False  # Flag to control sniper execution
        self.sniper_task = None  # Reference to the sniper task
        self.ws = None  # WebSocket connection reference
        self.load_data()

    def load_data(self):
        """Load wallets and settings from file."""
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r') as f:
                    data = json.load(f)
                    # Reconstruct wallets from seeds
                    for user_id, wallet_data in data.get('wallets', {}).items():
                        self.wallets[int(user_id)] = Wallet(wallet_data['seed'], 0)
                    self.snipe_settings = {int(k): v for k, v in data.get('settings', {}).items()}
                logger.info(f"Loaded data for {len(self.wallets)} users")
            except Exception as e:
                logger.error(f"Error loading data: {e}")
    
    def save_data(self):
        """Save wallets and settings to file."""
        try:
            data = {
                'wallets': {
                    str(user_id): {'seed': wallet.seed, 'address': wallet.classic_address}
                    for user_id, wallet in self.wallets.items()
                },
                'settings': {str(k): v for k, v in self.snipe_settings.items()}
            }
            with open(self.data_file, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info("Data saved successfully")
        except Exception as e:
            logger.error(f"Error saving data: {e}")

    def add_wallet(self, user_id: int, wallet_data: dict):
        """Adds a wallet to the sniper bot for a specific user."""
        self.wallets[user_id] = Wallet(wallet_data["seed"], 0) # Store xrpl.wallet.Wallet object
        self.save_data()
        logger.info(f"Wallet added for user {user_id}: {self.wallets[user_id].classic_address}")

    def update_snipe_settings(self, user_id: int, settings: dict):
        """Updates sniping settings for a user."""
        self.snipe_settings[user_id] = settings
        self.save_data()
        logger.info(f"Sniping settings updated for user {user_id}: {settings}")

    async def _keep_alive(self):
        """Sends periodic ping to keep WebSocket connection alive."""
        try:
            while self.running and self.ws:
                await asyncio.sleep(30)  # Ping every 30 seconds
                if self.ws and not self.ws.closed:
                    await self.ws.ping()
                    logger.debug("Sent WebSocket ping")
        except Exception as e:
            logger.error(f"Keep-alive error: {e}")

    async def _subscribe_to_transactions(self):
        """Subscribes to real-time transaction streams on the XRPL with auto-reconnect."""
        reconnect_delay = 5  # Initial reconnect delay in seconds
        max_reconnect_delay = 60  # Maximum reconnect delay
        
        while self.running:
            try:
                logger.info(f"Connecting to WebSocket: {WEBSOCKET_URL}")
                async with websockets.connect(
                    WEBSOCKET_URL,
                    ping_interval=30,  # Built-in ping every 30 seconds
                    ping_timeout=10,   # Timeout for ping response
                    close_timeout=10
                ) as ws:
                    self.ws = ws
                    
                    # Subscribe to all transactions and ledger streams for comprehensive monitoring
                    await ws.send(json.dumps({
                        "id": 1,
                        "command": "subscribe",
                        "streams": ["transactions", "ledger"]
                    }))
                    
                    response = await ws.recv()
                    logger.info(f"Subscription response: {response}")
                    
                    # Reset delay on successful connection
                    reconnect_delay = 5
                    
                    # Start keep-alive task (optional, since we use ping_interval)
                    # keep_alive_task = asyncio.create_task(self._keep_alive())
                    
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
                    
                    # Exponential backoff
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
            # Monitor for TrustSet transactions (new token issuances, though less direct for sniping)
            elif tx_type == "TrustSet":
                await self._handle_trustset_transaction(transaction, meta)
            # Add other transaction types relevant to token sniping (e.g., AMMCreate if supported)

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
        elif isinstance(taker_gets, str): # XRP
            payment_currency = "XRP"

        if isinstance(taker_pays, dict) and "currency" in taker_pays:
            payment_currency = taker_pays["currency"]
        elif isinstance(taker_pays, str): # XRP
            payment_currency = "XRP"

        if token_currency and token_issuer and payment_currency == "XRP":
            logger.info(f"Potential new listing: {token_currency}.{token_issuer} against XRP")
            for user_id, settings in self.snipe_settings.items():
                if settings.get("afk_mode") and self._matches_snipe_criteria(user_id, token_currency, token_issuer, transaction):
                    logger.info(f"Attempting to snipe token {token_currency}.{token_issuer} for user {user_id}")
                    await self._execute_buy_order(user_id, token_currency, token_issuer, settings["buy_amount_xrp"], settings.get("slippage", 0.01))

    async def _handle_trustset_transaction(self, transaction: dict, meta: dict):
        """Handles TrustSet transactions (less direct for sniping, but can indicate new tokens)."""
        logger.info(f"Detected TrustSet transaction: {transaction.get('hash')}")
        # This can be used to track new tokens, but OfferCreate is more direct for sniping opportunities.
        # Further logic can be added here if specific TrustSet patterns indicate a snipe.

    def _matches_snipe_criteria(self, user_id: int, currency: str, issuer: str, transaction: dict) -> bool:
        """Checks if the token matches the user's sniping criteria."""
        settings = self.snipe_settings.get(user_id)
        if not settings:
            return False

        # Criteria 1: Developer wallet
        dev_wallet_address = settings.get("dev_wallet_address")
        if dev_wallet_address and transaction.get("Account") == dev_wallet_address:
            logger.info(f"Match by developer wallet: {dev_wallet_address}")
            return True

        # Criteria 2: Token name/ticket (currency code)
        target_currency = settings.get("target_currency")
        if target_currency and target_currency.upper() == currency.upper():
            logger.info(f"Match by currency code: {target_currency}")
            return True

        # Criteria 3: Issuer address
        target_issuer = settings.get("target_issuer")
        if target_issuer and target_issuer == issuer:
            logger.info(f"Match by target issuer: {target_issuer}")
            return True

        # Add more complex criteria here (e.g., initial liquidity, transaction volume, etc.)
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

    async def _execute_buy_order(self, user_id: int, currency: str, issuer: str, buy_amount_xrp: float, slippage: float):
        """Executes a buy order for a token on the XRPL DEX."""
        if user_id not in self.wallets:
            logger.error(f"No wallet configured for user {user_id}. Cannot execute buy order.")
            return

        wallet = self.wallets[user_id]
        
        # First, ensure a trustline exists for the token
        try:
            trust_set_tx = TrustSet(
                account=wallet.classic_address,
                limit_amount=IssuedCurrencyAmount(
                    currency=currency,
                    issuer=issuer,
                    value="10000000000000000" # Large limit
                ),
            )
            response = submit_and_wait(trust_set_tx, client, wallet)

            if response.result['engine_result'] not in ['tesSUCCESS', 'tecNO_LINE', 'tecNO_LINE_INSUF_RESERVE']:
                logger.warning(f"TrustSet failed for {currency}.{issuer}: {response.result}")
            else:
                logger.info(f"Trustline set for {currency}.{issuer} for user {user_id}")
        except Exception as e:
            logger.error(f"Error setting trustline for {currency}.{issuer}: {e}")
            # Continue anyway, trustline might already exist

        # Query order book to get realistic price
        offers = self.get_order_book("XRP", None, currency, issuer)
        
        if not offers:
            logger.warning(f"No offers found in order book for {currency}.{issuer}")
            # Use fallback estimation
            estimated_token_amount = buy_amount_xrp * 1000
        else:
            # Calculate based on first offer
            first_offer = offers[0]
            taker_gets = first_offer.get("TakerGets")
            taker_pays = first_offer.get("TakerPays")
            
            # Calculate exchange rate
            if isinstance(taker_gets, dict) and isinstance(taker_pays, str):
                token_amount = float(taker_gets.get("value", 0))
                xrp_amount = float(taker_pays) / 1_000_000  # Convert drops to XRP
                
                if xrp_amount > 0:
                    rate = token_amount / xrp_amount
                    estimated_token_amount = buy_amount_xrp * rate * (1 - slippage)
                    logger.info(f"Calculated rate: {rate} {currency} per XRP, buying {estimated_token_amount} {currency}")
                else:
                    estimated_token_amount = buy_amount_xrp * 1000
            else:
                estimated_token_amount = buy_amount_xrp * 1000

        # Create OfferCreate transaction
        offer = OfferCreate(
            account=wallet.classic_address,
            taker_gets=IssuedCurrencyAmount(
                currency=currency,
                issuer=issuer,
                value=str(estimated_token_amount) # Amount of token to receive
            ),
            taker_pays=str(xrpl.utils.xrp_to_drops(buy_amount_xrp)), # Amount of XRP to pay
        )

        try:
            response = submit_and_wait(offer, client, wallet)

            if response.result['engine_result'] == 'tesSUCCESS':
                logger.info(f"Successfully executed buy order for {buy_amount_xrp} XRP worth of {currency}.{issuer} for user {user_id}")
                # TODO: Notify user via Telegram bot
                return True
            else:
                logger.warning(f"Buy order failed for {currency}.{issuer}: {response.result}")
                return False
        except Exception as e:
            logger.error(f"Error executing buy order for {currency}.{issuer}: {e}")
            return False

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
        
        # Close WebSocket connection if open
        if self.ws and not self.ws.closed:
            await self.ws.close()
        
        # Cancel sniper task if exists
        if self.sniper_task and not self.sniper_task.done():
            self.sniper_task.cancel()
            try:
                await self.sniper_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Sniper stopped successfully")

# Example Usage (for testing the sniping logic independently)
async def main():
    sniper = XRPSniper()

    # Simulate adding a user's wallet and settings
    # IMPORTANT: In a real scenario, never hardcode seeds. Use secure storage.
    # For testnet, you can generate a wallet and fund it via https://faucet.altnet.rippletest.net/
    # Replace with a real testnet seed for actual testing
    test_seed = "sEdTxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" # Replace with your testnet wallet seed
    test_wallet_data = {"seed": test_seed, "address": Wallet(test_seed, 0).classic_address}
    sniper.add_wallet(123, test_wallet_data)

    sniper.update_snipe_settings(123, {
        "afk_mode": True,
        "buy_amount_xrp": 10, # Amount of XRP to spend
        "slippage": 0.05, # 5% slippage tolerance
        "target_issuer": "rP9jygWvBfR4q4b6v2W2b7x3f3g3h3i3j3k3l3m3n", # Example issuer on testnet
        "target_currency": "USD" # Example currency code
        # "dev_wallet_address": "rxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" # Example dev wallet to monitor
    })

    try:
        await sniper.start_sniper()
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
        await sniper.stop_sniper()

if __name__ == "__main__":
    asyncio.run(main())
