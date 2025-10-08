import xrpl
from xrpl.wallet import generate_faucet_wallet, Wallet
from xrpl.clients import JsonRpcClient
from xrpl.models import Payment, TrustSet, IssuedCurrencyAmount
from xrpl.transaction import submit_and_wait
import asyncio
import threading

# Initialize the XRP Ledger client (using a testnet for development)
JSON_RPC_URL = "https://s.altnet.rippletest.net:51234/"
client = JsonRpcClient(JSON_RPC_URL)

# Helper function to run an async coroutine in a new event loop in a separate thread
def _run_async_in_new_loop(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

async def _async_generate_faucet_wallet_isolated():
    """Isolated async function to generate and fund a wallet from the faucet."""
    try:
        # The generate_faucet_wallet call itself is async and needs to be awaited
        test_wallet = await asyncio.wait_for(generate_faucet_wallet(client), timeout=30)
        return {
            "address": test_wallet.classic_address,
            "seed": test_wallet.seed,
            "public_key": test_wallet.public_key,
            "private_key": test_wallet.private_key,
        }
    except asyncio.TimeoutError:
        return {"error": "XRP Ledger faucet timed out. Please try again later."}
    except Exception as e:
        return {"error": f"Failed to generate wallet: {e}"}

def generate_new_wallet_sync():
    """
    Synchronous function to generate a new XRP Ledger wallet.
    It runs the async faucet call in a dedicated event loop in a separate thread.
    """
    # Use the helper to run the async function in its own event loop
    return _run_async_in_new_loop(_async_generate_faucet_wallet_isolated())

def import_wallet(seed: str):
    """Imports an existing XRP Ledger wallet from a seed."""
    try:
        imported_wallet = Wallet(seed=seed, sequence=0)
        return {
            "address": imported_wallet.classic_address,
            "seed": imported_wallet.seed,
            "public_key": imported_wallet.public_key,
            "private_key": imported_wallet.private_key,
        }
    except Exception as e:
        return {"error": str(e)}

def get_account_info(address: str):
    """Retrieves account information for a given XRP Ledger address."""
    try:
        acct_info = client.request(xrpl.models.requests.AccountInfo(account=address))
        return acct_info.result
    except Exception as e:
        return {"error": str(e)}

def send_xrp(sender_seed: str, destination_address: str, amount: float):
    """Sends XRP from one address to another."""
    sender_wallet = Wallet(sender_seed, 0)
    payment = Payment(
        account=sender_wallet.classic_address,
        amount=xrpl.utils.xrp_to_drops(amount),
        destination=destination_address,
    )
    try:
        response = submit_and_wait(payment, client, sender_wallet)
        return response.result
    except Exception as e:
        return {"error": str(e)}

def set_trustline(sender_seed: str, currency_code: str, issuer_address: str, limit: str = "10000000000000000"):
    """Sets a trustline for an issued token."""
    sender_wallet = Wallet(sender_seed, 0)
    trust_set = TrustSet(
        account=sender_wallet.classic_address,
        limit_amount=IssuedCurrencyAmount(
            currency=currency_code,
            issuer=issuer_address,
            value=limit,
        ),
    )
    try:
        response = submit_and_wait(trust_set, client, sender_wallet)
        return response.result
    except Exception as e:
        return {"error": str(e)}

# Example Usage (for testing purposes)
if __name__ == "__main__":
    print("Generating a new wallet...")
    # For standalone testing, call the synchronous generate_new_wallet_sync
    new_wallet = generate_new_wallet_sync()
    if "error" not in new_wallet:
        print(f"New Wallet Address: {new_wallet["address"]}")
        print(f"New Wallet Seed: {new_wallet["seed"]}")

        print("\nGetting account info for the new wallet...")
        account_info = get_account_info(new_wallet["address"])
        print(account_info)

        print("\nSetting a trustline (example for a hypothetical token)... ")
        try:
            trustline_result = set_trustline(new_wallet["seed"], "USD", "rP9jygWvBfR4q4b6v2W2b7x3f3g3h3i3j3k3l3m3n")
            print(trustline_result)
        except Exception as e:
            print(f"Error setting trustline: {e}")
    else:
        print(f"Error: {new_wallet["error"]}")

