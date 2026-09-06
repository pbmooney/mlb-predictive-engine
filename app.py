import streamlit as st
import pandas as pd
import pybaseball as pyb
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
from datetime import datetime, timedelta
import unicodedata

# --- ORIGINAL STABLE PLAYER ID LOOKUP ---
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

# --- DATA FETCHING FUNCTIONS ---
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

if 'edge_report' not in st.session_state:
    st.session_state.edge_report = []

if len(st.session_state.edge_report) > 0:
    st.sidebar.write(f"**{len(st.session_state.edge_report)}** +EV spots saved.")
    
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

if "run_query" not in st.session_state:
    st.session_state.run_query = False

if st.sidebar.button("Get Stats"):
    st.session_state.run_query = True

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
                has_h2h = bool(opp_first and opp_last)
                opp_id = None
                
                if has_h2h:
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
                        has_h2h = False

                if not has_h2h:
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
                    st.success(f"Successfully pulled data for {first_name} {last_name}!")
                    
                    # ==========================================================
                    # MODE A: H2H MICRO VIEW (Opponent Specified)
                    # ==========================================================
                    if has_h2h:
                        st.markdown(f"### ⚔️ H2H Matchup: {first_name.title()} {last_name.title()} vs. {opp_first.title()} {opp_last.title()}")
                        
                        in_play = ['hit_into_play', 'hit_into_play_no_out', 'hit_into_play_score']
                        swings = ['swinging_strike', 'swinging_strike_blocked', 'foul', 'foul_tip', 'hit_into_play', 'hit_into_play_no_out', 'hit_into_play_score', 'missed_bunt']
                        whiffs = ['swinging_strike', 'swinging_strike_blocked', 'missed_bunt']
                        
                        h2h_bbe = data[data['description'].isin(in_play)].copy()
                        h2h_swings = data[data['description'].isin(swings)].copy()
                        
                        total_pitches = len(data)
                        avg_ev = h2h_bbe['launch_speed'].mean() if not h2h_bbe.empty else 0
                        hard_hits = (h2h_bbe['launch_speed'] >= 95).sum() if not h2h_bbe.empty else 0
                        bbe_count = len(h2h_bbe)
                        hard_hit_pct = (hard_hits / bbe_count * 100) if bbe_count > 0 else 0
                        
                        whiff_count = h2h_swings['description'].isin(whiffs).sum()
                        swing_count = len(h2h_swings)
                        whiff_pct = (whiff_count / swing_count * 100) if swing_count > 0 else 0

                        st.markdown("##### 📜 Historical Box Score")
                        at_bats = data.dropna(subset=['events']).copy()
                        if not at_bats.empty:
                            if player_type == "Batter":
                                hits = at_bats['events'].isin(['single', 'double', 'triple', 'home_run']).sum()
                                hrs = (at_bats['events'] == 'home_run').sum()
                                ks = at_bats['events'].isin(['strikeout', 'strikeout_double_play']).sum()
                                official_abs = (~at_bats['events'].isin(['walk', 'hit_by_pitch', 'sac_fly', 'sac_bunt'])).sum()
                                ba = (hits / official_abs) if official_abs > 0 else 0.0
                                
                                t1, t2, t3, t4 = st.columns(4)
                                t1.metric("Hits / ABs", f"{hits} / {official_abs}")
                                t2.metric("Batting Avg", f".{int(ba * 1000):03d}")
                                t3.metric("Home Runs", f"{hrs}")
                                t4.metric("Strikeouts", f"{ks}")
                            else:
                                batters_faced = len(at_bats)
                                ks = at_bats['events'].isin(['strikeout', 'strikeout_double_play']).sum()
                                hits_allowed = at_bats['events'].isin(['single', 'double', 'triple', 'home_run']).sum()
                                walks = (at_bats['events'] == 'walk').sum()
                                
                                t1, t2, t3, t4 = st.columns(4)
                                t1.metric("Batters Faced", batters_faced)
                                t2.metric("Strikeouts", ks)
                                t3.metric("Hits Allowed", hits_allowed)
                                t4.metric("Walks Allowed", walks)
                        
                        st.markdown("<br>", unsafe_allow_html=True)
                        
                        st.markdown("##### 🔬 Underlying Physics")
                        st.caption(f"**Sample Size:** {total_pitches} total pitches seen in this specific matchup.")
                        
                        h1, h2, h3 = st.columns(3)
                        h1.metric("H2H Avg Exit Velo", f"{avg_ev:.1f} mph" if avg_ev > 0 else "N/A")
                        h2.metric("H2H Hard Hit %", f"{hard_hit_pct:.1f}%" if bbe_count > 0 else "N/A")
                        h3.metric("H2H Whiff %", f"{whiff_pct:.1f}%" if swing_count > 0 else "N/A")
                        
                        st.markdown("---")
                        st.markdown("##### 📅 Recent Game Logs (H2H)")
                        if player_type == "Batter":
                            events_df = data.dropna(subset=['events']).copy()
                            if not events_df.empty:
                                events_df['TB'] = events_df['events'].map({'single': 1, 'double': 2, 'triple': 3, 'home_run': 4}).fillna(0)
                                events_df['Hit'] = events_df['events'].isin(['single', 'double', 'triple', 'home_run']).astype(int)
                                events_df['HR'] = (events_df['events'] == 'home_run').astype(int)
                                game_logs = events_df.groupby('game_date').agg(TB=('TB', 'sum'), Hits=('Hit', 'sum'), HRs=('HR', 'sum')).reset_index().sort_values('game_date', ascending=False)
                                st.dataframe(game_logs, hide_index=True)
                        else:
                            events_df = data.dropna(subset=['events']).copy()
                            if not events_df.empty:
                                events_df['K'] = (events_df['events'] == 'strikeout').astype(int)
                                game_logs = events_df.groupby('game_date').agg(Strikeouts=('K', 'sum')).reset_index().sort_values('game_date', ascending=False)
                                st.dataframe(game_logs, hide_index=True)

                        st.markdown("---")
                        if player_type == "Batter":
                            st.markdown("##### 💥 Quality of Contact")
                            bbe_df = data[data['description'].isin(in_play)].dropna(subset=['launch_speed', 'launch_angle']).copy()
                            if not bbe_df.empty:
                                total_bbe = len(bbe_df)
                                bbe_df['Hard_Hit'] = (bbe_df['launch_speed'] >= 95).astype(int)
                                bbe_df['Barrel'] = ((bbe_df['launch_speed'] >= 98) & (bbe_df['launch_angle'] >= 26) & (bbe_df['launch_angle'] <= 30)).astype(int)
                                
                                c1, c2, c3, c4 = st.columns(4)
                                c1.metric("Avg Exit Velo", f"{bbe_df['launch_speed'].mean():.1f} mph")
                                c2.metric("Max Exit Velo", f"{bbe_df['launch_speed'].max():.1f} mph")
                                c3.metric("Hard Hit %", f"{(bbe_df['Hard_Hit'].sum() / total_bbe) * 100:.1f}%")
                                c4.metric("Barrel %", f"{(bbe_df['Barrel'].sum() / total_bbe) * 100:.1f}%")
                            else:
                                st.info("Not enough batted ball data in this matchup.")
                        else:
                            st.markdown("##### 📈 Advanced Pitcher Diagnostics")
                            pitch_df = data.dropna(subset=['pitch_name', 'description']).copy()
                            if not pitch_df.empty:
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
                                
                                diag_table['Whiff%'] = (diag_table['Whiffs'] / diag_table['Swings'].replace(0, np.nan)).fillna(0) * 100
                                diag_table['CSW%'] = (diag_table['CSW'] / diag_table['Total_Pitches']).fillna(0) * 100
                                diag_table = diag_table.sort_values(by='Total_Pitches', ascending=False)
                                
                                diag_table['Whiff%'] = diag_table['Whiff%'].map("{:.1f}%".format)
                                diag_table['CSW%'] = diag_table['CSW%'].map("{:.1f}%".format)
                                
                                st.dataframe(diag_table[['pitch_name', 'Total_Pitches', 'Whiff%', 'CSW%']].rename(columns={'pitch_name': 'Pitch Type'}), hide_index=True)

                        if player_type == "Batter":
                            st.markdown("---")
                            st.markdown("##### ⚾ Performance by Pitch Type (Seen)")
                            at_bats_p = data.dropna(subset=['events']).copy()
                            if not at_bats_p.empty:
                                at_bats_p['Hit'] = at_bats_p['events'].isin(['single', 'double', 'triple', 'home_run'])
                                at_bats_p['Home_Run'] = at_bats_p['events'] == 'home_run'
                                match_table = at_bats_p.groupby('pitch_name').agg(
                                    Total_Seen=('events', 'count'),
                                    Hits=('Hit', 'sum'),
                                    Home_Runs=('Home_Run', 'sum')
                                ).reset_index().rename(columns={'pitch_name': 'Pitch Type', 'Total_Seen': 'Plate Appearances'}).sort_values(by='Plate Appearances', ascending=False)
                                st.dataframe(match_table, hide_index=True)

                    # ==========================================================
                    # MODE B: MACRO PLAYER PROFILE (No Opponent Specified)
                    # ==========================================================
                    else:
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

                        if 'game_logs' in locals() and not game_logs.empty and 'props' in locals():
                            st.markdown("---")
                            st.markdown("##### 💰 Bookmaker Edge & +EV Calculator")
                            st.caption("Compare your modeled win probability against the sportsbook line to find mathematical edge.")
                            
                            ev_col1, ev_col2, ev_col3 = st.columns([2, 1, 1])
                            
                            prop_options = [p["Prop"] for p in props]
                            selected_prop = ev_col1.selectbox("Select Target Prop", prop_options, key="macro_prop_sel")
                            sample_window = ev_col2.selectbox("Model Baseline", ["L10", "L5", "L20"], key="macro_sample_win")
                            book_odds = ev_col3.number_input("Sportsbook Odds (American)", value=-110, step=5, key="macro_book_odds")
                            
                            prop_idx = prop_options.index(selected_prop)
                            target_col = props[prop_idx]["Column"]
                            target_val = props[prop_idx]["Target"]
                            
                            sample_n = 10 if sample_window == "L10" else (5 if sample_window == "L5" else 20)
                            if len(game_logs) >= sample_n:
                                my_prob = (game_logs.head(sample_n)[target_col] >= target_val).mean()
                                implied_book_prob = american_to_prob(book_odds)
                                
                                if implied_book_prob:
                                    edge = (my_prob - implied_book_prob) * 100
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
                                        
                                    if st.button("➕ Save to Daily Edge Report", key="macro_save_edge"):
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

                        if player_type == "Batter":
                            st.markdown("---")
                            st.subheader("Luck Regression (Expected vs Actual)")
                            st.caption("Identifies 'Buy Low' or 'Sell High' candidates by comparing actual results to Statcast's expected metrics.")
                            
                            ab_events = ['single', 'double', 'triple', 'home_run', 'field_out', 'grounded_into_dp', 
                                         'force_out', 'fielders_choice', 'field_error', 'strikeout', 'strikeout_double_play']
                            ab_df = data[data['events'].isin(ab_events)].copy()
                            
                            if not ab_df.empty:
                                ab_df['Hit'] = ab_df['events'].isin(['single', 'double', 'triple', 'home_run']).astype(int)
                                ab_df['TB'] = ab_df['events'].map({'single': 1, 'double': 2, 'triple': 3, 'home_run': 4}).fillna(0)
                                
                                actual_ba = ab_df['Hit'].mean()
                                actual_slg = ab_df['TB'].mean()
                                
                                ab_df['xBA'] = ab_df['estimated_ba_using_speedangle'].fillna(0)
                                ab_df['xSLG'] = ab_df['estimated_slg_using_speedangle'].fillna(0)
                                
                                xba = ab_df['xBA'].mean()
                                xslg = ab_df['xSLG'].mean()
                                
                                ba_diff = xba - actual_ba
                                slg_diff = xslg - actual_slg
                                
                                r1, r2, r3, r4 = st.columns(4)
                                r1.metric("Actual BA", f".{str(actual_ba).split('.')[1][:3].ljust(3, '0')}" if actual_ba > 0 else ".000")
                                r2.metric("Expected BA (xBA)", f".{str(xba).split('.')[1][:3].ljust(3, '0')}" if xba > 0 else ".000", delta=f"{ba_diff:+.3f} Diff")
                                r3.metric("Actual SLG", f".{str(actual_slg).split('.')[1][:3].ljust(3, '0')}" if actual_slg > 0 else ".000")
                                r4.metric("Expected SLG (xSLG)", f".{str(xslg).split('.')[1][:3].ljust(3, '0')}" if xslg > 0 else ".000", delta=f"{slg_diff:+.3f} Diff")
                                
                                if ba_diff > 0.040:
                                    st.success(f"📈 **Buy Low Alert:** Hitter is batting **.{str(actual_ba).split('.')[1][:3]}** but making contact well enough to bat **.{str(xba).split('.')[1][:3]}**.")
                                elif ba_diff < -0.040:
                                    st.error(f"📉 **Sell High Alert:** Hitter is batting **.{str(actual_ba).split('.')[1][:3]}** but contact quality implies they should be batting **.{str(xba).split('.')[1][:3]}**.")
                                else:
                                    st.info("⚖️ **Balanced Profile:** The hitter's actual outcomes closely match their contact quality.")

                        if player_type == "Batter":
                            st.markdown("---")
                            st.subheader("🏟️ Enterprise Park Factors (Handedness Splits)")
                            
                            b_hand = data['stand'].mode()[0] if 'stand' in data.columns and not data['stand'].empty else 'R'
                            hand_label = "Left-Handed" if b_hand == 'L' else "Right-Handed"
                            
                            park_factors_adv = {
                                "Average / Neutral Park": {'L': {'Hit': 100, 'HR': 100}, 'R': {'Hit': 100, 'HR': 100}},
                                "Coors Field (COL)": {'L': {'Hit': 113, 'HR': 105}, 'R': {'Hit': 113, 'HR': 110}},
                                "Great American Ball Park (CIN)": {'L': {'Hit': 104, 'HR': 136}, 'R': {'Hit': 100, 'HR': 121}},
                                "Fenway Park (BOS)": {'L': {'Hit': 107, 'HR': 85}, 'R': {'Hit': 108, 'HR': 95}}, 
                                "Yankee Stadium (NYY)": {'L': {'Hit': 97, 'HR': 122}, 'R': {'Hit': 98, 'HR': 103}},
                                "Dodger Stadium (LAD)": {'L': {'Hit': 100, 'HR': 112}, 'R': {'Hit': 98, 'HR': 115}},
                                "Oracle Park (SF)": {'L': {'Hit': 96, 'HR': 84}, 'R': {'Hit': 97, 'HR': 91}},
                                "Citi Field (NYM)": {'L': {'Hit': 97, 'HR': 90}, 'R': {'Hit': 95, 'HR': 94}}
                            }
                            
                            st.info(f"Swing Profile Detected: **{hand_label}**")
                            park_sel = st.selectbox("Select Upcoming Venue", list(park_factors_adv.keys()), key="macro_park_sel")
                            
                            hit_factor = park_factors_adv[park_sel][b_hand]['Hit'] / 100.0
                            hr_factor = park_factors_adv[park_sel][b_hand]['HR'] / 100.0
                            
                            ab_events_local = ['single', 'double', 'triple', 'home_run', 'field_out', 'grounded_into_dp', 'force_out', 'fielders_choice', 'field_error', 'strikeout', 'strikeout_double_play']
                            ab_df_park = data[data['events'].isin(ab_events_local)].copy()
                            if not ab_df_park.empty:
                                base_xba = ab_df_park['estimated_ba_using_speedangle'].fillna(0).mean()
                                base_xslg = ab_df_park['estimated_slg_using_speedangle'].fillna(0).mean()
                                
                                adj_xba = base_xba * hit_factor
                                adj_xslg = base_xslg * ((hit_factor * 0.4) + (hr_factor * 0.6))
                                
                                pk1, pk2 = st.columns(2)
                                pk1.metric(f"Park-Adjusted xBA", f".{str(adj_xba).split('.')[1][:3].ljust(3, '0')}" if adj_xba > 0 else ".000", delta=f"{adj_xba - base_xba:+.3f}")
                                pk2.metric(f"Park-Adjusted xSLG", f".{str(adj_xslg).split('.')[1][:3].ljust(3, '0')}" if adj_xslg > 0 else ".000", delta=f"{adj_xslg - base_xslg:+.3f}")

                        if player_type == "Batter":
                            st.markdown("---")
                            st.subheader("🔥 Batter Heat Zones & Spray Chart")
                            col_hz, col_sc = st.columns(2)
                            with col_hz:
                                st.markdown("**Hot Zones (Exit Velo > 90mph)**")
                                hot_data = data[(data['launch_speed'] >= 90) & (data['plate_x'].notnull()) & (data['plate_z'].notnull())]
                                if not hot_data.empty:
                                    fig, ax = plt.subplots(figsize=(4, 4))
                                    sns.scatterplot(data=hot_data, x='plate_x', y='plate_z', hue='launch_speed', palette='Reds', ax=ax, alpha=0.8, legend=False)
                                    ax.set_xlim(-1.5, 1.5)
                                    ax.set_ylim(0.5, 4.5)
                                    ax.axvline(0.83, color='grey', ls='--')
                                    ax.axvline(-0.83, color='grey', ls='--')
                                    ax.axhline(1.5, color='grey', ls='--')
                                    ax.axhline(3.5, color='grey', ls='--')
                                    ax.set_title("Hard-Hit Locations (EV >= 90)")
                                    st.pyplot(fig)
                                    plt.close(fig)
                                else:
                                    st.info("Not enough hard-hit tracking data available.")
                            with col_sc:
                                st.markdown("**Batted Ball Spray Chart**")
                                spray_data = data[data['hc_x'].notnull() & data['hc_y'].notnull()].copy()
                                if not spray_data.empty:
                                    fig, ax = plt.subplots(figsize=(6, 4))
                                    spray_data['spray_x'] = spray_data['hc_x'] - 125.42
                                    spray_data['spray_y'] = 200 - (spray_data['hc_y'] - 125.42)
                                    sns.scatterplot(data=spray_data, x='spray_x', y='spray_y', hue='events', ax=ax, palette='Set1', s=25, alpha=0.8)
                                    ax.set_xlim(-150, 150)
                                    ax.set_ylim(-50, 250)
                                    ax.axis('off')
                                    ax.set_title("Estimated Spray Distribution")
                                    ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left', fontsize='x-small', frameon=False)
                                    plt.tight_layout()
                                    st.pyplot(fig)
                                    plt.close(fig)
                                else:
                                    st.info("Not enough coordinate data for spray chart.")

                        st.markdown("---")
                        if player_type == "Batter":
                            st.subheader("Performance by Pitch Type (Seen)")
                            at_bats = data.dropna(subset=['events']).copy()
                            if not at_bats.empty:
                                at_bats['Hit'] = at_bats['events'].isin(['single', 'double', 'triple', 'home_run'])
                                at_bats['Home_Run'] = at_bats['events'] == 'home_run'
                                matchup_table = at_bats.groupby('pitch_name').agg(
                                    Total_Seen=('events', 'count'),
                                    Hits=('Hit', 'sum'),
                                    Home_Runs=('Home_Run', 'sum')
                                ).reset_index().rename(columns={'pitch_name': 'Pitch Type', 'Total_Seen': 'Plate Appearances'}).sort_values(by='Plate Appearances', ascending=False)
                                st.dataframe(matchup_table, hide_index=True)
                        else:
                            st.subheader("Advanced Pitcher Diagnostics")
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
                                
                                diag_table['Whiff%'] = (diag_table['Whiffs'] / diag_table['Swings'].replace(0, np.nan)).fillna(0) * 100
                                diag_table['CSW%'] = (diag_table['CSW'] / diag_table['Total_Pitches']).fillna(0) * 100
                                diag_table = diag_table.sort_values(by='Total_Pitches', ascending=False)
                                
                                diag_table['Whiff%'] = diag_table['Whiff%'].map("{:.1f}%".format)
                                diag_table['CSW%'] = diag_table['CSW%'].map("{:.1f}%".format)
                                
                                st.dataframe(diag_table[['pitch_name', 'Total_Pitches', 'Whiff%', 'CSW%']].rename(columns={'pitch_name': 'Pitch Type'}), hide_index=True)

                            st.markdown("---")
                            st.subheader("❄️ Pitcher Cold Zones & Velocity Trends")
                            col_cz, col_vt = st.columns(2)
                            with col_cz:
                                st.markdown("**Cold Zones (Whiff Locations)**")
                                whiff_des = ['swinging_strike', 'swinging_strike_blocked', 'missed_bunt']
                                whiff_data = data[data['description'].isin(whiff_des) & data['plate_x'].notnull() & data['plate_z'].notnull()]
                                if not whiff_data.empty:
                                    fig, ax = plt.subplots(figsize=(4, 4))
                                    sns.scatterplot(data=whiff_data, x='plate_x', y='plate_z', hue='pitch_name', ax=ax, palette='tab10', alpha=0.8, legend=False)
                                    ax.set_xlim(-1.5, 1.5)
                                    ax.set_ylim(0.5, 4.5)
                                    ax.axvline(0.83, color='grey', ls='--')
                                    ax.axvline(-0.83, color='grey', ls='--')
                                    ax.axhline(1.5, color='grey', ls='--')
                                    ax.axhline(3.5, color='grey', ls='--')
                                    ax.set_title("Whiff Locations")
                                    st.pyplot(fig)
                                    plt.close(fig)
                                else:
                                    st.info("Not enough whiff location data available.")
                            with col_vt:
                                st.markdown("**Pitch Velocity Over Time**")
                                velo_data = data.dropna(subset=['game_date', 'release_speed', 'pitch_name']).copy()
                                if not velo_data.empty:
                                    velo_data['game_date'] = pd.to_datetime(velo_data['game_date'])
                                    velo_data = velo_data.sort_values('game_date')
                                    
                                    fig, ax = plt.subplots(figsize=(6, 4))
                                    sns.lineplot(data=velo_data, x='game_date', y='release_speed', hue='pitch_name', ax=ax, marker='o', errorbar=None)
                                    ax.set_title("Velocity Trend by Pitch Type")
                                    ax.set_xlabel("Date")
                                    ax.set_ylabel("Velo (mph)")
                                    
                                    ax.xaxis.set_major_locator(plt.MaxNLocator(6))
                                    fig.autofmt_xdate()
                                    
                                    ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left', fontsize='x-small', frameon=False)
                                    plt.tight_layout()
                                    st.pyplot(fig)
                                    plt.close(fig)
                                else:
                                    st.info("Not enough velocity tracking data available.")

                        # --- INNING SPLITS (PITCHER ONLY) ---
                        if player_type == "Pitcher":
                            st.markdown("---")
                            st.subheader("Fatigue & Inning Splits (NRFI / Pitch Outs)")
                            pitch_data = data.copy()
                            pitch_data['pa_idx'] = pitch_data.groupby('game_date')['at_bat_number'].transform(lambda x: x.rank(method='dense'))
                            pitch_data['tto_raw'] = np.ceil(pitch_data['pa_idx'] / 9.0)
                            pitch_data['TTO'] = pitch_data['tto_raw'].map({1.0: "1st Time", 2.0: "2nd Time", 3.0: "3rd+ Time"}).fillna("3rd+ Time")
                            
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
                                with i2:
                                    st.markdown("**Times Through Order (Decay)**")
                                    tto_stats = pa_df.groupby('TTO').agg(
                                        Batters_Faced=('events', 'count'),
                                        K_Rate=('is_k', 'mean'),
                                        OBP=('is_on_base', 'mean')
                                    ).reset_index()
                                    tto_stats['K_Rate'] = (tto_stats['K_Rate'] * 100).map("{:.1f}%".format)
                                    tto_stats['OBP'] = tto_stats['OBP'].apply(lambda x: f".{str(x).split('.')[1][:3].ljust(3, '0')}" if pd.notnull(x) and '.' in str(x) else ".000")
                                    st.dataframe(tto_stats, hide_index=True, use_container_width=True)

