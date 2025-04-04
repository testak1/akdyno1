# app.py - AK-TUNING DYNO Webapp i Streamlit

import streamlit as st
import os
import datetime
import matplotlib.pyplot as plt
import numpy as np
from scipy.interpolate import make_interp_spline
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
from fpdf import FPDF
import chromedriver_autoinstaller
import tempfile

# --- Globala variabler ---
user_custom_values = None

# --- Hjälpmetoder ---
def get_garantibevis_folder():
    folder = os.path.join(os.path.expanduser("~"), "Desktop", "Garantibevis")
    os.makedirs(folder, exist_ok=True)
    return folder

def log_pdf_creation(regnr, filepath):
    log_path = os.path.join(get_garantibevis_folder(), "logg.txt")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {regnr} - {filepath}\n")

def extract_tuning_info(url):
    try:
        chromedriver_autoinstaller.install()
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        service = Service("chromedriver.exe")
        driver = webdriver.Chrome(service=service, options=options)

        driver.get(url)

        # Vänta på att breadcrumb ska ladda (som en indikation på att hela sidan är laddad)
        try:
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.ID, "breadcrumb"))
            )
        except:
            st.warning("Timeout – sidan laddades inte klart.")
            driver.quit()
            return None, "DYNO"

        # Försök klicka på Stage 1-tab om den finns
        try:
            stage_link = driver.find_element(By.CSS_SELECTOR, 'a[href="#stage-1"]')
            driver.execute_script("arguments[0].click();", stage_link)
        except:
            st.info("Ingen Stage 1-flik hittades – försöker ändå läsa data.")

        time.sleep(1.5)  # liten paus för att innehåll ska hinna uppdateras
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        driver.quit()

        breadcrumb = soup.find("span", {"id": "breadcrumb"})
        car_name = breadcrumb.get_text(strip=True).replace(" ->", "") if breadcrumb else "DYNO"

        stage1_tab = soup.find("div", {"id": "stage-1"})
        if not stage1_tab:
            return None, car_name

        rows = stage1_tab.find_all("tr")
        hk_values, nm_values = [], []
        for row in rows:
            cols = row.find_all("td")
            if len(cols) >= 2:
                val_text = cols[1].text.strip().replace("hk", "").replace("Nm", "").replace("+", "").strip()
                if val_text.isdigit():
                    val = int(val_text)
                    if "HK" in cols[1].text.upper():
                        hk_values.append(val)
                    elif "NM" in cols[1].text.upper():
                        nm_values.append(val)

        if len(hk_values) >= 3 and len(nm_values) >= 3:
            return {
                "Original": {"hk": hk_values[0], "Nm": nm_values[0]},
                "Tuned": {"hk": hk_values[1], "Nm": nm_values[1]},
                "Increase": {"hk": hk_values[2], "Nm": nm_values[2]}
            }, car_name
        else:
            return None, car_name

    except Exception as e:
        st.error(f"Kunde inte hämta data: {e}")
        return None, "DYNO"

def plot_dyno(data, car_name, is_diesel=True):
    global user_custom_values
    tuned = user_custom_values if user_custom_values else data["Tuned"]
    rpm = np.array([1500, 2000, 2500, 3000, 3500, 4000, 4500, 5000]) if is_diesel else \
          np.array([1500, 2000, 3000, 4000, 5000, 6000, 6500, 7000])
    nm_shape = np.array([0.7, 0.9, 1.0, 0.95, 0.85, 0.75, 0.65, 0.5])
    hk_shape = np.array([0.2, 0.45, 0.65, 0.8, 0.9, 1.0, 0.95, 0.85])

    rpm_smooth = np.linspace(rpm.min(), rpm.max(), 300)
    fig, ax1 = plt.subplots(figsize=(9, 5))
    ax1.plot(rpm_smooth, make_interp_spline(rpm, hk_shape * data["Original"]["hk"])(rpm_smooth), label="Original HK")
    ax1.plot(rpm_smooth, make_interp_spline(rpm, hk_shape * tuned["hk"])(rpm_smooth), label="Tuned HK", color='red')
    ax2 = ax1.twinx()
    ax2.plot(rpm_smooth, make_interp_spline(rpm, nm_shape * data["Original"]["Nm"])(rpm_smooth), linestyle="--", label="Original NM")
    ax2.plot(rpm_smooth, make_interp_spline(rpm, nm_shape * tuned["Nm"])(rpm_smooth), linestyle="--", label="Tuned NM", color='red')
    ax1.set_title("DYNO Chart")
    ax1.set_xlabel("RPM")
    ax1.set_ylabel("Effekt (HK)")
    ax2.set_ylabel("Vridmoment (Nm)")
    fig.legend(loc="upper left")
    st.pyplot(fig)
    return fig

