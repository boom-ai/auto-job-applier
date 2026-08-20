import streamlit as st
import pandas as pd
import asyncio
import os
from google import genai

# Import functions from main.py
from main import read_jobs_data, scrape_job_description, tailor_resume, generate_resume_document

st.set_page_config(page_title="Auto Job Applier", layout="wide")

st.title("🚀 Auto Job Applier")
st.markdown("Automate your resume tailoring process with Playwright and Gemini!")

with st.sidebar:
    st.header("Settings")
    api_key = st.text_input("Gemini API Key", type="password")
    
    st.markdown("### Upload Files")
    resume_file = st.file_uploader("Upload Base Resume (.txt)", type=["txt"])
    jobs_file = st.file_uploader("Upload Jobs List (.csv)", type=["csv"])

st.subheader("Process Applications")
run_limit = st.number_input("How many jobs to process? (0 for all)", min_value=0, value=3)

if st.button("Start Tailoring"):
    if not api_key:
        st.error("Please enter your Gemini API Key in the sidebar.")
    elif not resume_file:
        st.error("Please upload your base resume (.txt).")
    elif not jobs_file:
        st.error("Please upload your jobs list (.csv).")
    else:
        # 1. Initialize Gemini Client
        try:
            client = genai.Client(api_key=api_key)
        except Exception as e:
            st.error(f"Failed to initialize Gemini Client: {e}")
            st.stop()
            
        # 2. Read Base Resume
        base_resume_text = resume_file.read().decode("utf-8")
        
        # 3. Save CSV temporarily so pandas can read it (or read directly)
        jobs_df = pd.read_csv(jobs_file)
        jobs = jobs_df.to_dict('records')
        
        total_jobs = len(jobs)
        if run_limit > 0:
            total_jobs = min(total_jobs, run_limit)
            
        st.write(f"Found {len(jobs)} jobs. Processing {total_jobs}...")
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        generated_files = []
        
        # 4. Process Loop
        for idx, job in enumerate(jobs):
            if run_limit > 0 and idx >= run_limit:
                break
                
            company = job.get('Company', f'Unknown_{idx}')
            url = job.get('Application Link', '')
            title = job.get('Job Title', '')
            
            if pd.isna(url) or url == 'Not Applied' or url == 'NaN':
                st.warning(f"Skipping {title} at {company} (No valid URL)")
                progress_bar.progress((idx + 1) / total_jobs)
                continue
                
            status_text.write(f"**Processing:** {title} @ {company}")
            
            # Scrape
            with st.spinner(f"Scraping job description from {company}..."):
                # Run async playwright code in sync Streamlit context
                try:
                    jd = asyncio.run(scrape_job_description(url))
                except RuntimeError as e:
                    # Handle event loop already running issues if any
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    jd = loop.run_until_complete(scrape_job_description(url))
            
            # Tailor
            with st.spinner(f"Tailoring resume with Gemini..."):
                tailored_content = tailor_resume(base_resume_text, jd, client)
            
            # Generate Document
            with st.spinner("Generating .docx file..."):
                resume_path = generate_resume_document(tailored_content, company)
                generated_files.append((company, title, resume_path))
                
            progress_bar.progress((idx + 1) / total_jobs)
            st.success(f"✅ Completed: {title} @ {company}")
            
        status_text.write("🎉 **All processing complete!**")
        
        st.subheader("Download Tailored Resumes")
        for company, title, path in generated_files:
            with open(path, "rb") as file:
                btn = st.download_button(
                    label=f"Download Resume for {company}",
                    data=file,
                    file_name=os.path.basename(path),
                    mime="application/pdf"
                )
