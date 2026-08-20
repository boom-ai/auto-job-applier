import os
import time
import json
import asyncio
import pandas as pd
import requests
from dotenv import load_dotenv
from google import genai
from playwright.async_api import async_playwright

from main import scrape_job_description, tailor_resume, generate_resume_document

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

SHEET_URL = "https://docs.google.com/spreadsheets/d/143rAI2kOfYtTjRkK4WABzlCkYKy8wsgMCfOmO0f3RYg/export?format=csv&gid=0"
STATE_FILE = "applied_jobs.json"
RESUME_FILE = "base_resume.txt"

# Fake user data for auto-apply heuristics
USER_PROFILE = {
    "first_name": "Sanket",
    "last_name": "Sharma",
    "email": "sanketsharma8083@gmail.com",
    "phone": "7973798820",
    "linkedin": "https://linkedin.com/in/sanketsharma",
    "github": "https://github.com/sanketsharma"
}

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"applied_urls": []}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=4)

async def attempt_auto_apply(url, resume_path):
    """
    Heuristic-based auto-apply using Playwright.
    Attempts to fill common fields and upload resume.
    """
    print(f"  -> Attempting auto-apply to {url}")
    success = False
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, wait_until='networkidle', timeout=30000)

            # Heuristic 1: Upload Resume
            # Look for file inputs
            file_inputs = await page.locator("input[type='file']").all()
            if file_inputs:
                print("    -> Found file upload input, uploading resume...")
                await file_inputs[0].set_input_files(resume_path)
            
            # Heuristic 2: Fill text fields based on labels/names
            # This is extremely rudimentary and will fail on complex forms like Workday
            inputs = await page.locator("input[type='text'], input[type='email'], input[type='tel']").all()
            for inp in inputs:
                name = await inp.get_attribute("name") or ""
                id_attr = await inp.get_attribute("id") or ""
                placeholder = await inp.get_attribute("placeholder") or ""
                combined = f"{name} {id_attr} {placeholder}".lower()
                
                if "email" in combined:
                    await inp.fill(USER_PROFILE["email"])
                elif "first" in combined and "name" in combined:
                    await inp.fill(USER_PROFILE["first_name"])
                elif "last" in combined and "name" in combined:
                    await inp.fill(USER_PROFILE["last_name"])
                elif "name" in combined:
                    await inp.fill(f"{USER_PROFILE['first_name']} {USER_PROFILE['last_name']}")
                elif "phone" in combined or "tel" in combined:
                    await inp.fill(USER_PROFILE["phone"])
                elif "linkedin" in combined:
                    await inp.fill(USER_PROFILE["linkedin"])
                elif "github" in combined:
                    await inp.fill(USER_PROFILE["github"])

            # We attempt to auto-click submit here to fully automate the process.
            submit_button = page.locator("button:has-text('Submit'), button:has-text('Apply')").first
            if await submit_button.count() > 0:
                print("    -> Clicking Submit/Apply button...")
                await submit_button.click()
            
            print("    -> Form filled heuristics completed.")
            success = True
            await browser.close()
    except Exception as e:
        print(f"    -> Auto-apply failed: {e}")
        
    return success

async def run_sync_cycle():
    print(f"\n--- Starting Sync Cycle at {time.strftime('%X')} ---")
    
    # 1. Fetch Latest Sheet
    print("Fetching latest Google Sheet...")
    try:
        response = requests.get(SHEET_URL)
        response.raise_for_status()
        with open("live_jobs.csv", "wb") as f:
            f.write(response.content)
        df = pd.read_csv("live_jobs.csv")
        jobs = df.to_dict('records')
    except Exception as e:
        print(f"Error fetching sheet: {e}")
        return

    # 2. Load State
    state = load_state()
    
    # 3. Read Base Resume
    try:
        with open(RESUME_FILE, "r") as f:
            base_resume_text = f.read()
    except Exception as e:
        print(f"Error reading base resume: {e}")
        return

    # 4. Process New Jobs
    new_jobs_processed = 0
    for job in jobs:
        url = job.get('Application Link', '')
        title = job.get('Job Title', 'Unknown Role')
        company = job.get('Company', 'Unknown Company')
        
        if pd.isna(url) or url == 'Not Applied' or url == 'NaN' or url in state["applied_urls"]:
            continue
            
        print(f"\n[NEW JOB FOUND] {title} @ {company}")
        
        # Scrape
        jd = await scrape_job_description(url)
        
        # Tailor
        tailored_content = tailor_resume(base_resume_text, jd, client)
        
        # Generate
        resume_path = generate_resume_document(tailored_content, company)
        
        # Auto-Apply Heuristic Routing
        if "myworkdayjobs.com" in url.lower():
            from workday import attempt_workday_apply
            success = await attempt_workday_apply(url, resume_path, USER_PROFILE)
        else:
            success = await attempt_auto_apply(url, resume_path)
            
        if success:
            print(f"Successfully processed and attempted apply for {company}.")
            
        # Record state regardless of apply success so we don't spam it
        state["applied_urls"].append(url)
        save_state(state)
        new_jobs_processed += 1
        
    print(f"--- Cycle Complete. Processed {new_jobs_processed} new jobs. ---")

async def daemon_loop():
    print("Autonomous Job Applier Daemon Started.")
    while True:
        await run_sync_cycle()
        # Sleep for 1 hour (3600 seconds)
        print("Sleeping for 1 hour...")
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(daemon_loop())
