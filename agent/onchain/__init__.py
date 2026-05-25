"""On-chain settlement on Arc: anchor reasoning-trace hashes + settle USDC."""

from agent.onchain.arc import ArcClient, get_arc
from agent.onchain.trace import build_trace, canonical, trace_hash

__all__ = ["ArcClient", "get_arc", "build_trace", "canonical", "trace_hash"]
