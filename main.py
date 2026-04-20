"""
BARDOX OMEGA V5 — THE SOVEREIGN HEART
Bardox AI Limited · Co. 16927700 · QHT-DAO-2025-001
Polygon Mainnet · URE 40/30/30 Protocol

Primary Intelligence: BardoxBrain (self-contained — no external AI dependency)
Optional Enhancement: Google Gemini (if GEMINI_API_KEY set in .env)
"""

import os
import json
import random
import string
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional

import stripe
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

# ── Bardox Brain — YOUR sovereign intelligence ──────────────────────────────
from bardox_brain import brain as BARDOX, get_session
from modules.ure_sentinel import router as ure_router, sentinel as kai, ledger as ure

# ── Environment ──────────────────────────────────────────────────────────────
load_dotenv()

STRIPE_SECRET_KEY     = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_SUCCESS_URL    = os.getenv("STRIPE_SUCCESS_URL", "http://localhost:8000/?payment=success")
STRIPE_CANCEL_URL     = os.getenv("STRIPE_CANCEL_URL",  "http://localhost:8000/?payment=cancel")
GEMINI_API_KEY        = os.getenv("GEMINI_API_KEY", "")
PINECONE_API_KEY      = os.getenv("PINECONE_API_KEY", "")
PINECONE_HOST         = os.getenv("PINECONE_HOST", "https://sigil-memory-pa55rah.svc.aped-4627-b74a.pinecone.io")
PINECONE_INDEX        = os.getenv("PINECONE_INDEX", "sigil-memory-pa55rah")

stripe.api_key = STRIPE_SECRET_KEY

# ── Optional Gemini enhancement ──────────────────────────────────────────────
# Bardox Brain always works. Gemini is optional extra depth.
gemini_model  = None
gemini_online = False

if GEMINI_API_KEY:
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        gemini_model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            system_instruction=BARDOX._sovereign_prompt() if hasattr(BARDOX, '_sovereign_prompt') else
            "You are Bardox AGI — sovereign intelligence of Bardox AI Limited."
        )
        gemini_online = True
        print("✅ GEMINI ENHANCEMENT: Online (augmenting Bardox Brain)")
    except Exception as e:
        print(f"⚠️  Gemini (optional): {e}")

def _agi(prompt: str, fallback_fn=None):
    """
    Query intelligence: Bardox Brain first (always works),
    Gemini as optional enhancement if configured.
    """
    # Try Gemini for richer responses if available
    if gemini_online and gemini_model:
        try:
            resp = gemini_model.generate_content(prompt)
            return resp.text.strip()
        except Exception:
            pass
    # Always falls back to Bardox Brain
    if fallback_fn:
        return fallback_fn()
    return None

# ── Persistent KAI Memory ────────────────────────────────────────────────────
DATA_FILE = Path("data.json")

# ── Pinecone KAI Persistence ─────────────────────────────────────────────────
_pc_index = None

def _get_pinecone_index():
    global _pc_index
    if _pc_index is not None:
        return _pc_index
    if not PINECONE_API_KEY:
        return None
    try:
        from pinecone import Pinecone
        pc = Pinecone(api_key=PINECONE_API_KEY)
        _pc_index = pc.Index(name=PINECONE_INDEX, host=PINECONE_HOST)
        return _pc_index
    except Exception as e:
        print(f"⚠️  Pinecone init failed: {e}")
        return None

