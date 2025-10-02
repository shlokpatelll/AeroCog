#!/usr/bin/env python3
"""
orchestrator_demo.py
Minimal UAV orchestration: user prompt + video features -> LLM -> validated server JSON.

Setup:
  pip install openai
  export OPENAI_API_KEY="sk-..."   # (macOS/Linux)
  # or in PowerShell:
  # $env:OPENAI_API_KEY="sk-..."

Run:
  python orchestrator_demo.py
"""

import json, os, time, uuid
from typing import List, Dict, Any, Tuple

# ==============================
# 0) Minimal helpers / parsing
# ==============================

def parse_user_prompt(text: str) -> Dict[str, Any]:
    t = text.lower()
    intent = (
        "capture_photo" if ("photo" in t or "picture" in t)
        else ("search_poi" if "coffee shop" in t
              else "navigate")
    )

    targets: List[str] = []
    if "red house" in t: targets.append("red house")
    if "coffee shop" in t:
        targets.append("coffee shop")
        if "open" in t: targets.append("open_now")

    constraints = {}
    if "2 mile" in t or "two mile" in t: constraints["radius_m"] = 3218

    success = {}
    if intent == "capture_photo": success["photo_saved"] = True
    elif intent == "search_poi":  success["answer_yes_no"] = True

    return {
        "intent": intent,
        "targets": targets or ["target"],
        "constraints": constraints,
        "success": success,
        "ambiguities": []
    }

def summarize_video_features(features: List[Dict[str, Any]],
                             max_frames: int = 5,
                             max_objs_per_frame: int = 5) -> List[Dict[str, Any]]:
    if not features: return []
    frames = features[-max_frames:]
    trimmed = []
    for fr in frames:
        objs = fr.get("objects", [])[:max_objs_per_frame]
        trimmed.append({
            "ts": fr.get("ts"),
            "objects": [
                {"label": o.get("label"),
                 "score": round(float(o.get("score", 0)), 3),
                 "box": o.get("box")}
                for o in objs
            ]
        })
    return trimmed

# ======================================
# 1) JSON schema (server expects this)
# ======================================

def expected_payload_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "required": ["task_id","mission","environment_summary","plan","safety","server_payload"],
        "properties": {
            "task_id": {"type":"string"},
            "mission": {
                "type":"object",
                "required":["intent","targets","constraints","success"],
                "properties":{
                    "intent":{"type":"string"},
                    "targets":{"type":"array","items":{"type":"string"}},
                    "constraints":{"type":"object"},
                    "success":{"type":"object"}
                }
            },
            "environment_summary": {
                "type":"object",
                "required":["video_digest"],
                "properties":{
                    "video_digest":{"type":"array"}
                }
            },
            "plan": {
                "type":"object",
                "required":["high_level_steps","next_action"],
                "properties":{
                    "high_level_steps":{"type":"array","items":{"type":"string"}},
                    "next_action":{"type":"object"}  # e.g., { "tool":"NAV.yaw", "args":{"deg": 45}, "why":"..." }
                }
            },
            "safety": {
                "type":"object",
                "required":["geofence","altitude_min_m","altitude_max_m","low_battery_pct"],
                "properties":{
                    "geofence":{"type":"array"},   # list of [lon,lat]
                    "altitude_min_m":{"type":"number"},
                    "altitude_max_m":{"type":"number"},
                    "low_battery_pct":{"type":"number"}
                }
            },
            "server_payload": {
                "type":"object",
                "required":["timestamp","llm_version","data"],
                "properties":{
                    "timestamp":{"type":"number"},
                    "llm_version":{"type":"string"},
                    "data":{"type":"object"}
                }
            }
        }
    }

# ==============================
# 2) Prompt construction
# ==============================

def build_system_prompt(safety_cfg: Dict[str, Any]) -> str:
    alt_min = safety_cfg.get("altitude_min_m", 5)
    alt_max = safety_cfg.get("altitude_max_m", 60)
    low_batt = safety_cfg.get("low_battery_pct", 20)
    geofence = safety_cfg.get(
        "geofence_points",
        [(-73.0, 40.7), (-73.0, 40.8), (-72.9, 40.8), (-72.9, 40.7)]
    )

    return f"""
You are the UAV Orchestration Service. Your job is to produce ONE JSON object called the SERVER PROMPT.
Rules:
- Include all required fields in the schema below (no extra top-level keys).
- Be concise but complete. No explanation text outside JSON.
- Respect safety constraints first.

SAFETY (hard):
- Altitude: {alt_min}–{alt_max} m AGL
- Low battery threshold: {low_batt}%
- Geofence polygon: {geofence}

TOOLS (examples used by downstream planner; you don't execute them here):
- NAV.move_to({{ "lat":float, "lon":float, "alt":float }})
- NAV.yaw({{ "deg":float }})
- LOOK.find({{ "query":string, "box_threshold":0..1 }})
- CAPTURE.photo({{ "target":"current_view" }})

OUTPUT SCHEMA (JSON ONLY):
{json.dumps(expected_payload_schema(), indent=2)}
""".strip()

