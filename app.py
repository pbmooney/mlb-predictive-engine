import streamlit as st
import pandas as pd
import pybaseball as pyb
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
from datetime import datetime, timedelta

# --- DATA FETCHING FUNCTIONS ---
@st.cache_data
def get_player_id(first, last):
    try:
        if not first or not last:
            return None
        df = pyb.playerid_lookup(last, first)
        if not df.empty:
            return int(df['key_mlbam'].values[0])
    except Exception:
        pass
    return None

@st.cache_data
def get_statcast_data(player_id, days, player_type):
    end_dt = datetime.today().strftime('%Y-%m-%d')
    start_dt = (datetime.today() - timedelta(days=days)).strftime('%Y-%m-%d')
    
    if player_type == "Batter":
        return pyb.statcast_batter(start_dt=start_dt, end_dt=end_dt, player_id=player_id)
    else:
        return pyb.statcast_pitcher(start_dt=start_dt, end_dt=end_dt, player_id=player_id)

# --- SIDEBAR UI ---
st.sidebar.header("Search Primary Player")
player_type = st.sidebar.radio("Player Type", ["Batter", "Pitcher"])

first_name = st.sidebar.text_input("First Name", "Aaron")
last_name = st.sidebar.text_input("Last Name", "Judge")
days_back = st.sidebar.slider("Days of History", 15, 1000, 365) 

st.sidebar.markdown("---")
st.sidebar.subheader("Specific Matchup (Optional)")
st.sidebar.caption(f"Filter by a specific opposing {'Pitcher' if player_type == 'Batter' else 'Batter'}.")
opp_first = st.sidebar.text_input("Opponent First Name", "")
opp_last = st.sidebar.text_input("Opponent Last Name", "")

st.sidebar.markdown("---")
st.sidebar.subheader("Situational Splits")

if player_type == "Batter":
    opp_hand = st.sidebar.radio("Opposing Pitcher Hand", ["All", "RHP", "LHP"])
else:
    opp_hand = st.sidebar.radio("Opposing Batter Hand", ["All", "RHB", "LHB"])
    
location = st.sidebar.radio("Location", ["All", "Home", "Away"])

# --- SIDEBAR: DAILY EDGE REPORT ---
st.sidebar.markdown("---")
st.sidebar.subheader("📋 Daily Edge Report")

# Initialize the "shopping cart" memory
if 'edge_report' not in st.session_state:
    st.session_state.edge_report = []

if len(st.session_state.edge_report) > 0:
    st.sidebar.write(f"**{len(st.session_state.edge_report)}** +EV spots saved.")
    
    # Convert saved bets to a DataFrame and encode as CSV
    report_df = pd.DataFrame(st.session_state.edge_report)
    csv = report_df.to_csv(index=False).encode('utf-8')
    
    st.sidebar.download_button(
        label="📥 Download CSV Report",
        data=csv,
        file_name=f"Edge_Report_{datetime.today().strftime('%Y%m%d')}.csv",
        mime="text/csv"
    )
    
    if st.sidebar.button("Clear Report"):
        st.session_state.edge_report = []
        st.rerun()
else:
    st.sidebar.caption("No +EV spots saved yet. Run the calculator to find edges!")

# --- MAIN APP LOGIC ---
st.title("MLB Props Dashboard")

# [NEW] Give the app a memory to remember the button click
if "run_query" not in st.session_state:
    st.session_state.run_query = False

if st.sidebar.button("Get Stats"):
    st.session_state.run_query = True

# [NEW] Create App Tabs
tab1, tab2, tab3, tab4 = st.tabs(["Player Dashboard", "Team Matchups", "Matchup Simulator Hub", "📖 Betting Playbook"])

# ==========================================
# TAB 1: PLAYER DASHBOARD
# ==========================================
with tab1:
    if st.session_state.run_query:
        player_id = get_player_id(first_name, last_name)
        
        if player_id:
            with st.spinner("Fetching data from Baseball Savant..."):
                data = get_statcast_data(player_id, days_back, player_type)
            
            if not data.empty:
                if opp_first and opp_last:
                    opp_id = get_player_id(opp_first, opp_last)
                    if opp_id:
                        if player_type == "Batter":
                            data = data[data['pitcher'] == opp_id]
                        else:
                            data = data[data['batter'] == opp_id]
                            
                        if data.empty:
                            st.warning(f"No matchups found between {first_name} {last_name} and {opp_first} {opp_last} in the last {days_back} days.")
                            st.stop()
                    else:
                        st.warning("Opposing player not found. Double check the spelling. Showing all data instead.")

                if player_type == "Batter":
                    if opp_hand == "RHP":
                        data = data[data['p_throws'] == 'R']
                    elif opp_hand == "LHP":
                        data = data[data['p_throws'] == 'L']
                else:
                    if opp_hand == "RHB":
                        data = data[data['stand'] == 'R']
                    elif opp_hand == "LHB":
                        data = data[data['stand'] == 'L']
                    
                if location == "Home":
                    data = data[data['inning_topbot'] == 'Bot']
                elif location == "Away":
                    data = data[data['inning_topbot'] == 'Top']
                
                if not data.empty:
                    st.success(f"Successfully pulled {len(data)} pitches for {first_name} {last_name}!")
                    
                    # --- ROLLING PROP HIT RATES ---
                    st.markdown("---")
                    st.subheader("Rolling Prop Hit Rates (L5 / L10 / L20)")
                    
                    events_df = data.dropna(subset=['events']).copy()
                    
                    if not events_df.empty:
                        st.caption("Adjust the targets below to match current sportsbook lines.")
                        
                        if player_type == "Batter":
                            events_df['TB'] = events_df['events'].map({'single': 1, 'double': 2, 'triple': 3, 'home_run': 4}).fillna(0)
                            events_df['Hit'] = events_df['events'].isin(['single', 'double', 'triple', 'home_run']).astype(int)
                            events_df['HR'] = (events_df['events'] == 'home_run').astype(int)
                            
                            game_logs = events_df.groupby('game_date').agg(
                                TB=('TB', 'sum'),
                                Hits=('Hit', 'sum'),
                                HRs=('HR', 'sum')
                            ).reset_index().sort_values('game_date', ascending=False)
                            
                            col_h, col_tb, col_hr = st.columns(3)
                            t_hits = col_h.number_input("Hits", min_value=1, max_value=5, value=1)
                            t_tb = col_tb.number_input("Total Bases", min_value=1, max_value=10, value=2)
                            t_hr = col_hr.number_input("Home Runs", min_value=1, max_value=4, value=1)
                            
                            props = [
                                {"Prop": f"{t_hits}+ Hits", "Column": "Hits", "Target": t_hits},
                                {"Prop": f"{t_tb}+ Total Bases", "Column": "TB", "Target": t_tb},
                                {"Prop": f"{t_hr}+ Home Runs", "Column": "HRs", "Target": t_hr}
                            ]
                        else:
                            events_df['K'] = (events_df['events'] == 'strikeout').astype(int)
                            game_logs = events_df.groupby('game_date').agg(
                                Strikeouts=('K', 'sum')
                            ).reset_index().sort_values('game_date', ascending=False)
                            
                            col_k1, col_k2 = st.columns(2)
                            t_k1 = col_k1.number_input("Main Strikeout Line", min_value=1, max_value=20, value=5)
                            t_k2 = col_k2.number_input("Alt Strikeout Line", min_value=1, max_value=20, value=7)
                            
                            props = [
                                {"Prop": f"{t_k1}+ Strikeouts", "Column": "Strikeouts", "Target": t_k1},
                                {"Prop": f"{t_k2}+ Strikeouts", "Column": "Strikeouts", "Target": t_k2},
                            ]
                            
                        if not game_logs.empty:
                            rates_data = []
                            for p in props:
                                col = p["Column"]
                                target = p["Target"]
                                l5 = f"{(game_logs.head(5)[col] >= target).mean() * 100:.0f}%" if len(game_logs) >= 5 else "N/A (<5 G)"
                                l10 = f"{(game_logs.head(10)[col] >= target).mean() * 100:.0f}%" if len(game_logs) >= 10 else "N/A (<10 G)"
                                l20 = f"{(game_logs.head(20)[col] >= target).mean() * 100:.0f}%" if len(game_logs) >= 20 else "N/A (<20 G)"
                                rates_data.append({"Prop": p["Prop"], "L5": l5, "L10": l10, "L20": l20})
                                
# Helper functions for betting math
                            def prob_to_american(p):
                                if p <= 0: return "N/A"
                                if p >= 1: return "-∞"
                                if p >= 0.5:
                                    return f"-{int(round((p / (1 - p)) * 100))}"
                                else:
                                    return f"+{int(round(((1 - p) / p) * 100))}"

                            def american_to_prob(odds):
                                try:
                                    odds = float(odds)
                                    if odds < 0:
                                        return abs(odds) / (abs(odds) + 100.0)
                                    else:
                                        return 100.0 / (odds + 100.0)
                                except Exception:
                                    return None

                            rates_data = []
                            for p in props:
                                col = p["Column"]
                                target = p["Target"]
                                
                                p5 = (game_logs.head(5)[col] >= target).mean() if len(game_logs) >= 5 else None
                                p10 = (game_logs.head(10)[col] >= target).mean() if len(game_logs) >= 10 else None
                                p20 = (game_logs.head(20)[col] >= target).mean() if len(game_logs) >= 20 else None
                                
                                l5_str = f"{p5 * 100:.0f}% ({prob_to_american(p5)})" if p5 is not None else "N/A (<5 G)"
                                l10_str = f"{p10 * 100:.0f}% ({prob_to_american(p10)})" if p10 is not None else "N/A (<10 G)"
                                l20_str = f"{p20 * 100:.0f}% ({prob_to_american(p20)})" if p20 is not None else "N/A (<20 G)"
                                
                                rates_data.append({
                                    "Prop": p["Prop"], 
                                    "L5 (Fair Odds)": l5_str, 
                                    "L10 (Fair Odds)": l10_str, 
                                    "L20 (Fair Odds)": l20_str,
                                    "p10_raw": p10
                                })
                                
                            rates_df = pd.DataFrame(rates_data)
                            st.dataframe(rates_df[["Prop", "L5 (Fair Odds)", "L10 (Fair Odds)", "L20 (Fair Odds)"]], hide_index=True)


