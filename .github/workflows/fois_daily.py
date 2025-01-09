# %%
# !pip install selenium pillow pytesseract webdriver-manager pandas tqdm telegram python-dotenv


# %%
from datetime import datetime

# Get the current date and time
current_datetime = datetime.now()

# Format the date and time
formatted_datetime = current_datetime.strftime("%Y-%m-%d %H:%M:%S")

print("Current date and time:", formatted_datetime)


# %% [markdown]
# # improved

# %%
from datetime import datetime, timedelta

past_24_hours_date = (datetime.now() - timedelta(days=1)).strftime("%d-%m-%y %H:%M:%S")
print(f"Date for past 24 hours: {past_24_hours_date}")

# %%
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from PIL import Image, ImageEnhance, ImageFilter
import pytesseract
from io import BytesIO
from webdriver_manager.chrome import ChromeDriverManager
import time
import re
import pandas as pd
from tqdm import tqdm
import concurrent.futures
from datetime import datetime, timedelta
import os
import shutil
# Function to solve CAPTCHA with retry logic
def solve_captcha(driver, image_xpath):
    while True:
        try:
            captcha_element = driver.find_element(By.XPATH, image_xpath)
            captcha_image = captcha_element.screenshot_as_png
            captcha_image = Image.open(BytesIO(captcha_image))
            captcha_image = captcha_image.convert("L")
            captcha_image = captcha_image.filter(ImageFilter.MedianFilter(size=3))
            enhancer = ImageEnhance.Contrast(captcha_image)
            captcha_image = enhancer.enhance(2)
            captcha_text = pytesseract.image_to_string(captcha_image, config='--psm 6')
            cleaned_text = re.sub(r'[^A-Za-z0-9]', '', captcha_text)
            captcha_field = driver.find_element(By.XPATH, "//*[@id='captchaText']")
            captcha_field.clear()
            captcha_field.send_keys(cleaned_text)
            submit_button = driver.find_element(By.XPATH, "//*[@id='collapse1']/div[5]/button")
            submit_button.click()
            time.sleep(2)
            if not is_captcha_incorrect(driver, "//*[@id='errmsg']"):
                print("Captcha accepted, proceeding...")
                return True
        except NoSuchElementException:
            print("CAPTCHA element not found. Retrying...")
        except Exception as e:
            print(f"Error while solving CAPTCHA: {e}")
            time.sleep(1)

def is_captcha_incorrect(driver, error_xpath):
    try:
        error_message = driver.find_element(By.XPATH, error_xpath).text
        if "Captcha Code doesn't Match" in error_message:
            print("Detected Captcha error: Code doesn't match. Retrying...")
            return True
    except NoSuchElementException:
        pass
    return False

def process_region(region_code):
    # Cleanup existing drivers
    driver_cache_path = '/home/runner/.wdm/drivers/chromedriver'
    if os.path.exists(driver_cache_path):
        shutil.rmtree(driver_cache_path)

    options = Options()
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--start-maximized")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    all_region_data = []
    try:
        url = "https://www.fois.indianrail.gov.in/FOISWebPortal/pages/FWP_ODROtsgDtls.jsp"
        driver.get(url)
        print(f"\nPage Loaded for region: {region_code}")
        wait = WebDriverWait(driver, 120)

        outstanding_odr_option = wait.until(EC.presence_of_element_located((By.ID, "Zone")))
        outstanding_odr_option.click()
        outstanding_odr_option.send_keys(region_code)
        print(f"Selected '{region_code}' from the dropdown.")
        
        captcha_image_xpath = "/html/body/div[4]/center/form/div/div[2]/div[4]/img[1]"
        if not solve_captcha(driver, captcha_image_xpath):
            raise Exception(f"Unable to solve Captcha for region {region_code} after multiple attempts.")

        print("Waiting for iframe to load...")
        data_div = wait.until(EC.presence_of_element_located((By.XPATH, "//*[@id='dataDiv']")))
        iframe = data_div.find_element(By.TAG_NAME, "iframe")
        driver.switch_to.frame(iframe)

        print("Waiting for the table to load...")
        table_element = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "body > div > table")))
        tbody_element = table_element.find_element(By.TAG_NAME, "tbody")
        rows = tbody_element.find_elements(By.TAG_NAME, "tr")

        region_data_list = []
        
        # Get current date and time for filtering
        current_time = datetime.now()  

        # current_time = datetime.strptime("08-01-2025 16:00", "%d-%m-%Y %H:%M")  # Current date and time for testing.
        past_24_hours = current_time - timedelta(hours=24)

        # Get today's and yesterday's date in DD-MM-YY format.
        today_date_str = current_time.strftime("%d-%m-%y")
        yesterday_date_str = (current_time - timedelta(days=1)).strftime("%d-%m-%y")

        for row in rows:
            columns = [col.text for col in row.find_elements(By.TAG_NAME, "td")]
            
            # Check if there are enough columns and filter based on conditions.
            if len(columns) >= 10 and columns[9] in ["FG", "DOC"]:
                demand_date_str = columns[4]  # Assuming this is in DD-MM-YY format.
                demand_time_str = columns[5]

                # Convert DEMAND DATE and DEMAND TIME into a single datetime object.
                demand_datetime_str = f"{demand_date_str} {demand_time_str}"
                demand_datetime_obj = datetime.strptime(demand_datetime_str, "%d-%m-%y %H:%M")

                # Check if DEMAND DATE is today or yesterday and within the last 24 hours.
                if (demand_date_str == today_date_str or demand_date_str == yesterday_date_str) and past_24_hours <= demand_datetime_obj <= current_time:
                    print(columns)  # Print each valid row's data for debugging purposes.
                    region_data_list.append(columns)

            elif len(columns) < 23:
                print(f"Skipping row with insufficient columns: {columns}")
            elif not any(columns):
                print("Skipping empty row.")
        
        if not region_data_list:
            print(f"No valid data found for region {region_code}. Skipping this region.")
            return None
        
        column_names = [
            "S.No.", "DVSN", "STTN FROM", "DEMAND NO.", "DEMAND DATE", 
            "DEMAND TIME", "Expected loading date", "CNSR", 
            "CNSG", "CMDT", "TT", "PC", 
            "PBF", "VIA", "RAKE CMDT", 
            "DSTN", "INDENTED TYPE", 
            "INDENTED UNTS", "INDENTED 8W", 
            "OTSG UNTS", "OTSG 8W", 
            "SUPPLIED UNTS", "SUPPLIED TIME"
        ]
        
        df_region = pd.DataFrame(region_data_list, columns=column_names)
        df_region['Region'] = region_code
        
        return df_region
    
    except Exception as e:
        print(f"An error occurred while processing region {region_code}: {e}")
        return None
    
    finally:
        driver.quit()