def save_pdf(car_name, regnr, miltal, tillval, extra, data, fig):
    tuned_data = user_custom_values if user_custom_values else data["Tuned"]
    folder = get_garantibevis_folder()
    filepath = os.path.join(folder, f"Garantibevis - {regnr}.pdf")
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, "AK-TUNING Garantibevis", ln=True, align='C')
    pdf.set_font("Arial", size=12)
    pdf.cell(0, 10, f"Bilmodell: {car_name}", ln=True)
    pdf.cell(0, 10, f"Regnr: {regnr}", ln=True)
    pdf.cell(0, 10, f"Miltal: {miltal}", ln=True)
    pdf.cell(0, 10, f"Datum: {datetime.date.today()}", ln=True)
    if tillval:
        pdf.multi_cell(0, 10, f"Tillval: {', '.join(tillval)}")
    if extra:
        pdf.multi_cell(0, 10, f"Extra: {extra}")
    pdf.cell(0, 10, f"HK: {tuned_data['hk']}", ln=True)
    pdf.cell(0, 10, f"NM: {tuned_data['Nm']}", ln=True)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmpfile:
        fig.savefig(tmpfile.name)
        pdf.image(tmpfile.name, x=10, y=None, w=180)
    pdf.output(filepath)
    log_pdf_creation(regnr, filepath)
    st.success(f"PDF sparades i: {filepath}")

# --- Streamlit UI ---
st.set_page_config(page_title="AK-TUNING DYNO", layout="centered")
st.title("AK-TUNING DYNO Webapp")

url = st.text_input("Klistra in AK Performance URL")
engine = st.radio("Motortyp", ["Diesel", "Bensin"])
is_diesel = engine == "Diesel"

if st.button("Hämta tuningdata"):
    result, car_name = extract_tuning_info(url)
    if result:
        st.session_state["tuningdata"] = result
        st.session_state["car_name"] = car_name
        fig = plot_dyno(result, car_name, is_diesel)
        st.session_state["dyno_fig"] = fig

if "tuningdata" in st.session_state:
    st.markdown("---")
    st.header("Skapa garantibevis")
    col1, col2 = st.columns(2)
    with col1:
        regnr = st.text_input("Registreringsnummer")
        miltal = st.text_input("Miltal")
    with col2:
        hk = st.number_input("Egen Tuned HK", value=0)
        nm = st.number_input("Egen Tuned NM", value=0)
    tillval = st.multiselect("Tillval", ["VMAX OFF", "DPF OFF", "EGR OFF", "ADBLUE OFF", "DECAT", "OPF OFF", "POPS&BANGS"])
    extra = st.text_input("Extra (DTC/Felkod mm)")
if st.button("Skapa PDF"):
    if hk > 0 and nm > 0:
        user_custom_values = {"hk": hk, "Nm": nm}
    else:
        user_custom_values = None
    save_pdf(st.session_state["car_name"], regnr, miltal, tillval, extra, st.session_state["tuningdata"], st.session_state["dyno_fig"])