# --- ADVANCED HEAD-TO-HEAD ENGINE ---
                        # Only display this section if the user actually typed an opponent in the sidebar
                        if opp_first and opp_last:
                            st.markdown("---")
                            st.subheader(f"⚔️ Matchup: vs. {opp_first.title()} {opp_last.title()}")
                            
                            # The 'data' variable is already filtered by your sidebar inputs!
                            h2h_df = data.copy()
                            
                            if not h2h_df.empty:
                                # Filter to batted balls and swings
                                in_play = ['hit_into_play', 'hit_into_play_no_out', 'hit_into_play_score']
                                swings = ['swinging_strike', 'swinging_strike_blocked', 'foul', 'foul_tip', 'hit_into_play', 'hit_into_play_no_out', 'hit_into_play_score', 'missed_bunt']
                                whiffs = ['swinging_strike', 'swinging_strike_blocked', 'missed_bunt']
                                
                                h2h_bbe = h2h_df[h2h_df['description'].isin(in_play)].copy()
                                h2h_swings = h2h_df[h2h_df['description'].isin(swings)].copy()
                                
                                # Calculate Metrics
                                total_pitches = len(h2h_df)
                                avg_ev = h2h_bbe['launch_speed'].mean() if not h2h_bbe.empty else 0
                                hard_hits = (h2h_bbe['launch_speed'] >= 95).sum() if not h2h_bbe.empty else 0
                                bbe_count = len(h2h_bbe)
                                hard_hit_pct = (hard_hits / bbe_count * 100) if bbe_count > 0 else 0
                                
                                whiff_count = h2h_swings['description'].isin(whiffs).sum()
                                swing_count = len(h2h_swings)
                                whiff_pct = (whiff_count / swing_count * 100) if swing_count > 0 else 0

                                
# --- TRADITIONAL BvP STATS ---
                                at_bats = h2h_df.dropna(subset=['events']).copy()
                                if not at_bats.empty:
                                    hits = at_bats['events'].isin(['single', 'double', 'triple', 'home_run']).sum()
                                    hrs = (at_bats['events'] == 'home_run').sum()
                                    ks = at_bats['events'].isin(['strikeout', 'strikeout_double_play']).sum()
                                    official_abs = (~at_bats['events'].isin(['walk', 'hit_by_pitch', 'sac_fly', 'sac_bunt'])).sum()
                                    
                                    ba = (hits / official_abs) if official_abs > 0 else 0.0
                                    
                                    st.markdown("##### 📜 Historical Box Score")
                                    t1, t2, t3, t4 = st.columns(4)
                                    t1.metric("Hits / ABs", f"{hits} / {official_abs}")
                                    t2.metric("Batting Avg", f".{int(ba * 1000):03d}")
                                    t3.metric("Home Runs", f"{hrs}")
                                    t4.metric("Strikeouts", f"{ks}")
                                    st.markdown("<br>", unsafe_allow_html=True)
                                
                                # Render the UI
                                st.markdown("##### 🔬 Underlying Physics")
                                st.caption(f"**Sample Size:** {total_pitches} total pitches seen in this specific matchup.")
                                
                                h1, h2, h3 = st.columns(3)
                                h1.metric("H2H Avg Exit Velo", f"{avg_ev:.1f} mph" if avg_ev > 0 else "N/A")
                                h2.metric("H2H Hard Hit %", f"{hard_hit_pct:.1f}%" if bbe_count > 0 else "N/A")
                                h3.metric("H2H Whiff %", f"{whiff_pct:.1f}%" if swing_count > 0 else "N/A")
                                
                                # Insight Generator
                                if bbe_count >= 3:
                                    if hard_hit_pct >= 50.0 and whiff_pct <= 25.0:
                                        st.success(f"🔥 **Elite Matchup:** The batter sees the ball incredibly well in this matchup, making frequent, high-quality contact.")
                                    elif hard_hit_pct < 30.0 and whiff_pct >= 35.0:
                                        st.error(f"⚠️ **Bad Matchup:** The batter struggles heavily in this matchup (high swing & miss, weak contact).")
                            else:
                                st.info("No matchup data found in this timeframe.")
                            
                            # --- +EV EDGE CALCULATOR ---
                            st.markdown("##### 💰 Bookmaker Edge & +EV Calculator")
                            st.caption("Compare your modeled win probability against the sportsbook line to find mathematical edge.")
                            
                            ev_col1, ev_col2, ev_col3 = st.columns([2, 1, 1])
                            
                            prop_options = [p["Prop"] for p in props]
                            selected_prop = ev_col1.selectbox("Select Target Prop", prop_options)
                            sample_window = ev_col2.selectbox("Model Baseline", ["L10", "L5", "L20"])
                            book_odds = ev_col3.number_input("Sportsbook Odds (American)", value=-110, step=5)
                            
                            # Grab selected prop's raw hit rate
                            prop_idx = prop_options.index(selected_prop)
                            target_col = props[prop_idx]["Column"]
                            target_val = props[prop_idx]["Target"]
                            
                            sample_n = 10 if sample_window == "L10" else (5 if sample_window == "L5" else 20)
                            if len(game_logs) >= sample_n:
                                my_prob = (game_logs.head(sample_n)[target_col] >= target_val).mean()
                                implied_book_prob = american_to_prob(book_odds)
                                
                                if implied_book_prob:
                                    edge = (my_prob - implied_book_prob) * 100
                                    
                                    # Expected value on a $100 bet
                                    # Decimal payout = Profit on $100
                                    profit = (100.0 / abs(book_odds) * 100.0) if book_odds < 0 else (book_odds)
                                    ev = (my_prob * profit) - ((1.0 - my_prob) * 100.0)
                                    
                                    m1, m2, m3 = st.columns(3)
                                    m1.metric("Model Implied Prob", f"{my_prob * 100:.1f}%")
                                    m2.metric("Book Implied Prob", f"{implied_book_prob * 100:.1f}%")
                                    
                                    delta_label = f"{edge:+.1f}% Edge"
                                    m3.metric("Expected Value (per $100)", f"${ev:+.2f}", delta=delta_label)
                                    
                                    if ev > 0:
                                        st.success(f"🔥 **+EV Spot Identified:** You have a **{edge:.1f}%** edge over the book line ({book_odds:+d}).")
                                    else:
                                        st.error(f"⚠️ **-EV Spot:** The book line ({book_odds:+d}) requires a {implied_book_prob*100:.1f}% win rate, but the current baseline is {my_prob*100:.1f}%.")
                                        
                                    # Add to Report Button
                                    if st.button("➕ Save to Daily Edge Report"):
                                        st.session_state.edge_report.append({
                                            "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                            "Player": f"{first_name} {last_name}",
                                            "Prop": selected_prop,
                                            "Baseline": sample_window,
                                            "Model Prob": f"{my_prob * 100:.1f}%",
                                            "Book Odds": book_odds,
                                            "Edge %": f"{edge:+.1f}%",
                                            "EV ($100)": f"${ev:+.2f}"
                                        })
                                        st.rerun()
                            else:
                                st.info(f"Need at least {sample_n} games of sample data to run EV calculation.")
                            
                            with st.expander("View Recent Game Logs"):
                                st.dataframe(game_logs.head(20), hide_index=True)
                        else:
                            st.info("No game logs generated.")
                    else:
                        st.info("Not enough event data to calculate rolling prop rates.")
                    
                    # --- QUALITY OF CONTACT ---
                    if player_type == "Batter":
                        st.markdown("---")
                        st.subheader("Quality of Contact (Batted Balls)")
                        
                        in_play = ['hit_into_play', 'hit_into_play_no_out', 'hit_into_play_score']
                        bbe_df = data[data['description'].isin(in_play)].dropna(subset=['launch_speed', 'launch_angle']).copy()
                        
                        if not bbe_df.empty:
                            total_bbe = len(bbe_df)
                            bbe_df['Hard_Hit'] = (bbe_df['launch_speed'] >= 95).astype(int)
                            
                            bbe_df['Barrel'] = ((bbe_df['launch_speed'] >= 98) & 
                                                (bbe_df['launch_angle'] >= 26) & 
                                                (bbe_df['launch_angle'] <= 30)).astype(int)
                            
                            c1, c2, c3, c4 = st.columns(4)
                            c1.metric("Avg Exit Velo", f"{bbe_df['launch_speed'].mean():.1f} mph")
                            c2.metric("Max Exit Velo", f"{bbe_df['launch_speed'].max():.1f} mph")
                            c3.metric("Hard Hit %", f"{(bbe_df['Hard_Hit'].sum() / total_bbe) * 100:.1f}%")
                            c4.metric("Barrel %", f"{(bbe_df['Barrel'].sum() / total_bbe) * 100:.1f}%")
                        else:
                            st.info("Not enough batted ball data to calculate Quality of Contact.")