# List of region codes to process
region_codes = [
    "CR", "DFCR", "EC", "ECO", "ER", 
    "KR", "NC", "NE", "NF", "NPLR", 
    "NR", "NW", "SC", "SE", "SEC", 
    "SR", "SW", "WC", "WR"
]

# Combine all region DataFrames into a single DataFrame using parallel processing
all_regions_data = []
with concurrent.futures.ThreadPoolExecutor() as executor:
    results = list(tqdm(executor.map(process_region, region_codes), total=len(region_codes), desc="Processing Regions"))

# Filter out None results and concatenate DataFrames into a single DataFrame and save it.
results = [df for df in results if df is not None]
if results:
    final_df = pd.concat(results, ignore_index=True)
    print(final_df.head())  # Display first few rows of the final DataFrame.
    
    final_df.to_csv('output_combined_regions_daily.csv', index=False)  # Save combined output
    
    # Count and print the number of rows after filtering
    filtered_rows_count = len(final_df)
    print(f"Total rows with FG or DOC from today and yesterday: {filtered_rows_count}")
else:
    print("No data collected from any regions.")

final_df_without_FCI = final_df[final_df['CNSR'] != "FCI"]
final_df_without_FCI.to_csv('final_df_without_FCI.csv', index=False)
print("final_df_without_FCI saved")

# Read dropdown options data
options_df = pd.read_csv('dropdown_options.csv')
print("options_df opened successfully")

# Extract short forms and full forms
options_df['Short_Form'] = options_df['Current_Stations'].str.extract(r'\((.*?)\)')
options_df['Full_Form'] = options_df['Current_Stations'].str.replace(r'\(.*?\)', '', regex=True).str.strip()

# Create mapping dictionary short form to full form
short_form_dict_stn = dict(zip(options_df['Short_Form'], options_df['Full_Form']))
final_df_without_FCI['STTN FROM'] = final_df_without_FCI['STTN FROM'].map(short_form_dict_stn).fillna(final_df_without_FCI['STTN FROM'])
final_df_without_FCI['DSTN'] = final_df_without_FCI['DSTN'].map(short_form_dict_stn).fillna(final_df_without_FCI['DSTN'])

# Consignee mappings
consignee_consiner_df = pd.read_csv('consignee_consiner_data.csv')
print("consignee_consiner_df opened successfully")
consignee_consiner_df['Short_Form'] = consignee_consiner_df['Consignee Name'].str.extract(r'\((.*?)\)')
consignee_consiner_df['Full_Form'] = consignee_consiner_df['Consignee Name'].str.replace(r'\(.*?\)', '', regex=True).str.strip()
short_form_dict = dict(zip(consignee_consiner_df['Short_Form'], consignee_consiner_df['Full_Form']))
final_df_without_FCI['CNSR_Full'] = final_df_without_FCI['CNSR'].map(short_form_dict)
final_df_without_FCI['CNSG_Full'] = final_df_without_FCI['CNSG'].map(short_form_dict)