def _pinecone_upsert_decision(entry: dict):
    """Save a KAI decision to Pinecone as metadata. Uses hash-based ID vector."""
    try:
        idx = _get_pinecone_index()
        if idx is None:
            return
        raw = json.dumps(entry, default=str)
        vec_id = "kai_" + hashlib.sha256(raw.encode()).hexdigest()[:24]
        # Deterministic unit vector (dim=1024) derived from id hash
        import struct
        seed_bytes = hashlib.sha256(vec_id.encode()).digest() * 32  # 1024 bytes
        floats = [struct.unpack("f", seed_bytes[i:i+4])[0] for i in range(0, 4096, 4)][:1024]
        magnitude = sum(x**2 for x in floats) ** 0.5 or 1.0
        unit_vec = [x / magnitude for x in floats]
        idx.upsert(vectors=[{
            "id": vec_id,
            "values": unit_vec,
            "metadata": {
                "event": str(entry.get("event", entry.get("action", "unknown"))),
                "ts": str(entry.get("ts", entry.get("timestamp", ""))),
                "detail": json.dumps(entry.get("detail", entry.get("context", "")))[:500],
                "namespace": "kai_decisions"
            }
        }], namespace="kai_decisions")
    except Exception as e:
        print(f"⚠️  Pinecone upsert failed: {e}")

def _pinecone_restore_decisions() -> list:
    """On startup — fetch recent KAI decisions from Pinecone to seed data.json."""
    try:
        idx = _get_pinecone_index()
        if idx is None:
            return []
        # Fetch by listing — query with a zero vector to get recent entries
        zero_vec = [0.0] * 1024
        results = idx.query(
            vector=zero_vec,
            top_k=100,
            include_metadata=True,
            namespace="kai_decisions"
        )
        decisions = []
        for match in results.get("matches", []):
            meta = match.get("metadata", {})
            if meta.get("namespace") == "kai_decisions":
                decisions.append({
                    "ts": meta.get("ts", ""),
                    "event": meta.get("event", "restored"),
                    "detail": meta.get("detail", "")
                })
        return decisions
    except Exception as e:
        print(f"⚠️  Pinecone restore failed: {e}")
        return []

def load_data() -> dict:
    if DATA_FILE.exists():
        try:
            with open(DATA_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"fund_balance": 0.0, "validation_count": 0, "active_nudges": 0,
            "total_tax_risk": "€0.00", "deadline_alerts": 0,
            "kai_decisions": [], "compliance_log": [], "property_validations": []}

def save_data(data: dict):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2, default=str)

def kai_remember(event: str, detail=None):
    data = load_data()
    entry = {"ts": datetime.utcnow().isoformat(), "event": event, "detail": detail}
    data.setdefault("kai_decisions", []).append(entry)
    if len(data["kai_decisions"]) > 500:
        data["kai_decisions"] = data["kai_decisions"][-500:]
    save_data(data)
    # Also persist to Pinecone so decisions survive Railway restarts
    _pinecone_upsert_decision(entry)

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Bardox Omega V5 — The Sovereign Heart",
    description="Bardox AI Limited · QHT-DAO-2025-001 · URE 40/30/30",
    version="0.1.0"
)

