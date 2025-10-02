#!/usr/bin/env python3
"""
test_prompts.py
Test file with 10 example UAV prompts and LLM response generation.
"""

import json
import time
import os
from dotenv import load_dotenv
from agentic.orchestrator_demo import (
    parse_user_prompt, 
    summarize_video_features, 
    build_system_prompt, 
    build_user_content, 
    call_llm, 
    validate_payload
)

# Load environment variables from .env file
load_dotenv()

def get_test_prompts():
    """Return 10 diverse UAV mission prompts"""
    return [
        "Find the red house and take a photo, then come back.",
        "Search for coffee shops within 2 miles and tell me if any are open now.",
        "Navigate to the tallest building in the area and survey the surroundings.",
        "Take a photo of the car parked near the house.",
        "Look for any people in the park and count how many you see.",
        "Find the nearest gas station and check if it's operational.",
        "Survey the construction site and identify any safety hazards.",
        "Search for lost pets in the neighborhood within a 1-mile radius.",
        "Take aerial photos of the traffic intersection during rush hour.",
        "Find the blue car that was reported stolen and capture its license plate."
    ]

def get_sample_video_features():
    """Return realistic video features for testing"""
    return [
        {"ts": 10.1, "objects": [
            {"label": "house", "score": 0.81, "box": [100, 120, 300, 420]},
            {"label": "car", "score": 0.74, "box": [30, 60, 80, 100]},
            {"label": "person", "score": 0.68, "box": [200, 150, 250, 300]}
        ]},
        {"ts": 10.5, "objects": [
            {"label": "red object", "score": 0.65, "box": [90, 110, 310, 430]},
            {"label": "building", "score": 0.79, "box": [400, 200, 600, 500]},
            {"label": "tree", "score": 0.72, "box": [50, 50, 120, 200]}
        ]},
        {"ts": 11.0, "objects": [
            {"label": "house", "score": 0.86, "box": [105, 125, 295, 415]},
            {"label": "vehicle", "score": 0.71, "box": [25, 55, 85, 105]},
            {"label": "sign", "score": 0.63, "box": [300, 100, 350, 150]}
        ]},
        {"ts": 11.5, "objects": [
            {"label": "construction", "score": 0.77, "box": [500, 300, 700, 600]},
            {"label": "crane", "score": 0.69, "box": [480, 280, 520, 400]},
            {"label": "worker", "score": 0.58, "box": [520, 350, 560, 420]}
        ]},
        {"ts": 12.0, "objects": [
            {"label": "park", "score": 0.82, "box": [100, 200, 400, 500]},
            {"label": "bench", "score": 0.64, "box": [150, 250, 200, 280]},
            {"label": "dog", "score": 0.59, "box": [180, 270, 220, 320]}
        ]}
    ]

def get_safety_config():
    """Return safety configuration"""
    return {
        "altitude_min_m": 5,
        "altitude_max_m": 60,
        "low_battery_pct": 20,
        "geofence_points": [(-73.0, 40.7), (-73.0, 40.8), (-72.9, 40.8), (-72.9, 40.7)]
    }

def test_single_prompt(prompt_text, video_features, safety_cfg, prompt_id):
    """Test a single prompt and return results"""
    print(f"Testing Prompt {prompt_id}: '{prompt_text}'")
    
    try:
        # Parse user prompt
        mission = parse_user_prompt(prompt_text)
        
        # Summarize video features
        video_digest = summarize_video_features(video_features, max_frames=3, max_objs_per_frame=3)
        
        # Build prompts
        system_prompt = build_system_prompt(safety_cfg)
        user_content = build_user_content(mission, video_digest, extras={"prompt_id": prompt_id})
        
        # Call LLM
        start_time = time.time()
        llm_response = call_llm(system_prompt, user_content)
        response_time = time.time() - start_time
        
        # Parse and validate response
        payload = json.loads(llm_response)
        is_valid, validation_msg = validate_payload(payload)
        
        return {
            "prompt_id": prompt_id,
            "prompt_text": prompt_text,
            "mission_parsed": mission,
            "video_digest": video_digest,
            "llm_response": llm_response,
            "payload": payload,
            "is_valid": is_valid,
            "validation_msg": validation_msg,
            "response_time": response_time,
            "timestamp": time.time()
        }
        
    except Exception as e:
        return {
            "prompt_id": prompt_id,
            "prompt_text": prompt_text,
            "error": str(e),
            "timestamp": time.time()
        }

def run_all_tests():
    """Run all test prompts and save results"""
    prompts = get_test_prompts()
    video_features = get_sample_video_features()
    safety_cfg = get_safety_config()
    
    print("🚁 UAV Orchestration Test Suite")
    print("=" * 60)
    print(f"Testing {len(prompts)} prompts...")
    print("=" * 60)
    
    results = []
    
    for i, prompt in enumerate(prompts, 1):
        result = test_single_prompt(prompt, video_features, safety_cfg, i)
        results.append(result)
        
        if "error" in result:
            print(f"❌ Prompt {i} failed: {result['error']}")
        else:
            status = "✅" if result["is_valid"] else "⚠️"
            print(f"{status} Prompt {i} completed in {result['response_time']:.2f}s")
            if not result["is_valid"]:
                print(f"   Validation: {result['validation_msg']}")
        
        # Small delay between requests
        time.sleep(1)
    
    return results

def save_results_to_file(results, filename="output.txt"):
    """Save all test results to a text file"""
    with open(filename, 'w', encoding='utf-8') as f:
        f.write("UAV Orchestration Test Results\n")
        f.write("=" * 50 + "\n")
        f.write(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total Prompts Tested: {len(results)}\n\n")
        
        for result in results:
            f.write(f"\n{'='*60}\n")
            f.write(f"PROMPT {result['prompt_id']}\n")
            f.write(f"{'='*60}\n")
            f.write(f"Text: {result['prompt_text']}\n")
            f.write(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(result['timestamp']))}\n")
            
            if "error" in result:
                f.write(f"ERROR: {result['error']}\n")
            else:
                f.write(f"Response Time: {result['response_time']:.2f}s\n")
                f.write(f"Valid JSON: {result['is_valid']}\n")
                if not result['is_valid']:
                    f.write(f"Validation Error: {result['validation_msg']}\n")
                
                f.write(f"\nParsed Mission:\n")
                f.write(json.dumps(result['mission_parsed'], indent=2))
                
                f.write(f"\n\nVideo Digest:\n")
                f.write(json.dumps(result['video_digest'], indent=2))
                
                f.write(f"\n\nLLM Response:\n")
                f.write(result['llm_response'])
                
                f.write(f"\n\nParsed Payload:\n")
                f.write(json.dumps(result['payload'], indent=2))
            
            f.write(f"\n\n")
    
    print(f"\n📄 Results saved to {filename}")

def main():
    """Main test runner"""
    results = run_all_tests()
    
    # Print summary
    successful = sum(1 for r in results if "error" not in r and r.get("is_valid", False))
    failed = sum(1 for r in results if "error" in r)
    invalid_json = sum(1 for r in results if "error" not in r and not r.get("is_valid", False))
    
    print(f"\n📊 Test Summary:")
    print(f"✅ Successful: {successful}")
    print(f"⚠️  Invalid JSON: {invalid_json}")
    print(f"❌ Failed: {failed}")
    print(f"📈 Success Rate: {successful/len(results)*100:.1f}%")
    
    # Save to file
    save_results_to_file(results)

if __name__ == "__main__":
    main()
