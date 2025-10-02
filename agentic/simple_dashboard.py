#!/usr/bin/env python3
"""
simple_dashboard.py
Simple HTML dashboard for visualizing UAV orchestration test results.
No external dependencies required.
"""

import json
import re
from datetime import datetime

def parse_output_file(filename="output.txt"):
    """Parse the output.txt file and extract structured data"""
    with open(filename, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Split content by prompt sections
    prompt_sections = re.split(r'={60}\nPROMPT \d+\n={60}', content)[1:]  # Skip header
    
    results = []
    
    for i, section in enumerate(prompt_sections, 1):
        try:
            # Extract prompt text
            prompt_match = re.search(r'Text: (.+)', section)
            prompt_text = prompt_match.group(1) if prompt_match else f"Prompt {i}"
            
            # Extract timestamp
            timestamp_match = re.search(r'Timestamp: (.+)', section)
            timestamp = timestamp_match.group(1) if timestamp_match else "Unknown"
            
            # Extract response time
            response_time_match = re.search(r'Response Time: ([\d.]+)s', section)
            response_time = float(response_time_match.group(1)) if response_time_match else 0
            
            # Extract validation status
            valid_match = re.search(r'Valid JSON: (True|False)', section)
            is_valid = valid_match.group(1) == "True" if valid_match else False
            
            # Extract validation error if any
            validation_error = ""
            if not is_valid:
                error_match = re.search(r'Validation Error: (.+)', section)
                validation_error = error_match.group(1) if error_match else "Unknown error"
            
            # Extract parsed mission
            mission_match = re.search(r'Parsed Mission:\n({.+?})\n\nVideo Digest:', section, re.DOTALL)
            mission_data = {}
            if mission_match:
                try:
                    mission_data = json.loads(mission_match.group(1))
                except:
                    pass
            
            # Extract LLM response
            llm_response_match = re.search(r'LLM Response:\n(.+?)\n\nParsed Payload:', section, re.DOTALL)
            llm_response = llm_response_match.group(1).strip() if llm_response_match else ""
            
            # Extract parsed payload
            payload_match = re.search(r'Parsed Payload:\n({.+?})\n\n\n', section, re.DOTALL)
            payload_data = {}
            if payload_match:
                try:
                    payload_data = json.loads(payload_match.group(1))
                except:
                    pass
            
            results.append({
                'prompt_id': i,
                'prompt_text': prompt_text,
                'timestamp': timestamp,
                'response_time': response_time,
                'is_valid': is_valid,
                'validation_error': validation_error,
                'mission_intent': mission_data.get('intent', 'Unknown'),
                'mission_targets': mission_data.get('targets', []),
                'mission_constraints': mission_data.get('constraints', {}),
                'mission_success': mission_data.get('success', {}),
                'llm_response': llm_response,
                'payload_data': payload_data,
                'next_action_tool': payload_data.get('plan', {}).get('next_action', {}).get('tool', 'Unknown'),
                'next_action_why': payload_data.get('plan', {}).get('next_action', {}).get('why', ''),
                'high_level_steps': payload_data.get('plan', {}).get('high_level_steps', [])
            })
            
        except Exception as e:
            print(f"Error parsing prompt {i}: {str(e)}")
            continue
    
    return results

def generate_html_dashboard(data, output_file="dashboard.html"):
    """Generate HTML dashboard"""
    
    # Calculate metrics
    total_prompts = len(data)
    successful_prompts = sum(1 for d in data if d['is_valid'])
    failed_prompts = total_prompts - successful_prompts
    avg_response_time = sum(d['response_time'] for d in data) / total_prompts if total_prompts > 0 else 0
    
    # Count intents
    intent_counts = {}
    for d in data:
        intent = d['mission_intent']
        intent_counts[intent] = intent_counts.get(intent, 0) + 1
    
    # Count tools
    tool_counts = {}
    for d in data:
        tool = d['next_action_tool']
        tool_counts[tool] = tool_counts.get(tool, 0) + 1
    
    html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>UAV Orchestration Dashboard</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 30px;
            text-align: center;
        }}
        .metrics {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .metric-card {{
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            text-align: center;
        }}
        .metric-value {{
            font-size: 2em;
            font-weight: bold;
            color: #667eea;
        }}
        .metric-label {{
            color: #666;
            margin-top: 5px;
        }}
        .section {{
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            margin-bottom: 30px;
        }}
        .chart-container {{
            width: 100%;
            height: 400px;
        }}
        .prompt-card {{
            background: #f8f9fa;
            border-left: 4px solid #667eea;
            padding: 15px;
            margin: 10px 0;
            border-radius: 5px;
        }}
        .prompt-text {{
            font-weight: bold;
            margin-bottom: 10px;
        }}
        .prompt-details {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 10px;
            font-size: 0.9em;
            color: #666;
        }}
        .status-success {{
            color: #28a745;
        }}
        .status-error {{
            color: #dc3545;
        }}
        .collapsible {{
            background-color: #f1f1f1;
            color: #444;
            cursor: pointer;
            padding: 18px;
            width: 100%;
            border: none;
            text-align: left;
            outline: none;
            font-size: 15px;
            border-radius: 5px;
            margin: 5px 0;
        }}
        .active, .collapsible:hover {{
            background-color: #ccc;
        }}
        .content {{
            padding: 0 18px;
            display: none;
            overflow: hidden;
            background-color: #f1f1f1;
            border-radius: 5px;
        }}
        .json-content {{
            background: #2d3748;
            color: #e2e8f0;
            padding: 15px;
            border-radius: 5px;
            overflow-x: auto;
            font-family: 'Courier New', monospace;
            font-size: 0.9em;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🚁 UAV Orchestration Test Results Dashboard</h1>
        <p>Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>

    <div class="metrics">
        <div class="metric-card">
            <div class="metric-value">{total_prompts}</div>
            <div class="metric-label">Total Prompts</div>
        </div>
        <div class="metric-card">
            <div class="metric-value">{successful_prompts/total_prompts*100:.1f}%</div>
            <div class="metric-label">Success Rate</div>
        </div>
        <div class="metric-card">
            <div class="metric-value">{failed_prompts}</div>
            <div class="metric-label">Failed Prompts</div>
        </div>
        <div class="metric-card">
            <div class="metric-value">{avg_response_time:.2f}s</div>
            <div class="metric-label">Avg Response Time</div>
        </div>
    </div>

    <div class="section">
        <h2>🎯 Mission Intent Distribution</h2>
        <div class="chart-container" id="intentChart"></div>
    </div>

    <div class="section">
        <h2>🔧 Tool Usage Distribution</h2>
        <div class="chart-container" id="toolChart"></div>
    </div>

    <div class="section">
        <h2>⏱️ Response Time Analysis</h2>
        <div class="chart-container" id="responseTimeChart"></div>
    </div>

    <div class="section">
        <h2>📋 Individual Prompt Analysis</h2>
        <div id="promptDetails">
"""
    
    # Add individual prompt details
    for d in data:
        status_class = "status-success" if d['is_valid'] else "status-error"
        status_text = "✅ Valid" if d['is_valid'] else "❌ Invalid"
        
        html_content += f"""
            <div class="prompt-card">
                <div class="prompt-text">Prompt {d['prompt_id']}: {d['prompt_text']}</div>
                <div class="prompt-details">
                    <div><strong>Intent:</strong> {d['mission_intent']}</div>
                    <div><strong>Status:</strong> <span class="{status_class}">{status_text}</span></div>
                    <div><strong>Response Time:</strong> {d['response_time']:.2f}s</div>
                    <div><strong>Next Tool:</strong> {d['next_action_tool']}</div>
                </div>
                <button class="collapsible">View Details</button>
                <div class="content">
                    <h4>Mission Targets:</h4>
                    <p>{', '.join(d['mission_targets']) if d['mission_targets'] else 'None'}</p>
                    
                    <h4>High-level Steps:</h4>
                    <ul>
"""
        for step in d['high_level_steps']:
            html_content += f"<li>{step}</li>"
        
        html_content += f"""
                    </ul>
                    
                    <h4>Next Action Reasoning:</h4>
                    <p>{d['next_action_why']}</p>
                    
                    <h4>Raw LLM Response:</h4>
                    <div class="json-content">{d['llm_response']}</div>
                </div>
            </div>
"""
    
    html_content += """
        </div>
    </div>

    <script>
        // Intent distribution chart
        const intentData = """ + json.dumps(list(intent_counts.items())) + """;
        const intentChart = {
            x: intentData.map(d => d[0]),
            y: intentData.map(d => d[1]),
            type: 'bar',
            marker: {color: '#667eea'}
        };
        Plotly.newPlot('intentChart', [intentChart], {
            title: 'Intent Distribution',
            xaxis: {title: 'Intent'},
            yaxis: {title: 'Count'}
        });

        // Tool usage chart
        const toolData = """ + json.dumps(list(tool_counts.items())) + """;
        const toolChart = {
            labels: toolData.map(d => d[0]),
            values: toolData.map(d => d[1]),
            type: 'pie',
            marker: {colors: ['#667eea', '#764ba2', '#f093fb', '#f5576c']}
        };
        Plotly.newPlot('toolChart', [toolChart], {
            title: 'Tool Usage Distribution'
        });

        // Response time chart
        const responseTimes = """ + json.dumps([d['response_time'] for d in data]) + """;
        const promptIds = """ + json.dumps([d['prompt_id'] for d in data]) + """;
        const isValid = """ + json.dumps([d['is_valid'] for d in data]) + """;
        
        const responseTimeChart = {
            x: promptIds,
            y: responseTimes,
            mode: 'markers',
            type: 'scatter',
            marker: {
                color: isValid.map(v => v ? '#28a745' : '#dc3545'),
                size: 10
            }
        };
        Plotly.newPlot('responseTimeChart', [responseTimeChart], {
            title: 'Response Time by Prompt',
            xaxis: {title: 'Prompt ID'},
            yaxis: {title: 'Response Time (seconds)'}
        });

        // Collapsible functionality
        var coll = document.getElementsByClassName("collapsible");
        var i;
        for (i = 0; i < coll.length; i++) {
            coll[i].addEventListener("click", function() {
                this.classList.toggle("active");
                var content = this.nextElementSibling;
                if (content.style.display === "block") {
                    content.style.display = "none";
                } else {
                    content.style.display = "block";
                }
            });
        }
    </script>
</body>
</html>
"""
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"Dashboard generated: {output_file}")

def main():
    """Main function"""
    try:
        data = parse_output_file()
        if not data:
            print("No data found in output.txt file")
            return
        
        generate_html_dashboard(data)
        print(f"\n📊 Dashboard Summary:")
        print(f"Total Prompts: {len(data)}")
        print(f"Successful: {sum(1 for d in data if d['is_valid'])}")
        print(f"Failed: {sum(1 for d in data if not d['is_valid'])}")
        print(f"Average Response Time: {sum(d['response_time'] for d in data) / len(data):.2f}s")
        
    except FileNotFoundError:
        print("output.txt file not found. Please run the test_prompts.py script first.")
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    main()