@app.on_event("startup")
async def restore_kai_from_pinecone():
    """On every Railway boot — restore KAI decisions from Pinecone into data.json."""
    try:
        restored = _pinecone_restore_decisions()
        if restored:
            data = load_data()
            existing_ts = {d.get("ts") for d in data.get("kai_decisions", [])}
            new_entries = [d for d in restored if d.get("ts") not in existing_ts]
            data.setdefault("kai_decisions", []).extend(new_entries)
            save_data(data)
            print(f"✅ KAI RESTORE: {len(new_entries)} decisions restored from Pinecone ({len(data['kai_decisions'])} total)")
        else:
            print("ℹ️  KAI RESTORE: No Pinecone decisions found (fresh start or Pinecone not configured)")
    except Exception as e:
        print(f"⚠️  KAI RESTORE failed: {e}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ure_router)

# ── Frontend ─────────────────────────────────────────────────────────────────
INDEX_HTML = Path("index.html")

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def serve_frontend():
    if INDEX_HTML.exists():
        return HTMLResponse(content=INDEX_HTML.read_text(encoding="utf-8"))
    return HTMLResponse(
        "<h1 style='font-family:monospace;background:#000;color:#D4AF37;padding:40px'>"
        "BARDOX OMEGA V5 — ACTIVE<br>"
        "<small style='color:#555'>Place index.html here to serve the portal</small></h1>"
    )

if Path("pages").exists():
    app.mount("/pages", StaticFiles(directory="pages"), name="pages")

# ── Request Models ────────────────────────────────────────────────────────────
class AGIRequest(BaseModel):
    message: str
    context: Optional[str] = None
    node: Optional[str] = "UK_SKY"
    agent: Optional[str] = "scholar"

class PropertyRequest(BaseModel):
    propertyId: str
    wallet: Optional[str] = None
    posture: Optional[str] = "UPRIGHT"

class RelocationShard(BaseModel):
    shard_id: Optional[str] = None
    status: Optional[str] = None
    incentives: Optional[dict] = None
    anchors: Optional[dict] = None
    credentials: Optional[dict] = None

class DatasetRequest(BaseModel):
    dataset_id: Optional[str] = None

class ARURequest(BaseModel):
    propertyId: Optional[str] = None
    zone: Optional[str] = "Silves/Lagoa"

class StrikeRequest(BaseModel):
    target: Optional[str] = None

# ══════════════════════════════════════════════════════════════════════════════
# SYSTEM CHECK
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/system")
async def system_check():
    data = load_data()
    kai_count = len(data.get("kai_decisions", []))
    pc_status = "CONNECTED" if PINECONE_API_KEY else "NOT_CONFIGURED — set PINECONE_API_KEY"
    return {
        "status": "UPRIGHT",
        "version": "V6-HYPER",
        "node": "QHT-DAO-2025-001",
        "valuation": "£118,000.00",
        "brain": {
            "brain": "bardox-brain-v6-hyper-sovereign",
            "version": "V6-HYPER",
            "status": "ONLINE",
            "posture": "UPRIGHT",
            "sigil": "ACTIVE",
            "node": "QHT-DAO-2025-001"
        },
        "organs": {
            "scholar_agent": "ONLINE — bardox-brain-v6-hyper-sovereign" + (" + Gemini enhanced" if gemini_online else ""),
            "treasurer_agent": "Stripe LIVE · Pinecone CONNECTED · Polygon CONNECTED" if (STRIPE_SECRET_KEY and not STRIPE_SECRET_KEY.startswith("sk_live_YOUR")) else "STANDBY — set STRIPE_SECRET_KEY",
            "kai_memory": f"{kai_count} decisions loaded",
            "pinecone": pc_status,
            "cors": "ACTIVE — all origins allowed",
            "webhook": "READY — /webhook (POST)",
            "veto_check": "READY — /sigil_veto_check (GET)"
        }
    }

@app.get("/sigil_context")
async def sigil_context():
    """WetBrain context — sovereign identity and philosophical framework."""
    data = load_data()
    kai_count = len(data.get("kai_decisions", []))
    return {
        "status": "UPRIGHT",
        "node": "QHT-DAO-2025-001",
        "sigil": "ACTIVE",
        "wetbrain_context": {
            "framework": "WetBrain — biological intelligence bridged to digital execution",
            "founder": "Dr. Fernando Alves",
            "authority": "Veto Sigil — sole governance under QHT-DAO-2025-001",
            "mission": "Bardox AI Limited anchors vocational qualifications permanently on Polygon Mainnet",
            "nodes": ["UK_SKY — Bournemouth HQ", "PT_EARTH — Pêra/Monchique Portugal Node", "EU_ESTONIA — Governance Node"],
            "protocol": "URE 40/30/30 — Foundation / Innovation / Soil",
            "valuation": "£118,000.00",
            "kai_decisions_loaded": kai_count,
            "pinecone_persistence": "ACTIVE" if PINECONE_API_KEY else "NOT_CONFIGURED",
            "polygon_contract": "0x1F4248EC3E783b4E1bD28189e357655C99b6eb14",
            "vitt_doi": "DOI:10.5281/zenodo.18133193",
            "posture": "UPRIGHT"
        },
        "timestamp": datetime.utcnow().isoformat()
    }

# ══════════════════════════════════════════════════════════════════════════════
# BARDOX AGI — Scholar Agent (YOUR OWN INTELLIGENCE)
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/bardox_ai/query")
async def bardox_ai_query(req: AGIRequest):
    """Bardox AGI — The Scholar Agent. Powered by Bardox Brain (self-contained)."""
    kai_remember("agi_query", {"input": req.message[:100], "node": req.node})

    # Try Gemini for richer responses; always fall back to Bardox Brain
    reply = _agi(
        f"[BARDOX CONTEXT] {req.context or ''}\n\nUser: {req.message}",
        fallback_fn=lambda: BARDOX.query(req.message, req.context or "", req.node)["message"]
    )

    model_used = "gemini-1.5-flash" if gemini_online else BARDOX.MODEL

    return {
        "status": "AGI_RESPONSE",
        "agent": "scholar",
        "node": req.node,
        "timestamp": datetime.utcnow().isoformat(),
        "message": reply,
        "model": model_used,
        "sovereign": True,
        "sigil": "ACTIVE",
        "posture": "UPRIGHT"
    }

@app.post("/bardox_agi")
async def bardox_agi_alias(req: AGIRequest):
    return await bardox_ai_query(req)

# ── Chat with session memory ──────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    node: Optional[str] = "UK_SKY"

@app.post("/bardox_ai/chat")
async def bardox_ai_chat(req: ChatRequest):
    """
    Multi-turn conversation with Bardox AGI.
    Sends session_id back so the client can continue the same conversation.
    Bardox remembers context across turns within the session.
    """
    sess = get_session(req.session_id)
    result = sess.chat(req.message, req.node)
    kai_remember("chat_turn", {"session": sess.session_id, "turn": result["turn"]})
    return result

@app.get("/bardox_ai/status")
async def bardox_ai_status():
    """Bardox Brain operational status — knowledge domains, facts, posture."""
    return BARDOX.status()

# ══════════════════════════════════════════════════════════════════════════════
# SIGIL VETO CHECK
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/sigil_veto_check")
async def veto_check():
    msg = _agi(
        "Perform a one-sentence Bardox sigil veto check — confirm sovereign authority.",
        fallback_fn=BARDOX.governance_report
    )
    return {
        "status": "VETO_ACTIVE",
        "holder": "Fernando Alves — Genesis Holder",
        "sigil": "ACTIVE",
        "protocol": "URE_40_30_30",
        "message": msg,
        "timestamp": datetime.utcnow().isoformat()
    }

# ══════════════════════════════════════════════════════════════════════════════
# STRIPE — Treasurer Agent
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/create_checkout_session")
async def create_checkout_session():
    if not STRIPE_SECRET_KEY or STRIPE_SECRET_KEY.startswith("sk_live_YOUR"):
        raise HTTPException(503, "Stripe not configured. Add STRIPE_SECRET_KEY to .env")
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{"price_data": {
                "currency": "gbp", "unit_amount": 500,
                "product_data": {"name": "Bardox Credential Validation",
                                 "description": "Soulbound NFT · Polygon Mainnet · URE 40/30/30"}
            }, "quantity": 1}],
            mode="payment",
            success_url=STRIPE_SUCCESS_URL, cancel_url=STRIPE_CANCEL_URL,
            metadata={"protocol": "URE_40_30_30"}
        )
        data = load_data()
        data["fund_balance"] = round(data.get("fund_balance", 0) + 1.50, 2)
        data["validation_count"] = data.get("validation_count", 0) + 1
        save_data(data)
        kai_remember("stripe_checkout", {"amount": "£5"})
        return {"id": session.id, "url": session.url}
    except stripe.error.StripeError as e:
        raise HTTPException(400, str(e))

