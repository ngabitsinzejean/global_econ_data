import streamlit as st
import duckdb
import pandas as pd
import plotly.express as px

# ---------------------------------------------------------
# 1. PAGE CONFIGURATION & HEADER
# ---------------------------------------------------------
st.set_page_config(
    page_title="Global & Rwanda Verified Economics Hub",
    page_icon="🌍",
    layout="wide"
)

st.title("Global & Rwanda Verified Economics Intelligence Hub")
st.markdown(
    "Standardized economic datasets from **World Bank**, **IMF**, **FRED**, and **NISR**, "
    "paired with live updates from **BNR** and Rwandan financial institutions."
)

# Direct Quick-Launch Buttons for Official Portals
p1, p2, p3, p4 = st.columns(4)
p1.link_button("Open NISR Portal", "https://statistics.gov.rw", use_container_width=True)
p2.link_button("Open World Bank DataBank", "https://worldbank.org", use_container_width=True)
p3.link_button("Open BNR (Central Bank)", "https://bnr.rw", use_container_width=True)
p4.link_button("Open MINECOFIN Rwanda", "https://minecofin.gov.rw", use_container_width=True)

# ---------------------------------------------------------
# 2. DATA & NEWS LOADING
# ---------------------------------------------------------
@st.cache_data(ttl=600)
def load_database():
    con = duckdb.connect("economics_hub.duckdb", read_only=True)
    tables = [t[0] for t in con.execute("SHOW TABLES").fetchall()]
    
    indicators_df = con.execute("SELECT * FROM indicators ORDER BY date").df() if "indicators" in tables else pd.DataFrame()
    news_df = con.execute("SELECT * FROM rwanda_finance_news").df() if "rwanda_finance_news" in tables else pd.DataFrame()
    
    con.close()
    return indicators_df, news_df

try:
    df, news_df = load_database()
except Exception as e:
    st.error(f"Database initializing: {e}")
    st.stop()

if df.empty:
    st.warning("No verified indicator records found yet. Run your GitHub Actions workflow once.")
    st.stop()

# ---------------------------------------------------------
# 3. VERIFICATION BANNER & KEY METRICS
# ---------------------------------------------------------
last_sync = df['last_verified_utc'].iloc[-1] if 'last_verified_utc' in df.columns else "Recently"
st.caption(f"Last Verified Automated Sync: **{last_sync}** | Status: **Validated & Active**")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Verified Records", f"{len(df):,}")
col2.metric("Economies & Regions", df['country'].nunique())
col3.metric("Indicators Tracked", df['indicator'].nunique())
col4.metric("Rwanda Finance Updates", len(news_df))

st.divider()

