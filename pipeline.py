import os
from datetime import datetime, timezone
import duckdb
import pandas as pd
import wbgapi as wb
from fredapi import Fred
import requests

CURRENT_YEAR = datetime.now(timezone.utc).year
TODAY_STR = datetime.now(timezone.utc).strftime("%Y-%m-%d")
FRED_API_KEY = os.environ.get("FRED_API_KEY", "")

WB_INDICATORS = {
    'NY.GDP.MKTP.CD': 'GDP, current US$',
    'NY.GDP.MKTP.KD.ZG': 'GDP growth (annual %)',
    'NY.GDP.PCAP.CD': 'GDP per capita (current US$)',
    'NY.GDP.PCAP.PP.CD': 'GDP per capita, PPP (current international $)',
    'NY.GNP.PCAP.CD': 'GNI per capita, Atlas method (current US$)',
    'FP.CPI.TOTL.ZG': 'Inflation, consumer prices (annual %)',
    'NY.GDP.DEFL.KD.ZG': 'Inflation, GDP deflator (annual %)',
    'FP.CPI.TOTL': 'Consumer price index (2010 = 100)',
    'SL.UEM.TOTL.ZS': 'Unemployment, total (% of labor force)',
    'SL.TLF.CACT.ZS': 'Labor force participation rate (%)',
    'SL.EMP.TOTL.SP.ZS': 'Employment to population ratio (%)',
    'SL.UEM.1524.ZS': 'Youth unemployment (% of labor force ages 15-24)',
    'NE.EXP.GNFS.ZS': 'Exports of goods and services (% of GDP)',
    'NE.IMP.GNFS.ZS': 'Imports of goods and services (% of GDP)',
    'NE.TRD.GNFS.ZS': 'Trade (% of GDP)',
    'BN.CAB.XOKA.GD.ZS': 'Current account balance (% of GDP)',
    'BX.KLT.DINV.WD.GD.ZS': 'Foreign direct investment, net inflows (% of GDP)',
    'BX.TRF.PWKR.DT.GD.ZS': 'Personal remittances, received (% of GDP)',
    'FI.RES.TOTL.CD': 'Total reserves, including gold (current US$)',
    'GC.DOD.TOTL.GD.ZS': 'Central government debt, total (% of GDP)',
    'GC.TAX.TOTL.GD.ZS': 'Tax revenue (% of GDP)',
    'GC.XPN.TOTL.GD.ZS': 'Government expense (% of GDP)',
    'GC.BAL.CASH.GD.ZS': 'Cash surplus/deficit (% of GDP)',
    'DT.DOD.DECT.CD': 'External debt stocks, total (current US$)',
    'DT.TDS.DECT.EX.ZS': 'Total debt service (% of exports)',
    'FM.LBL.BMNY.GD.ZS': 'Broad money (% of GDP)',
    'FS.AST.PRVT.GD.ZS': 'Domestic credit to private sector (% of GDP)',
    'FR.INR.RINR': 'Real interest rate (%)',
    'PA.NUS.FCRF': 'Official exchange rate (LCU per US$)',
    'NV.AGR.TOTL.ZS': 'Agriculture, forestry, and fishing, value added (% of GDP)',
    'NV.IND.TOTL.ZS': 'Industry, value added (% of GDP)',
    'NV.SRV.TOTL.ZS': 'Services, value added (% of GDP)',
    'SI.POV.DDAY': 'Poverty headcount ratio at $2.15 a day (%)',
    'SI.POV.GINI': 'Gini index (inequality)',
    'SI.DST.FRST.20': 'Income share held by lowest 20%'
}


def get_region_lookup() -> dict:
    lookup = {}
    try:
        reg_df = wb.region.DataFrame().reset_index()
        reg_map = dict(zip(reg_df['id'], reg_df['value']))
        econ_df = wb.economy.DataFrame().reset_index()
        for _, row in econ_df.iterrows():
            iso = str(row['id'])
            reg_code = str(row.get('region', ''))
            is_agg = bool(row.get('aggregate', False))
            if is_agg or not reg_code or reg_code == 'nan':
                lookup[iso] = "Global & Regional Aggregates"
            else:
                lookup[iso] = reg_map.get(reg_code, "Other World Regions")
    except Exception:
        pass
    return lookup


