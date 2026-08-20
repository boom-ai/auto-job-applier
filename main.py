import os
import argparse
import pandas as pd
import asyncio
from dotenv import load_dotenv
from google import genai
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

# Load environment variables
load_dotenv()
# Removed global client config so it can be instantiated per request.

def read_jobs_data(source):
    print(f"Reading jobs from {source}...")
    if source.endswith('.csv'):
        df = pd.read_csv(source)
        return df.to_dict('records')
    return []

async def scrape_job_description(url):
    print(f"Scraping job description from: {url}")
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            # Navigate to the job listing page
            await page.goto(url, wait_until='domcontentloaded', timeout=15000)
            html = await page.content()
            await browser.close()
            
            # Use BeautifulSoup to parse HTML and extract text
            soup = BeautifulSoup(html, 'html.parser')
            # Remove scripts, styles, and other non-text elements
            for script in soup(["script", "style", "nav", "footer", "header"]):
                script.extract()
            text = soup.get_text(separator=' ', strip=True)
            # Limit the size to avoid overloading the LLM context window
            return text[:10000]
    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return ""

def tailor_resume(base_resume_text, job_description, client):
    print("Tailoring resume with LLM...")
    if not job_description:
        print("No job description found, skipping tailoring.")
        return base_resume_text
        
    prompt = f"""
    You are an expert technical resume writer. Below is a base resume and a job description. 
    Rewrite the resume to specifically target the job description.
    
    Guidelines:
    - Keep the core format (Professional Summary, Core Competencies, Experience, Education, Skills, Projects).
    - Reword the Professional Summary and Core Competencies to align with the job requirements and keywords.
    - Highlight and prioritize the skills and project bullets that most directly match the job description.
    - Do not invent experience or lie, but emphasize what matches.
    - Output ONLY the raw tailored resume text, without any markdown formatting block wrappers (like ```).
    
    JOB DESCRIPTION:
    {job_description}
    
    BASE RESUME:
    {base_resume_text}
    """
    
    try:
        response = client.models.generate_content(
            model='gemini-3.6-flash',
            contents=prompt
        )
        return response.text
    except Exception as e:
        print(f"Error calling LLM: {e}")
        return base_resume_text

from fpdf import FPDF

def generate_resume_document(tailored_text, company_name):
    # Sanitize company name for filename
    company_name = "".join([c for c in str(company_name) if c.isalpha() or c.isdigit() or c==' ']).rstrip()
    filename = f"tailored_resumes/Resume_{company_name}.pdf".replace(" ", "_")
    os.makedirs("tailored_resumes", exist_ok=True)
    
    print(f"Generating resume document: {filename}")
    
    pdf = FPDF()
    pdf.add_page()
    # Add a Unicode capable font if possible, but core fonts support latin1
    # For a robust resume we should just stick to standard font and encode properly
    pdf.set_auto_page_break(auto=True, margin=15)
    
    for line in tailored_text.split('\n'):
        line = line.strip()
        if not line:
            pdf.ln(5)
            continue
            
        # Basic parsing to bold section headers
        if line.isupper() or line in ["Professional Summary", "Core Competencies", "Professional Experience", "Education", "Technical Skills", "Projects", "Certifications", "Achievements", "Languages"]:
            pdf.set_font("Helvetica", style="B", size=12)
            # Encode and decode to ignore weird characters that might crash standard fonts
            pdf.multi_cell(0, 7, line.encode('latin-1', 'replace').decode('latin-1'))
        else:
            pdf.set_font("Helvetica", size=11)
            pdf.multi_cell(0, 6, line.encode('latin-1', 'replace').decode('latin-1'))
            
    pdf.output(filename)
    return filename
async def main_async():
    parser = argparse.ArgumentParser(description="Automated Job Application Assistant")
    parser.add_argument('--jobs', required=True, help="Path to the jobs CSV")
    parser.add_argument('--resume', required=True, help="Path to your base resume txt")
    args = parser.parse_args()

    # 1. Read the base resume
    print(f"Loading base resume from {args.resume}...")
    try:
        with open(args.resume, 'r') as f:
            base_resume_text = f.read()
    except Exception as e:
        print(f"Error reading resume: {e}")
        return

    # 2. Get list of jobs
    jobs = read_jobs_data(args.jobs)

    # Initialize client for CLI mode
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    # 3. Process each job
    for idx, job in enumerate(jobs):
        if idx >= 3:
            break
            
        company = job.get('Company', f'Unknown_{idx}')
        url = job.get('Application Link', '')
        title = job.get('Job Title', '')
        
        # Skip invalid URLs
        if not url or pd.isna(url) or url == 'Not Applied' or url == 'NaN':
            continue
            
        print(f"\n--- Processing application for {title} @ {company} ---")
        
        # Scrape Description
        jd = await scrape_job_description(url)
        
        # Tailor Resume
        tailored_content = tailor_resume(base_resume_text, jd, client)
        
        # Generate Document
        resume_path = generate_resume_document(tailored_content, company)
            
    print("\nProcessing complete! Tailored resumes are in the 'tailored_resumes' folder.")

if __name__ == "__main__":
    asyncio.run(main_async())
