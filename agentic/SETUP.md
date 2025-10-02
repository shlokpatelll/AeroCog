# UAV Orchestration Setup Guide

## Environment Setup

1. **Install Dependencies**

   ```bash
   pip install -r requirements.txt
   ```

2. **Set up Environment Variables**

   - Copy your OpenAI API key to the `.env` file:

   ```bash
   echo "OPENAI_API_KEY=your_api_key_here" > .env
   ```

   - Or manually create/edit the `.env` file with:

   ```
   OPENAI_API_KEY=sk-proj-your-actual-api-key-here
   ```

3. **Run Tests**

   ```bash
   python test_prompts.py
   ```

4. **Generate Dashboard**
   ```bash
   python simple_dashboard.py
   ```
   This will create `dashboard.html` that you can open in your browser.

## Security Notes

- The `.env` file is already added to `.gitignore` to prevent accidental commits
- Never commit your actual API keys to version control
- The `.env.example` file shows the expected format

## Files Structure

- `agentic/orchestrator_demo.py` - Main orchestration logic
- `test_prompts.py` - Test suite with 10 example prompts
- `simple_dashboard.py` - HTML dashboard generator
- `dashboard.py` - Streamlit dashboard (requires additional setup)
- `output.txt` - Test results (generated after running tests)
- `dashboard.html` - Visual dashboard (generated after running simple_dashboard.py)