# Mapping DVSN
dvsn_mapping = {
    'BB': 'Bandra Division',
    'BSL': 'Bhopal Division',
    'NGP': 'Nagpur Division',
    'PUNE': 'Pune Division',
    'SUR': 'Surat Division',
    'WDFC': 'Western Dedicated Freight Corridor',
    'DDU': 'Deen Dayal Upadhyaya Junction',
    'DHN': 'Dhanbad Division',
    'DNR': 'Danapur Division',
    'SEE': 'Sealdah Division',
    'SPJ': 'Samastipur Division',
    'KUR': 'Khurda Road Division',
    'SBP': 'Sambalpur Division',
    'WAT': 'Wadi Division',
    'ASN': 'Asansol Division',
    'HWH': 'Howrah Division',
    'MLDT': 'Malda Town Division',
    'KAWR': 'Kalyan Division',
    'RN':  'Rourkela Division',
    'AGRA':  "Agra Division",
    'JHS':  "Jhansi Division",
    'PRYJ':  "Prayagraj Junction",
    'BSB':  "Varanasi Division",
    'IZN':  "Izatnagar Division",
    'LJN':  "Lucknow Junction",
    'APDJ':  "Amritsar Division",
    'KIR':  "Kharagpur Division",
    'LMG':  "Ludhiana Division",
    'RNY':  "Rani Kamlapati Division",
    'TSK':  "Tinsukia Division",
    'DLI':  "Delhi Division",
    'FZR':  "Ferozepur Division",
    'LKO':  "Lucknow Division",
    'MB':   "Moradabad Division",
    'UMB':  "Ambala Division",
    'AII':  "Ajmer Division",
    'BKN':  "Bikaner Division",
    'JP':   "Jaipur Division",
    'JU':   "Jodhpur Division",
    'BZA':  "Vijayawada Division",
    'GNT':  "Guntur Division",
    'GTL':  "Guntakal Junction",
    'HYB':  "Hyderabad Division",
    'NED':  "Nanded Division",
    "ADRA": "Adra Junction",
    "CKP": "Chhapra Kacheri",
    "KGP": "Kharagpur",
    "RNC": "Ranchi",
    "BSP": "Bilaspur",
    "NAG": "Nagaur",
    "R": "Rourkela",
    "MAS": "Chennai Egmore (Madras)",
    "MDU": "Madurai",
    "SA": "Salem",
    "TPJ": "Tiruchirappalli Junction",
    "TVC": "Thiruvananthapuram Central",
    "MYS": "Mysuru",
    "SBC": "Krantivira Sangolli Rayanna (Bangalore City)",
    "UBL": "Hubli",
    "BPL": "Bhopal",
    "JBP": "Jabalpur",
    "KOTA": "Kota",
    "ADI": "Ahmedabad",
    "BCT": "Bhavnagar Terminus",
    "BRC": "Vadodara Junction (Baroda)",
    "BVC": "Bhopal (BVC)",
    "RJT": "Rajkot Junction",
    "RTM": "Ratlam Junction"
}
final_df_without_FCI['DVSN'] = final_df_without_FCI['DVSN'].replace(dvsn_mapping)

final_df_without_FCI.to_csv('final_df_without_FCI.csv', index=False)
print("Final file has been generated.")


# %%
# from selenium import webdriver
# from selenium.webdriver.common.by import By
# from selenium.webdriver.chrome.service import Service
# from selenium.webdriver.chrome.options import Options
# from selenium.webdriver.support.ui import WebDriverWait
# from selenium.webdriver.support import expected_conditions as EC
# from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
# from PIL import Image, ImageEnhance, ImageFilter
# import pytesseract
# from io import BytesIO
# from webdriver_manager.chrome import ChromeDriverManager
# import time
# import re
# import pandas as pd  # Import pandas
# from tqdm import tqdm  # Import tqdm for progress bars
# import concurrent.futures
# from datetime import datetime, timedelta

# # Function to solve CAPTCHA with retry logic
# def solve_captcha(driver, image_xpath):
#     while True:  # Keep trying to solve CAPTCHA indefinitely until successful.
#         try:
#             captcha_element = driver.find_element(By.XPATH, image_xpath)
#             captcha_image = captcha_element.screenshot_as_png
#             captcha_image = Image.open(BytesIO(captcha_image))

#             # Preprocess the image to improve OCR accuracy
#             captcha_image = captcha_image.convert("L")  # Convert to grayscale
#             captcha_image = captcha_image.filter(ImageFilter.MedianFilter(size=3))  # Reduce noise
#             enhancer = ImageEnhance.Contrast(captcha_image)
#             captcha_image = enhancer.enhance(2)  # Increase contrast
            
