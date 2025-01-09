# %% 
# !pip install selenium pillow pytesseract webdriver-manager pandas tqdm telegram python-dotenv 

# %% 
from datetime import datetime, timedelta
import os
import shutil
import time
import re
import pandas as pd
from tqdm import tqdm
import concurrent.futures

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException
from PIL import Image, ImageEnhance, ImageFilter
import pytesseract
from io import BytesIO
from webdriver_manager.chrome import ChromeDriverManager

# Get the current date and time
current_datetime = datetime.now()
formatted_datetime = current_datetime.strftime("%Y-%m-%d %H:%M:%S")
print("Current date and time:", formatted_datetime)

# Date for past 24 hours
past_24_hours_date = (datetime.now() - timedelta(days=1)).strftime("%d-%m-%y %H:%M:%S")
print(f"Date for past 24 hours: {past_24_hours_date}")

# Function to solve CAPTCHA with retry logic
def solve_captcha(driver, image_xpath):
    while True:
        try:
            captcha_element = driver.find_element(By.XPATH, image_xpath)
            captcha_image = captcha_element.screenshot_as_png
            captcha_image = Image.open(BytesIO(captcha_image)).convert("L")
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
            
            time.sleep(2)  # Allow time for form processing
            
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
    options.add_argument("--headless")  # Run in headless mode
    options.add_argument("--start-maximized")

    # Retry logic for ChromeDriver installation
    retries = 3
    for attempt in range(retries):
        try:
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
            break  # Exit loop if successful
        except Exception as e:
            print(f"Attempt {attempt + 1} failed to install ChromeDriver: {e}")
            time.sleep(2)  # Wait before retrying
            if attempt == retries - 1:
                raise

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
        past_24_hours = current_time - timedelta(hours=24)

        today_date_str = current_time.strftime("%d-%m-%y")
        yesterday_date_str = (current_time - timedelta(days=1)).strftime("%d-%m-%y")

        for row in rows:
            columns = [col.text for col in row.find_elements(By.TAG_NAME, "td")]
            
            # Check if there are enough columns and filter based on conditions.
            if len(columns) >= 10 and columns[9] in ["FG", "DOC"]:
                demand_date_str = columns[4]
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
            "S.No.", "DVSN", "STTN FROM", "DEMAND NO.", 
            "DEMAND DATE", "DEMAND TIME", "Expected loading date", 
            "CNSR", "CNSG", "CMDT", "TT", 
            "PC", "PBF", "VIA", "RAKE CMDT", 
            "DSTN", "INDENTED TYPE", "INDENTED UNTS", 
            "INDENTED 8W", "OTSG UNTS", "OTSG 8W", 
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
    "CR", "DFCR", "EC", "ECO", 
    "ER", "KR", "NC", "NE", 
    "NF", "NPLR", "NR", "NW",
    "SC", "SE", "SEC", "SR",
    "SW", "WC", "WR"
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

final_df_without_FCI = final_df[final_df['CNSR'] != 'FCI']
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

short_form_dict_consignees = dict(zip(consignee_consiner_df['Short_Form'], consignee_consiner_df['Full_Form']))
final_df_without_FCI['CNSR_Full'] = final_df_without_FCI['CNSR'].map(short_form_dict_consignees)
final_df_without_FCI['CNSG_Full'] = final_df_without_FCI['CNSG'].map(short_form_dict_consignees)

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
