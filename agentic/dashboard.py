#!/usr/bin/env python3
"""
dashboard.py
Interactive dashboard for visualizing UAV orchestration test results.
"""

import json
import re
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
from datetime import datetime
import ast

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
            st.error(f"Error parsing prompt {i}: {str(e)}")
            continue
    
    return results

def create_summary_metrics(df):
    """Create summary metrics for the dashboard"""
    total_prompts = len(df)
    successful_prompts = len(df[df['is_valid'] == True])
    failed_prompts = len(df[df['is_valid'] == False])
    avg_response_time = df['response_time'].mean()
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Prompts", total_prompts)
    
    with col2:
        st.metric("Success Rate", f"{successful_prompts/total_prompts*100:.1f}%")
    
    with col3:
        st.metric("Failed Prompts", failed_prompts)
    
    with col4:
        st.metric("Avg Response Time", f"{avg_response_time:.2f}s")

def create_intent_analysis(df):
    """Create intent analysis visualizations"""
    st.subheader("🎯 Mission Intent Analysis")
    
    # Intent distribution
    intent_counts = df['mission_intent'].value_counts()
    
    col1, col2 = st.columns(2)
    
    with col1:
        fig = px.pie(values=intent_counts.values, names=intent_counts.index, 
                    title="Intent Distribution")
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        fig = px.bar(x=intent_counts.index, y=intent_counts.values,
                    title="Intent Counts", labels={'x': 'Intent', 'y': 'Count'})
        st.plotly_chart(fig, use_container_width=True)

def create_response_time_analysis(df):
    """Create response time analysis"""
    st.subheader("⏱️ Response Time Analysis")
    
    col1, col2 = st.columns(2)
    
    with col1:
        fig = px.histogram(df, x='response_time', nbins=10, 
                          title="Response Time Distribution")
        fig.update_xaxis(title="Response Time (seconds)")
        fig.update_yaxis(title="Count")
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        fig = px.scatter(df, x='prompt_id', y='response_time', 
                        color='is_valid', title="Response Time by Prompt",
                        labels={'prompt_id': 'Prompt ID', 'response_time': 'Response Time (s)'})
        st.plotly_chart(fig, use_container_width=True)

def create_tool_analysis(df):
    """Create tool usage analysis"""
    st.subheader("🔧 Tool Usage Analysis")
    
    tool_counts = df['next_action_tool'].value_counts()
    
    fig = px.bar(x=tool_counts.index, y=tool_counts.values,
                title="Next Action Tools Distribution",
                labels={'x': 'Tool', 'y': 'Count'})
    st.plotly_chart(fig, use_container_width=True)

def create_detailed_prompt_view(df):
    """Create detailed view of individual prompts"""
    st.subheader("📋 Detailed Prompt Analysis")
    
    selected_prompt = st.selectbox(
        "Select a prompt to analyze:",
        options=df.index,
        format_func=lambda x: f"Prompt {df.loc[x, 'prompt_id']}: {df.loc[x, 'prompt_text'][:50]}..."
    )
    
    if selected_prompt is not None:
        prompt_data = df.loc[selected_prompt]
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**Prompt Details:**")
            st.write(f"**Text:** {prompt_data['prompt_text']}")
            st.write(f"**Intent:** {prompt_data['mission_intent']}")
            st.write(f"**Targets:** {', '.join(prompt_data['mission_targets'])}")
            st.write(f"**Response Time:** {prompt_data['response_time']:.2f}s")
            st.write(f"**Valid JSON:** {'✅' if prompt_data['is_valid'] else '❌'}")
            
            if not prompt_data['is_valid']:
                st.write(f"**Validation Error:** {prompt_data['validation_error']}")
        
        with col2:
            st.write("**Mission Plan:**")
            if prompt_data['high_level_steps']:
                st.write("**High-level Steps:**")
                for i, step in enumerate(prompt_data['high_level_steps'], 1):
                    st.write(f"{i}. {step}")
            
            st.write(f"**Next Action Tool:** {prompt_data['next_action_tool']}")
            if prompt_data['next_action_why']:
                st.write(f"**Reasoning:** {prompt_data['next_action_why']}")
        
        # Show raw LLM response
        with st.expander("View Raw LLM Response"):
            st.code(prompt_data['llm_response'], language='json')

def create_object_detection_analysis(df):
    """Create object detection analysis from video digest"""
    st.subheader("👁️ Object Detection Analysis")
    
    # Extract all detected objects from the data
    all_objects = []
    for idx, row in df.iterrows():
        # This would need to be extracted from the video digest data
        # For now, we'll create a placeholder
        pass
    
    st.info("Object detection analysis would require parsing video digest data from the output file.")

def main():
    """Main dashboard function"""
    st.set_page_config(
        page_title="UAV Orchestration Dashboard",
        page_icon="🚁",
        layout="wide"
    )
    
    st.title("🚁 UAV Orchestration Test Results Dashboard")
    st.markdown("---")
    
    # Load and parse data
    try:
        data = parse_output_file()
        df = pd.DataFrame(data)
        
        if df.empty:
            st.error("No data found in output.txt file")
            return
        
        # Summary metrics
        create_summary_metrics(df)
        st.markdown("---")
        
        # Main analysis sections
        create_intent_analysis(df)
        st.markdown("---")
        
        create_response_time_analysis(df)
        st.markdown("---")
        
        create_tool_analysis(df)
        st.markdown("---")
        
        create_detailed_prompt_view(df)
        st.markdown("---")
        
        # Raw data table
        st.subheader("📊 Raw Data Table")
        st.dataframe(df[['prompt_id', 'prompt_text', 'mission_intent', 'response_time', 'is_valid', 'next_action_tool']])
        
        # Download button
        csv = df.to_csv(index=False)
        st.download_button(
            label="Download CSV",
            data=csv,
            file_name="uav_test_results.csv",
            mime="text/csv"
        )
        
    except FileNotFoundError:
        st.error("output.txt file not found. Please run the test_prompts.py script first.")
    except Exception as e:
        st.error(f"Error loading data: {str(e)}")

if __name__ == "__main__":
    main()