#             # Use Tesseract to extract text
#             captcha_text = pytesseract.image_to_string(captcha_image, config='--psm 6')
#             cleaned_text = re.sub(r'[^A-Za-z0-9]', '', captcha_text)  # Remove special characters
            
#             # Enter Captcha text into the input field
#             captcha_field = driver.find_element(By.XPATH, "//*[@id='captchaText']")
#             captcha_field.clear()
#             captcha_field.send_keys(cleaned_text)
            
#             # Submit the form and check for success or failure.
#             submit_button = driver.find_element(By.XPATH, "//*[@id='collapse1']/div[5]/button")
#             submit_button.click()
            
#             time.sleep(2)  # Allow time for form to process
            
#             if not is_captcha_incorrect(driver, "//*[@id='errmsg']"):
#                 print("Captcha accepted, proceeding...")
#                 return True  # Captcha solved successfully

#         except NoSuchElementException:
#             print("CAPTCHA element not found. Retrying...")
#         except Exception as e:
#             print(f"Error while solving CAPTCHA: {e}")
        
#         time.sleep(1)  # Small delay before retrying

# def is_captcha_incorrect(driver, error_xpath):
#     try:
#         error_message = driver.find_element(By.XPATH, error_xpath).text
#         if "Captcha Code doesn't Match" in error_message:
#             print("Detected Captcha error: Code doesn't match. Retrying...")
#             return True
#     except NoSuchElementException:
#         pass
#     return False

# # Function to process each region code with improved handling for stale elements and timeouts.
# def process_region(region_code):
#     options = Options()
#     # options.add_argument("--headless")  # Run Chrome in headless mode
#     options.add_argument("--disable-gpu")
#     options.add_argument("--no-sandbox")
#     options.add_argument("--disable-dev-shm-usage")
#     options.add_argument("--start-maximized")

#     service = Service(ChromeDriverManager().install())
#     driver = webdriver.Chrome(service=service, options=options)

#     all_region_data = []

#     try:
#         url = "https://www.fois.indianrail.gov.in/FOISWebPortal/pages/FWP_ODROtsgDtls.jsp"
        
#         driver.get(url)
#         print(f"\nPage Loaded for region: {region_code}")

#         wait = WebDriverWait(driver, 120)  # Wait indefinitely for elements to load
        
#         outstanding_odr_option = wait.until(EC.presence_of_element_located((By.ID, "Zone")))
#         outstanding_odr_option.click()
#         outstanding_odr_option.send_keys(region_code)
#         print(f"Selected '{region_code}' from the dropdown.")

#         captcha_image_xpath = "/html/body/div[4]/center/form/div/div[2]/div[4]/img[1]"
        
#         if not solve_captcha(driver, captcha_image_xpath):
#             raise Exception(f"Unable to solve Captcha for region {region_code} after multiple attempts.")

#         print("Waiting for iframe to load...")
        
#         data_div = wait.until(EC.presence_of_element_located((By.XPATH, "//*[@id='dataDiv']")))
        
#         iframe = data_div.find_element(By.TAG_NAME, "iframe")
#         driver.switch_to.frame(iframe)
        
#         print("Waiting for the table to load...")
        
#         table_element = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "body > div > table")))
        
#         tbody_element = table_element.find_element(By.TAG_NAME, "tbody")
        
#         rows = tbody_element.find_elements(By.TAG_NAME, "tr")

#         region_data_list = []

#         date = time.strftime("%d-%m-%y")  # Get today's date in DD-MM-YY format

#         for row in rows:
#             columns = [col.text for col in row.find_elements(By.TAG_NAME, "td")]
            
#             # Filter rows: Column 10 must be 'FG' or 'DOC' and Column 5 must be today's date
#             if len(columns) >= 10 and columns[9] in ["FG", "DOC"] and columns[4] == date:
#                 print(columns)  # Print each row's data for debugging purposes.
#                 region_data_list.append(columns)

#             elif len(columns) < 23:
#                 print(f"Skipping row with insufficient columns: {columns}")

#             elif not any(columns):
#                 print("Skipping empty row.")

#         if not region_data_list:
#             print(f"No valid data found for region {region_code}. Skipping this region.")
#             return None

#         column_names = [
#             "S.No.", "DVSN", "STTN FROM", "DEMAND NO.", 
#             "DEMAND DATE", "DEMAND TIME", "Expected loading date", 
#             "CNSR", "CNSG", "CMDT", 
#             "TT", "PC", "PBF", 
#             "VIA", "RAKE CMDT", "DSTN", 
#             "INDENTED TYPE", "INDENTED UNTS", 
#             "INDENTED 8W", "OTSG UNTS", 
#             "OTSG 8W", "SUPPLIED UNTS", 
#             "SUPPLIED TIME"
#         ]