# --- EXPECTED VS ACTUAL REGRESSION ---
                    if player_type == "Batter":
                        st.markdown("---")
                        st.subheader("Luck Regression (Expected vs Actual)")
                        st.caption("Identifies 'Buy Low' or 'Sell High' candidates by comparing actual results to Statcast's expected metrics (based on exit velocity and launch angle).")
                        
                        # Filter to true At-Bats (excludes walks, HBP, etc.)
                        ab_events = ['single', 'double', 'triple', 'home_run', 'field_out', 'grounded_into_dp', 
                                     'force_out', 'fielders_choice', 'field_error', 'strikeout', 'strikeout_double_play']
                        
                        ab_df = data[data['events'].isin(ab_events)].copy()
                        
                        if not ab_df.empty:
                            # 1. Calculate Actuals
                            ab_df['Hit'] = ab_df['events'].isin(['single', 'double', 'triple', 'home_run']).astype(int)
                            ab_df['TB'] = ab_df['events'].map({'single': 1, 'double': 2, 'triple': 3, 'home_run': 4}).fillna(0)
                            
                            actual_ba = ab_df['Hit'].mean()
                            actual_slg = ab_df['TB'].mean()
                            
                            # 2. Calculate Expected (Fill Strikeouts and non-contact outs with 0 expected stats)
                            ab_df['xBA'] = ab_df['estimated_ba_using_speedangle'].fillna(0)
                            ab_df['xSLG'] = ab_df['estimated_slg_using_speedangle'].fillna(0)
                            
                            xba = ab_df['xBA'].mean()
                            xslg = ab_df['xSLG'].mean()
                            
                            ba_diff = xba - actual_ba
                            slg_diff = xslg - actual_slg
                            
                            # 3. Render the UI
                            r1, r2, r3, r4 = st.columns(4)
                            
                            r1.metric("Actual BA", f".{str(actual_ba).split('.')[1][:3].ljust(3, '0')}" if actual_ba > 0 else ".000")
                            r2.metric("Expected BA (xBA)", f".{str(xba).split('.')[1][:3].ljust(3, '0')}" if xba > 0 else ".000", delta=f"{ba_diff:+.3f} Diff")
                            
                            r3.metric("Actual SLG", f".{str(actual_slg).split('.')[1][:3].ljust(3, '0')}" if actual_slg > 0 else ".000")
                            r4.metric("Expected SLG (xSLG)", f".{str(xslg).split('.')[1][:3].ljust(3, '0')}" if xslg > 0 else ".000", delta=f"{slg_diff:+.3f} Diff")
                            
                            # 4. Trigger Automatic Alerts
                            if ba_diff > 0.040:
                                st.success(f"📈 **Buy Low Alert:** Hitter is batting **.{str(actual_ba).split('.')[1][:3]}** but making contact well enough to bat **.{str(xba).split('.')[1][:3]}**. Massive positive regression candidate for Hits/Total Bases props.")
                            elif ba_diff < -0.040:
                                st.error(f"📉 **Sell High Alert:** Hitter is batting **.{str(actual_ba).split('.')[1][:3]}** but contact quality implies they should be batting **.{str(xba).split('.')[1][:3]}**. Negative regression candidate (fade Hits props).")
                            else:
                                st.info("⚖️ **Balanced Profile:** The hitter's actual outcomes are closely matching their underlying contact quality metrics.")
                        else:
                            st.info("Not enough At-Bats to calculate regression metrics.")
# --- BALLPARK & ALTITUDE FACTORS (ENTERPRISE) ---
                    if player_type == "Batter":
                        st.markdown("---")
                        st.subheader("🏟️ Enterprise Park Factors (Handedness Splits)")
                        st.caption("Adjusts expected metrics based on stadium dimensions, altitude, and the batter's specific handedness.")
                        
                        # Determine Batter Handedness directly from their Statcast profile
                        if 'stand' in data.columns and not data['stand'].empty:
                            b_hand = data['stand'].mode()[0]
                            hand_label = "Left-Handed" if b_hand == 'L' else "Right-Handed"
                        else:
                            b_hand = 'R' # Default fallback
                            hand_label = "Right-Handed (Default)"
                            
                        # Advanced Matrix: { Venue: { 'L': { 'Hit': X, 'HR': Y }, 'R': { 'Hit': X, 'HR': Y } } }
                        park_factors_adv = {
                            "Average / Neutral Park": {'L': {'Hit': 100, 'HR': 100}, 'R': {'Hit': 100, 'HR': 100}},
                            "Coors Field (COL)": {'L': {'Hit': 113, 'HR': 105}, 'R': {'Hit': 113, 'HR': 110}},
                            "Great American Ball Park (CIN)": {'L': {'Hit': 104, 'HR': 136}, 'R': {'Hit': 100, 'HR': 121}},
                            "Fenway Park (BOS)": {'L': {'Hit': 107, 'HR': 85}, 'R': {'Hit': 108, 'HR': 95}}, 
                            "Yankee Stadium (NYY)": {'L': {'Hit': 97, 'HR': 122}, 'R': {'Hit': 98, 'HR': 103}},
                            "Guaranteed Rate Field (CHW)": {'L': {'Hit': 100, 'HR': 117}, 'R': {'Hit': 101, 'HR': 113}},
                            "Citizens Bank Park (PHI)": {'L': {'Hit': 102, 'HR': 112}, 'R': {'Hit': 100, 'HR': 111}},
                            "Dodger Stadium (LAD)": {'L': {'Hit': 100, 'HR': 112}, 'R': {'Hit': 98, 'HR': 115}},
                            "Globe Life Field (TEX)": {'L': {'Hit': 102, 'HR': 107}, 'R': {'Hit': 101, 'HR': 105}},
                            "Kauffman Stadium (KC)": {'L': {'Hit': 105, 'HR': 83}, 'R': {'Hit': 103, 'HR': 82}},
                            "Truist Park (ATL)": {'L': {'Hit': 101, 'HR': 104}, 'R': {'Hit': 100, 'HR': 106}},
                            "Rogers Centre (TOR)": {'L': {'Hit': 99, 'HR': 103}, 'R': {'Hit': 100, 'HR': 106}},
                            "Minute Maid Park (HOU)": {'L': {'Hit': 97, 'HR': 110}, 'R': {'Hit': 98, 'HR': 101}},
                            "Target Field (MIN)": {'L': {'Hit': 101, 'HR': 95}, 'R': {'Hit': 100, 'HR': 99}},
                            "Wrigley Field (CHC)": {'L': {'Hit': 99, 'HR': 101}, 'R': {'Hit': 100, 'HR': 99}},
                            "Nationals Park (WSH)": {'L': {'Hit': 100, 'HR': 101}, 'R': {'Hit': 98, 'HR': 103}},
                            "Angel Stadium (LAA)": {'L': {'Hit': 98, 'HR': 109}, 'R': {'Hit': 97, 'HR': 100}},
                            "Chase Field (ARI)": {'L': {'Hit': 100, 'HR': 92}, 'R': {'Hit': 99, 'HR': 93}},
                            "PNC Park (PIT)": {'L': {'Hit': 97, 'HR': 82}, 'R': {'Hit': 100, 'HR': 89}},
                            "Camden Yards (BAL)": {'L': {'Hit': 100, 'HR': 101}, 'R': {'Hit': 98, 'HR': 80}}, 
                            "loanDepot park (MIA)": {'L': {'Hit': 99, 'HR': 86}, 'R': {'Hit': 98, 'HR': 90}},
                            "Comerica Park (DET)": {'L': {'Hit': 100, 'HR': 90}, 'R': {'Hit': 99, 'HR': 86}},
                            "Tropicana Field (TB)": {'L': {'Hit': 97, 'HR': 94}, 'R': {'Hit': 96, 'HR': 95}},
                            "Busch Stadium (STL)": {'L': {'Hit': 97, 'HR': 88}, 'R': {'Hit': 98, 'HR': 90}},
                            "Progressive Field (CLE)": {'L': {'Hit': 101, 'HR': 93}, 'R': {'Hit': 98, 'HR': 95}},
                            "American Family Field (MIL)": {'L': {'Hit': 97, 'HR': 107}, 'R': {'Hit': 99, 'HR': 106}},
                            "Oakland Coliseum (OAK)": {'L': {'Hit': 95, 'HR': 84}, 'R': {'Hit': 95, 'HR': 87}},
                            "T-Mobile Park (SEA)": {'L': {'Hit': 95, 'HR': 95}, 'R': {'Hit': 94, 'HR': 94}},
                            "Oracle Park (SF)": {'L': {'Hit': 96, 'HR': 84}, 'R': {'Hit': 97, 'HR': 91}},
                            "Petco Park (SD)": {'L': {'Hit': 96, 'HR': 94}, 'R': {'Hit': 94, 'HR': 92}},
                            "Citi Field (NYM)": {'L': {'Hit': 97, 'HR': 90}, 'R': {'Hit': 95, 'HR': 94}}
                        }
                        
                        st.info(f"Swing Profile Detected: **{hand_label}**")
                        park_sel = st.selectbox("Select Upcoming Venue", list(park_factors_adv.keys()))
                        
                        hit_factor = park_factors_adv[park_sel][b_hand]['Hit'] / 100.0
                        hr_factor = park_factors_adv[park_sel][b_hand]['HR'] / 100.0
                        
                        ab_events_park = ['single', 'double', 'triple', 'home_run', 'field_out', 'grounded_into_dp', 'force_out', 'fielders_choice', 'field_error', 'strikeout', 'strikeout_double_play']
                        ab_df_park = data[data['events'].isin(ab_events_park)].copy()
                        
                        if not ab_df_park.empty:
                            ab_df_park['xBA'] = ab_df_park['estimated_ba_using_speedangle'].fillna(0)
                            ab_df_park['xSLG'] = ab_df_park['estimated_slg_using_speedangle'].fillna(0)
                            
                            base_xba = ab_df_park['xBA'].mean()
                            base_xslg = ab_df_park['xSLG'].mean()
                            
                            if hit_factor != 1.0 or hr_factor != 1.0:
                                # Apply hit factor to BA, and a blended HR/Hit factor to Slugging
                                adj_xba = base_xba * hit_factor
                                adj_xslg = base_xslg * ((hit_factor * 0.4) + (hr_factor * 0.6))
                                
                                pk1, pk2 = st.columns(2)
                                pk1.metric(f"Park-Adjusted xBA ({b_hand})", f".{str(adj_xba).split('.')[1][:3].ljust(3, '0')}" if adj_xba > 0 else ".000", delta=f"{adj_xba - base_xba:+.3f} vs Neutral")
                                pk2.metric(f"Park-Adjusted xSLG ({b_hand})", f".{str(adj_xslg).split('.')[1][:3].ljust(3, '0')}" if adj_xslg > 0 else ".000", delta=f"{adj_xslg - base_xslg:+.3f} vs Neutral")
                                
                                st.caption(f"**Analytics Note:** At {park_sel}, {hand_label}s see a **{int((hit_factor-1)*100):+d}%** shift in base hits and a **{int((hr_factor-1)*100):+d}%** shift in Home Runs.")
                            else:
                                st.success("Neutral park selected. No altitude or dimension adjustments applied.")
                        else:
                            st.info("Not enough data to calculate park adjustments.")                            
                    # --- PITCH ARSENAL / DIAGNOSTICS ---
                    st.markdown("---")
                    
                    if player_type == "Batter":
                        st.subheader("Performance by Pitch Type (Seen)")
                        at_bats = data.dropna(subset=['events']).copy()
                        
                        if not at_bats.empty:
                            hit_types = ['single', 'double', 'triple', 'home_run']
                            at_bats['Hit'] = at_bats['events'].isin(hit_types)
                            at_bats['Home_Run'] = at_bats['events'] == 'home_run'
                            
                            matchup_table = at_bats.groupby('pitch_name').agg(
                                Total_Seen=('events', 'count'),
                                Hits=('Hit', 'sum'),
                                Home_Runs=('Home_Run', 'sum')
                            ).reset_index().sort_values(by='Total_Seen', ascending=False)
                            
                            matchup_table = matchup_table.rename(columns={
                                'pitch_name': 'Pitch Type', 
                                'Total_Seen': 'Plate Appearances (Ending Pitch)'
                            })
                            
                            st.dataframe(matchup_table, hide_index=True)
                        else:
                            st.info("Not enough data to calculate pitch matchups.")
                    else:
                        st.subheader("Advanced Pitcher Diagnostics")
                        st.caption("Whiff% (Swings & Misses / Total Swings) | CSW% (Called Strikes + Whiffs / Total Pitches)")
                        
                        pitch_df = data.dropna(subset=['pitch_name', 'description']).copy()
                        
                        if not pitch_df.empty:
                            swings = ['swinging_strike', 'swinging_strike_blocked', 'foul', 'foul_tip', 'hit_into_play', 'hit_into_play_no_out', 'hit_into_play_score']
                            whiffs = ['swinging_strike', 'swinging_strike_blocked', 'missed_bunt']
                            called_strikes = ['called_strike']
                            
                            pitch_df['is_swing'] = pitch_df['description'].isin(swings).astype(int)
                            pitch_df['is_whiff'] = pitch_df['description'].isin(whiffs).astype(int)
                            pitch_df['is_csw'] = pitch_df['description'].isin(whiffs + called_strikes).astype(int)
                            
                            diag_table = pitch_df.groupby('pitch_name').agg(
                                Total_Pitches=('pitch_name', 'count'),
                                Swings=('is_swing', 'sum'),
                                Whiffs=('is_whiff', 'sum'),
                                CSW=('is_csw', 'sum')
                            ).reset_index()
                            
                            diag_table['Whiff%'] = (diag_table['Whiffs'] / diag_table['Swings']).replace([np.inf, -np.inf], np.nan).fillna(0) * 100
                            diag_table['CSW%'] = (diag_table['CSW'] / diag_table['Total_Pitches']).replace([np.inf, -np.inf], np.nan).fillna(0) * 100
                            
                            diag_table = diag_table.sort_values(by='Total_Pitches', ascending=False)
                            
                            diag_table['Whiff%'] = diag_table['Whiff%'].map("{:.1f}%".format)
                            diag_table['CSW%'] = diag_table['CSW%'].map("{:.1f}%".format)
                            
                            st.dataframe(diag_table[['pitch_name', 'Total_Pitches', 'Whiff%', 'CSW%']].rename(columns={'pitch_name': 'Pitch Type'}), hide_index=True)
                        else:
                            st.info("Not enough data to calculate pitch diagnostics.")
