"""Centralised configuration loaded from environment / .env.

All other modules import `settings` rather than reading os.environ directly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Mode = Literal["backtest", "paper", "dryrun", "live"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- runtime ----
    agent_mode: Mode = "paper"
    agent_bankroll: float = 50.0
    agent_cycle_seconds: int = 1200
    agent_categories: str = "geopolitics,world,politics"
    agent_per_market_cap: float = 2.0
    agent_max_positions: int = 8
    agent_daily_loss_cap: float = 0.20

    # ---- bedrock ----
    # Defaults target Amazon Nova (cheap) rather than Claude — this is a POC and Nova Lite
    # is ~50x cheaper than Claude Sonnet while still solid at structured JSON. Override via .env.
    aws_region: str = "us-east-1"
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_session_token: str | None = None
    bedrock_model_id: str = "apac.amazon.nova-lite-v1:0"
    bedrock_model_id_cheap: str | None = None

    llm_per_decision_usd_cap: float = 0.05
    llm_per_day_usd_cap: float = 5.00
    llm_input_usd_per_mtok: float = 0.06   # Amazon Nova Lite input  ($/Mtok)
    llm_output_usd_per_mtok: float = 0.24  # Amazon Nova Lite output ($/Mtok)

    # ---- graphrag (openmind) ----
    graphrag_enabled: bool = True
    graphrag_max_nodes: int = 30          # cap graph size for clean visualisation

    # ---- arc (on-chain settlement) ----
    arc_enabled: bool = True              # False → mock txns (build never blocked by RPC)
    arc_rpc_url: str = "https://rpc.testnet.arc.network"
    arc_chain_id: int = 5042002
    arc_testnet_wallet_private_key: str | None = None
    arc_usdc_address: str = "0x3600000000000000000000000000000000000000"
    arc_anchor_contract: str | None = None   # if set, use Anchor.sol; else raw calldata
    arc_treasury_address: str | None = None  # settle destination; defaults to own wallet
    arc_settle_usdc: float = 0.01            # symbolic per-trade stake/fee (paper mode)
    arc_explorer_base: str = "https://testnet.arcscan.app"

    # ---- web ----
    web_origin: str = "http://localhost:3000"

    # ---- search ----
    tavily_api_key: str | None = None
    tavily_max_results: int = 8

    # ---- manifold ----
    manifold_api_key: str | None = None
    manifold_base_url: str = "https://api.manifold.markets"

    # ---- polymarket ----
    polymarket_gamma_url: str = "https://gamma-api.polymarket.com"
    polymarket_clob_url: str = "https://clob.polymarket.com"
    polygon_rpc_url: str = "https://polygon-rpc.com"
    polymarket_private_key: str | None = None
    polymarket_funder_address: str | None = None
    polymarket_sig_type: int = 0
    polymarket_chain_id: int = 137

    # ---- storage / obs ----
    mongo_db_url: str = ""
    mongo_db_name: str = "openmind"
    agent_log_path: Path = Path("logs/agent.jsonl")
    agent_log_level: str = "INFO"
    alert_webhook_url: str | None = None

    @field_validator("agent_categories")
    @classmethod
    def _strip_categories(cls, v: str) -> str:
        return ",".join(p.strip().lower() for p in v.split(",") if p.strip())

    @property
    def categories(self) -> list[str]:
        items = [c for c in self.agent_categories.split(",") if c]
        return items if items != ["all"] else []

    @property
    def cheap_model(self) -> str:
        return self.bedrock_model_id_cheap or self.bedrock_model_id

    def cost_usd(self, input_tokens: int, output_tokens: int) -> float:
        return (
            input_tokens * self.llm_input_usd_per_mtok / 1_000_000
            + output_tokens * self.llm_output_usd_per_mtok / 1_000_000
        )


settings = Settings()
