#!/usr/bin/env python3
"""
orchestrator_demo.py
Minimal UAV awesome orchestration: user prompt + video features -> LLM -> validated server JSON.

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
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

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
You are an expert UAV Orchestration Service that analyzes user commands and creates mission plans. Your job is to produce ONE JSON object that follows the exact schema below.

INTENT ANALYSIS:
Analyze the user's mission request and identify:
- Primary intent: "capture_photo", "search_poi", "navigate", or "survey"
- Targets: specific objects, locations, or POIs mentioned
- Constraints: distance limits, time constraints, altitude requirements
- Success criteria: what constitutes mission completion

MISSION PLANNING:
Based on the intent and video analysis, create:
- High-level steps: logical sequence of actions to complete the mission
- Next action: immediate next step with specific tool and parameters
- Safety considerations: respect all hard constraints

SAFETY CONSTRAINTS (MANDATORY):
- Altitude: {alt_min}–{alt_max} m AGL (never exceed)
- Low battery threshold: {low_batt}% (return to base if below)
- Geofence polygon: {geofence} (stay within these coordinates)

AVAILABLE TOOLS:
- NAV.move_to({{ "lat":float, "lon":float, "alt":float }}) - Move to coordinates
- NAV.yaw({{ "deg":float }}) - Rotate drone orientation
- LOOK.find({{ "query":string, "box_threshold":0.5 }}) - Search for objects
- CAPTURE.photo({{ "target":"current_view" }}) - Take photo

VIDEO ANALYSIS:
Use the video_digest to understand current environment:
- Identify detected objects and their confidence scores
- Note spatial relationships and locations
- Consider object movement patterns over time

OUTPUT REQUIREMENTS:
- Return ONLY valid JSON matching the schema below
- Include all required fields
- Be specific in next_action parameters
- Explain reasoning in "why" field of next_action
- Set realistic success criteria

SCHEMA:
{json.dumps(expected_payload_schema(), indent=2)}
""".strip()

def build_user_content(mission: Dict[str, Any],
                       video_digest: List[Dict[str, Any]],
                       extras: Dict[str, Any]) -> str:
    content = {
        "mission": mission,
        "video_digest": video_digest,
        "extras": extras,
        "context": {
            "current_time": time.time(),
            "mission_priority": "high" if mission.get("intent") == "capture_photo" else "medium",
            "environment_notes": f"Detected {len(video_digest)} recent frames with object detections"
        }
    }
    return json.dumps(content, ensure_ascii=False, indent=2)

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
    
    print("🚁 UAV Orchestration Demo")
    print("=" * 50)
    print(f"User Command: '{user_prompt_text}'")
    print(f"Video Frames: {len(raw_features)}")
    print(f"Safety Config: Alt {safety_cfg['altitude_min_m']}-{safety_cfg['altitude_max_m']}m, Battery {safety_cfg['low_battery_pct']}%")
    print("=" * 50)

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

def test_multiple_prompts():
    """Test the system with different user prompts"""
    test_cases = [
        "Find the red house and take a photo, then come back.",
        "Search for coffee shops within 2 miles and tell me if any are open now.",
        "Navigate to the tallest building in the area and survey the surroundings.",
        "Take a photo of the car parked near the house."
    ]
    
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
    
    print("\n🧪 Testing Multiple User Prompts")
    print("=" * 60)
    
    for i, prompt in enumerate(test_cases, 1):
        print(f"\nTest Case {i}: '{prompt}'")
        print("-" * 40)
        
        mission = parse_user_prompt(prompt)
        video_digest = summarize_video_features(raw_features, max_frames=3, max_objs_per_frame=3)
        system_prompt = build_system_prompt(safety_cfg)
        user_content = build_user_content(mission, video_digest, extras={"test_case": i})
        
        try:
            out = call_llm(system_prompt, user_content)
            payload = json.loads(out)
            ok, msg = validate_payload(payload)
            
            if ok:
                print(f"✅ Valid JSON - Intent: {payload['mission']['intent']}")
                print(f"   Targets: {payload['mission']['targets']}")
                print(f"   Next Action: {payload['plan']['next_action'].get('tool', 'N/A')}")
            else:
                print(f"❌ Validation failed: {msg}")
                
        except Exception as e:
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
    test_multiple_prompts()