# --- INNING SPLITS & TTO (FATIGUE) ---
                        st.markdown("---")
                        st.subheader("Fatigue & Inning Splits (NRFI / Pitch Outs)")
                        
                        # Calculate PA Index and Times Through Order (TTO)
                        pitch_data = data.copy()
                        pitch_data['pa_idx'] = pitch_data.groupby('game_date')['at_bat_number'].transform(lambda x: x.rank(method='dense'))
                        pitch_data['tto_raw'] = np.ceil(pitch_data['pa_idx'] / 9.0)
                        pitch_data['TTO'] = pitch_data['tto_raw'].map({1.0: "1st Time", 2.0: "2nd Time", 3.0: "3rd+ Time"}).fillna("3rd+ Time")
                        
                        # Filter to just the pitches that end an At-Bat to calculate actual outcomes
                        pa_events = ['strikeout', 'walk', 'single', 'double', 'triple', 'home_run', 'field_out', 'grounded_into_dp', 'force_out', 'fielders_choice', 'field_error', 'hit_by_pitch']
                        pa_df = pitch_data[pitch_data['events'].isin(pa_events)].copy()
                        
                        if not pa_df.empty:
                            pa_df['is_k'] = (pa_df['events'] == 'strikeout').astype(int)
                            pa_df['is_on_base'] = pa_df['events'].isin(['single', 'double', 'triple', 'home_run', 'walk', 'hit_by_pitch']).astype(int)
                            
                            i1, i2 = st.columns(2)
                            
                            with i1:
                                st.markdown("**1st Inning (NRFI Engine)**")
                                inn1 = pa_df[pa_df['inning'] == 1]
                                if not inn1.empty:
                                    k_rate_1 = inn1['is_k'].mean() * 100
                                    obp_1 = inn1['is_on_base'].mean() * 100
                                    st.metric("1st Inning K%", f"{k_rate_1:.1f}%")
                                    st.metric("1st Inning OBP", f".{str(obp_1/100).split('.')[1][:3].ljust(3, '0')}" if obp_1 > 0 else ".000")
                                    
                                    if obp_1 <= 28.0 and k_rate_1 >= 25.0:
                                        st.success("🔥 **Elite NRFI Target:** High strikeout rate and elite baserunner suppression in the 1st inning.")
                                    elif obp_1 >= 35.0:
                                        st.error("⚠️ **YRFI Danger:** Struggles heavily with baserunners out of the gate.")
                                else:
                                    st.info("No 1st Inning data available.")
                                    
                            with i2:
                                st.markdown("**Times Through Order (Decay)**")
                                tto_stats = pa_df.groupby('TTO').agg(
                                    Batters_Faced=('events', 'count'),
                                    K_Rate=('is_k', 'mean'),
                                    OBP=('is_on_base', 'mean')
                                ).reset_index()
                                
                                # Format the output
                                tto_stats['K_Rate'] = (tto_stats['K_Rate'] * 100).map("{:.1f}%".format)
                                tto_stats['OBP'] = tto_stats['OBP'].apply(lambda x: f".{str(x).split('.')[1][:3].ljust(3, '0')}" if x > 0 else ".000")
                                
                                # Sort logically
                                tto_stats['sort_col'] = tto_stats['TTO'].map({"1st Time": 1, "2nd Time": 2, "3rd+ Time": 3})
                                tto_stats = tto_stats.sort_values('sort_col').drop(columns=['sort_col'])
                                
                                st.dataframe(tto_stats, hide_index=True, use_container_width=True)
                        else:
                            st.info("Not enough At-Bat data to calculate Inning Splits.")
                        
                    # --- ADVANCED VISUALS ---
                    st.markdown("---")
                    st.subheader("Advanced Visuals")
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        fig, ax = plt.subplots(figsize=(6, 6))
                        
                        # Draw the Strike Zone
                        sz_top = data['sz_top'].mean() if not data['sz_top'].isna().all() else 3.5
                        sz_bot = data['sz_bot'].mean() if not data['sz_bot'].isna().all() else 1.5
                        rect = plt.Rectangle((-0.71, sz_bot), 1.42, sz_top - sz_bot, fill=False, color='black', linewidth=2, zorder=10)
                        ax.add_patch(rect)
                        
                        # Dynamic Heatmap Logic
                        if player_type == "Batter":
                            st.markdown("**Hot Zones (Exit Velo > 90mph)**")
                            heat_data = data[(data['launch_speed'] >= 90)].dropna(subset=['plate_x', 'plate_z'])
                            cmap_color = "Reds"
                        else:
                            st.markdown("**Cold Zones (Whiffs)**")
                            whiffs = ['swinging_strike', 'swinging_strike_blocked', 'missed_bunt']
                            heat_data = data[data['description'].isin(whiffs)].dropna(subset=['plate_x', 'plate_z'])
                            cmap_color = "Blues"

                        # Generate the glowing KDE plot
                        if not heat_data.empty:
                            sns.kdeplot(
                                data=heat_data, x='plate_x', y='plate_z', 
                                fill=True, cmap=cmap_color, alpha=0.8, 
                                levels=15, thresh=0.05, ax=ax
                            )
                        else:
                            st.info("Not enough data to generate a heatmap.")
                        
                        ax.set_xlim(-3, 3)
                        ax.set_ylim(0, 5)
                        ax.set_xlabel("Horizontal Location (ft)")
                        ax.set_ylabel("Vertical Location (ft)")
                        st.pyplot(fig)
                        
                    with col2:
                        if player_type == "Batter":
                            st.markdown("**Batted Ball Spray Chart**")
                            hits_df = data.dropna(subset=['hc_x', 'hc_y', 'events']).copy()
                            
                            if not hits_df.empty:
                                hits_df['x_feet'] = 2.5 * (hits_df['hc_x'] - 125.42)
                                hits_df['y_feet'] = 2.5 * (198.27 - hits_df['hc_y'])
                                
                                fig2, ax2 = plt.subplots(figsize=(6, 6))
                                
                                bases_x = [0, 63.6, 0, -63.6, 0]
                                bases_y = [0, 63.6, 127.3, 63.6, 0]
                                ax2.plot(bases_x, bases_y, color='gray', linestyle='--')
                                
                                theta = np.linspace(-np.pi/4, np.pi/4, 100)
                                r = 350 
                                ax2.plot(r*np.sin(theta), r*np.cos(theta), color='gray')
                                
                                sns.scatterplot(data=hits_df, x='x_feet', y='y_feet', hue='events', ax=ax2, alpha=0.8, palette="Set1")
                                
                                ax2.set_xlim(-250, 250)
                                ax2.set_ylim(-50, 450)
                                ax2.set_xlabel("Feet (L/R)")
                                ax2.set_ylabel("Feet (Distance)")
                                ax2.legend(bbox_to_anchor=(0.5, -0.15), loc='upper center', ncol=2, fontsize='small')
                                st.pyplot(fig2)
                            else:
                                st.info("No batted ball data found for this timeframe.")
                        else:
                            st.markdown("**Pitch Velocity Over Time**")
                            fig2, ax2 = plt.subplots(figsize=(6, 6))
                            
                            vel_df = data.dropna(subset=['release_speed', 'pitch_name'])
                            if not vel_df.empty:
                                sns.lineplot(data=vel_df, x='game_date', y='release_speed', hue='pitch_name', ax=ax2, marker='o')
                                ax2.set_xlabel("Game Date")
                                ax2.set_ylabel("Velocity (mph)")
                                plt.xticks(rotation=45)
                                ax2.legend(bbox_to_anchor=(0.5, -0.15), loc='upper center', ncol=2, fontsize='small')
                                st.pyplot(fig2)
                            else:
                                st.info("No velocity data available.")
                else:
                    st.warning("No Statcast data found after applying your situational splits.")
            else:
                st.warning("No Statcast data found for this timeframe.")
        else:
            st.error("Player not found. Check the spelling!")

