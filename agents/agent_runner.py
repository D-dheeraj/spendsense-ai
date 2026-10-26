"""
SpendSense AI — Agent Runner
==============================
Calls the Gemini API for each of the 4 agents.
Each function takes structured data and returns agent output.

If GOOGLE_API_KEY is not set, all agents return graceful
placeholder text so the dashboard still works in ML-only mode.
"""

import json
import re
from config import GOOGLE_API_KEY, GEMINI_MODEL_NAME, AGENTS_ENABLED, get_effective_google_api_key, is_agents_enabled

# ─────────────────────────────────────────────────────────────────────────────
# Gemini Client Setup
# ─────────────────────────────────────────────────────────────────────────────

_gemini_client = None
_last_configured_key = None

def _get_gemini_client():
    global _gemini_client, _last_configured_key
    active_key = get_effective_google_api_key()
    if not active_key:
        return None

    if _gemini_client is None or _last_configured_key != active_key:
        try:
            import google.generativeai as genai
            genai.configure(api_key=active_key)
            _gemini_client = genai
            _last_configured_key = active_key
            print(f"[AgentRunner] ✅ Gemini configured with active key ({active_key[:6]}...{active_key[-4:]})")
        except Exception as e:
            print(f"[AgentRunner] Gemini init failed: {e}")
            return None
    return _gemini_client


def _call_gemini(system_prompt: str, user_message: str) -> str:
    """
    Call the Gemini API with a system prompt + user message.
    Tries primary model (gemini-flash-latest) and falls back to alternatives.
    Handles older SDK versions that do not support the system_instruction keyword.
    """
    genai = _get_gemini_client()
    if genai is None:
        return "__NO_API_KEY__"

    models_to_try = [
        GEMINI_MODEL_NAME,
        "gemini-3.5-flash-lite",
        "gemini-flash-lite-latest",
        "gemini-3.8-flash",
        "gemini-flash-latest"
    ]
    last_err = None

    # De-duplicate while preserving order
    tried = set()
    for model_name in models_to_try:
        if model_name in tried:
            continue
        tried.add(model_name)
        try:
            # Try with system_instruction first, fallback to prompt concatenation
            try:
                model = genai.GenerativeModel(
                    model_name=model_name,
                    system_instruction=system_prompt
                )
                response = model.generate_content(user_message)
            except (TypeError, Exception):
                model = genai.GenerativeModel(model_name=model_name)
                combined_prompt = f"[SYSTEM INSTRUCTIONS]\n{system_prompt}\n\n[USER REQUEST / DATA CONTEXT]\n{user_message}"
                response = model.generate_content(combined_prompt)

            if response and response.text:
                return response.text.strip()
        except Exception as e:
            last_err = e
            err_str = str(e).lower()
            print(f"[AgentRunner] Gemini call with '{model_name}' failed: {e}")
            if "429" in err_str or "quota" in err_str or "resourceexhausted" in err_str:
                print("[AgentRunner] Rate limit / quota reached (429). Fast-failing to instant rule-based generation.")
                break
            continue

    print(f"[AgentRunner] All Gemini models failed. Last error: {last_err}")
    return "__API_ERROR__"


