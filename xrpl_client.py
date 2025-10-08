import asyncio
import xrpl
from xrpl.clients import JsonRpcClient
from xrpl.wallet import Wallet, generate_faucet_wallet

# Corrected imports for xrpl.models
from xrpl.models.requests import AccountInfoRequest
from xrpl.models.transactions import TrustSet
from xrpl.models.amounts import IssuedCurrencyAmount

# Standard JSON-RPC Client for the XRP Testnet
JSON_RPC_URL = "https://s.altnet.rippletest.net/"
client = JsonRpcClient(JSON_RPC_URL )

# --- Synchronous Wrapper for Async XRPL Functions ---
# This is crucial for integrating with python-telegram-bot's event loop

def _run_async_in_new_loop(coro):
    """Runs an async coroutine in a new, dedicated event loop in a separate thread."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

def generate_new_wallet_sync():
    """Generates a new XRPL wallet and funds it via the faucet (synchronous wrapper)."""
    async def _generate_and_fund():
        try:
            # Use asyncio.wait_for to prevent indefinite hanging
            faucet_wallet = await asyncio.wait_for(generate_faucet_wallet(client), timeout=30)
            return {"address": faucet_wallet.classic_address, "seed": faucet_wallet.seed}
        except asyncio.TimeoutError:
            return {"error": "Faucet did not respond in time. Please try again later."}
        except Exception as e:
            # Log the actual exception for debugging
            print(f"Error in _generate_and_fund: {e}")
            return {"error": f"Failed to generate wallet: {e}"}

    return _run_async_in_new_loop(_generate_and_fund())

def import_wallet(seed: str):
    """Imports a wallet from a seed (synchronous wrapper)."""
    try:
        wallet = Wallet(seed)
        return {"address": wallet.classic_address, "seed": wallet.seed}
    except Exception as e:
        return {"error": f"Invalid seed or error importing wallet: {e}"}

def get_account_info(address: str):
    """Gets account info for a given address (synchronous wrapper)."""
    async def _get_info():
        try:
            acct_info = await client.request(AccountInfoRequest(account=address))
            return acct_info.result
        except Exception as e:
            return {"error": f"Failed to get account info: {e}"}
    return _run_async_in_new_loop(_get_info())

def set_trustline(seed: str, currency: str, issuer: str):
    """Sets a trustline for a given wallet (synchronous wrapper)."""
    async def _set_trustline():
        try:
            wallet = Wallet(seed)
            trust_set_tx = TrustSet(
                account=wallet.classic_address,
                fee="12", # Example fee
                limit_amount=IssuedCurrencyAmount(
                    currency=currency,
                    issuer=issuer,
                    value="1000000000" # Large enough limit
                )
            )
            # Sign and send the transaction
            signed_tx = xrpl.transaction.safe_sign_and_autofill_transaction(trust_set_tx, wallet, client)
            response = await xrpl.transaction.send_reliable_submission(signed_tx, client)
            return response.result
        except Exception as e:
            return {"error": f"Failed to set trustline: {e}"}
    return _run_async_in_new_loop(_set_trustline())

# Example usage (for local testing of xrpl_client.py)
if __name__ == "__main__":
    print("Generating a new wallet...")
    new_wallet = generate_new_wallet_sync()
    if new_wallet and "address" in new_wallet:
        print(f"New Wallet Address: {new_wallet['address']}")
        print(f"New Wallet Seed: {new_wallet['seed']}")

        print("\nGetting account info for the new wallet...")
        account_info = get_account_info(new_wallet['address'])
        print(account_info)

        # Example of setting a trustline (replace with actual currency/issuer)
        # print("\nSetting a trustline (example for a hypothetical token)... ")
        # try:
        #     trustline_result = set_trustline(new_wallet['seed'], "USD", "rP9jygWvBfR4q4b6v2W2b7x3f3g3h3i3j3k4l6m8n")
        #     print(trustline_result)
        # except Exception as e:
        #     print(f"Error setting trustline: {e}")
    else:
        print(f"Error: {new_wallet.get('error', 'Unknown error during generation')}")

    print("\nImporting a wallet (example with a dummy seed)...")
    dummy_seed = "sEdTj4Pqmkzzw45Cg1v6x3t7m1g3n5h2j1k4l6m8n"
    imported_wallet = import_wallet(dummy_seed)
    if imported_wallet and "address" in imported_wallet:
        print(f"Imported Wallet Address: {imported_wallet['address']}")
    else:
        print(f"Error importing wallet: {imported_wallet.get('error', 'Unknown error during import')}")
