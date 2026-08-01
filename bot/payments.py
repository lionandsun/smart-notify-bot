import asyncio
import re
from dataclasses import dataclass, asdict
from typing import Optional

TX_HASH_REGEX = re.compile(r"^[A-Fa-f0-9]{64}$")

@dataclass
class PaymentVerification:
    confirmed: bool
    tx_hash: str
    amount_usdt: float
    network: str = "TRC20"
    confirmations: int = 0
    error: Optional[str] = None
    raw: Optional[dict] = None

def is_valid_tx_hash(tx_hash):
    return bool(TX_HASH_REGEX.match(tx_hash.strip()))

async def verify_usdt_trc20_transaction(tx_hash, expected_amount_usdt):
    """Mock USDT TRC20 payment verification. Replace with real TronGrid API."""
    tx_hash = tx_hash.strip()
    await asyncio.sleep(1.0)
    raw = {"txID": tx_hash, "network": "TRON", "token": "USDT", "mock": True}
    if not is_valid_tx_hash(tx_hash):
        return PaymentVerification(confirmed=False, tx_hash=tx_hash, amount_usdt=0.0, error="Invalid TX hash format.", raw=raw)
    if tx_hash.lower().startswith("dead"):
        return PaymentVerification(confirmed=False, tx_hash=tx_hash, amount_usdt=0.0, error="Transaction not found or not confirmed.", raw=raw)
    raw.update({"amount": expected_amount_usdt, "confirmed": True, "confirmations": 20})
    return PaymentVerification(confirmed=True, tx_hash=tx_hash, amount_usdt=expected_amount_usdt, confirmations=20, raw=raw)