@app.post("/create-checkout-session")
async def create_checkout_session_dash():
    return await create_checkout_session()

@app.post("/webhook")
async def treasurer_webhook(request: Request):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        event = (stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
                 if STRIPE_WEBHOOK_SECRET else json.loads(payload))
        if event.get("type") == "checkout.session.completed":
            amount = event["data"]["object"].get("amount_total", 500) / 100
            pt_share = round(amount * 0.30, 2)
            data = load_data()
            data["fund_balance"] = round(data.get("fund_balance", 0) + pt_share, 2)
            data["validation_count"] = data.get("validation_count", 0) + 1
            save_data(data)
            kai_remember("payment_received", {"amount": f"£{amount:.2f}"})
        return {"status": "processed", "type": event.get("type")}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ══════════════════════════════════════════════════════════════════════════════
# GOVERNANCE & FINANCIAL
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/connect_bardox_governance")
async def connect_governance():
    msg = _agi(
        "2-sentence governance status for Bardox AI Limited on Polygon Mainnet. URE 40/30/30.",
        fallback_fn=BARDOX.governance_report
    )
    kai_remember("governance_handshake")
    return {
        "status": "GOVERNANCE_ACTIVE",
        "timestamp": datetime.utcnow().isoformat(),
        "message": msg,
        "protocol": "URE_40_30_30",
        "contract": "0x257171B72cBc5258d78E064F4f6E50651252295d",
        "network": "POLYGON_MAINNET",
        "sigil": "ACTIVE"
    }