# ==========================================
# TAB 2: LIVE TEAM VULNERABILITY BOARD
# ==========================================
with tab2:
    st.subheader("🎯 Team Target Finder (Statcast Engine)")
    st.write("Pull live, trailing offensive splits directly from raw MLB Statcast data to identify pitching targets.")
    
    # --- UI CONTROLS ---
    t_col1, t_col2 = st.columns(2)
    timeframe = t_col1.radio("Select Timeframe", ["Last 7 Days", "Last 14 Days", "Last 21 Days", "Last 30 Days"])
    split = t_col2.radio("Opposing Pitcher Handedness", ["Overall", "vs RHP", "vs LHP"])
    
    if st.button("Fetch Team Stats"):
        from datetime import datetime, timedelta
        import numpy as np
        import pybaseball as pyb
        
        # Extract number of days from selection
        days_back = int(timeframe.split()[1])
        start_dt = (datetime.today() - timedelta(days=days_back)).strftime('%Y-%m-%d')
        end_dt = datetime.today().strftime('%Y-%m-%d')
        
        with st.spinner(f"Downloading every MLB pitch from the last {days_back} days... (Takes ~30-60 seconds)"):
            try:
                sc_data = pyb.statcast(start_dt=start_dt, end_dt=end_dt)
                
                if not sc_data.empty:
                    # Filter by Handedness Split
                    if split == "vs RHP":
                        sc_data = sc_data[sc_data['p_throws'] == 'R'].copy()
                    elif split == "vs LHP":
                        sc_data = sc_data[sc_data['p_throws'] == 'L'].copy()
                        
                    if not sc_data.empty:
                        # Determine which team is batting based on the inning half
                        sc_data['batting_team'] = np.where(sc_data['inning_topbot'] == 'Bot', sc_data['home_team'], sc_data['away_team'])
                        
                        # Filter down to pitches that end the At-Bat
                        pa_events = ['strikeout', 'strikeout_double_play', 'walk', 'single', 'double', 'triple', 'home_run', 'field_out', 'grounded_into_dp', 'force_out', 'fielders_choice', 'field_error', 'hit_by_pitch', 'sac_fly', 'sac_bunt']
                        pa_df = sc_data[sc_data['events'].isin(pa_events)].copy()
                        
                        if not pa_df.empty:
                            # Map discrete events for Pandas math
                            pa_df['is_k'] = pa_df['events'].isin(['strikeout', 'strikeout_double_play']).astype(int)
                            pa_df['is_bb'] = (pa_df['events'] == 'walk').astype(int)
                            pa_df['is_hbp'] = (pa_df['events'] == 'hit_by_pitch').astype(int)
                            pa_df['is_sf'] = (pa_df['events'] == 'sac_fly').astype(int)
                            pa_df['is_ab'] = (~pa_df['events'].isin(['walk', 'hit_by_pitch', 'sac_fly', 'sac_bunt'])).astype(int)
                            pa_df['tb'] = pa_df['events'].map({'single': 1, 'double': 2, 'triple': 3, 'home_run': 4}).fillna(0)
                            pa_df['hit'] = pa_df['events'].isin(['single', 'double', 'triple', 'home_run']).astype(int)
                            
                            # Group by team and sum the outcomes
                            team_agg = pa_df.groupby('batting_team').agg(
                                PA=('events', 'count'),
                                AB=('is_ab', 'sum'),
                                K_Total=('is_k', 'sum'),
                                BB_Total=('is_bb', 'sum'),
                                HBP_Total=('is_hbp', 'sum'),
                                SF_Total=('is_sf', 'sum'),
                                Hits_Total=('hit', 'sum'),
                                TB_Total=('tb', 'sum')
                            ).reset_index()
                            
                            # Calculate the advanced metrics
                            team_agg['K%'] = (team_agg['K_Total'] / team_agg['PA']) * 100
                            team_agg['BB%'] = (team_agg['BB_Total'] / team_agg['PA']) * 100
                            team_agg['BA'] = team_agg['Hits_Total'] / team_agg['AB']
                            team_agg['SLG'] = team_agg['TB_Total'] / team_agg['AB']
                            team_agg['ISO'] = team_agg['SLG'] - team_agg['BA']
                            team_agg['OBP'] = (team_agg['Hits_Total'] + team_agg['BB_Total'] + team_agg['HBP_Total']) / (team_agg['AB'] + team_agg['BB_Total'] + team_agg['HBP_Total'] + team_agg['SF_Total'])
                            
                            # Format for UI
                            display_df = team_agg[['batting_team', 'PA', 'K%', 'BB%', 'ISO', 'OBP']].copy()
                            display_df = display_df.rename(columns={'batting_team': 'Team'})
                            
                            # Sort by OBP (Worst offenses at the top)
                            display_df = display_df.sort_values('OBP', ascending=True) 
                            
                            # Clean up the decimals
                            display_df['K%'] = display_df['K%'].map("{:.1f}%".format)
                            display_df['BB%'] = display_df['BB%'].map("{:.1f}%".format)
                            display_df['ISO'] = display_df['ISO'].map("{:.3f}".format)
                            display_df['OBP'] = display_df['OBP'].map("{:.3f}".format)
                            
                            st.success(f"Successfully crunched {len(sc_data):,} {split.replace('Overall', 'total')} pitches over the last {days_back} days!")
                            st.dataframe(display_df, hide_index=True, use_container_width=True)
                            
                            st.caption("Note: wRC+ is omitted for custom splits because it requires full-season league-wide context. OBP and ISO are used instead to measure current offensive vulnerability.")
                        else:
                            st.warning("No At-Bat data found for this split in this date range.")
                    else:
                        st.warning("No pitches found for this handedness split in this date range.")
            except Exception as e:
                st.error(f"Error fetching Statcast data: {e}")

# ==========================================
# TAB 3: MATCHUP SIMULATOR HUB
# ==========================================
with tab3:
    st.subheader("⚔️ Matchup Simulator Hub")
    st.write("Simulate matchups by cross-referencing pitch arsenals against specific teams or individual hitters.")
    