#         df_region = pd.DataFrame(region_data_list, columns=column_names)
#         df_region['Region'] = region_code  

#         return df_region

#     except Exception as e:
#         print(f"An error occurred while processing region {region_code}: {e}")
#         return None

#     finally:
#         driver.quit()

# # List of region codes to process
# # region_codes = ["SW"]
# region_codes = [
#     "CR", "DFCR", "EC", "ECO", "ER", 
#     "KR", "NC", "NE", "NF", "NPLR", 
#     "NR", "NW", "SC", "SE", "SEC", 
#     "SR", "SW", "WC", "WR"
# ]

# # Combine all region DataFrames into a single DataFrame using parallel processing
# all_regions_data = []

# with concurrent.futures.ThreadPoolExecutor() as executor:
#     results = list(tqdm(executor.map(process_region, region_codes), total=len(region_codes), desc="Processing Regions"))

# # Filter out None results and concatenate DataFrames into a single DataFrame and save it.
# results = [df for df in results if df is not None]

# if results:
#     final_df = pd.concat(results, ignore_index=True)
    
#     print(final_df.head())  # Display first few rows of the final DataFrame.
    
#     final_df.to_csv('output_combined_regions_daily.csv', index=False)

#     # Count and print the number of rows after filtering
#     filtered_rows_count = len(final_df)
#     print(f"Total rows with FG or DOC and today's date: {filtered_rows_count}")
# else:
#     print("No data collected from any regions.")

# final_df_without_FCI = final_df[final_df['CNSR'] != "FCI"]
# final_df_without_FCI.to_csv('final_df_without_FCI.csv', index=False)

# print("final_df_without_FCI saved")

# # Read dropdown options data
# options_df = pd.read_csv('dropdown_options.csv')
# print("options_df opened successfully")

# # Extract short forms and full forms
# options_df['Short_Form'] = options_df['Current_Stations'].str.extract(r'\((.*?)\)')
# options_df['Full_Form'] = options_df['Current_Stations'].str.replace(r'\(.*?\)', '', regex=True).str.strip()

# # Create mapping dictionary
# short_form_dict_stn = dict(zip(options_df['Short_Form'], options_df['Full_Form']))

# # Replace short forms in 'STTN FROM' and 'DSTN'
# final_df_without_FCI['STTN FROM'] = final_df_without_FCI['STTN FROM'].map(short_form_dict_stn).fillna(final_df_without_FCI['STTN FROM'])
# final_df_without_FCI['DSTN'] = final_df_without_FCI['DSTN'].map(short_form_dict_stn).fillna(final_df_without_FCI['DSTN'])

# # Consignee mappings
# consignee_consiner_df = pd.read_csv('consignee_consiner_data.csv')
# print("consignee_consiner_df opened successfully")

# consignee_consiner_df['Short_Form'] = consignee_consiner_df['Consignee Name'].str.extract(r'\((.*?)\)')
# consignee_consiner_df['Full_Form'] = consignee_consiner_df['Consignee Name'].str.replace(r'\(.*?\)', '', regex=True).str.strip()

# short_form_dict = dict(zip(consignee_consiner_df['Short_Form'], consignee_consiner_df['Full_Form']))

# final_df_without_FCI['CNSR_Full'] = final_df_without_FCI['CNSR'].map(short_form_dict)
# final_df_without_FCI['CNSG_Full'] = final_df_without_FCI['CNSG'].map(short_form_dict)