def _extract_json(text: str):
    """
    Extract the first JSON array or object from a text response.
    Gemini sometimes wraps JSON in markdown code blocks — this handles that.
    """
    # Try stripping markdown code blocks
    cleaned = re.sub(r"```(?:json)?\s*", "", text)
    cleaned = re.sub(r"```", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Try finding JSON inside the text
        match = re.search(r"(\[.*\]|\{.*\})", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except Exception:
                pass
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Agent 1 — Categorization Agent
# ─────────────────────────────────────────────────────────────────────────────

def run_categorization_agent(transactions: list) -> list:
    """
    Agent 1: Reviews ML predictions and refines low-confidence labels.

    Input:
      transactions — list of dicts with keys:
        transaction_id, merchant, description, predicted_category, confidence

    Output:
      list of dicts: [{transaction_id: str, final_category: str}, ...]
      Falls back to ML predictions if API unavailable.
    """
    from agents.prompts import CATEGORIZATION_AGENT_PROMPT

    if not is_agents_enabled():
        # Fallback: use ML predictions as final
        return [
            {"transaction_id": t.get("transaction_id", str(i)),
             "final_category": t.get("predicted_category", "Shopping")}
            for i, t in enumerate(transactions)
        ]

    # Only send low-confidence or ambiguous ones to save API calls
    low_conf = [t for t in transactions
                if t.get("confidence", 1.0) < 0.60]

    if not low_conf:
        # All high-confidence — just use ML predictions
        return [
            {"transaction_id": t.get("transaction_id", str(i)),
             "final_category": t.get("predicted_category", "Shopping")}
            for i, t in enumerate(transactions)
        ]

    user_message = (
        f"Review these {len(low_conf)} low-confidence transaction predictions "
        f"and assign the correct category:\n\n"
        f"{json.dumps(low_conf, indent=2)}"
    )

    response_text = _call_gemini(CATEGORIZATION_AGENT_PROMPT, user_message)

    if response_text in ("__NO_API_KEY__", "__API_ERROR__"):
        return [
            {"transaction_id": t.get("transaction_id", str(i)),
             "final_category": t.get("predicted_category", "Shopping")}
            for i, t in enumerate(transactions)
        ]

    agent_corrections = _extract_json(response_text)

    # Build correction lookup: {transaction_id: final_category}
    correction_map = {}
    if isinstance(agent_corrections, list):
        for item in agent_corrections:
            if isinstance(item, dict) and "transaction_id" in item:
                correction_map[item["transaction_id"]] = item.get("final_category", "")

    # Apply corrections; keep ML prediction for non-corrected rows
    result = []
    for i, t in enumerate(transactions):
        txn_id = t.get("transaction_id", str(i))
        result.append({
            "transaction_id": txn_id,
            "final_category": correction_map.get(
                txn_id, t.get("predicted_category", "Shopping")
            )
        })
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Helper Fallback Generators (Used when LLM API key is not configured or offline)
# ─────────────────────────────────────────────────────────────────────────────

def _generate_fallback_insight(summary_data: dict) -> str:
    cat = summary_data.get("category_totals", {})
    total = summary_data.get("total_amount", 0)
    month = summary_data.get("month", "this period")
    anomalies = summary_data.get("anomaly_count", 0)
    top_merchants = summary_data.get("top_merchants", [])

    sorted_cats = sorted(cat.items(), key=lambda x: x[1], reverse=True)
    top_cat, top_amt = sorted_cats[0] if sorted_cats else ("Expenses", 0)
    pct = (top_amt / total * 100) if total > 0 else 0

    narrative = (
        f"In {month}, your total expenditure was ₹{total:,.0f} distributed across {len(cat)} spending categories. "
        f"Your highest spending category was {top_cat}, amounting to ₹{top_amt:,.0f} ({pct:.1f}% of total outflow)."
    )

    if len(sorted_cats) > 1:
        narrative += f" This was followed by {sorted_cats[1][0]} at ₹{sorted_cats[1][1]:,.0f}."

    if top_merchants:
        merchants_str = ", ".join(top_merchants[:3])
        narrative += f" The top merchants driving this spend were {merchants_str}."

    if anomalies > 0:
        narrative += (
            f" Notably, the Isolation Forest ML model flagged {anomalies} transaction(s) as statistical anomalies "
            f"that deviated significantly from normal baseline spending patterns."
        )
    else:
        narrative += " Spending remained consistent and within expected statistical boundaries."

    return narrative


def _generate_fallback_tips(spending_data: dict) -> list:
    cat = spending_data.get("category_totals", {})
    total = spending_data.get("total_amount", 0)
    top = max(cat, key=cat.get) if cat else "discretionary categories"
    top_amt = cat.get(top, 0)
    pct = (top_amt / total * 100) if total > 0 else 0

    return [
        f"Optimize {top} spend: It represents {pct:.0f}% (₹{top_amt:,.0f}) of your total outflow. Capping this by 15% would save ₹{top_amt * 0.15:,.0f}.",
        "Establish category-specific weekly caps to prevent mid-month budget overruns.",
        "Audit recurring subscription & utility bills for any dormant services or redundant plans.",
        "Implement a 48-hour cooling-off rule on high-value non-essential purchases.",
        "Set an emergency liquidity buffer equal to at least 20% of your average monthly outflow."
    ]


def _generate_fallback_alerts(anomalies: list) -> list:
    alerts = []
    for a in anomalies:
        amt = a.get('amount', 0)
        merchant = a.get('merchant', 'Unknown Merchant')
        date = a.get('date', 'Unknown Date')
        alerts.append(
            f"⚠️ Unusual transaction of ₹{amt:,.0f} detected at {merchant} on {date}. This significantly exceeds expected variance."
        )
    return alerts


# ─────────────────────────────────────────────────────────────────────────────
# Agent 2 — Insight Agent
# ─────────────────────────────────────────────────────────────────────────────

def run_insight_agent(summary_data: dict) -> str:
    """
    Agent 2: Generates a plain-English monthly spending narrative.
    """
    from agents.prompts import INSIGHT_AGENT_PROMPT

    if not is_agents_enabled():
        return _generate_fallback_insight(summary_data)

    user_message = (
        f"Generate the monthly spending insight for this data:\n\n"
        f"{json.dumps(summary_data, indent=2)}"
    )

    response = _call_gemini(INSIGHT_AGENT_PROMPT, user_message)

    if response in ("__NO_API_KEY__", "__API_ERROR__") or not response.strip():
        return _generate_fallback_insight(summary_data)

    return response


# ─────────────────────────────────────────────────────────────────────────────
# Agent 3 — Budget Advisor Agent
# ─────────────────────────────────────────────────────────────────────────────

def run_budget_advisor_agent(spending_data: dict) -> list:
    """
    Agent 3: Returns 5 specific, actionable money-saving tips.
    """
    from agents.prompts import BUDGET_ADVISOR_PROMPT

    if not is_agents_enabled():
        return _generate_fallback_tips(spending_data)

    user_message = (
        f"Generate 5 personalized budget tips for this spending data:\n\n"
        f"{json.dumps(spending_data, indent=2)}"
    )

    response_text = _call_gemini(BUDGET_ADVISOR_PROMPT, user_message)

    if response_text in ("__NO_API_KEY__", "__API_ERROR__"):
        return _generate_fallback_tips(spending_data)

    tips = _extract_json(response_text)
    if isinstance(tips, list) and tips:
        return [str(t) for t in tips]

    lines = [l.strip() for l in response_text.split("\n") if l.strip()]
    return lines[:5] if lines else _generate_fallback_tips(spending_data)


# ─────────────────────────────────────────────────────────────────────────────
# Agent 4 — Alert Agent
# ─────────────────────────────────────────────────────────────────────────────

def run_alert_agent(anomalies: list) -> list:
    """
    Agent 4: Converts anomaly flags into readable alert messages.
    """
    from agents.prompts import ALERT_AGENT_PROMPT

    if not anomalies:
        return []

    if not is_agents_enabled():
        return _generate_fallback_alerts(anomalies)

    user_message = (
        f"Write alert messages for these {len(anomalies)} flagged transactions:\n\n"
        f"{json.dumps(anomalies, indent=2)}"
    )

    response_text = _call_gemini(ALERT_AGENT_PROMPT, user_message)

    if response_text in ("__NO_API_KEY__", "__API_ERROR__"):
        return _generate_fallback_alerts(anomalies)

    alerts = _extract_json(response_text)
    if isinstance(alerts, list) and alerts:
        return [str(a) for a in alerts]

    lines = [l.strip() for l in response_text.split("\n") if l.strip()]
    return lines if lines else _generate_fallback_alerts(anomalies)


# ─────────────────────────────────────────────────────────────────────────────
# Agent 5 — Chat with Data Agent
# ─────────────────────────────────────────────────────────────────────────────

def _generate_fallback_chat_reply(user_message: str, summary_data: dict) -> str:
    """Intelligent rule-based financial chat fallback."""
    if not summary_data.get("has_data"):
        return "Aapka transaction data abhi available nahi hai. Kripya pehle transaction statement (CSV) upload karein!"

    msg_lower = user_message.lower()
    total_spend = summary_data.get("total_spend", 0)
    total_txns  = summary_data.get("total_txns", 0)
    cat_totals  = summary_data.get("category_totals", {})
    sorted_cats = sorted(cat_totals.items(), key=lambda x: x[1], reverse=True)
    top_cat, top_cat_amt = sorted_cats[0] if sorted_cats else ("Expenses", 0)

    # 1. Specific merchant match
    spec = summary_data.get("specific_merchant_match")
    if spec:
        return (
            f"Aapne **{spec['merchant']}** par kul **₹{spec['total_spend']:,.0f}** kharch kiye hain "
            f"({spec['txn_count']} transactions). Average transaction amount **₹{spec['avg_spend']:,.0f}** rahi hai "
            f"({spec['first_date']} se {spec['last_date']} tak)."
        )

    # 2. Anomalies question
    if any(w in msg_lower for w in ["anomaly", "anomalies", "unusual", "fraud", "flag"]):
        anom_count = summary_data.get("anomaly_count", 0)
        samples = summary_data.get("anomaly_samples", [])
        if anom_count == 0:
            return "Good news! Aapke kisi bhi transaction me ML anomaly flag nahi hua hai. Sabhi kharche normal pattern me hain."
        sample_str = ""
        if samples:
            s0 = samples[0]
            sample_str = f" Sabse bada flagged transaction ₹{s0['amount']:,.0f} ({s0['merchant']}, {s0['final_category']}) par tha."
        return f"Aapke data me kul **{anom_count} anomalous transactions** detect hui hain.{sample_str} Inhe verify karein!"

    # 3. Highest / Top category
    if any(w in msg_lower for w in ["highest", "sabse zyada", "top category", "maximum", "max"]):
        pct = (top_cat_amt / total_spend * 100) if total_spend > 0 else 0
        return (
            f"Aapka sabse bada kharcha **{top_cat}** category me hua hai: **₹{top_cat_amt:,.0f}** "
            f"({pct:.1f}% of total spend). Iske baad {sorted_cats[1][0] if len(sorted_cats) > 1 else 'other'} me kharcha raha."
        )

    # 4. Total spend
    if any(w in msg_lower for w in ["total", "kul", "spend", "balance", "kharcha"]):
        return (
            f"Aapka total expenditure **₹{total_spend:,.0f}** hai across **{total_txns} transactions** and "
            f"**{len(cat_totals)} categories**."
        )

    # 5. Default contextual answer
    return (
        f"Aapka total spend **₹{total_spend:,.0f}** hai. Sabse zyada kharcha **{top_cat}** (₹{top_cat_amt:,.0f}) me hua hai. "
        f"Aap kisi bhi specific merchant (jaise Zomato, Amazon, MakeMyTrip) ya category ke baare me poochh sakte hain!"
    )


def run_chat_agent(user_message: str, summary_data: dict) -> str:
    """
    Agent 5: Conversational AI responding to user questions about their financial data.
    """
    from agents.prompts import CHAT_AGENT_PROMPT

    if not is_agents_enabled():
        return _generate_fallback_chat_reply(user_message, summary_data)

    payload = {
        "user_query": user_message,
        "financial_summary": summary_data
    }

    response = _call_gemini(CHAT_AGENT_PROMPT, json.dumps(payload, indent=2))
    if response in ("__NO_API_KEY__", "__API_ERROR__") or not response.strip():
        return _generate_fallback_chat_reply(user_message, summary_data)

    return response