# Internal sub-navigation
    sim_team_tab, sim_batter_tab, sim_team_matrix_tab, edge_scanner_tab = st.tabs([
        "Pitcher vs. Team (Historical)", 
        "Pitcher vs. Batter (Arsenal Matrix)", 
        "Pitcher vs. Team (Arsenal Matrix)",
        "🚨 Edge Scanner"
    ])
    
    from datetime import datetime, timedelta
    from pybaseball import playerid_lookup, statcast_pitcher, statcast_batter
    import numpy as np

    # -------------------------------------------------------------
    # SUB-TAB 1: PITCHER VS. TEAM (HISTORICAL)
    # -------------------------------------------------------------
    with sim_team_tab:
        st.markdown("#### 🏢 Pitcher vs. Team Matchup")
        
        c1, c2, c3 = st.columns(3)
        p_first = c1.text_input("Pitcher First Name", value="Tarik", key="pvt_first").strip().lower()
        p_last = c2.text_input("Pitcher Last Name", value="Skubal", key="pvt_last").strip().lower()
        
        teams = sorted(['NYY', 'BAL', 'TBR', 'BOS', 'TOR', 'CLE', 'KCR', 'MIN', 'DET', 'CHW', 'HOU', 'SEA', 'TEX', 'OAK', 'LAA', 'PHI', 'ATL', 'NYM', 'WSN', 'MIA', 'MIL', 'STL', 'CHC', 'PIT', 'CIN', 'LAD', 'SDP', 'ARI', 'SFG', 'COL'])
        target_team = c3.selectbox("Opposing Team", teams, key="pvt_team")
        
        if st.button("Run Team Simulation", key="btn_pvt"):
            with st.spinner(f"Pulling 2-year history for {p_first.title()} {p_last.title()} vs. {target_team}..."):
                try:
                    meta = playerid_lookup(p_last, p_first)
                    if not meta.empty:
                        p_id = meta['key_mlbam'].values[0]
                        start_dt = (datetime.today() - timedelta(days=730)).strftime('%Y-%m-%d')
                        end_dt = datetime.today().strftime('%Y-%m-%d')
                        
                        p_data = statcast_pitcher(start_dt, end_dt, p_id)
                        
                        if not p_data.empty:
                            p_data['batting_team'] = np.where(p_data['inning_topbot'] == 'Bot', p_data['home_team'], p_data['away_team'])
                            matchup_data = p_data[p_data['batting_team'] == target_team].copy()
                            
                            if not matchup_data.empty:
                                at_bats = matchup_data.dropna(subset=['events']).copy()
                                
                                pa_events = ['strikeout', 'strikeout_double_play', 'walk', 'single', 'double', 'triple', 'home_run', 'field_out', 'grounded_into_dp', 'force_out', 'fielders_choice', 'field_error', 'hit_by_pitch', 'sac_fly', 'sac_bunt']
                                pa_df = matchup_data[matchup_data['events'].isin(pa_events)].copy()
                                total_pa = len(pa_df)
                                
                                hits = at_bats['events'].isin(['single', 'double', 'triple', 'home_run']).sum()
                                hrs = (at_bats['events'] == 'home_run').sum()
                                ks = at_bats['events'].isin(['strikeout', 'strikeout_double_play']).sum()
                                official_abs = (~at_bats['events'].isin(['walk', 'hit_by_pitch', 'sac_fly', 'sac_bunt'])).sum()
                                ba = (hits / official_abs) if official_abs > 0 else 0.0
                                
                                k_pct = (ks / total_pa * 100) if total_pa > 0 else 0.0
                                
                                one_out_events = ['strikeout', 'field_out', 'force_out', 'fielders_choice_out', 'sac_fly', 'sac_bunt', 'other_out', 'caught_stealing_2b', 'caught_stealing_3b', 'caught_stealing_home', 'pickoff_1b', 'pickoff_2b', 'pickoff_3b']
                                two_out_events = ['grounded_into_dp', 'strikeout_double_play', 'double_play', 'sac_fly_double_play']
                                three_out_events = ['triple_play']
                                
                                total_outs = (
                                    matchup_data['events'].isin(one_out_events).sum() +
                                    (matchup_data['events'].isin(two_out_events).sum() * 2) +
                                    (matchup_data['events'].isin(three_out_events).sum() * 3)
                                )
                                ip_full = total_outs // 3
                                ip_remainder = total_outs % 3
                                ip_formatted = f"{ip_full}.{ip_remainder}"
                                
                                st.markdown("---")
                                st.markdown(f"##### 📊 Historical Box Score: vs {target_team} (Last 2 Years)")
                                
                                row1_c1, row1_c2, row1_c3 = st.columns(3)
                                row1_c1.metric("Innings Pitched (IP)", ip_formatted)
                                row1_c2.metric("Strikeout Rate (K%)", f"{k_pct:.1f}%")
                                row1_c3.metric("Strikeouts (Total)", f"{ks}")
                                
                                row2_c1, row2_c2, row2_c3 = st.columns(3)
                                row2_c1.metric("Hits / ABs", f"{hits} / {official_abs}")
                                row2_c2.metric("Opponent BA", f".{int(ba * 1000):03d}")
                                row2_c3.metric("Home Runs Allowed", f"{hrs}")
                                
                                st.markdown("<br>", unsafe_allow_html=True)
                                st.markdown(f"##### 🔬 Pitch Arsenal Breakdown vs {target_team}")
                                
                                matchup_data['is_swing'] = matchup_data['description'].isin(['swinging_strike', 'swinging_strike_blocked', 'foul', 'foul_tip', 'hit_into_play', 'hit_into_play_no_out', 'hit_into_play_score', 'missed_bunt'])
                                matchup_data['is_whiff'] = matchup_data['description'].isin(['swinging_strike', 'swinging_strike_blocked', 'missed_bunt'])
                                matchup_data['is_hard_hit'] = matchup_data['launch_speed'] >= 95
                                
                                arsenal = matchup_data.groupby('pitch_name').agg(
                                    Pitches=('pitch_type', 'count'),
                                    Avg_Velo=('release_speed', 'mean'),
                                    Swings=('is_swing', 'sum'),
                                    Whiffs=('is_whiff', 'sum'),
                                    BBE=('launch_speed', 'count'),
                                    Hard_Hits=('is_hard_hit', 'sum')
                                ).reset_index()
                                
                                arsenal['Usage %'] = (arsenal['Pitches'] / arsenal['Pitches'].sum() * 100).map("{:.1f}%".format)
                                arsenal['Whiff %'] = (arsenal['Whiffs'] / arsenal['Swings'] * 100).fillna(0).map("{:.1f}%".format)
                                arsenal['Hard Hit %'] = (arsenal['Hard_Hits'] / arsenal['BBE'] * 100).fillna(0).map("{:.1f}%".format)
                                arsenal['Avg Velo'] = arsenal['Avg_Velo'].map("{:.1f} mph".format)
                                
                                display_arsenal = arsenal[['pitch_name', 'Usage %', 'Avg Velo', 'Pitches', 'Whiff %', 'Hard Hit %']].sort_values(by='Pitches', ascending=False)
                                display_arsenal = display_arsenal.rename(columns={'pitch_name': 'Pitch Type'})
                                
                                st.dataframe(display_arsenal, hide_index=True, use_container_width=True)
                            else:
                                st.warning(f"No matchups found against {target_team} in the last 2 years.")
                        else:
                            st.warning("No pitch data found for this pitcher.")
                    else:
                        st.error("Pitcher not found. Check spelling.")
                except Exception as e:
                    st.error(f"Error: {e}")

    # -------------------------------------------------------------
    # SUB-TAB 2: PITCHER VS. BATTER (ARSENAL MATRIX)
    # -------------------------------------------------------------
    with sim_batter_tab:
        st.markdown("#### 🎯 Pitcher Arsenal vs. Batter Vulnerability Matrix")
        
        b_col1, b_col2 = st.columns(2)
        with b_col1:
            st.caption("**Pitcher**")
            pvb_p_first = st.text_input("Pitcher First Name", value="Paul", key="pvb_p_first").strip().lower()
            pvb_p_last = st.text_input("Pitcher Last Name", value="Skenes", key="pvb_p_last").strip().lower()
        with b_col2:
            st.caption("**Batter**")
            pvb_b_first = st.text_input("Batter First Name", value="Elly", key="pvb_b_first").strip().lower()
            pvb_b_last = st.text_input("Batter Last Name", value="De La Cruz", key="pvb_b_last").strip().lower()
            
        lookback_days = st.slider("Days of Pitch History to Analyze", min_value=90, max_value=730, value=365, step=30, key="pvb_days")
        
        if st.button("Generate Arsenal Matrix", key="btn_pvb"):
            with st.spinner("Crunching pitch profiles and swing tendencies..."):
                try:
                    p_meta = playerid_lookup(pvb_p_last, pvb_p_first)
                    b_meta = playerid_lookup(pvb_b_last, pvb_b_first)
                    
                    if not p_meta.empty and not b_meta.empty:
                        p_id = p_meta['key_mlbam'].values[0]
                        b_id = b_meta['key_mlbam'].values[0]
                        
                        start_dt = (datetime.today() - timedelta(days=lookback_days)).strftime('%Y-%m-%d')
                        end_dt = datetime.today().strftime('%Y-%m-%d')
                        
                        p_pitches = statcast_pitcher(start_dt, end_dt, p_id)
                        b_pitches = statcast_batter(start_dt, end_dt, b_id)
                        
                        if not p_pitches.empty and not b_pitches.empty:
                            p_usage = p_pitches.groupby('pitch_name').agg(
                                Pitcher_Pitches=('pitch_type', 'count'),
                                Avg_Velo=('release_speed', 'mean')
                            ).reset_index()
                            p_usage['Usage %'] = (p_usage['Pitcher_Pitches'] / p_usage['Pitcher_Pitches'].sum() * 100)
                            
                            b_pitches['is_swing'] = b_pitches['description'].isin(['swinging_strike', 'swinging_strike_blocked', 'foul', 'foul_tip', 'hit_into_play', 'hit_into_play_no_out', 'hit_into_play_score', 'missed_bunt'])
                            b_pitches['is_whiff'] = b_pitches['description'].isin(['swinging_strike', 'swinging_strike_blocked', 'missed_bunt'])
                            b_pitches['is_hard_hit'] = b_pitches['launch_speed'] >= 95
                            
                            b_perf = b_pitches.groupby('pitch_name').agg(
                                Batter_Pitches_Seen=('pitch_type', 'count'),
                                Swings=('is_swing', 'sum'),
                                Whiffs=('is_whiff', 'sum'),
                                BBE=('launch_speed', 'count'),
                                Hard_Hits=('is_hard_hit', 'sum')
                            ).reset_index()
                            
                            b_perf['Batter Whiff %'] = (b_perf['Whiffs'] / b_perf['Swings'] * 100).fillna(0)
                            b_perf['Batter Hard Hit %'] = (b_perf['Hard_Hits'] / b_perf['BBE'] * 100).fillna(0)
                            
                            matrix = p_usage.merge(b_perf, on='pitch_name', how='inner')
                            
                            if not matrix.empty:
                                matrix = matrix.sort_values(by='Usage %', ascending=False)
                                
                                matrix_display = matrix[['pitch_name', 'Usage %', 'Avg_Velo', 'Batter_Pitches_Seen', 'Batter Whiff %', 'Batter Hard Hit %']].copy()
                                matrix_display = matrix_display.rename(columns={
                                    'pitch_name': 'Pitch Type',
                                    'Avg_Velo': 'Avg Velo',
                                    'Batter_Pitches_Seen': 'Pitches Seen by Batter'
                                })
                                
                                matrix_display['Usage %'] = matrix_display['Usage %'].map("{:.1f}%".format)
                                matrix_display['Avg Velo'] = matrix_display['Avg Velo'].map("{:.1f} mph".format)
                                matrix_display['Batter Whiff %'] = matrix_display['Batter Whiff %'].map("{:.1f}%".format)
                                matrix_display['Batter Hard Hit %'] = matrix_display['Batter Hard Hit %'].map("{:.1f}%".format)
                                
                                st.markdown("---")
                                st.markdown(f"##### 🔬 Arsenal Matchup Matrix: {pvb_p_first.title()} {pvb_p_last.title()} vs. {pvb_b_first.title()} {pvb_b_last.title()}")
                                st.dataframe(matrix_display, hide_index=True, use_container_width=True)
                            else:
                                st.warning("No overlapping pitch types found in the data.")
                        else:
                            st.warning("Insufficient pitch data for one or both players.")
                    else:
                        st.error("Could not find one or both players in the MLB database.")
                except Exception as e:
                    st.error(f"Error generating matrix: {e}")

