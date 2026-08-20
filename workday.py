import asyncio
from playwright.async_api import async_playwright

async def attempt_workday_apply(url, resume_path, profile):
    print(f"  -> [WORKDAY] Attempting Workday auto-apply to {url}")
    success = False
    
    # Standardized password for Workday accounts
    WD_PASSWORD = "AutoApply123!"
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()
            
            # 1. Navigate to Job
            await page.goto(url, wait_until='networkidle', timeout=30000)
            
            # 2. Click Apply
            apply_btn = page.locator("button:has-text('Apply'), a:has-text('Apply')").first
            if await apply_btn.count() > 0:
                print("    -> [WORKDAY] Found Apply button, clicking...")
                await apply_btn.click()
                await page.wait_for_timeout(2000)
                
                # Check for "Apply Manually" or "Autofill with Resume" options
                manual_btn = page.locator("a:has-text('Apply Manually'), button:has-text('Apply Manually')").first
                if await manual_btn.count() > 0:
                    await manual_btn.click()
                    await page.wait_for_timeout(2000)
            else:
                print("    -> [WORKDAY] Could not find initial Apply button.")
                await browser.close()
                return False

            # 3. Click Create Account
            create_acc_btn = page.locator("button:has-text('Create Account'), a:has-text('Create Account')").first
            if await create_acc_btn.count() > 0:
                print("    -> [WORKDAY] Found Create Account, clicking...")
                await create_acc_btn.click()
                await page.wait_for_timeout(2000)
            else:
                print("    -> [WORKDAY] Could not find Create Account button.")
                # We might already be on the create account page or login page
            
            # 4. Fill Create Account Form
            # Workday uses labels, we can try to find inputs near those labels
            email_input = page.locator("input[type='text'], input[type='email']").first
            pass_inputs = page.locator("input[type='password']").all()
            
            if await email_input.count() > 0:
                print("    -> [WORKDAY] Filling account details...")
                await email_input.fill(profile["email"])
                
                passes = await pass_inputs
                if len(passes) >= 2:
                    await passes[0].fill(WD_PASSWORD)
                    await passes[1].fill(WD_PASSWORD)
                
                # Checkbox for Terms
                checkbox = page.locator("input[type='checkbox']").first
                if await checkbox.count() > 0:
                    # Sometimes workday checkboxes are custom divs, we use force
                    await checkbox.check(force=True)
                
                # Click Create Account submit
                submit_create = page.locator("button:has-text('Create Account')").first
                if await submit_create.count() > 0:
                    await submit_create.click()
                    await page.wait_for_timeout(5000)
            
            # 5. Check for Email Verification wall
            verify_text = page.locator("text='verification code', text='Verify your email'").first
            if await verify_text.count() > 0:
                print("    -> [WORKDAY] Hit Email Verification wall! Cannot proceed autonomously.")
                await browser.close()
                return False
                
            # 6. Upload Resume
            print("    -> [WORKDAY] Checking for resume upload...")
            file_inputs = await page.locator("input[type='file']").all()
            if file_inputs:
                await file_inputs[0].set_input_files(resume_path)
                await page.wait_for_timeout(3000) # wait for upload
                
            # 7. Step through pages (My Information, My Experience, etc)
            # Workday usually has a "Save and Continue" button on every page
            for i in range(5): # try up to 5 pages
                print(f"    -> [WORKDAY] Processing application page {i+1}...")
                
                # Attempt to fill basic text fields heuristically
                inputs = await page.locator("input[type='text'], input[type='email'], input[type='tel']").all()
                for inp in inputs:
                    name = await inp.get_attribute("name") or ""
                    id_attr = await inp.get_attribute("id") or ""
                    placeholder = await inp.get_attribute("placeholder") or ""
                    combined = f"{name} {id_attr} {placeholder}".lower()
                    
                    try:
                        if "email" in combined and await inp.is_editable():
                            await inp.fill(profile["email"])
                        elif "first" in combined and "name" in combined and await inp.is_editable():
                            await inp.fill(profile["first_name"])
                        elif "last" in combined and "name" in combined and await inp.is_editable():
                            await inp.fill(profile["last_name"])
                        elif "phone" in combined or "tel" in combined and await inp.is_editable():
                            await inp.fill(profile["phone"])
                    except:
                        pass
                
                # We attempt to auto-click Save and Continue
                next_btn = page.locator("button:has-text('Save and Continue'), button:has-text('Next')").first
                if await next_btn.count() > 0:
                    await next_btn.click()
                    await page.wait_for_timeout(4000)
                else:
                    # Maybe we hit Submit?
                    submit_btn = page.locator("button:has-text('Submit')").first
                    if await submit_btn.count() > 0:
                        print("    -> [WORKDAY] Reached final Submit page! (Submit bypassed for safety)")
                        # await submit_btn.click()
                        success = True
                        break
                    else:
                        print("    -> [WORKDAY] Could not find Next or Submit button, stuck on page.")
                        break
            
            await browser.close()
    except Exception as e:
        print(f"    -> [WORKDAY] Fatal error during Workday apply: {e}")
        
    return success