# ==========================================
# TAB 2: LIVE TEAM VULNERABILITY BOARD
# ==========================================
with tab2:
    st.subheader("🎯 Team Target Finder (Statcast Engine)")
    st.write("Pull live, trailing offensive splits directly from raw MLB Statcast data to identify pitching targets.")
    
    t_col1, t_col2 = st.columns(2)
    timeframe = t_col1.radio("Select Timeframe", ["Last 7 Days", "Last 14 Days", "Last 21 Days", "Last 30 Days"], key="t_frame")
    split = t_col2.radio("Opposing Pitcher Handedness", ["Overall", "vs RHP", "vs LHP"], key="t_split")
    
    if st.button("Fetch Team Stats", key="btn_team_stats"):
        days_back_t = int(timeframe.split()[1])
        start_dt = (datetime.today() - timedelta(days=days_back_t)).strftime('%Y-%m-%d')
        end_dt = datetime.today().strftime('%Y-%m-%d')
        
        with st.spinner(f"Downloading every MLB pitch from the last {days_back_t} days..."):
            try:
                sc_data = pyb.statcast(start_dt=start_dt, end_dt=end_dt)
                if not sc_data.empty:
                    if split == "vs RHP":
                        sc_data = sc_data[sc_data['p_throws'] == 'R'].copy()
                    elif split == "vs LHP":
                        sc_data = sc_data[sc_data['p_throws'] == 'L'].copy()
                        
                    if not sc_data.empty:
                        sc_data['batting_team'] = np.where(sc_data['inning_topbot'] == 'Bot', sc_data['home_team'], sc_data['away_team'])
                        pa_events = ['strikeout', 'strikeout_double_play', 'walk', 'single', 'double', 'triple', 'home_run', 'field_out', 'grounded_into_dp', 'force_out', 'fielders_choice', 'field_error', 'hit_by_pitch', 'sac_fly', 'sac_bunt']
                        pa_df = sc_data[sc_data['events'].isin(pa_events)].copy()
                        
                        if not pa_df.empty:
                            pa_df['is_k'] = pa_df['events'].isin(['strikeout', 'strikeout_double_play']).astype(int)
                            pa_df['is_bb'] = (pa_df['events'] == 'walk').astype(int)
                            pa_df['is_hbp'] = (pa_df['events'] == 'hit_by_pitch').astype(int)
                            pa_df['is_sf'] = (pa_df['events'] == 'sac_fly').astype(int)
                            pa_df['is_ab'] = (~pa_df['events'].isin(['walk', 'hit_by_pitch', 'sac_fly', 'sac_bunt'])).astype(int)
                            pa_df['tb'] = pa_df['events'].map({'single': 1, 'double': 2, 'triple': 3, 'home_run': 4}).fillna(0)
                            pa_df['hit'] = pa_df['events'].isin(['single', 'double', 'triple', 'home_run']).astype(int)
                            
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
                            
                            team_agg['K%'] = (team_agg['K_Total'] / team_agg['PA']) * 100
                            team_agg['BB%'] = (team_agg['BB_Total'] / team_agg['PA']) * 100
                            team_agg['BA'] = team_agg['Hits_Total'] / team_agg['AB']
                            team_agg['SLG'] = team_agg['TB_Total'] / team_agg['AB']
                            team_agg['ISO'] = team_agg['SLG'] - team_agg['BA']
                            team_agg['OBP'] = (team_agg['Hits_Total'] + team_agg['BB_Total'] + team_agg['HBP_Total']) / (team_agg['AB'] + team_agg['BB_Total'] + team_agg['HBP_Total'] + team_agg['SF_Total'])
                            
                            display_df = team_agg[['batting_team', 'PA', 'K%', 'BB%', 'ISO', 'OBP']].copy().rename(columns={'batting_team': 'Team'})
                            display_df = display_df.sort_values('OBP', ascending=True)
                            
                            display_df['K%'] = display_df['K%'].map("{:.1f}%".format)
                            display_df['BB%'] = display_df['BB%'].map("{:.1f}%".format)
                            display_df['ISO'] = display_df['ISO'].map("{:.3f}".format)
                            display_df['OBP'] = display_df['OBP'].map("{:.3f}".format)
                            
                            st.success(f"Successfully crunched team splits over the last {days_back_t} days!")
                            st.dataframe(display_df, hide_index=True, use_container_width=True)
            except Exception as e:
                st.error(f"Error fetching team stats: {e}")