# -------------------------------------------------------------
    # SUB-TAB 3: PITCHER VS. TEAM (GLOBAL ARSENAL MATRIX)
    # -------------------------------------------------------------
    with sim_team_matrix_tab:
        st.markdown("#### ⚾ Pitcher vs. Team (Arsenal Matrix)")
        st.write("Compare a pitcher's pitch mix against how a lineup performs against those specific pitch types globally.")
        
        import pybaseball as pyb
        from datetime import datetime, timedelta
        import numpy as np
        
        # Enable pybaseball's internal cache
        pyb.cache.enable()
        
        mlb_teams = [
            "ARI", "ATL", "BAL", "BOS", "CHC", "CIN", "CLE", "COL", "CWS", 
            "DET", "HOU", "KC", "LAA", "LAD", "MIA", "MIL", "MIN", "NYM", 
            "NYY", "OAK", "PHI", "PIT", "SD", "SEA", "SF", "STL", "TB", 
            "TEX", "TOR", "WSH"
        ]
        
        @st.cache_data(ttl=3600)
        def fetch_arsenal_data(days_back):
            start_date = (datetime.today() - timedelta(days=days_back)).strftime('%Y-%m-%d')
            end_date = datetime.today().strftime('%Y-%m-%d')
            return pyb.statcast(start_dt=start_date, end_dt=end_date), start_date, end_date

        col_p, col_t, col_d = st.columns(3)
        with col_p:
            matrix_pitcher_full = st.text_input("Pitcher Full Name", value="Tarik Skubal", key="matrix_p2").strip()
        with col_t:
            matrix_team = st.selectbox("Opposing Team", mlb_teams, index=mlb_teams.index("NYY") if "NYY" in mlb_teams else 0, key="matrix_t2")
        with col_d:
            lookback_days = st.slider("Lookback Window (Days)", min_value=7, max_value=45, value=30, step=1)

        if st.button("Run Arsenal Matrix", key="btn_matrix"):
            if matrix_pitcher_full:
                with st.spinner(f"Pulling {lookback_days}-day global data... (Caching for faster reloads)"):
                    try:
                        # Parse First and Last Name
                        name_parts = matrix_pitcher_full.split()
                        if len(name_parts) < 2:
                            st.error("Please enter both first and last name for the pitcher.")
                        else:
                            p_first_input, p_last_input = name_parts[0], name_parts[-1]
                            
                            # Fetch Cached Global Data
                            sc_data, s_dt, e_dt = fetch_arsenal_data(lookback_days)
                            sc_data['batting_team'] = np.where(sc_data['inning_topbot'] == 'Bot', sc_data['home_team'], sc_data['away_team'])
                            
                            # Fetch Pitcher Data
                            meta = pyb.playerid_lookup(p_last_input, p_first_input)
                            if meta.empty:
                                meta = pyb.playerid_lookup(p_last_input) # Fallback
                                
                            if meta.empty:
                                st.error(f"Pitcher not found: {matrix_pitcher_full}")
                            else:
                                p_id = meta['key_mlbam'].values[0]
                                p_first = meta['name_first'].values[0].title()
                                p_last = meta['name_last'].values[0].title()
                                
                                p_pitches = pyb.statcast_pitcher(s_dt, e_dt, p_id)
                                
                                if p_pitches.empty:
                                    st.warning("No pitch data found for this pitcher in the selected window.")
                                else:
                                    # Calculate Pitcher Usage
                                    p_usage = p_pitches.groupby('pitch_name').agg(Pitches=('pitch_type', 'count')).reset_index()
                                    p_usage['Usage %'] = (p_usage['Pitches'] / p_usage['Pitches'].sum() * 100)
                                    
                                    # Calculate Team Performance
                                    t_pitches = sc_data[sc_data['batting_team'] == matrix_team].copy()
                                    t_pitches['is_swing'] = t_pitches['description'].isin(['swinging_strike', 'swinging_strike_blocked', 'foul', 'foul_tip', 'hit_into_play', 'hit_into_play_no_out', 'hit_into_play_score', 'missed_bunt'])
                                    t_pitches['is_whiff'] = t_pitches['description'].isin(['swinging_strike', 'swinging_strike_blocked', 'missed_bunt'])
                                    t_pitches['is_hard_hit'] = t_pitches['launch_speed'] >= 95
                                    
                                    t_perf = t_pitches.groupby('pitch_name').agg(
                                        Swings=('is_swing', 'sum'),
                                        Whiffs=('is_whiff', 'sum'),
                                        BBE=('launch_speed', 'count'),
                                        Hard_Hits=('is_hard_hit', 'sum')
                                    ).reset_index()
                                    
                                    t_perf['Team Whiff %'] = (t_perf['Whiffs'] / t_perf['Swings'] * 100).fillna(0)
                                    t_perf['Team Hard Hit %'] = (t_perf['Hard_Hits'] / t_perf['BBE'] * 100).fillna(0)
                                    
                                    # Merge and Display
                                    matrix = p_usage.merge(t_perf, on='pitch_name', how='inner').sort_values(by='Usage %', ascending=False)
                                    
                                    st.success(f"Arsenal Matchup: {p_first} {p_last} vs. {matrix_team} ({lookback_days}-Day Form)")
                                    
                                    st.dataframe(
                                        matrix[['pitch_name', 'Usage %', 'Team Whiff %', 'Team Hard Hit %']].style.format({
                                            'Usage %': '{:.1f}%',
                                            'Team Whiff %': '{:.1f}%',
                                            'Team Hard Hit %': '{:.1f}%'
                                        }),
                                        width="stretch"
                                    )
                    except Exception as e:
                        st.error(f"Error loading matrix: {e}")

# -------------------------------------------------------------
    # SUB-TAB 4: AUTOMATED SLATE EDGE SCANNER
    # -------------------------------------------------------------
    with edge_scanner_tab:
        st.markdown("#### 🚨 Targeted Slate Edge Scanner")
        st.write("Input up to 3 matchups you are eyeing today. The engine will run the Playbook Decision Matrix and flag quantitative betting edges.")
        
        from datetime import datetime, timedelta
        import pybaseball as pyb
        import numpy as np
        from pybaseball import playerid_lookup, statcast_pitcher
        
        # Turn on pybaseball's internal cache
        pyb.cache.enable()
        
        # Official MLB Team Abbreviations Dropdown List
        mlb_teams = [
            "ARI", "ATL", "BAL", "BOS", "CHC", "CIN", "CLE", "COL", "CWS", 
            "DET", "HOU", "KC", "LAA", "LAD", "MIA", "MIL", "MIN", "NYM", 
            "NYY", "OAK", "PHI", "PIT", "SD", "SEA", "SF", "STL", "TB", 
            "TEX", "TOR", "WSH"
        ]
        
        @st.cache_data(ttl=3600)
        def fetch_scanner_data():
            s_dt = (datetime.today() - timedelta(days=10)).strftime('%Y-%m-%d')
            e_dt = datetime.today().strftime('%Y-%m-%d')
            return pyb.statcast(start_dt=s_dt, end_dt=e_dt), s_dt, e_dt
            
        # Slate Input UI with Full Names & Team Dropdowns
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("**Matchup 1**")
            s1_p = st.text_input("Pitcher Full Name", value="Tarik Skubal", key="s1_p").strip()
            s1_t = st.selectbox("Opponent Team", mlb_teams, index=mlb_teams.index("NYY") if "NYY" in mlb_teams else 0, key="s1_t")
        with col2:
            st.markdown("**Matchup 2**")
            s2_p = st.text_input("Pitcher Full Name", value="Paul Skenes", key="s2_p").strip()
            s2_t = st.selectbox("Opponent Team", mlb_teams, index=mlb_teams.index("CHC") if "CHC" in mlb_teams else 0, key="s2_t")
        with col3:
            st.markdown("**Matchup 3 (Optional)**")
            s3_p = st.text_input("Pitcher Full Name", value="", key="s3_p").strip()
            s3_t = st.selectbox("Opponent Team", [""] + mlb_teams, key="s3_t")
            
        if st.button("Scan Slate for Edges", key="btn_scan"):
            matchups = []
            if s1_p and s1_t: matchups.append((s1_p, s1_t))
            if s2_p and s2_t: matchups.append((s2_p, s2_t))
            if s3_p and s3_t: matchups.append((s3_p, s3_t))
            
            if not matchups:
                st.warning("Please enter at least one matchup.")
            else:
                with st.spinner("Downloading recent MLB data and running Playbook Matrix..."):
                    try:
                        sc_data, start_dt, end_dt = fetch_scanner_data()
                        sc_data['batting_team'] = np.where(sc_data['inning_topbot'] == 'Bot', sc_data['home_team'], sc_data['away_team'])
                        
                        st.markdown("---")
                        
                        for p_full, team in matchups:
                            st.markdown(f"### 🔎 Scanning: {p_full} vs. {team}")
                            
                            # Parse First and Last Name for robust ID lookup
                            name_parts = p_full.split()
                            if len(name_parts) < 2:
                                st.error(f"Please enter both first and last name for: {p_full}")
                                continue
                            p_first, p_last = name_parts[0], name_parts[-1]
                            
                            meta = playerid_lookup(p_last, p_first)
                            if meta.empty:
                                # Fallback lookup by last name only if exact first/last fails
                                meta = playerid_lookup(p_last)
                            
                            if meta.empty:
                                st.error(f"Could not find pitcher: {p_full}")
                                continue
                                
                            p_id = meta['key_mlbam'].values[0]
                            found_first = meta['name_first'].values[0]
                            found_last = meta['name_last'].values[0]
                            
                            p_pitches = statcast_pitcher(start_dt, end_dt, p_id)
                            
                            if p_pitches.empty:
                                st.warning(f"No recent data for {found_first.title()} {found_last.title()}.")
                                continue
                                
                            # Pitcher Arsenal
                            p_usage = p_pitches.groupby('pitch_name').agg(Pitches=('pitch_type', 'count')).reset_index()
                            p_usage['Usage %'] = (p_usage['Pitches'] / p_usage['Pitches'].sum() * 100)
                            
                            # Team Global Performance
                            t_pitches = sc_data[sc_data['batting_team'] == team].copy()
                            t_pitches['is_swing'] = t_pitches['description'].isin(['swinging_strike', 'swinging_strike_blocked', 'foul', 'foul_tip', 'hit_into_play', 'hit_into_play_no_out', 'hit_into_play_score', 'missed_bunt'])
                            t_pitches['is_whiff'] = t_pitches['description'].isin(['swinging_strike', 'swinging_strike_blocked', 'missed_bunt'])
                            t_pitches['is_hard_hit'] = t_pitches['launch_speed'] >= 95
                            
                            t_perf = t_pitches.groupby('pitch_name').agg(
                                Swings=('is_swing', 'sum'),
                                Whiffs=('is_whiff', 'sum'),
                                BBE=('launch_speed', 'count'),
                                Hard_Hits=('is_hard_hit', 'sum')
                            ).reset_index()
                            
                            t_perf['Team Whiff %'] = (t_perf['Whiffs'] / t_perf['Swings'] * 100).fillna(0)
                            t_perf['Team Hard Hit %'] = (t_perf['Hard_Hits'] / t_perf['BBE'] * 100).fillna(0)
                            
                            # Merge for logic
                            matrix = p_usage.merge(t_perf, on='pitch_name', how='inner')
                            if matrix.empty:
                                st.write("Insufficient overlap data.")
                                continue
                                
                            # EVALUATE DECISION MATRIX RULES
                            edge_found = False
                            primary = matrix.sort_values(by='Usage %', ascending=False).iloc[0]
                            
                            # Rule 1: Strikeout Mismatch (Usage > 30% AND Team Whiff > 30%)
                            if primary['Usage %'] > 30 and primary['Team Whiff %'] > 30:
                                st.success(f"🚨 **STRIKEOUT EDGE DETECTED: {found_last.title()} OVER Ks**")
                                st.write(f"*{found_first.title()} {found_last.title()} throws his {primary['pitch_name']} {primary['Usage %']:.1f}% of the time. The {team} have a massive {primary['Team Whiff %']:.1f}% Whiff Rate against that pitch globally over the last 10 days.*")
                                edge_found = True
                                
                            # Rule 2: Fade Pitcher Mismatch (Usage > 30% AND Team Hard Hit > 40%)
                            if primary['Usage %'] > 30 and primary['Team Hard Hit %'] > 40:
                                st.error(f"🚨 **FADE PITCHER DETECTED: {team} TEAM TOTAL OVER**")
                                st.write(f"*{team} crushes the {primary['pitch_name']} with a {primary['Team Hard Hit %']:.1f}% Hard Hit rate. {found_last.title()} relies on this pitch {primary['Usage %']:.1f}% of the time, creating a dangerous structural mismatch.*")
                                edge_found = True
                                
                            if not edge_found:
                                st.info(f"⚖️ **No Structural Edge Found.** {team} hits {found_last.title()}'s primary pitches at a league-average rate. Skip derivative props and look for a better game.")
                                
                    except Exception as e:
                        st.error(f"Scanner Error: {e}")

