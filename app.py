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
if "edit_id" not in st.session_state: st.session_state.edit_id = None
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

# --- 4. MANAGER PRO MODE ---
if app_mode == "📋 Manager Pro":
    st.title("📋 Futsal Manager Pro")
    
    with SessionLocal() as session:
        # --- PLAYER MANAGEMENT ---
        with st.expander("👤 Player Management", expanded=(st.session_state.edit_id is not None)):
            target = session.query(Player).filter(Player.id == st.session_state.edit_id).first() if st.session_state.edit_id else None
            with st.form("p_form"):
                st.write("### " + ("Edit Player" if target else "Add New Player"))
                f_name = st.text_input("Name", value=target.name if target else "")
                f_rate = st.slider("Rating", 1, 10, target.rating if target else 5)
                f_pos = st.selectbox("Position", ["GK", "DEF", "FWD"], index=["GK", "DEF", "FWD"].index(target.position) if target else 1)
                f_gk = st.checkbox("Is Goalie?", value=target.is_goalie if target else False)
                if st.form_submit_button("💾 Save Player"):
                    if target:
                        target.name, target.rating, target.position, target.is_goalie = f_name, f_rate, f_pos, f_gk
                    else:
                        session.add(Player(name=f_name, rating=f_rate, position=f_pos, is_goalie=f_gk))
                    session.commit(); st.session_state.edit_id = None; st.rerun()

        # --- ATTENDANCE ---
        st.subheader("📋 Attendance")
        players = session.query(Player).order_by(Player.name).all()
        c_all1, c_all2 = st.columns(2)
        if c_all1.button("✅ Check All", use_container_width=True):
            for p in players: st.session_state[f"at_{p.id}"] = True
            st.rerun()
        if c_all2.button("❌ Uncheck All", use_container_width=True):
            for p in players: st.session_state[f"at_{p.id}"] = False
            st.rerun()

        st.divider()
        for p in players:
            r1, r2, r3, r4 = st.columns([3, 1, 1, 1])
            r1.write(f"{'🧤' if p.is_goalie else '🏃'} **{p.name}** ({p.position})")
            r2.checkbox("Here", key=f"at_{p.id}")
            if r3.button("📝", key=f"ed_{p.id}"): st.session_state.edit_id = p.id; st.rerun()
            if r4.button("🗑️", key=f"del_{p.id}"): session.delete(p); session.commit(); st.rerun()

    st.divider()
    t_count = st.radio("Number of Teams:", [2, 3], horizontal=True, index=1, on_change=wipe_teams)
    
    if st.button("🎲 Generate Balanced Teams", use_container_width=True):
        wipe_teams()
        with SessionLocal() as session:
            present = [p for p in session.query(Player).all() if st.session_state.get(f"at_{p.id}")]
            if len(present) < (t_count * 2): st.error("Check more players!")
            else:
                random.shuffle(present)
                gks = sorted([p for p in present if p.is_goalie], key=lambda x: x.rating, reverse=True)
                outs = sorted([p for p in present if not p.is_goalie], key=lambda x: x.rating, reverse=True)
                teams = [{"name": f"Team {chr(65+i)}", "players": [], "rating": 0, "has_gk": False} for i in range(t_count)]
                for i, gk in enumerate(gks):
                    idx = i % t_count if (i // t_count) % 2 == 0 else (t_count - 1) - (i % t_count)
                    if idx < t_count: teams[idx]["players"].append(gk); teams[idx]["rating"] += gk.rating; teams[idx]["has_gk"] = True
                    else: outs.append(gk)
                outs.sort(key=lambda x: x.rating, reverse=True)
                for p in outs:
                    teams.sort(key=lambda x: (len(x["players"]), x["rating"]))
                    teams[0]["players"].append(p); teams[0]["rating"] += p.rating
                teams.sort(key=lambda x: x["name"])
                st.session_state.final_teams = teams; st.rerun()

    # --- TEAM DISPLAY, SWAP & TELEGRAM ---
    if "final_teams" in st.session_state:
        st.divider()
        if st.session_state.swap_list:
            st.info(f"🔄 **Selected:** {st.session_state.swap_list[0]['p'].name}. Click another player to swap.")
            if st.button("Cancel Swap"): st.session_state.swap_list = []; st.rerun()

        cols = st.columns(len(st.session_state.final_teams))
        for i, t in enumerate(st.session_state.final_teams):
            with cols[i]:
                st.markdown(f"### {t['name']}")
                st.metric("Total Pts", t['rating'])
                for p in t["players"]:
                    btn_label = f"{'🧤' if p.is_goalie else '🏃'} {p.name} ({p.rating})"
                    if st.button(btn_label, key=f"swp_{p.id}_{i}", use_container_width=True):
                        st.session_state.swap_list.append({"p": p, "t_idx": i})
                        if len(st.session_state.swap_list) == 2:
                            s1, s2 = st.session_state.swap_list
                            t1 = st.session_state.final_teams[s1['t_idx']]["players"]
                            t2 = st.session_state.final_teams[s2['t_idx']]["players"]
                            idx1 = next(j for j, pl in enumerate(t1) if pl.id == s1['p'].id)
                            idx2 = next(j for j, pl in enumerate(t2) if pl.id == s2['p'].id)
                            t1[idx1], t2[idx2] = t2[idx2], t1[idx1]
                            for team in st.session_state.final_teams:
                                team["rating"] += 0 # Force refresh logic
                                team["rating"] = sum(pl.rating for pl in team["players"])
                                team["has_gk"] = any(pl.is_goalie for pl in team["players"])
                            st.session_state.swap_list = []; st.rerun()

        # --- TELEGRAM SHARE SECTION ---
        st.divider()
        share_msg = "⚽ *FUTSAL LINEUPS* ⚽\n\n"
        for t in st.session_state.final_teams:
            share_msg += f"*{t['name']}* (Rating: {t['rating']})\n"
            for p in t["players"]:
                share_msg += f"{'🧤' if p.is_goalie else '🏃'} {p.name}\n"
            share_msg += "\n"
        
        st.code(share_msg, language="markdown")
        st.markdown(f"[✈️ Share Lineups to Telegram](https://t.me/share/url?url={urllib.parse.quote(share_msg)})")

# --- 5. WATCH REF & 6. LEAGUE STATS ---
elif app_mode == "⏱️ Watch Ref":
    st.title("⏱️ Watch Ref v3.0")
    if st.session_state.ref_3_teams is None:
        if st.button("Start 3-Team Rotation"): st.session_state.ref_3_teams = True; st.rerun()
    else:
        rots = [("Team A", "Team B", "Team C"), ("Team B", "Team C", "Team A"), ("Team C", "Team A", "Team B")]
        cur = rots[st.session_state.rotation_idx % 3]
        c1, c2, c3 = st.columns([2, 1, 2])
        with c1: 
            st.header(cur[0]); st.title(st.session_state.score_a)
            if st.button(f"Goal {cur[0]}", key="ga"): st.session_state.score_a += 1; st.rerun()
        with c3: 
            st.header(cur[1]); st.title(st.session_state.score_b)
            if st.button(f"Goal {cur[1]}", key="gb"): st.session_state.score_b += 1; st.rerun()
        st.divider()
        if st.button("💾 Save Score & Next Match", use_container_width=True):
            with SessionLocal() as session:
                winner = cur[0] if st.session_state.score_a > st.session_state.score_b else cur[1] if st.session_state.score_b > st.session_state.score_a else "Draw"
                session.add(MatchResult(team_a_name=cur[0], team_b_name=cur[1], score_a=st.session_state.score_a, score_b=st.session_state.score_b, winner=winner))
                session.commit()
            st.session_state.rotation_idx += 1; st.session_state.score_a = 0; st.session_state.score_b = 0; st.rerun()

else:
    st.title("📊 League Stats")
    with SessionLocal() as session:
        data = session.query(MatchResult).order_by(MatchResult.timestamp.desc()).all()
        if data:
            standings = {"Team A": 0, "Team B": 0, "Team C": 0}
            for m in data:
                if m.winner == "Draw": standings[m.team_a_name] += 1; standings[m.team_b_name] += 1
                elif m.winner in standings: standings[m.winner] += 3
            st.subheader("🏆 Leaderboard")
            st.bar_chart(pd.Series(standings))
            if st.button("🧨 Reset League Stats"):
                session.query(MatchResult).delete(); session.commit(); st.rerun()
        else: st.info("No matches recorded yet.")