# ==========================================
# TAB 3: MATCHUP SIMULATOR HUB
# ==========================================
with tab3:
    st.subheader("⚔️ Matchup Simulator Hub")
    sim_team_tab, sim_batter_tab, sim_team_matrix_tab, edge_scanner_tab = st.tabs([
        "Pitcher vs. Team (Historical)", 
        "Pitcher vs. Batter (Arsenal Matrix)", 
        "Pitcher vs. Team (Arsenal Matrix)",
        "🚨 Edge Scanner"
    ])
    
    mlb_teams = ["ARI", "ATL", "BAL", "BOS", "CHC", "CIN", "CLE", "COL", "CWS", "DET", "HOU", "KC", "LAA", "LAD", "MIA", "MIL", "MIN", "NYM", "NYY", "OAK", "ATH", "PHI", "PIT", "SD", "SEA", "SF", "STL", "TB", "TEX", "TOR", "WSH"]

    with sim_team_tab:
        st.markdown("#### 📊 Pitcher vs. Team (Historical Context)")
        col_hp, col_ht, col_hd = st.columns(3)
        hist_pitcher_full = col_hp.text_input("Pitcher Full Name", value="Tarik Skubal", key="hist_p").strip()
        hist_team = col_ht.selectbox("Opposing Team", mlb_teams, index=mlb_teams.index("CWS") if "CWS" in mlb_teams else 0, key="hist_t")
        hist_years = col_hd.selectbox("Historical Window", ["1 Year", "2 Years", "3 Years"], index=1, key="hist_y")
        
        query_team = "ATH" if hist_team == "OAK" else hist_team
        
        if st.button("Run Historical Matchup", key="btn_hist"):
            if hist_pitcher_full:
                with st.spinner("Querying multi-year head-to-head Statcast logs..."):
                    try:
                        years_back = 1 if hist_years == "1 Year" else (2 if hist_years == "2 Years" else 3)
                        start_date = (datetime.today() - timedelta(days=years_back * 365)).strftime('%Y-%m-%d')
                        end_date = datetime.today().strftime('%Y-%m-%d')
                        
                        name_parts = hist_pitcher_full.split()
                        if len(name_parts) < 2:
                            st.error("Please enter both first and last name.")
                        else:
                            p_id = get_player_id(name_parts[0], name_parts[-1])
                            if not p_id:
                                st.error(f"Pitcher not found: {hist_pitcher_full}")
                            else:
                                p_data = pyb.statcast_pitcher(start_date, end_date, p_id)
                                if p_data.empty:
                                    st.warning("No historical data found for this pitcher.")
                                else:
                                    p_data['batting_team'] = np.where(p_data['inning_topbot'] == 'Bot', p_data['home_team'], p_data['away_team'])
                                    vs_team_data = p_data[p_data['batting_team'] == query_team].copy()
                                    
                                    if vs_team_data.empty:
                                        st.warning(f"No recorded matchups found against {hist_team} over the past {hist_years}.")
                                    else:
                                        total_pitches = len(vs_team_data)
                                        strikeouts = len(vs_team_data[vs_team_data['events'] == 'strikeout'])
                                        whiffs = len(vs_team_data[vs_team_data['description'].isin(['swinging_strike', 'swinging_strike_blocked', 'missed_bunt'])])
                                        swings = len(vs_team_data[vs_team_data['description'].isin(['swinging_strike', 'swinging_strike_blocked', 'foul', 'foul_tip', 'hit_into_play', 'hit_into_play_no_out', 'hit_into_play_score', 'missed_bunt'])])
                                        
                                        k_rate = (strikeouts / max(1, vs_team_data['events'].dropna().count())) * 100
                                        whiff_rate = (whiffs / max(1, swings)) * 100
                                        
                                        st.success(f"Historical Matchup Found vs. {hist_team} ({hist_years})")
                                        m1, m2, m3, m4 = st.columns(4)
                                        m1.metric("Total Pitches", total_pitches)
                                        m2.metric("Strikeouts", strikeouts)
                                        m3.metric("Strikeout %", f"{k_rate:.1f}%")
                                        m4.metric("Whiff Rate", f"{whiff_rate:.1f}%")
                    except Exception as e:
                        st.error(f"Historical Query Error: {e}")

    with sim_batter_tab:
        st.markdown("#### 🎯 Pitcher Arsenal vs. Batter Vulnerability Matrix")
        b_col1, b_col2 = st.columns(2)
        pvb_p_full = b_col1.text_input("Pitcher Full Name", value="Paul Skenes", key="pvb_p_full").strip()
        pvb_b_full = b_col2.text_input("Batter Full Name", value="Elly De La Cruz", key="pvb_b_full").strip()
        lookback_days = st.slider("Days of Pitch History", min_value=90, max_value=730, value=365, step=30, key="pvb_days")
        
        if st.button("Generate Arsenal Matrix", key="btn_pvb"):
            with st.spinner("Crunching pitch profiles..."):
                try:
                    p_parts = pvb_p_full.split()
                    b_parts = pvb_b_full.split()
                    p_id = get_player_id(p_parts[0] if len(p_parts)>1 else "", p_parts[-1])
                    b_id = get_player_id(b_parts[0] if len(b_parts)>1 else "", b_parts[-1])
                    
                    if p_id and b_id:
                        start_dt = (datetime.today() - timedelta(days=lookback_days)).strftime('%Y-%m-%d')
                        end_dt = datetime.today().strftime('%Y-%m-%d')
                        p_pitches = pyb.statcast_pitcher(start_dt, end_dt, p_id)
                        b_pitches = pyb.statcast_batter(start_dt, end_dt, b_id)
                        
                        if not p_pitches.empty and not b_pitches.empty:
                            p_usage = p_pitches.groupby('pitch_name').agg(Pitcher_Pitches=('pitch_type', 'count'), Avg_Velo=('release_speed', 'mean')).reset_index()
                            p_usage['Usage %'] = (p_usage['Pitcher_Pitches'] / p_usage['Pitcher_Pitches'].sum() * 100)
                            
                            b_pitches['is_swing'] = b_pitches['description'].isin(['swinging_strike', 'swinging_strike_blocked', 'foul', 'foul_tip', 'hit_into_play', 'hit_into_play_no_out', 'hit_into_play_score', 'missed_bunt'])
                            b_pitches['is_whiff'] = b_pitches['description'].isin(['swinging_strike', 'swinging_strike_blocked', 'missed_bunt'])
                            b_pitches['is_hard_hit'] = b_pitches['launch_speed'] >= 95
                            
                            b_perf = b_pitches.groupby('pitch_name').agg(Swings=('is_swing', 'sum'), Whiffs=('is_whiff', 'sum'), BBE=('launch_speed', 'count'), Hard_Hits=('is_hard_hit', 'sum')).reset_index()
                            b_perf['Batter Whiff %'] = (b_perf['Whiffs'] / b_perf['Swings'] * 100).fillna(0)
                            b_perf['Batter Hard Hit %'] = (b_perf['Hard_Hits'] / b_perf['BBE'] * 100).fillna(0)
                            
                            matrix = p_usage.merge(b_perf, on='pitch_name', how='inner').sort_values(by='Usage %', ascending=False)
                            st.dataframe(matrix[['pitch_name', 'Usage %', 'Avg_Velo', 'Batter Whiff %', 'Batter Hard Hit %']], hide_index=True)
                except Exception as e:
                    st.error(f"Error: {e}")

    with sim_team_matrix_tab:
        st.markdown("#### ⚾ Pitcher vs. Team (Arsenal Matrix)")
        col_p, col_t, col_d = st.columns(3)
        matrix_pitcher_full = col_p.text_input("Pitcher Full Name", value="Tarik Skubal", key="matrix_p2").strip()
        matrix_team = col_t.selectbox("Opposing Team", mlb_teams, key="matrix_t2")
        lookback_days_team = col_d.slider("Lookback Window (Days)", min_value=7, max_value=45, value=30, step=1, key="matrix_l_days")

        matrix_query_team = "ATH" if matrix_team == "OAK" else matrix_team

        if st.button("Run Arsenal Matrix", key="btn_matrix"):
            if matrix_pitcher_full:
                with st.spinner("Pulling global data..."):
                    try:
                        name_parts = matrix_pitcher_full.split()
                        p_id = get_player_id(name_parts[0] if len(name_parts)>1 else "", name_parts[-1])
                        if p_id:
                            start_date = (datetime.today() - timedelta(days=lookback_days_team)).strftime('%Y-%m-%d')
                            end_date = datetime.today().strftime('%Y-%m-%d')
                            sc_data = pyb.statcast(start_dt=start_date, end_dt=end_date)
                            sc_data['batting_team'] = np.where(sc_data['inning_topbot'] == 'Bot', sc_data['home_team'], sc_data['away_team'])
                            
                            p_pitches = pyb.statcast_pitcher(start_date, end_date, p_id)
                            p_usage = p_pitches.groupby('pitch_name').agg(Pitches=('pitch_type', 'count')).reset_index()
                            p_usage['Usage %'] = (p_usage['Pitches'] / p_usage['Pitches'].sum() * 100)
                            
                            t_pitches = sc_data[sc_data['batting_team'] == matrix_query_team].copy()
                            t_pitches['is_swing'] = t_pitches['description'].isin(['swinging_strike', 'swinging_strike_blocked', 'foul', 'foul_tip', 'hit_into_play', 'hit_into_play_no_out', 'hit_into_play_score', 'missed_bunt'])
                            t_pitches['is_whiff'] = t_pitches['description'].isin(['swinging_strike', 'swinging_strike_blocked', 'missed_bunt'])
                            t_pitches['is_hard_hit'] = t_pitches['launch_speed'] >= 95
                            
                            t_perf = t_pitches.groupby('pitch_name').agg(Swings=('is_swing', 'sum'), Whiffs=('is_whiff', 'sum'), BBE=('launch_speed', 'count'), Hard_Hits=('is_hard_hit', 'sum')).reset_index()
                            t_perf['Team Whiff %'] = (t_perf['Whiffs'] / t_perf['Swings'] * 100).fillna(0)
                            t_perf['Team Hard Hit %'] = (t_perf['Hard_Hits'] / t_perf['BBE'] * 100).fillna(0)
                            
                            matrix = p_usage.merge(t_perf, on='pitch_name', how='inner').sort_values(by='Usage %', ascending=False)
                            st.dataframe(matrix[['pitch_name', 'Usage %', 'Team Whiff %', 'Team Hard Hit %']], hide_index=True)
                    except Exception as e:
                        st.error(f"Error: {e}")

    with edge_scanner_tab:
        st.markdown("#### 🚨 Targeted Slate Edge Scanner")
        col1, col2, col3 = st.columns(3)
        s1_p = col1.text_input("Pitcher Full Name", value="Tarik Skubal", key="s1_p").strip()
        s1_t = col1.selectbox("Opponent Team", mlb_teams, key="s1_t")
        s2_p = col2.text_input("Pitcher Full Name", value="Paul Skenes", key="s2_p").strip()
        s2_t = col2.selectbox("Opponent Team", mlb_teams, index=2, key="s2_t")
        s3_p = col3.text_input("Pitcher Full Name", value="", key="s3_p").strip()
        s3_t = col3.selectbox("Opponent Team", [""] + mlb_teams, key="s3_t")
        
        if st.button("Scan Slate for Edges", key="btn_scan"):
            matchups = []
            if s1_p and s1_t: matchups.append((s1_p, s1_t))
            if s2_p and s2_t: matchups.append((s2_p, s2_t))
            if s3_p and s3_t: matchups.append((s3_p, s3_t))
            
            if matchups:
                with st.spinner("Scanning slate..."):
                    try:
                        s_dt = (datetime.today() - timedelta(days=10)).strftime('%Y-%m-%d')
                        e_dt = datetime.today().strftime('%Y-%m-%d')
                        sc_data = pyb.statcast(start_dt=s_dt, end_dt=e_dt)
                        sc_data['batting_team'] = np.where(sc_data['inning_topbot'] == 'Bot', sc_data['home_team'], sc_data['away_team'])
                        
                        for p_full, team in matchups:
                            scan_query_team = "ATH" if team == "OAK" else team
                            st.markdown(f"### 🔎 Scanning: {p_full} vs. {team}")
                            parts = p_full.split()
                            p_id = get_player_id(parts[0] if len(parts)>1 else "", parts[-1])
                            if p_id:
                                p_pitches = pyb.statcast_pitcher(s_dt, e_dt, p_id)
                                p_usage = p_pitches.groupby('pitch_name').agg(Pitches=('pitch_type', 'count')).reset_index()
                                p_usage['Usage %'] = (p_usage['Pitches'] / p_usage['Pitches'].sum() * 100)
                                
                                t_pitches = sc_data[sc_data['batting_team'] == scan_query_team].copy()
                                t_pitches['is_swing'] = t_pitches['description'].isin(['swinging_strike', 'swinging_strike_blocked', 'foul', 'foul_tip', 'hit_into_play', 'hit_into_play_no_out', 'hit_into_play_score', 'missed_bunt'])
                                t_pitches['is_whiff'] = t_pitches['description'].isin(['swinging_strike', 'swinging_strike_blocked', 'missed_bunt'])
                                t_pitches['is_hard_hit'] = t_pitches['launch_speed'] >= 95
                                
                                t_perf = t_pitches.groupby('pitch_name').agg(Swings=('is_swing', 'sum'), Whiffs=('is_whiff', 'sum'), BBE=('launch_speed', 'count'), Hard_Hits=('is_hard_hit', 'sum')).reset_index()
                                t_perf['Team Whiff %'] = (t_perf['Whiffs'] / t_perf['Swings'] * 100).fillna(0)
                                t_perf['Team Hard Hit %'] = (t_perf['Hard_Hits'] / t_perf['BBE'] * 100).fillna(0)
                                
                                matrix = p_usage.merge(t_perf, on='pitch_name', how='inner')
                                if not matrix.empty:
                                    primary = matrix.sort_values(by='Usage %', ascending=False).iloc[0]
                                    if primary['Usage %'] > 20 and primary['Team Whiff %'] > 22:
                                        st.success(f"🚨 **STRIKEOUT EDGE DETECTED: OVER Ks** ({primary['pitch_name']} Usage: {primary['Usage %']:.1f}%, Team Whiff: {primary['Team Whiff %']:.1f}%)")
                                    elif primary['Usage %'] > 20 and primary['Team Hard Hit %'] > 32:
                                        st.error(f"🚨 **FADE PITCHER DETECTED: TEAM TOTAL OVER** ({primary['pitch_name']} Hard Hit: {primary['Team Hard Hit %']:.1f}%)")
                                    else:
                                        st.info("⚖️ No structural edge found.")
                    except Exception as e:
                        st.error(f"Error: {e}")

# ==========================================
# TAB 4: THE BETTING PLAYBOOK
# ==========================================
with tab4:
    st.header("📖 The Quantitative Bettor's Playbook")
    st.write("A complete guide to finding predictive edges across the platform.")