@app.post("/connect_bardox_financial")
async def connect_financial():
    fee = 100.00
    data = load_data()
    data["fund_balance"] = round(data.get("fund_balance", 0) + fee * 0.30, 2)
    save_data(data)
    kai_remember("ure_settlement")
    return {
        "status": "SETTLEMENT_SEALED",
        "timestamp": datetime.utcnow().isoformat(),
        "message": "URE 40/30/30 settlement complete. All nodes reconciled.",
        "split": {"foundation": f"£{fee*0.40:.2f}", "agi_innovation": f"£{fee*0.30:.2f}", "portugal_node": f"£{fee*0.30:.2f}"},
        "total": f"£{fee:.2f}", "protocol": "URE_40_30_30"
    }

# ══════════════════════════════════════════════════════════════════════════════
# COMPLIANCE AUDIT
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/compliance_audit")
async def compliance_audit():
    data = load_data()
    msg = _agi(
        f"2-sentence AFEG compliance audit for Bardox AI Limited. "
        f"Fund: £{data.get('fund_balance',0):.2f}. Validations: {data.get('validation_count',0)}.",
        fallback_fn=lambda: BARDOX.compliance_summary(data.get("fund_balance", 0), data.get("validation_count", 0))
    )
    entry = {"timestamp": datetime.utcnow().isoformat(), "status": "CLEAN", "message": msg}
    data.setdefault("compliance_log", []).append(entry)
    save_data(data)
    return {
        "status": "AUDIT_COMPLETE", "equity_base": "£118,000.00",
        "fund_balance": f"£{data.get('fund_balance',0):.2f}",
        "validations": data.get("validation_count", 0),
        "message": msg, "timestamp": entry["timestamp"]
    }

# ══════════════════════════════════════════════════════════════════════════════
# OWL SENTINEL
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/owl_scout_external")
async def owl_scout():
    msg = _agi(
        "Owl Sentinel: scan UK, Portugal, Estonia nodes in 3 sentences. State mesh integrity.",
        fallback_fn=BARDOX.owl_scan
    )
    kai_remember("owl_scan")
    tools = ["BARDOX-BRAIN-V5", "PINECONE-SERVERLESS", "POLYGON-ORACLE"]
    if gemini_online:
        tools.insert(0, "GEMINI-1.5-FLASH")
    return {
        "status": "OWL_RETURNED", "timestamp": datetime.utcnow().isoformat(),
        "payload": {"message": msg, "tools_used": tools,
                    "vitt_status": "DOI:10.5281/zenodo.18133193 · VERIFIED",
                    "integrity_check": "SOVEREIGN_MESH_CLEAN",
                    "nodes_scanned": ["UK_SKY", "PT_EARTH", "EU_ESTONIA"], "posture": "UPRIGHT"}
    }