def build_user_content(mission: Dict[str, Any],
                       video_digest: List[Dict[str, Any]],
                       extras: Dict[str, Any]) -> str:
    content = {
        "mission": mission,
        "video_digest": video_digest,
        "extras": extras
    }
    return json.dumps(content, ensure_ascii=False)

# ==============================
# 3) OpenAI LLM call (real)
# ==============================

def call_llm(system_prompt: str, user_content: str) -> str:
    """
    Attempts Structured Outputs (Responses API). If unavailable, falls back to
    Chat Completions with JSON mode. Returns a JSON string.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set.")

    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    schema = expected_payload_schema()

    # --- Try strict JSON Schema via Responses API ---
    try:
        resp = client.responses.create(
            model="gpt-4o-mini",
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "ServerPrompt",
                    "schema": schema,
                    "strict": True
                }
            },
            temperature=0
        )
        # Prefer the SDK convenience:
        content = getattr(resp, "output_text", None)
        if not content:
            # Fallback: try to extract first text-like output
            out = getattr(resp, "output", None)
            if isinstance(out, list):
                for chunk in out:
                    if getattr(chunk, "type", "") == "output_text":
                        content = getattr(chunk, "text", None)
                        if content:
                            break
        if not content:
            raise RuntimeError("Empty response from Responses API.")
        return content
    except Exception:
        # Fall back to JSON mode via Chat Completions
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        )
        return completion.choices[0].message.content

# ==============================
# 4) Lightweight validation
# ==============================

def validate_payload(payload: Dict[str, Any]) -> Tuple[bool, str]:
    schema = expected_payload_schema()
    missing = [k for k in schema["required"] if k not in payload]
    if missing:
        return False, f"Missing keys: {missing}"
    for k in ["intent","targets","constraints","success"]:
        if k not in payload["mission"]:
            return False, f"mission.{k} missing"
    if "video_digest" not in payload["environment_summary"]:
        return False, "environment_summary.video_digest missing"
    if "next_action" not in payload["plan"]:
        return False, "plan.next_action missing"
    return True, "ok"

# ==============================
# 5) Demo runner
# ==============================

def main():
    # A) Inputs you already have
    user_prompt_text = "Find the red house and take a photo, then come back."
    raw_features = [
        {"ts": 10.1, "objects":[{"label":"house","score":0.81,"box":[100,120,300,420]},
                                {"label":"car","score":0.74,"box":[30,60,80,100]}]},
        {"ts": 10.5, "objects":[{"label":"red object","score":0.65,"box":[90,110,310,430]}]},
        {"ts": 11.0, "objects":[{"label":"house","score":0.86,"box":[105,125,295,415]}]},
    ]
    safety_cfg = {
        "altitude_min_m": 5,
        "altitude_max_m": 60,
        "low_battery_pct": 20,
        "geofence_points": [(-73.0, 40.7), (-73.0, 40.8), (-72.9, 40.8), (-72.9, 40.7)]
    }

    # B) Build orchestration inputs
    mission = parse_user_prompt(user_prompt_text)
    video_digest = summarize_video_features(raw_features, max_frames=3, max_objs_per_frame=3)
    system_prompt = build_system_prompt(safety_cfg)
    user_content = build_user_content(mission, video_digest, extras={"source":"demo"})

    # C) Call the LLM (OpenAI)
    out = call_llm(system_prompt, user_content)

    # D) Validate & print
    try:
        payload = json.loads(out)
    except Exception as e:
        print("❌ LLM did not return valid JSON:", e)
        print("Raw output:\n", out)
        return

    ok, msg = validate_payload(payload)
    if not ok:
        print("❌ Payload failed validation:", msg)
        print(json.dumps(payload, indent=2))
        return

    print("\n✅ SERVER PROMPT JSON (validated):\n")
    print(json.dumps(payload, indent=2))

if __name__ == "__main__":
    main()