# ==========================================
# TAB 4: THE BETTING PLAYBOOK
# ==========================================
with tab4:
    st.header("📖 The Quantitative Bettor's Playbook")
    st.write("A complete guide to finding predictive edges across the platform.")
    
    st.markdown("""
    ### 1. The Player Dashboard (Tab 1: Identifying Individual Form)
    The Player Dashboard isolates an individual's current physical form from their stale, full-season statistics. The market prices props based on 162-game averages; you use this tab to exploit 14-to-30-day mechanical changes.
    
    * **Velocity & Spin Rate Tracking:** A pitcher whose average fastball drops by 1.5 mph over two consecutive starts is mathematically highly vulnerable to hard contact. The sportsbook will still price their outs or strikeout props based on their season average. Fade them immediately by betting their **Outs Recorded Under**.
    * **Rolling Rates vs. Season Rates (The Slump/Surge Trap):** A batter might have a respectable 18% Strikeout Rate on the season, but a 35% rate over their last 10 games due to a swing flaw. Identify these rolling surges and bet the **Batter Over 0.5/1.5 Strikeouts** before the books adjust to the new baseline.
    * **Batted Ball Luck (BABIP Regression):** If a hitter is batting .150 over the last week but has a 50% Hard Hit rate and elite exit velocities, they aren't actually slumping—they are hitting into bad luck. Target their **Over 1.5 Total Bases** or **Hits** props for positive regression at plus-money.
    
    ---
    
    ### 2. Team Matchups (Tab 2: Exploiting Macro Vulnerabilities)
    The Team Matchups tab evaluates the holistic 9-man lineup and pitching staff dynamics. This is where you find structural edges that dictate Moneyline, Run Line, and Team Total bets.
    
    * **Bullpen Exhaustion & Leverage:** A starting pitcher might only be projected for 5.0 innings. If this tab reveals that a team's top three high-leverage relievers pitched the last two consecutive days, the back-half of the game is mathematically unprotected. Target the **Full Game Opponent Team Total Over**.
    * **Granular Platoon Splits:** The public bets on basic Left vs. Right splits. Use this tab to dig deeper: Does a team hit LHP well overall, but struggle specifically on the road? Do they have a high wRC+ but also a massive strikeout rate against righties? Use these specific splits to find hidden value in **Team Strikeout Totals**.
    * **Run Environment Context:** Combine team offensive profiles with park factors. A fly-ball heavy lineup playing in a warm, hitter-friendly environment presents a massive edge for **First 5 Innings Over** wagers, whereas a ground-ball heavy team neutralizes those same park factors.
    
    ---
    
    ### 3. The Matchup Simulator (Tab 3: Arsenal Matchups)
    
    Traditional sports betting markets are fundamentally reactionary. Sportsbooks set opening lines based on macro-level box scores, recent surface outcomes, and historical trends—and the general betting public wagers almost exclusively on those same narratives. 
    
    True quantitative edge is found not in *what* happened in past box scores, but in the *physical mechanics* that dictate future outcomes. 
    
    #### Pitcher vs. Team (Historical Box Score & Rate Context)
    A standard box score is deceptive because it treats all volume equally. This module strips away superficial counting stats and injects operational rate metrics: **Innings Pitched (IP)**, **True Strikeout Rate (K%)**, and **Plate Appearance (PA) outcomes**.
    
    * **True K% vs. Raw Strikeouts:** A raw total of 14 strikeouts over two years looks dominant. However, if those 14 Ks required 21.0 innings (a below-average 17.5% K%), betting the **Over** on a 6.5 K line is a trap. Conversely, 14 Ks in 10.0 innings (35.0% K%) reveals elite swing-and-miss efficiency, signaling an immediate **Over** opportunity.
    * **Pitcher Outs Recorded (IP Stability):** By tracking exact out conversion, this module isolates whether a starter works deep against a specific lineup. High pitch counts and elevated hit rates indicate an early exit, signaling value on **Pitcher Outs Recorded Under (e.g., Under 17.5 Outs)**.
    
    #### Pitcher vs. Batter (Individual Arsenal Matrix)
    Baseball at-bats are micro-duels of pitch types versus bat paths. This module cross-references a pitcher's granular repertoire directly against a hitter's specific pitch-level swing tendencies.
    
    * **Exposing Lucky Hit Samples:** Batter A might be 4-for-8 (.500) historically against Pitcher B. But if the matrix shows that the pitcher throws 55% Sweepers and the batter possesses a 42% Whiff Rate against Sweepers, those previous hits were high-variance luck. You gain an edge by taking the **Under 0.5 or 1.5 Hits** at plus-money.
    * **Pitch-Mix Dependency & Longshot HR Value:** If a pitcher throws a high-velocity 4-Seamer 60% of the time, and an opposing power hitter possesses a .620 slugging percentage and a 55% Hard Hit rate against fastballs over 96 mph, that matchup is primed for hard contact. This unlocks high-ROI targets for **Over 1.5 Total Bases** and **To Hit a Home Run**.
    * **Batter Strikeout Props:** When a pitcher’s primary out-pitch directly attacks a hitter's primary zone of weakness, it triggers high-confidence wagers on **Batter Over 0.5/1.5 Strikeouts**.
    
    #### Pitcher vs. Team (Global Arsenal Matrix)
    This module solves the biggest limitation in baseball analytics: **Small Sample Noise**. It pulls thousands of league-wide pitch observations over a rolling 30-to-60-day window to evaluate how an entire lineup handles the pitcher's exact pitch mix.
    
    * **Dismantling the "Handedness Trap":** A lineup might rank top-5 in baseball against Left-Handed Pitching (LHP). However, if that ranking is driven by crushing soft-tossing fastballs, and the starting LHP throws a heavy diet of high-spin sliders (which the lineup struggles against), the generic split is meaningless. You exploit this discrepancy by backing the **Pitcher's Team Moneyline** or **Team Total Under**.
    * **Rolling Form vs. Stale Season Totals:** Using a customizable rolling window allows you to capture active mechanical tweaks, pitch velocity jumps, or offensive lineup slumps that full-season averages dilute.
    * **First 5 Innings (F5) Betting:** Bullpens introduce unpredictable variance. The Global Arsenal Matrix models the starting pitcher's interaction with the order through 15–20 outs, making it an ideal engine for **First 5 Innings (F5) Moneyline** and **F5 Under/Over** wagers.
    """)