# # Mapping DVSN
# # Create a mapping dictionary for DVSN short forms to full forms
# dvsn_mapping = {
#     'BB': 'Bandra Division',
#     'BSL': 'Bhopal Division',
#     'NGP': 'Nagpur Division',
#     'PUNE': 'Pune Division',
#     'SUR': 'Surat Division',
#     'WDFC': 'Western Dedicated Freight Corridor',
#     'DDU': 'Deen Dayal Upadhyaya Junction',
#     'DHN': 'Dhanbad Division',
#     'DNR': 'Danapur Division',
#     'SEE': 'Sealdah Division',
#     'SPJ': 'Samastipur Division',
#     'KUR': 'Khurda Road Division',
#     'SBP': 'Sambalpur Division',
#     'WAT': 'Wadi Division',
#     'ASN': 'Asansol Division',
#     'HWH': 'Howrah Division',
#     'MLDT': 'Malda Town Division',
#     'KAWR': 'Kalyan Division',
#     'RN':  'Rourkela Division',
#     'AGRA':  "Agra Division",
#     'JHS':  "Jhansi Division",
#     'PRYJ':  "Prayagraj Junction",
#     'BSB':  "Varanasi Division",
#     'IZN':  "Izatnagar Division",
#     'LJN':  "Lucknow Junction",
#     'APDJ':  "Amritsar Division",
#     'KIR':  "Kharagpur Division",
#     'LMG':  "Ludhiana Division",
#     'RNY':  "Rani Kamlapati Division",
#     'TSK':  "Tinsukia Division",
#     'DLI':  "Delhi Division",
#     'FZR':  "Ferozepur Division",
#     'LKO':  "Lucknow Division",
#     'MB':   "Moradabad Division",
#     'UMB':  "Ambala Division",
#     'AII':  "Ajmer Division",
#     'BKN':  "Bikaner Division",
#     'JP':   "Jaipur Division",
#     'JU':   "Jodhpur Division",
#     'BZA':  "Vijayawada Division",
#     'GNT':  "Guntur Division",
#     'GTL':  "Guntakal Junction",
#     'HYB':  "Hyderabad Division",
#     'NED':  "Nanded Division",
#     "ADRA": "Adra Junction",
#     "CKP": "Chhapra Kacheri",
#     "KGP": "Kharagpur",
#     "RNC": "Ranchi",
#     "BSP": "Bilaspur",
#     "NAG": "Nagaur",
#     "R": "Rourkela",
#     "MAS": "Chennai Egmore (Madras)",
#     "MDU": "Madurai",
#     "SA": "Salem",
#     "TPJ": "Tiruchirappalli Junction",
#     "TVC": "Thiruvananthapuram Central",
#     "MYS": "Mysuru",
#     "SBC": "Krantivira Sangolli Rayanna (Bangalore City)",
#     "UBL": "Hubli",
#     "BPL": "Bhopal",
#     "JBP": "Jabalpur",
#     "KOTA": "Kota",
#     "ADI": "Ahmedabad",
#     "BCT": "Bhavnagar Terminus",
#     "BRC": "Vadodara Junction (Baroda)",
#     "BVC": "Bhopal (BVC)",
#     "RJT": "Rajkot Junction",
#     "RTM": "Ratlam Junction"
# }

# final_df_without_FCI['DVSN'] = final_df_without_FCI['DVSN'].replace(dvsn_mapping)

# final_df_without_FCI.to_csv('final_df_without_FCI.csv', index=False)
# print("Final file has been generated.")


# %%
import pandas as pd
final_df_without_FCI= pd.read_csv('final_df_without_FCI.csv')


# %%
final_df_without_FCI

# %%
final_df_without_FCI = final_df_without_FCI[final_df_without_FCI['RAKE CMDT'].isin(['M', 'DOC'])]
final_df_without_FCI

# %%
final_df_without_FCI[['DVSN','STTN FROM','CNSR_Full','CNSG_Full','RAKE CMDT','Region']]

# %%
# Your actual bot token
BOT_TOKEN = "7836500041:AAHOL2jJ8WGrRVeAnjJ3a354W6c6jgD22RU"
# Replace with your actual chat IDs
# Dictionary mapping chat IDs to names
CHAT_IDS = {
    8147978368: "Mohan FarmIndia",
    499903657: "Mohan Personal",
    7967517419: "Rasheed",
    7507991236: "Vidish",
    8192726425: "Rishi"}


# %%
import nest_asyncio
import asyncio
import pandas as pd
from telegram import Bot
from datetime import datetime, timedelta

# Apply nest_asyncio to allow nested event loops in Jupyter Notebook
nest_asyncio.apply()