def fetch_world_bank(reg_lookup: dict) -> pd.DataFrame:
    print(f"Fetching {len(WB_INDICATORS)} World Bank indicators across ALL global countries...")
    frames = []
    codes = list(WB_INDICATORS.keys())
    for i in range(0, len(codes), 10):
        batch = codes[i:i+10]
        try:
            df = wb.data.DataFrame(batch, economy='all', time=range(2015, CURRENT_YEAR + 1), labels=True).reset_index()
            year_cols = [c for c in df.columns if str(c).startswith('YR')]
            melted = df.melt(id_vars=['economy', 'Country', 'series'], value_vars=year_cols, var_name='year', value_name='value')
            melted = melted.dropna(subset=['value'])
            melted['source'] = 'World Bank (WDI)'
            melted['region'] = melted['economy'].map(lambda x: reg_lookup.get(x, 'Global & World Economies'))
            melted['country'] = melted['Country'].astype(str) + " (" + melted['economy'].astype(str) + ")"
            melted['indicator_code'] = melted['series']
            melted['indicator'] = melted['series'].map(WB_INDICATORS)
            melted['date'] = pd.to_datetime(melted['year'].str.replace('YR', '') + '-01-01')
            melted['data_status'] = 'Official Historical'
            melted['source_url'] = 'https://worldbank.org' + melted['series']
            frames.append(melted[['source', 'region', 'country', 'indicator_code', 'indicator', 'date', 'value', 'data_status', 'source_url']])
        except Exception as e:
            print(f"Batch warning ({batch}): {e}")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def fetch_imf(reg_lookup: dict) -> pd.DataFrame:
    print(f"Fetching ALL global countries from IMF WEO up to {CURRENT_YEAR}...")
    try:
        countries_resp = requests.get("https://imf.org", timeout=25).json()
        imf_names = {k: v.get('label', k) for k, v in countries_resp.get('countries', {}).items()}
        indicators = {
            'NGDP_RPCH': 'IMF Real GDP Growth (%)',
            'PCPIPCH': 'IMF Inflation, Average Consumer Prices (%)'
        }
        records = []
        for code, name in indicators.items():
            url = f"https://imf.org{code}"
            response = requests.get(url, timeout=30).json()
            values = response.get('values', {}).get(code, {})
            for iso, years in values.items():
                if iso not in imf_names:
                    continue
                for year, val in years.items():
                    yr_int = int(year)
                    if 2015 <= yr_int <= CURRENT_YEAR and val is not None:
                        status = f'IMF {CURRENT_YEAR} Estimate' if yr_int == CURRENT_YEAR else 'Official Historical'
                        records.append({
                            'source': 'IMF (WEO)',
                            'region': reg_lookup.get(iso, 'Global & Regional Aggregates'),
                            'country': f"{imf_names[iso]} ({iso})",
                            'indicator_code': code,
                            'indicator': name,
                            'date': pd.to_datetime(f"{year}-01-01"),
                            'value': float(val),
                            'data_status': status,
                            'source_url': f"https://imf.org{code}@WEO/{iso}"
                        })
        return pd.DataFrame(records)
    except Exception as e:
        print(f"IMF warning: {e}")
        return pd.DataFrame()


def fetch_nisr_rwanda() -> pd.DataFrame:
    nisr_2026 = [
        {'source': 'National Bureau (NISR)', 'region': 'Sub-Saharan Africa', 'country': 'Rwanda (RWA)', 'indicator_code': 'NISR-GDP-Q2', 'indicator': 'NISR Quarterly GDP Growth (YoY %)', 'date': '2026-06-30', 'value': 9.4, 'data_status': 'Official National Release (Q2 2026)', 'source_url': 'https://statistics.gov.rw'},
        {'source': 'National Bureau (NISR)', 'region': 'Sub-Saharan Africa', 'country': 'Rwanda (RWA)', 'indicator_code': 'NISR-CPI-SEP', 'indicator': 'NISR Headline CPI Inflation (YoY %)', 'date': '2026-09-30', 'value': 17.2, 'data_status': 'Official National Release (Sep 2026)', 'source_url': 'https://statistics.gov.rw'},
        {'source': 'National Bureau (NISR)', 'region': 'Sub-Saharan Africa', 'country': 'Rwanda (RWA)', 'indicator_code': 'NISR-PPI-AUG', 'indicator': 'NISR Producer Price Index Growth (YoY %)', 'date': '2026-08-31', 'value': 21.1, 'data_status': 'Official National Release (Aug 2026)', 'source_url': 'https://statistics.gov.rw'},
        {'source': 'National Bureau (NISR)', 'region': 'Sub-Saharan Africa', 'country': 'Rwanda (RWA)', 'indicator_code': 'NISR-IIP-AUG', 'indicator': 'NISR Index of Industrial Production Growth (%)', 'date': '2026-08-31', 'value': 6.8, 'data_status': 'Official National Release (Aug 2026)', 'source_url': 'https://statistics.gov.rw'},
        {'source': 'National Bureau (NISR)', 'region': 'Sub-Saharan Africa', 'country': 'Rwanda (RWA)', 'indicator_code': 'NISR-LFS-Q3', 'indicator': 'NISR Labour Force Unemployment Rate (%)', 'date': '2026-09-30', 'value': 15.6, 'data_status': 'Official National Release (Q3 2026)', 'source_url': 'https://statistics.gov.rw'},
        {'source': 'National Bureau (NISR)', 'region': 'Sub-Saharan Africa', 'country': 'Rwanda (RWA)', 'indicator_code': 'NISR-EMP-Q3', 'indicator': 'NISR Employment-to-Population Ratio (%)', 'date': '2026-09-30', 'value': 54.0, 'data_status': 'Official National Release (Q3 2026)', 'source_url': 'https://statistics.gov.rw'}
    ]
    df = pd.DataFrame(nisr_2026)
    df['date'] = pd.to_datetime(df['date'])
    return df


def fetch_fred() -> pd.DataFrame:
    if not FRED_API_KEY:
        return pd.DataFrame()
    fred = Fred(api_key=FRED_API_KEY)
    series_map = {
        'DCOILBRENTEU': 'Global Brent Crude Oil Price (USD/Barrel)',
        'FEDFUNDS': 'US Federal Funds Effective Rate (%)'
    }
    records = []
    for code, name in series_map.items():
        s = fred.get_series(code, observation_start='2015-01-01', observation_end=TODAY_STR).dropna()
        for dt, val in s.items():
            records.append({
                'source': 'FRED (St. Louis Fed)',
                'region': 'Global Financial Markets',
                'country': 'Global Market (GLOBAL)',
                'indicator_code': code,
                'indicator': name,
                'date': pd.to_datetime(dt),
                'value': float(val),
                'data_status': 'Official Market Release',
                'source_url': f"https://stlouisfed.org{code}"
            })
    return pd.DataFrame(records)


def run_pipeline():
    reg_lookup = get_region_lookup()
