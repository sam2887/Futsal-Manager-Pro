import streamlit as st
import os
import random
import urllib.parse
import pandas as pd
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker

# --- 1. DATABASE MODELS ---
Base = declarative_base()

class Player(Base):
    __tablename__ = "Futsal_Permanent_DB"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)
    rating = Column(Integer, default=5)
    position = Column(String, default="DEF")
    is_goalie = Column(Boolean, default=False)
    linked_to = Column(String, nullable=True)

class MatchResult(Base):
    __tablename__ = "Futsal_Match_History"
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.now)
    team_a_name = Column(String)
    team_b_name = Column(String)
    score_a = Column(Integer)
    score_b = Column(Integer)
    winner = Column(String)

# --- 2. UI LAYOUT & STATE ---
st.set_page_config(page_title="Futsal Pro v3.0", layout="wide")

if "score_a" not in st.session_state: st.session_state.score_a = 0
if "score_b" not in st.session_state: st.session_state.score_b = 0
if "ref_3_teams" not in st.session_state: st.session_state.ref_3_teams = None
if "rotation_idx" not in st.session_state: st.session_state.rotation_idx = 0
if "db_connected" not in st.session_state: st.session_state.db_connected = False
if "swap_list" not in st.session_state: st.session_state.swap_list = []

def wipe_teams():
    for k in ["tA", "tB", "tC", "final_teams"]:
        if k in st.session_state: del st.session_state[k]
    st.session_state.swap_list = []

app_mode = st.sidebar.radio("Menu:", ["📋 Manager Pro", "⏱️ Watch Ref", "📊 League Stats"])

# --- 3. DATABASE ENGINE ---
raw_env = os.getenv("DATABASE_URL")
db_url_str = str(raw_env).replace("postgres://", "postgresql://", 1) if raw_env else "sqlite:///futsal.db"
engine = create_engine(db_url_str)
SessionLocal = sessionmaker(bind=engine)

if not st.session_state.db_connected:
    st.title("⚽ Futsal Pro v3.0")
    if st.button("🔗 Connect to Futsal_Permanent_DB"):
        Base.metadata.create_all(bind=engine)
        st.session_state.db_connected = True
        st.rerun()
    st.stop()

