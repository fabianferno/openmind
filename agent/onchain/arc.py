"""Arc testnet client (web3.py).

Two operations:
  - anchor(hash):  put a 32-byte reasoning-trace hash on-chain (tx calldata = the hash).
  - transfer_usdc: settle a symbolic USDC amount (stake/fee) to a treasury wallet.

Arc is EVM-compatible; gas is paid in USDC (the native balance), so a funded wallet needs
no separate gas token. Every method degrades gracefully to a clearly-flagged mock txn when
`ARC_ENABLED=false`, no key is set, or the RPC call fails — so the demo is never blocked.
"""

from __future__ import annotations

import secrets
from typing import Any

from agent.config import settings
from agent.logging import get_logger

log = get_logger(__name__)

# minimal ERC-20 ABI
ERC20_ABI = [
    {"constant": False, "inputs": [{"name": "to", "type": "address"},
     {"name": "amount", "type": "uint256"}], "name": "transfer",
     "outputs": [{"name": "", "type": "bool"}], "type": "function"},
    {"constant": True, "inputs": [{"name": "owner", "type": "address"}],
     "name": "balanceOf", "outputs": [{"name": "", "type": "uint256"}], "type": "function"},
]


class ArcClient:
    def __init__(self) -> None:
        self.enabled = bool(settings.arc_enabled and settings.arc_testnet_wallet_private_key)
        self.w3 = None
        self.address: str | None = None
        if not self.enabled:
            log.info("arc.mock_mode", reason="disabled_or_no_key")
            return
        try:
            from web3 import Web3

            self.w3 = Web3(Web3.HTTPProvider(settings.arc_rpc_url, request_kwargs={"timeout": 30}))
            try:  # tolerate POA-style extraData
                from web3.middleware import ExtraDataToPOAMiddleware

                self.w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
            except Exception:  # noqa: BLE001
                pass
            self.acct = self.w3.eth.account.from_key(settings.arc_testnet_wallet_private_key)
            self.address = self.acct.address
            log.info("arc.ready", address=self.address, chain=settings.arc_chain_id)
        except Exception as e:  # noqa: BLE001
            log.warning("arc.init_failed", error=str(e))
            self.enabled = False

    # ---- public ----

    @property
    def real(self) -> bool:
        return self.enabled and self.w3 is not None

    def treasury(self) -> str:
        return settings.arc_treasury_address or self.address or "0x" + "0" * 40

    def anchor(self, trace_hash: str, *, decision_id: int | None = None) -> dict[str, Any]:
        data = trace_hash if trace_hash.startswith("0x") else "0x" + trace_hash
        if not self.real:
            return self._mock("anchor", trace_hash=trace_hash, decision_id=decision_id)
        try:
            tx = {
                "from": self.address,
                "to": settings.arc_anchor_contract or self.address,  # self-send carries data
                "value": 0,
                "data": data,
                "nonce": self.w3.eth.get_transaction_count(self.address),
                "chainId": settings.arc_chain_id,
                "gas": 80_000,
                **self._fees(),
            }
            return self._send(tx, kind="anchor", trace_hash=trace_hash, decision_id=decision_id)
        except Exception as e:  # noqa: BLE001
            log.warning("arc.anchor_failed", error=str(e))
            return self._mock("anchor", trace_hash=trace_hash, decision_id=decision_id, error=str(e))

    def transfer_usdc(
        self, to: str, amount_usdc: float, *, decision_id: int | None = None
    ) -> dict[str, Any]:
        if not self.real:
            return self._mock("settle", usdc_amount=amount_usdc, to=to, decision_id=decision_id)
        try:
            to_addr = self.w3.to_checksum_address(to)
            usdc = self.w3.eth.contract(
                address=self.w3.to_checksum_address(settings.arc_usdc_address), abi=ERC20_ABI
            )
            amount = int(round(float(amount_usdc) * 10**6))  # USDC has 6 decimals
            base = {
                "from": self.address,
                "nonce": self.w3.eth.get_transaction_count(self.address),
                "chainId": settings.arc_chain_id,
                **self._fees(),
            }
            tx = usdc.functions.transfer(to_addr, amount).build_transaction(base)
            return self._send(
                tx, kind="settle", usdc_amount=amount_usdc, to=to_addr, decision_id=decision_id
            )
        except Exception as e:  # noqa: BLE001
            log.warning("arc.settle_failed", error=str(e))
            return self._mock(
                "settle", usdc_amount=amount_usdc, to=to, decision_id=decision_id, error=str(e)
            )

    def usdc_balance(self) -> float | None:
        if not self.real:
            return None
        try:
            usdc = self.w3.eth.contract(
                address=self.w3.to_checksum_address(settings.arc_usdc_address), abi=ERC20_ABI
            )
            return usdc.functions.balanceOf(self.address).call() / 10**6
        except Exception:  # noqa: BLE001
            return None

    # ---- internals ----

    def _fees(self) -> dict[str, Any]:
        try:
            base = self.w3.eth.get_block("latest").get("baseFeePerGas")
            if base is None:
                return {"gasPrice": self.w3.eth.gas_price}
            try:
                prio = self.w3.eth.max_priority_fee
            except Exception:  # noqa: BLE001
                prio = self.w3.to_wei(1, "gwei")
            return {"maxFeePerGas": base * 2 + prio, "maxPriorityFeePerGas": prio}
        except Exception:  # noqa: BLE001
            return {}

    def _send(self, tx: dict[str, Any], *, kind: str, **extra: Any) -> dict[str, Any]:
        signed = self.acct.sign_transaction(tx)
        raw = getattr(signed, "raw_transaction", None)
        if raw is None:                       # web3 v6 used rawTransaction
            raw = signed.rawTransaction
        txh = self.w3.eth.send_raw_transaction(raw)
        self.w3.eth.wait_for_transaction_receipt(txh, timeout=90)
        h = txh.hex()
        if not h.startswith("0x"):
            h = "0x" + h
        log.info("arc.tx", kind=kind, tx=h)
        return {
            "tx_hash": h,
            "explorer_url": f"{settings.arc_explorer_base}/tx/{h}",
            "mocked": False,
            "kind": kind,
            "network": "arc-testnet",
            **extra,
        }

    def _mock(self, kind: str, **extra: Any) -> dict[str, Any]:
        h = "0x" + secrets.token_hex(32)
        return {
            "tx_hash": h,
            "explorer_url": f"{settings.arc_explorer_base}/tx/{h}",
            "mocked": True,
            "kind": kind,
            "network": "arc-testnet",
            **extra,
        }


_client: ArcClient | None = None


def get_arc() -> ArcClient:
    global _client
    if _client is None:
        _client = ArcClient()
    return _client