# ---------------------------------------------------------
# 4. SIDEBAR FILTERS
# ---------------------------------------------------------
st.sidebar.header("Global Data Filters")
if st.sidebar.button("Refresh Latest Data & News", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

all_sources = sorted(list(df['source'].unique()))
selected_sources = st.sidebar.multiselect("1. Select Data Sources", options=all_sources, default=all_sources)
filtered_df = df[df['source'].isin(selected_sources)]

if filtered_df.empty:
    st.info("Select at least one Data Source in the left sidebar.")
    st.stop()

all_indicators = sorted(list(filtered_df['indicator'].unique()))
selected_indicator = st.sidebar.selectbox("2. Select Economic Indicator", options=all_indicators)
indicator_df = filtered_df[filtered_df['indicator'] == selected_indicator].copy()

all_regions = sorted(list(indicator_df['region'].unique()))
selected_regions = st.sidebar.multiselect("3. Filter by World Region", options=all_regions, default=all_regions)
region_df = indicator_df[indicator_df['region'].isin(selected_regions)].copy()

all_countries = sorted(list(region_df['country'].unique()))
select_all_countries = st.sidebar.checkbox("Plot All Countries in Filtered Regions", value=False)

if select_all_countries:
    selected_countries = all_countries
else:
    preferred_defaults = [
        'Rwanda (RWA)', 'United States (USA)', 'China (CHN)',
        'Kenya (KEN)', 'Germany (DEU)', 'India (IND)',
        'Brazil (BRA)', 'Global Market (GLOBAL)'
    ]
    default_selection = [c for c in preferred_defaults if c in all_countries] or all_countries[:5]
    selected_countries = st.sidebar.multiselect(
        f"4. Select Countries ({len(all_countries)} Available)",
        options=all_countries,
        default=default_selection
    )

chart_df = region_df[region_df['country'].isin(selected_countries)].copy()
available_hover = [c for c in ['source', 'region', 'indicator_code', 'data_status'] if c in chart_df.columns]

# ---------------------------------------------------------
# 5. MAIN DASHBOARD TABS (NEWS FIRST, TRENDS, MAP, AUDIT TABLE)
# ---------------------------------------------------------
tab_news, tab_trends, tab_map, tab_data = st.tabs([
    "BNR & Rwanda Finance News",
    "Time-Series Trends",
    "Global World Map",
    "Verified Audit Table & Export"
])

# --- TAB 1: BNR, NISR & RWANDA FINANCIAL NEWS FEED ---
with tab_news:
    st.subheader("Live Updates: BNR, NISR, MINECOFIN & Rwandan Financial Institutions")
    if news_df.empty:
        st.info("News feed is initializing. Run your GitHub Actions workflow to fetch the latest BNR and Rwanda financial headlines.")
    else:
        n_col1, n_col2 = st.columns([1, 2])
        with n_col1:
            institutions = ["All Institutions"] + sorted(list(news_df['institution'].unique()))
            selected_inst = st.selectbox("Filter by Institution", institutions)
        with n_col2:
            keyword_search = st.text_input("Search News Headlines (e.g., inflation, BNR, Bank of Kigali, GDP, bond)")

        filtered_news = news_df.copy()
        if selected_inst != "All Institutions":
            filtered_news = filtered_news[filtered_news['institution'] == selected_inst]
        if keyword_search:
            filtered_news = filtered_news[filtered_news['title'].str.contains(keyword_search, case=False, na=False)]

        st.caption(f"Showing **{len(filtered_news)}** verified headlines & institutional releases")

        for _, row in filtered_news.iterrows():
            with st.container(border=True):
                st.markdown(f"**[{row['title']}]({row['link']})**")
                st.caption(
                    f"🏛️ **{row['institution']}** | 📂 {row['category']} | "
                    f"📅 {row['published_date']} | ✅ {row['verified_source']}"
                )

# --- TAB 2: TIME-SERIES TRENDS ---
with tab_trends:
    if chart_df.empty:
        st.info("Select one or more countries in the left sidebar to display trend charts.")
    else:
        fig_line = px.line(
            chart_df,
            x='date',
            y='value',
            color='country',
            markers=True,
            hover_data=available_hover,
            title=f"{selected_indicator} — Historical & Current Trajectory"
        )
        fig_line.update_layout(xaxis_title="Observation Date", yaxis_title="Value", hovermode="x unified")
        st.plotly_chart(fig_line, use_container_width=True)

        latest_date = chart_df['date'].max()
        latest_snapshot = chart_df[chart_df['date'] == latest_date].sort_values(by='value', ascending=False)
        if len(latest_snapshot) > 1:
            fig_bar = px.bar(
                latest_snapshot.head(25),
                x='country',
                y='value',
                color='country',
                title=f"Latest Snapshot Comparison ({latest_date.strftime('%Y-%m-%d')})"
            )
            fig_bar.update_layout(showlegend=False, xaxis_title="Economy", yaxis_title="Value")
            st.plotly_chart(fig_bar, use_container_width=True)

# --- TAB 3: INTERACTIVE GLOBAL CHOROPLETH MAP ---
with tab_map:
    map_df = region_df.copy()
    map_df['iso3'] = map_df['country'].str.extract(r'\(([A-Z]{3})\)')
    map_df = map_df.dropna(subset=['iso3'])

    if map_df.empty:
        st.info("Global map view is available for country-level indicators (World Bank & IMF).")
    else:
        latest_map_date = map_df['date'].max()
        latest_map_df = map_df[map_df['date'] == latest_map_date]
        fig_map = px.choropleth(
            latest_map_df,
            locations="iso3",
            color="value",
            hover_name="country",
            hover_data=available_hover,
            color_continuous_scale=px.colors.sequential.Viridis,
            title=f"Global Distribution: {selected_indicator} ({latest_map_date.strftime('%Y')})"
        )
        fig_map.update_geos(showcoastlines=True, coastlinecolor="LightGray", showocean=True, oceancolor="#F4F8FB")
        fig_map.update_layout(margin={"r": 0, "t": 40, "l": 0, "b": 0}, height=550)
        st.plotly_chart(fig_map, use_container_width=True)

# --- TAB 4: AUDIT TABLE & CSV EXPORT ---
with tab_data:
    st.subheader("Verified Dataset & Institutional Provenance")
    if chart_df.empty:
        st.info("Select countries in the sidebar to inspect and export rows.")
    else:
        col_cfg = {
            "date": st.column_config.DateColumn("Observation Date", format="YYYY-MM-DD"),
            "value": st.column_config.NumberColumn("Value", format="%.2f")
        }
        if "source_url" in chart_df.columns:
            col_cfg["source_url"] = st.column_config.LinkColumn("Official Source Link")

        st.dataframe(
            chart_df.sort_values(by=['date', 'country'], ascending=[False, True]),
            use_container_width=True,
            column_config=col_cfg
        )

        st.download_button(
            label="Download Verified CSV (Audit-Ready)",
            data=chart_df.to_csv(index=False),
            file_name="verified_global_rwanda_econ_data.csv",
            mime="text/csv"
        )