# --- 4. MANAGER PRO MODE (THE DRAW) ---
if app_mode == "📋 Manager Pro":
    st.title("📋 Futsal Manager Pro")
    with SessionLocal() as session:
        with st.expander("👤 Player Management"):
            # Form to add/edit players
            with st.form("p_form"):
                f_name = st.text_input("Name")
                f_rate = st.slider("Rating", 1, 10, 5)
                f_pos = st.selectbox("Position", ["GK", "DEF", "FWD"])
                f_gk = st.checkbox("Is Goalie?")
                if st.form_submit_button("💾 Save Player"):
                    session.add(Player(name=f_name, rating=f_rate, position=f_pos, is_goalie=f_gk))
                    session.commit(); st.rerun()
            
            # Delete players list
            players_all = session.query(Player).order_by(Player.name).all()
            for p in players_all:
                c1, c2 = st.columns([4, 1])
                c1.write(f"{p.name} ({p.rating})")
                if c2.button("🗑️", key=f"del_{p.id}"):
                    session.delete(p)
                    session.commit(); st.rerun()
        
        st.subheader("📋 Attendance (Select 18 for perfect 39s)")
        players = session.query(Player).order_by(Player.name).all()
        cols = st.columns(3)
        for i, p in enumerate(players):
            cols[i % 3].checkbox(f"{p.name} ({p.rating})", key=f"at_{p.id}")

    st.divider()
    t_count = st.radio("Number of Teams:", [2, 3], horizontal=True, index=1)
    
    if st.button("🎲 Generate Balanced Teams (Greedy Engine)", use_container_width=True):
        wipe_teams()
        with SessionLocal() as session:
            present = [p for p in session.query(Player).all() if st.session_state.get(f"at_{p.id}")]
            if len(present) < (t_count * 2): st.error("Need more players!")
            else:
                random.shuffle(present)
                gks = sorted([p for p in present if p.is_goalie], key=lambda x: x.rating, reverse=True)
                outs = sorted([p for p in present if not p.is_goalie], key=lambda x: x.rating, reverse=True)
                teams = [{"name": f"Team {chr(65+i)}", "players": [], "rating": 0, "has_gk": False} for i in range(t_count)]
                
                # Distribute GKs
                for i, gk in enumerate(gks):
                    idx = i % t_count if (i//t_count)%2==0 else (t_count-1)-(i%t_count)
                    if idx < t_count: 
                        teams[idx]["players"].append(gk)
                        teams[idx]["rating"] += gk.rating
                        teams[idx]["has_gk"] = True
                
                # Greedy Outfielder Balance
                for p in outs:
                    teams.sort(key=lambda x: (len(x["players"]), x["rating"]))
                    teams[0]["players"].append(p)
                    teams[0]["rating"] += p.rating
                
                teams.sort(key=lambda x: x["name"])
                st.session_state.final_teams = teams; st.rerun()

    if "final_teams" in st.session_state:
        c = st.columns(t_count)
        for i, t in enumerate(st.session_state.final_teams):
            with c[i]:
                st.success(f"**{t['name']}** - {t['rating']} pts")
                for p in t["players"]: st.write(f"{'🧤' if p.is_goalie else '🏃'} {p.name}")

# --- 5. WATCH REF MODE (THE SAVER) ---
elif app_mode == "⏱️ Watch Ref":
    st.title("⏱️ Watch Ref v3.0")
    if st.session_state.ref_3_teams is None:
        if st.button("Start 3-Team Rotation"): st.session_state.ref_3_teams = True; st.rerun()
    else:
        rots = [("Team A", "Team B", "Team C"), ("Team B", "Team C", "Team A"), ("Team C", "Team A", "Team B")]
        cur = rots[st.session_state.rotation_idx % 3]
        
        c1, c2, c3 = st.columns([2, 1, 2])
        with c1: 
            st.header(cur[0])
            st.title(st.session_state.score_a)
            if st.button(f"Goal {cur[0]}", key="ga"): st.session_state.score_a += 1; st.rerun()
        with c3: 
            st.header(cur[1])
            st.title(st.session_state.score_b)
            if st.button(f"Goal {cur[1]}", key="gb"): st.session_state.score_b += 1; st.rerun()
        
        st.divider()
        st.info(f"Waiting: {cur[2]}")
        if st.button("💾 Save Score & Next Match", use_container_width=True):
            with SessionLocal() as session:
                winner = cur[0] if st.session_state.score_a > st.session_state.score_b else cur[1] if st.session_state.score_b > st.session_state.score_a else "Draw"
                session.add(MatchResult(team_a_name=cur[0], team_b_name=cur[1], score_a=st.session_state.score_a, score_b=st.session_state.score_b, winner=winner))
                session.commit()
            st.session_state.rotation_idx += 1
            st.session_state.score_a = 0; st.session_state.score_b = 0; st.rerun()

# --- 6. LEAGUE STATS (THE DASHBOARD) ---
else:
    st.title("📊 League Stats")
    with SessionLocal() as session:
        data = session.query(MatchResult).order_by(MatchResult.timestamp.desc()).all()
        if data:
            df = pd.DataFrame([(m.timestamp.strftime("%H:%M"), m.team_a_name, m.score_a, m.score_b, m.team_b_name, m.winner) for m in data], 
                              columns=["Time", "Home", "SH", "SA", "Away", "Winner"])
            
            # Standings calculation
            standings = {"Team A": 0, "Team B": 0, "Team C": 0}
            for m in data:
                if m.winner == "Draw":
                    standings[m.team_a_name] += 1
                    standings[m.team_b_name] += 1
                elif m.winner in standings:
                    standings[m.winner] += 3
            
            st.subheader("🏆 Leaderboard (Points)")
            st.bar_chart(pd.Series(standings))
            
            st.subheader("📝 Match History")
            st.table(df)
            
            if st.button("🧨 Reset League Stats"):
                session.query(MatchResult).delete()
                session.commit(); st.rerun()
        else:
            st.info("No matches recorded yet. Go to Watch Ref to save your first game!")