async def send_daily_alert() -> None:
    try:
        # Get current date and time for comparison
        current_time = datetime.now()  # Use actual current date and time.
        
        # Count total rows in final_df_without_FCI
        total_rows = len(final_df_without_FCI)
        print(f"Total rows in final_df_without_FCI: {total_rows}")

        # Filter the DataFrame for Rake Commodity 'M' and 'DOC'
        filtered_df = final_df_without_FCI[final_df_without_FCI['RAKE CMDT'].isin(['M', 'DOC'])]

        # Convert DEMAND TIME to a datetime object for sorting
        filtered_df['DEMAND TIME'] = pd.to_datetime(filtered_df['DEMAND TIME'], format='%H:%M').apply(
            lambda x: x.replace(year=current_time.year, month=current_time.month, day=current_time.day)
        )

        # Create a new column for full datetime for sorting
        filtered_df['FULL DATETIME'] = pd.to_datetime(
            filtered_df['DEMAND DATE'] + ' ' + filtered_df['DEMAND TIME'].dt.strftime('%H:%M'),
            format='%d-%m-%y %H:%M'
        )

        # Sort by FULL DATETIME from latest to oldest
        sorted_df = filtered_df.sort_values(by='FULL DATETIME', ascending=False)

        # Prepare the message with improved formatting
        message = "*Daily Competitor Alert:*\n\n"
        
        current_date = None  # To keep track of the current demand date in the loop
        
        for index, row in sorted_df.iterrows():
            if current_date != row['DEMAND DATE']:
                current_date = row['DEMAND DATE']
                message += f"*Demand Date:* {current_date}\n\n"  # Add Demand Date once per group

            message += (
                f"*From:* {row['STTN FROM']}\n"
                f"*To:* {row['DSTN']}\n"
                f"*CMDT:* {row['RAKE CMDT']}\n"
                f"*CNSR:* {row['CNSR_Full']}\n"
                f"*CNSG:* {row['CNSG_Full']}\n"
                f"*DVSN:* {row['DVSN']}\n"
                f"*Demand Time:* {row['DEMAND TIME'].strftime('%H:%M')} on {row['DEMAND DATE']}\n\n"  # Include date with time.
            )

            message += "\n"  # Add extra space between different entries

        # Print the complete message for debugging purposes
        print(message)

        # Create bot instance and send message to each chat ID with names.
        bot = Bot(token=BOT_TOKEN)
        
        sent_rows_count = 0  # Counter for sent rows
        
        for chat_id, name in CHAT_IDS.items():
            try:
                await bot.send_message(chat_id=chat_id, text=f"{name}, {message}", parse_mode='Markdown')
                sent_rows_count += len(sorted_df)  # Increment count by number of rows sent
            except Exception as e:
                print(f"An error occurred while sending message to {name}: {e}")

        print(f"Total rows sent: {sent_rows_count}")  # Print total sent rows

        # Check if there are any remaining rows that were not sent
        remaining_rows = final_df_without_FCI[~final_df_without_FCI.index.isin(sorted_df.index)]
        
        if not remaining_rows.empty:
            print("Remaining rows that were not sent:")
            print(remaining_rows[['DEMAND DATE', 'DEMAND TIME', 'STTN FROM', 'DSTN', 'RAKE CMDT']])
            
            remaining_message = "*Remaining Indents Not Sent:*\n\n"
            
            for index, row in remaining_rows.iterrows():
                remaining_message += (
                    f"*Demand Date:* {row['DEMAND DATE']}\n"
                    f"*From:* {row['STTN FROM']}\n"
                    f"*To:* {row['DSTN']}\n"
                    f"*CMDT:* {row['RAKE CMDT']}\n"
                    f"*CNSR:* {row['CNSR_Full']}\n"
                    f"*CNSG:* {row['CNSG_Full']}\n"
                    f"*DVSN:* {row['DVSN']}\n"
                    f"*Demand Time:* {row['DEMAND TIME']} on {row['DEMAND DATE']}\n\n"
                )
            
            print(remaining_message)  # Print remaining message for debugging
            
            for chat_id, name in CHAT_IDS.items():
                try:
                    await bot.send_message(chat_id=chat_id, text=f"{name}, {remaining_message}", parse_mode='Markdown')
                except Exception as e:
                    print(f"An error occurred while sending remaining message to {name}: {e}")

    except Exception as e:
        print(f"An error occurred: {e}")

# Run the alert sending function in an async context.
async def main():
    await send_daily_alert()

# Ensure this line is executed only if this script is run directly.
if __name__ == "__main__":
    asyncio.run(main())


# %%
# import nest_asyncio
# import asyncio
# import pandas as pd
# from telegram import Bot
# from telegram.ext import ApplicationBuilder, ContextTypes

# # Apply nest_asyncio to allow nested event loops in Jupyter Notebook
# nest_asyncio.apply()

# async def send_daily_alert() -> None:
#     # Assuming final_df_without_FCI is already defined and loaded elsewhere in the code
#     try:
#         # Filter the DataFrame for Rake Commodity 'M' and 'DOC'
#         filtered_df = final_df_without_FCI[final_df_without_FCI['RAKE CMDT'].isin(['M', 'DOC'])]

#         # Group and format the data, ensuring 'DVSN' is included
#         grouped_info = filtered_df.groupby(
#             ['DEMAND DATE', 'STTN FROM', 'DSTN', 'RAKE CMDT', 'CNSR_Full', 'CNSG_Full', 'DVSN', 'DEMAND TIME']
#         ).size().reset_index(name='Count')

#         # Prepare the message with improved formatting
#         message = "*Daily Competitor Alert:*\n\n"  # Bold title and add space

#         current_date = None  # To keep track of the current demand date in the loop
#         for index, row in grouped_info.iterrows():
#             if current_date != row['DEMAND DATE']:
#                 current_date = row['DEMAND DATE']
#                 message += f"*Demand Date:* {current_date}\n\n"  # Add Demand Date once per group