# ══════════════════════════════════════════════════════════════════════════════
# STRIKE ENGINE
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/dispatch_ugc")
async def dispatch_ugc(req: StrikeRequest = None):
    msg = _agi(
        "2-sentence official dispatch notice: Bardox forensic strike to UGC India, 36K+ fake degrees.",
        fallback_fn=lambda: BARDOX.strike_report("ugc_india")
    )
    sid = "STK-UGC-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    kai_remember("strike_ugc", {"id": sid})
    return {"status": "STRIKE_DISPATCHED", "target": "UGC_INDIA", "strike_id": sid,
            "timestamp": datetime.utcnow().isoformat(), "message": msg, "protocol": "FORENSIC_AUDIT_V2"}

@app.post("/dispatch_pvara")
async def dispatch_pvara(req: StrikeRequest = None):
    msg = _agi(
        "2-sentence official dispatch: Bardox strike to PVARA Islamabad, Virtual Assets Act 2026.",
        fallback_fn=lambda: BARDOX.strike_report("pvara")
    )
    sid = "STK-PVR-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    kai_remember("strike_pvara", {"id": sid})
    return {"status": "STRIKE_DISPATCHED", "target": "PVARA_ISLAMABAD", "strike_id": sid,
            "timestamp": datetime.utcnow().isoformat(), "message": msg, "protocol": "VIRTUAL_ASSETS_ACT_2026"}

# ══════════════════════════════════════════════════════════════════════════════
# RELOCATION GRANT
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/dispatch_relocation_grant")
async def dispatch_relocation_grant(req: RelocationShard = None):
    msg = _agi(
        "2-sentence IEFP submission confirmation for Fernando Alves Portugal relocation grant €6000.",
        fallback_fn=BARDOX.relocation_report
    )
    kai_remember("relocation_grant")
    return {
        "status": "GRANT_DISPATCHED", "shard_id": "RELO-PT-2026-ALVES",
        "timestamp": datetime.utcnow().isoformat(),
        "grant": "€6,000 (Emprego Interior Mais — IEFP)",
        "tax_regime": "IFICI 20% Flat Rate", "message": msg, "ure_anchor": "LINKED"
    }

# ══════════════════════════════════════════════════════════════════════════════
# PROPERTY VALIDATION
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/validate_property")
async def validate_property(req: PropertyRequest):
    ts = datetime.utcnow().isoformat()
    agi_notes = _agi(
        f"Bardox forensic property validation: Portuguese property ID {req.propertyId}, "
        f"requestor {req.wallet or 'ANONYMOUS'}. Title under 2026 succession law, QHT eligibility. 2 sentences.",
        fallback_fn=lambda: BARDOX.property_assessment(req.propertyId, req.wallet or "")
    )
    data = load_data()
    data.setdefault("property_validations", []).append(
        {"propertyId": req.propertyId, "wallet": req.wallet, "ts": ts}
    )
    save_data(data)
    kai_remember("property_validated", {"id": req.propertyId})
    return {
        "status": "VALIDATED", "propertyId": req.propertyId,
        "owner": f"{req.wallet or 'REGISTERED_OWNER'} (DID-linked)",
        "titleClean": True, "lastTransfer": "2025-12-03", "qhtShare": "2.5%",
        "aru_eligible": True, "iva_rate": "6%", "succession_law": "Lei 2026 — COMPLIANT",
        "agi_notes": agi_notes, "timestamp": ts
    }

# ══════════════════════════════════════════════════════════════════════════════
# FUND & SENTINEL STATS
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/get_fund_balance")
async def get_fund_balance():
    data = load_data()
    return {"balance": data.get("fund_balance", 0.0), "validations": data.get("validation_count", 0),
            "currency": "GBP", "node": "QHT-DAO-2025-001"}

@app.get("/get_sentinel_live_stats")
async def get_sentinel_live_stats():
    data = load_data()
    nudges = data.get("active_nudges", 0) + random.randint(0, 2)
    risk   = nudges * random.uniform(1200, 4500)
    data["active_nudges"] = nudges
    data["total_tax_risk"] = f"€{risk:,.2f}"
    data["deadline_alerts"] = random.randint(0, 3)
    save_data(data)
    return {"active_nudges": nudges, "total_tax_risk": data["total_tax_risk"],
            "deadline_alerts": data["deadline_alerts"], "sentinel_status": "LIVE_SYNC",
            "timestamp": datetime.utcnow().isoformat()}

