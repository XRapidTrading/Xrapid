import xrpl
from xrpl.wallet import generate_faucet_wallet, Wallet
from xrpl.clients import JsonRpcClient
from xrpl.models import Payment, TrustSet, IssuedCurrencyAmount
from xrpl.transaction import submit_and_wait

# Initialize the XRP Ledger client (using a testnet for development)
JSON_RPC_URL = "https://s.altnet.rippletest.net:51234/"
client = JsonRpcClient(JSON_RPC_URL)

async def generate_new_wallet():
    """Generates a new XRP Ledger wallet and funds it on the testnet."""
    test_wallet = await generate_faucet_wallet(client)

    return {
        "address": test_wallet.classic_address,
        "seed": test_wallet.seed,
        "public_key": test_wallet.public_key,
        "private_key": test_wallet.private_key,
    }

def import_wallet(seed: str):
    """Imports an existing XRP Ledger wallet from a seed."""
    try:
        imported_wallet = Wallet(seed, 0)
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

def set_trustline(sender_seed: str, currency_code: str, issuer_address: str, limit: str = "10000000000000000"): # Default large limit
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
    new_wallet = generate_new_wallet()
    print(f"New Wallet Address: {new_wallet['address']}")
    print(f"New Wallet Seed: {new_wallet['seed']}")

    print("\nGetting account info for the new wallet...")
    account_info = get_account_info(new_wallet['address'])
    print(account_info)

    # To test sending XRP, you would need another funded wallet.
    # For demonstration, let's assume we have a second wallet seed.
    # print("\nImporting a second wallet (replace with a real seed for testing send_xrp)...")
    # second_wallet_seed = "sEdxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    # second_wallet = import_wallet(second_wallet_seed)
    # if "error" not in second_wallet:
    #     print(f"Second Wallet Address: {second_wallet['address']}")
    #     print("\nSending 10 XRP from new_wallet to second_wallet...")
    #     send_result = send_xrp(new_wallet['seed'], second_wallet['address'], 10)
    #     print(send_result)
    # else:
    #     print(f"Error importing second wallet: {second_wallet['error']}")

    print("\nSetting a trustline (example for a hypothetical token)... ")
    # Replace with actual token details for a real test
    # Note: Setting a trustline requires the account to have enough XRP for reserves.
    # This example uses a placeholder for currency and issuer.
    # You would typically set a trustline for a specific token you intend to trade.
    try:
        trustline_result = set_trustline(new_wallet['seed'], "USD", "rP9jygWvBfR4q4b6v2W2b7x3f3g3h3i3j3k3l3m3n")
        print(trustline_result)
    except Exception as e:
        print(f"Error setting trustline: {e}")

