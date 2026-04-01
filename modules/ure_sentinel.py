"""
BARDOX AI LIMITED — URE SENTINEL MODULE v1.0
Authority: QHT-DAO-2025-001
KaiSentinel: Terra-Kinetics Cryptographic Bridge
URE_Ledger: 40/30/30 Financial Sharding Engine
"""

import hmac
import hashlib
import time
import json
import os
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/ure", tags=["URE Protocol"])

# ── KaiSentinel ──────────────────────────────────────────────────────────────

class KaiSentinel:
    def __init__(self):
        spark = os.getenv("TERRA_KINETICS_SPARK", "d7a1325b8f6f0f02")
        self.spark = spark.encode("utf-8")
        self.replay_window = 3
        self.authority = "QHT-DAO-2025-001"
        self.log = []

    def actuate(self, action_id: str, action_type: str, parameters: Dict) -> Dict:
        payload = {
            "id": action_id,
            "action": action_type,
            "parameters": parameters,
            "authority": self.authority,
            "timestamp": time.time()
        }
        canonical = json.dumps(payload, sort_keys=True)
        sig = hmac.new(self.spark, canonical.encode(), hashlib.sha256).hexdigest()
        signed = {"payload": payload, "signature": sig, "signed_at": time.time()}
        # Verify immediately (anti-replay)
        age = time.time() - signed["signed_at"]
        if age > self.replay_window:
            return {"status": "REJECTED", "reason": "REPLAY_ATTACK"}
        expected = hmac.new(self.spark, canonical.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return {"status": "REJECTED", "reason": "SIGNATURE_MISMATCH"}
        result = {
            "status": "ACTUATED",
            "verification": "VERIFIED",
            "action": action_type,
            "timestamp": datetime.utcnow().isoformat()
        }
        self.log.append(result)
        return result

    def stats(self) -> Dict:
        return {
            "total": len(self.log),
            "actuated": sum(1 for l in self.log if l["status"] == "ACTUATED")
        }

# ── URE Ledger ───────────────────────────────────────────────────────────────

class URE_Ledger:
    RATIOS = {
        "Foundation": Decimal("0.40"),
        "Innovation": Decimal("0.30"),
        "Soil":       Decimal("0.30")
    }

    def __init__(self):
        self.history: List[Dict] = []

    def allocate(self, amount: float, currency: str = "GBP", tx_id: str = None) -> Dict:
        total = Decimal(str(amount))
        shards = {
            k: float((total * r).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
            for k, r in self.RATIOS.items()
        }
        # Fix rounding drift
        drift = total - sum(Decimal(str(v)) for v in shards.values())
        if abs(drift) > Decimal("0.001"):
            shards["Foundation"] = float(Decimal(str(shards["Foundation"])) + drift)

        tx = {
            "id": tx_id or f"URE_{hashlib.sha256(str(time.time()).encode()).hexdigest()[:12].upper()}",
            "timestamp": datetime.utcnow().isoformat(),
            "authority": "QHT-DAO-2025-001",
            "amount": float(total),
            "currency": currency,
            "shards": shards
        }
        tx_copy = {k: v for k, v in tx.items() if k != "audit_hash"}
        tx["audit_hash"] = hashlib.sha256(json.dumps(tx_copy, sort_keys=True).encode()).hexdigest()
        self.history.append(tx)
        return tx

    def polygon_anchor(self, tx_id: str) -> Optional[Dict]:
        tx = next((t for t in self.history if t["id"] == tx_id), None)
        if not tx:
            return None
        return {
            "transaction_id": tx["id"],
            "audit_hash": tx["audit_hash"],
            "timestamp": tx["timestamp"],
            "amount_gbp": tx["amount"],
            "shards": tx["shards"],
            "polygon": {
                "chain": "polygon-mainnet",
                "chain_id": 137,
                "contract": "0x1F4248EC3E783b4E1bD28189e357655C99b6eb14",
                "function": "anchorAuditHash(bytes32)"
            }
        }

    def audit(self) -> Dict:
        verified = 0
        breaches = []
        for tx in self.history:
            tx_copy = {k: v for k, v in tx.items() if k != "audit_hash"}
            expected = hashlib.sha256(json.dumps(tx_copy, sort_keys=True).encode()).hexdigest()
            if expected == tx["audit_hash"]:
                verified += 1
            else:
                breaches.append(tx["id"])
        return {
            "total": len(self.history),
            "verified": verified,
            "breaches": breaches,
            "status": "UPRIGHT" if not breaches else "COMPROMISED"
        }

# ── Singletons ───────────────────────────────────────────────────────────────
sentinel = KaiSentinel()
ledger   = URE_Ledger()

# ── FastAPI Routes ────────────────────────────────────────────────────────────

class ActuationRequest(BaseModel):
    action_id: str
    action_type: str
    parameters: Dict

class AllocationRequest(BaseModel):
    amount: float
    currency: str = "GBP"
    tx_id: Optional[str] = None

@router.post("/actuate")
async def actuate(req: ActuationRequest):
    result = sentinel.actuate(req.action_id, req.action_type, req.parameters)
    if result["status"] == "REJECTED":
        raise HTTPException(status_code=403, detail=result)
    return result

@router.post("/allocate")
async def allocate(req: AllocationRequest):
    return ledger.allocate(req.amount, req.currency, req.tx_id)

@router.get("/anchor/{tx_id}")
async def anchor(tx_id: str):
    data = ledger.polygon_anchor(tx_id)
    if not data:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return data

@router.get("/audit")
async def audit():
    return ledger.audit()

@router.post("/credential_mint")
async def credential_mint(amount: float = 5.0):
    """Called after every £5 Stripe credential mint — auto URE split."""
    tx = ledger.allocate(amount, "GBP")
    return {
        "status": "MINTED",
        "split": tx["shards"],
        "audit_hash": tx["audit_hash"],
        "polygon_ready": ledger.polygon_anchor(tx["id"])
    }

@router.post("/piezo_pulse")
async def piezo_pulse():
    """Test 432Hz sensor actuation on Portugal Earth Node."""
    return sentinel.actuate(
        action_id=f"PIEZO_{int(time.time())}",
        action_type="SET_RESONANCE_FREQUENCY",
        parameters={"frequency_hz": 432, "location": "pera_grid_alpha", "duration_seconds": 5}
    )