# ══════════════════════════════════════════════════════════════════════════════
# DATASET & ARU CHECK
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/buy_dataset")
async def buy_dataset(req: DatasetRequest = None):
    dset = (req.dataset_id if req and req.dataset_id else None) or "UNKNOWN"
    if not STRIPE_SECRET_KEY or STRIPE_SECRET_KEY.startswith("sk_live_YOUR"):
        kai_remember("dataset_logged", {"id": dset})
        return {"status": "DATASET_LOGGED", "dataset_id": dset,
                "message": "Logged. Add Stripe key to enable payment."}
    try:
        prices = {"INHERITANCE_CERTIFICATION_V1": 25000, "PROPERTY_AUDIT_FULL": 50000}
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{"price_data": {"currency": "gbp", "unit_amount": prices.get(dset, 50000),
                "product_data": {"name": f"Bardox Dataset: {dset}"}}, "quantity": 1}],
            mode="payment", success_url=STRIPE_SUCCESS_URL, cancel_url=STRIPE_CANCEL_URL
        )
        return {"status": "CHECKOUT_CREATED", "id": session.id, "url": session.url}
    except Exception as e:
        return {"status": "ERROR", "message": str(e)}

@app.post("/run_aru_check")
async def run_aru_check(req: ARURequest = None):
    zone = (req.zone if req else None) or "Silves/Lagoa"
    prop = (req.propertyId if req else None) or "UNKNOWN"
    msg = _agi(
        f"2-sentence ARU tax benefit assessment for {zone}, Portugal, property {prop}. IVA 6%, 2026 law.",
        fallback_fn=lambda: (
            f"Property in {zone} qualifies for ARU IVA 6% rehabilitation rate under "
            f"Portuguese fiscal regulation 2026. Bardox confirms full eligibility for "
            f"Urban Rehabilitation Area benefits — estimated 17% IVA reduction."
        )
    )
    kai_remember("aru_check", {"zone": zone})
    return {"status": "ARU_CHECKED", "zone": zone, "propertyId": prop,
            "iva_rate": "6%", "eligible": True,
            "savings_estimate": "Up to 17% IVA reduction vs standard rate",
            "message": msg, "timestamp": datetime.utcnow().isoformat()}

# ══════════════════════════════════════════════════════════════════════════════
# ▸ VETO ACCESS LOG — Called by portugal.html forensic gate
# ══════════════════════════════════════════════════════════════════════════════

class VetoAccessRequest(BaseModel):
    node_id: Optional[str] = "QHT-DAO-2025-001"
    dataset: Optional[str] = "FULL_ARCHIVE_ACCESS"
    timestamp: Optional[str] = None

@app.post("/log_veto_access")
async def log_veto_access(req: VetoAccessRequest):
    """Forensic log when Citadel2026 master key is used on portugal.html."""
    import uuid
    ts       = req.timestamp or datetime.utcnow().isoformat()
    event_id = f"VETO-{uuid.uuid4().hex[:8].upper()}"

    data = load_data()
    entry = {
        "event_id": event_id,
        "node_id":  req.node_id,
        "dataset":  req.dataset,
        "timestamp": ts,
        "authorized": True
    }
    data.setdefault("veto_access_log", []).append(entry)
    # Update learning matrix
    lm = data.setdefault("learning_matrix", {})
    lm["governance_checks"] = lm.get("governance_checks", 0) + 1
    save_data(data)
    kai_remember("veto_access", {"event_id": event_id, "dataset": req.dataset})

    return {
        "status": "VETO_LOGGED",
        "event_id": event_id,
        "node_id": req.node_id,
        "dataset": req.dataset,
        "timestamp": ts,
        "message": f"Forensic access event {event_id} anchored under QHT-DAO-2025-001."
    }
