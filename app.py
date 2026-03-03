import streamlit as st
import os
import random
import urllib.parse
from sqlalchemy import create_engine, Column, Integer, String, Boolean
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

app_mode = st.sidebar.radio("App Mode:", ["📋 Manager Pro", "⏱️ Watch Ref"])

# --- 3. DATABASE ENGINE ---
raw_env = os.getenv("DATABASE_URL")
db_url_str = str(raw_env).replace("postgres://", "postgresql://", 1) if raw_env else "sqlite:///futsal.db"

if not st.session_state.db_connected:
    st.title("⚽ Futsal Pro v3.0")
    if st.button("🔗 Connect to Futsal_Permanent_DB"):
        try:
            engine = create_engine(db_url_str)
            Base.metadata.create_all(bind=engine)
            st.session_state.db_connected = True
            st.rerun()
        except Exception as e:
            st.error(f"Connection Failed: {e}")
    st.stop()

engine = create_engine(db_url_str)
SessionLocal = sessionmaker(bind=engine)

# --- 4. MANAGER PRO MODE ---
if app_mode == "📋 Manager Pro":
    st.title("📋 Futsal Manager Pro")

    with SessionLocal() as session:
        # Player Management
        with st.expander("👤 Player Management", expanded=(st.session_state.edit_id is not None)):
            raw_all = session.query(Player).order_by(Player.name).all()
            target = session.query(Player).filter(Player.id == st.session_state.edit_id).first() if st.session_state.edit_id else None

            with st.form("p_form"):
                f_name = st.text_input("Name", value=str(getattr(target, "name", "")))
                f_rate = st.slider("Rating", 1, 10, int(getattr(target, "rating", 5)))
                pos_options = ["GK", "DEF", "FWD"]
                curr_p = str(getattr(target, "position", "DEF")).upper()
                if curr_p == "MID": curr_p = "DEF"
                s_idx = pos_options.index(curr_p) if curr_p in pos_options else 1
                f_pos = st.selectbox("Position", pos_options, index=s_idx)
                f_gk = st.checkbox("Is Goalie?", value=bool(getattr(target, "is_goalie", False)) or f_pos == "GK")
                others = [str(p.name) for p in raw_all if p.name != f_name]
                curr_l = str(getattr(target, "linked_to", "None"))
                f_link = st.selectbox("Link Partner", ["None"] + others, index=(others.index(curr_l)+1 if curr_l in others else 0))

                if st.form_submit_button("💾 Save Player"):
                    if target:
                        target.name, target.rating, target.position, target.is_goalie, target.linked_to = f_name, f_rate, f_pos, f_gk, (None if f_link=="None" else f_link)
                    else:
                        session.add(Player(name=f_name, rating=f_rate, position=f_pos, is_goalie=f_gk, linked_to=(None if f_link=="None" else f_link)))
                    session.commit()
                    st.session_state.edit_id = None
                    st.rerun()

        # Attendance List
        with st.expander("📋 Attendance", expanded=True):
            players = session.query(Player).order_by(Player.name).all()
            c1, c2 = st.columns(2)
            if c1.button("✅ All Here"):
                for p in players: st.session_state[f"at_{p.id}"] = True
                st.rerun()
            if c2.button("❌ All Absent"):
                for p in players: st.session_state[f"at_{p.id}"] = False
                st.rerun()

            for i, p in enumerate(players, 1):
                r1, r2, r3, r4 = st.columns([3, 1, 1, 1])
                r1.write(f"**{i}.** {'🧤' if p.is_goalie else '🏃'} {p.name} ({p.position})")
                r2.checkbox("Here", key=f"at_{p.id}")
                if r3.button("📝", key=f"ed_{p.id}"):
                    st.session_state.edit_id = p.id
                    st.rerun()
                if r4.button("🗑️", key=f"del_{p.id}"):
                    session.delete(p)
                    session.commit()
                    st.rerun()

    st.divider()
    t_count = st.radio("Number of Teams:", [2, 3], horizontal=True, index=1, on_change=wipe_teams)

    if st.button("🎲 Generate Balanced Teams", use_container_width=True):
        wipe_teams()
        with SessionLocal() as session:
            present = [p for p in session.query(Player).all() if st.session_state.get(f"at_{p.id}", False)]
            if len(present) < (t_count * 2):
                st.error("Not enough players!")
            else:
                # --- GREEDY BALANCING ENGINE ---
                # 1. Shuffle everything first for true variety
                random.shuffle(present)
                
                # 2. Separate GKs (Elite first)
                gks = sorted([p for p in present if p.is_goalie or p.position == "GK"], key=lambda x: x.rating, reverse=True)
                outfielders = [p for p in present if p not in gks]
                outfielders.sort(key=lambda x: x.rating, reverse=True)

                final_teams = [{"name": f"Team {chr(65+i)}", "players": [], "rating": 0, "has_gk": False} for i in range(t_count)]
                
                # 3. Distribute GKs (Snake order for GKs)
                for i, gk in enumerate(gks):
                    target_idx = i % t_count if (i // t_count) % 2 == 0 else (t_count - 1) - (i % t_count)
                    if target_idx < t_count:
                        final_teams[target_idx]["players"].append(gk)
                        final_teams[target_idx]["rating"] += gk.rating
                        final_teams[target_idx]["has_gk"] = True
                    else:
                        outfielders.append(gk) # Extras become outfielders
                
                # 4. GREEDY DISTRIBUTION for Outfielders
                # We sort teams by current rating AND player count to keep it 6-6-6
                outfielders.sort(key=lambda x: x.rating, reverse=True)
                for p in outfielders:
                    # Pick the team that is either smaller OR has a lower rating if sizes are equal
                    final_teams.sort(key=lambda x: (len(x["players"]), x["rating"]))
                    final_teams[0]["players"].append(p)
                    final_teams[0]["rating"] += p.rating

                # Sort back to A-B-C for UI
                final_teams.sort(key=lambda x: x["name"])
                st.session_state.final_teams = final_teams
                st.rerun()

    # --- DISPLAY & ONE-TAP SWAP ---
    if "final_teams" in st.session_state:
        cols = st.columns(t_count)
        for i, team in enumerate(st.session_state.final_teams):
            with cols[i]:
                # Visual Team Strength
                st.subheader(f"{team['name']}")
                st.metric("Total Rating", f"{team['rating']} pts")
                if not team["has_gk"]: st.warning("🧤 Guest GK Needed")
                
                for p in team["players"]:
                    label = f"{'🧤' if p.is_goalie else '🏃'} {p.name} ({p.rating})"
                    if st.button(label, key=f"btn_{p.id}_{i}", use_container_width=True):
                        st.session_state.swap_list.append({"p": p, "t_idx": i})
                        if len(st.session_state.swap_list) == 2:
                            s1, s2 = st.session_state.swap_list
                            # Execute Swap
                            t1_list = st.session_state.final_teams[s1['t_idx']]["players"]
                            t2_list = st.session_state.final_teams[s2['t_idx']]["players"]
                            idx1 = next(idx for idx, player in enumerate(t1_list) if player.id == s1['p'].id)
                            idx2 = next(idx for idx, player in enumerate(t2_list) if player.id == s2['p'].id)
                            t1_list[idx1], t2_list[idx2] = t2_list[idx2], t1_list[idx1]
                            
                            # Refresh totals
                            for t in st.session_state.final_teams:
                                t["rating"] = sum(pl.rating for pl in t["players"])
                                t["has_gk"] = any(pl.is_goalie for pl in t["players"])
                            st.session_state.swap_list = []
                            st.rerun()
        
        if st.session_state.swap_list:
            st.info(f"🔄 Swapping: **{st.session_state.swap_list[0]['p'].name}**. Select another player to finish.")

        # Telegram Sharing
        msg = "⚽ *FUTSAL MATCH DAY* ⚽\n\n"
        for t in st.session_state.final_teams:
            msg += f"*{t['name']}* (Rating: {t['rating']})\n"
            for p in t["players"]:
                msg += f"{'🧤' if p.is_goalie else '🏃'} {p.name}\n"
            if not t["has_gk"]: msg += "⚠️ _Rotation GK Required_\n"
            msg += "\n"
        
        st.divider()
        st.code(msg)
        st.markdown(f"[✈️ Share to Telegram](https://t.me/share/url?url={urllib.parse.quote(msg)})")

# --- 5. WATCH REF MODE ---
else:
    st.title("⏱️ Watch Ref v3.0")
    if st.session_state.ref_3_teams is None:
        c1, c2 = st.columns(2)
        if c1.button("2 Teams Mode"): st.session_state.ref_3_teams = False; st.rerun()
        if c2.button("3 Teams Mode"): st.session_state.ref_3_teams = True; st.rerun()
    else:
        rots = [("RED", "BLUE", "GREEN"), ("BLUE", "GREEN", "RED"), ("GREEN", "RED", "BLUE")]
        cur = rots[st.session_state.rotation_idx % 3] if st.session_state.ref_3_teams else ("RED", "BLUE", "WAIT")
        col1, col2, col3 = st.columns([2, 1, 2])
        with col1:
            st.subheader(cur[0]); st.markdown(f"## {st.session_state.score_a}")
            if st.button("➕ Goal", key="ga"): st.session_state.score_a += 1; st.rerun()
        with col2:
            if st.button("🔄"): st.session_state.score_a = 0; st.session_state.score_b = 0; st.rerun()
        with col3:
            st.subheader(cur[1]); st.markdown(f"## {st.session_state.score_b}")
            if st.button("➕ Goal", key="gb"): st.session_state.score_b += 1; st.rerun()
        if st.session_state.ref_3_teams:
            st.info(f"Waiting: {cur[2]}")
            if st.button("🔄 Next Match"): st.session_state.rotation_idx += 1; st.session_state.score_a = 0; st.session_state.score_b = 0; st.rerun()
        if st.button("⚙️ Exit"): st.session_state.ref_3_teams = None; st.rerun()