#             message += (
#                 f"*From:* {row['STTN FROM']}\n"
#                 f"*To:* {row['DSTN']}\n"
#                 f"*CMDT:* {row['RAKE CMDT']}\n"
#                 f"*CNSR:* {row['CNSR_Full']}\n"
#                 f"*CNSG:* {row['CNSG_Full']}\n"
#                 f"*DVSN:* {row['DVSN']}\n"
#                 f"*Demand Time:* {row['DEMAND TIME']}\n\n"  # Add extra space between rows
#             )

#         # Create bot instance and send message to each chat ID with names
#         bot = Bot(token=BOT_TOKEN)
#         for chat_id, name in CHAT_IDS.items():
#             try:
#                 await bot.send_message(chat_id=chat_id, text=f"{name}, {message}", parse_mode='Markdown')  # Use Markdown for formatting
#             except Exception as e:
#                 print(f"An error occurred while sending message to {name}: {e}")

#     except Exception as e:
#         print(f"An error occurred: {e}")

# # Start the bot without using asyncio.run()
# await send_daily_alert()


# %%
from datetime import datetime

# Get the current date and time
current_datetime = datetime.now()

# Format the date and time
formatted_datetime = current_datetime.strftime("%Y-%m-%d %H:%M:%S")

print("Current date and time:", formatted_datetime)


# %% [markdown]
# # poll

# %%
# import nest_asyncio
# import asyncio
# from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
# from telegram.ext import ApplicationBuilder, CallbackQueryHandler, ContextTypes

# # Apply nest_asyncio to allow nested event loops
# nest_asyncio.apply()

# # Store user responses as a dictionary of user_id: (username, selected_option)
# user_responses = {}

# # Post the poll to all chat IDs
# async def post_poll(application):
#     question = "🤔 Which is the most important division for FG and DOC?"
#     options = [
#         "CR", "DFCR", "EC", "ECO", "ER",
#         "KR", "NC", "NE", "NF", "NPLR",
#         "NR", "NW", "SC", "SE", "SEC",
#         "SR", "SW", "WC", "WR"
#     ]

#     keyboard = [[InlineKeyboardButton(option, callback_data=option) for option in options[i:i + 4]] for i in range(0, len(options), 4)]
#     reply_markup = InlineKeyboardMarkup(keyboard)

#     # Send poll to all users
#     for chat_id, name in CHAT_IDS.items():
#         await application.bot.send_message(chat_id=chat_id, text=f"{name}, {question}", reply_markup=reply_markup)

#     # Schedule the poll to end after 1 minute
#     await asyncio.sleep(60)
#     await end_poll(application)

# # Handle poll responses
# async def handle_poll_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     query = update.callback_query
#     await query.answer()
#     selected_option = query.data
#     user_name = query.from_user.full_name

#     # Store user response
#     user_id = query.from_user.id
#     user_responses[user_id] = (user_name, selected_option)

#     # Log real-time responses for the programmer
#     print(f"Real-Time Update: {user_name} voted for {selected_option}")
#     print("Current User Responses (Real-Time):")
#     for uid, (name, option) in user_responses.items():
#         print(f" - {name}: {option}")

#     # Notify the user about their selection
#     await context.bot.send_message(
#         chat_id=query.message.chat_id,
#         text=f"You selected: {selected_option}"
#     )

# # End the poll and display results
# async def end_poll(application):
#     results_message = "*Poll Results:*\n"

#     # Count and display responses
#     response_count = {option: 0 for option in [
#         "CR", "DFCR", "EC", "ECO", "ER",
#         "KR", "NC", "NE", "NF", "NPLR",
#         "NR", "NW", "SC", "SE", "SEC",
#         "SR", "SW", "WC", "WR"
#     ]}

#     for user_id, (_, selected_option) in user_responses.items():
#         if selected_option in response_count:
#             response_count[selected_option] += 1

#     for option, count in response_count.items():
#         results_message += f"{option}: {count} votes\n"

#     # Send results to all users (anonymous)
#     for chat_id, name in CHAT_IDS.items():
#         await application.bot.send_message(chat_id=chat_id, text=f"{name}, {results_message}")

#     # Stop the bot and the event loop
#     print("Poll ended. Shutting down the bot.")
#     await application.stop()
#     asyncio.get_event_loop().stop()  # Stop the Jupyter notebook event loop

# # Main function to start the bot and run the poll
# async def main():
#     application = ApplicationBuilder().token(BOT_TOKEN).build()

#     # Add handlers
#     application.add_handler(CallbackQueryHandler(handle_poll_response))

#     # Start the poll immediately
#     asyncio.create_task(post_poll(application))

#     # Run the bot
#     await application.run_polling()

# # Run the bot
# if __name__ == "__main__":
#     asyncio.run(main())


# %%



