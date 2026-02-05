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
    position = Column(String, default="MID")
    is_goalie = Column(Boolean, default=False)
    linked_to = Column(String, nullable=True)


# --- 2. UI LAYOUT & STATE ---
st.set_page_config(page_title="Futsal Pro v3.0", layout="wide")

# Safe state initialization
if "score_a" not in st.session_state: st.session_state.score_a = 0
if "score_b" not in st.session_state: st.session_state.score_b = 0
if "ref_3_teams" not in st.session_state: st.session_state.ref_3_teams = None
if "rotation_idx" not in st.session_state: st.session_state.rotation_idx = 0
if "edit_id" not in st.session_state: st.session_state.edit_id = None
if "db_connected" not in st.session_state:
    st.session_state.db_connected = False


def wipe_teams():
    for k in ["tA", "tB", "tC"]:
        if k in st.session_state: del st.session_state[k]


app_mode = st.sidebar.radio("App Mode:", ["📋 Manager Pro", "⏱️ Watch Ref"])
match_logic = st.sidebar.selectbox("Match Logic:",
                                   ["⚖️ Fair Match", "🎲 Fun Match"])

# --- 3. DATABASE ENGINE ---
raw_env = os.getenv("DATABASE_URL")
db_url_str = str(raw_env).replace("postgres://", "postgresql://",
                                  1) if raw_env else ""

if not st.session_state.db_connected:
    st.title("⚽ Futsal Pro v3.0")
    if st.button("🔗 Connect to Futsal_Permanent_DB"):
        try:
            engine = create_engine(db_url_str)
            # FIXED: Corrected create_all method
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
        # Player Management Form
        with st.expander("👤 Player Management",
                         expanded=(st.session_state.edit_id is not None)):
            raw_all = session.query(Player).order_by(Player.name).all()
            target = session.query(Player).filter(
                Player.id == st.session_state.edit_id).first(
                ) if st.session_state.edit_id else None

            with st.form("p_form"):
                f_name = st.text_input("Name",
                                       value=str(getattr(target, "name", "")))
                f_rate = st.slider("Rating", 1, 10,
                                   int(getattr(target, "rating", 5)))

                pos_options = ["GK", "DEF", "MID", "FWD"]
                curr_p = str(getattr(target, "position", "MID")).upper()
                s_idx = 0 if "GK" in curr_p else 1 if "DEF" in curr_p else 3 if "FWD" in curr_p else 2

                f_pos = st.selectbox("Position", pos_options, index=s_idx)
                f_gk = st.checkbox("Goalie",
                                   value=bool(
                                       getattr(target, "is_goalie", False)))

                others = [
                    str(getattr(p, "name", "")) for p in raw_all
                    if str(getattr(p, "name", "")) != f_name
                ]
                curr_l = str(getattr(target, "linked_to", "None"))
                f_link = st.selectbox("Link Partner", ["None"] + others,
                                      index=(others.index(curr_l) +
                                             1 if curr_l in others else 0))

                if st.form_submit_button("💾 Save"):
                    l_val = None if f_link == "None" else f_link
                    if target:
                        setattr(target, "name", f_name)
                        setattr(target, "rating", f_rate)
                        setattr(target, "position", f_pos)
                        setattr(target, "is_goalie", f_gk)
                        setattr(target, "linked_to", l_val)
                    else:
                        session.add(
                            Player(name=f_name,
                                   rating=f_rate,
                                   position=f_pos,
                                   is_goalie=f_gk,
                                   linked_to=l_val))
                    session.commit()
                    st.session_state.edit_id = None
                    st.rerun()

        # Attendance List
        with st.expander("📋 Attendance & List", expanded=True):
            players = session.query(Player).order_by(Player.name).all()
            c1, c2 = st.columns([1, 4])
            if c1.button("✅ All"):
                for p in players:
                    st.session_state[f"at_{getattr(p, 'id')}"] = True
                st.rerun()
            if c2.button("❌ None"):
                for p in players:
                    st.session_state[f"at_{getattr(p, 'id')}"] = False
                st.rerun()

            st.divider()
            for i, p in enumerate(players, 1):
                pid = int(getattr(p, "id"))
                pname = str(getattr(p, "name"))
                ppos = str(getattr(p, "position"))
                r1, r2, r3, r4 = st.columns([3, 1, 1, 1])
                link_txt = f" 🔗({getattr(p, 'linked_to')})" if getattr(
                    p, 'linked_to') else ""
                r1.write(
                    f"**{i}.** {'🧤' if bool(getattr(p, 'is_goalie')) else '🏃'} {pname} ({ppos}){link_txt}"
                )
                r2.checkbox("Here", key=f"at_{pid}")
                if r3.button("📝", key=f"ed_{pid}"):
                    st.session_state.edit_id = pid
                    st.rerun()
                if r4.button("🗑️", key=f"del_{pid}"):
                    session.delete(p)
                    session.commit()
                    st.rerun()

    # --- TACTICAL GENERATOR ---
    st.divider()
    t_count = int(
        st.radio("Teams:", [2, 3],
                 horizontal=True,
                 key="tm_radio",
                 on_change=wipe_teams))

    if st.button("🎲 Generate Tactical Teams", use_container_width=True):
        wipe_teams()
        with SessionLocal() as session:
            present = [
                p for p in session.query(Player).all()
                if st.session_state.get(f"at_{int(getattr(p, 'id'))}", False)
            ]
            if len(present) < (t_count * 2):
                st.error("Need more players!")
                st.stop()

            teams = [[] for _ in range(t_count)]
            t_rates = [0.0 for _ in range(t_count)]
            assigned = set()

            def pick_and_assign(pool, count):
                random.shuffle(pool)
                for i in range(min(len(pool), count)):
                    idx = i % t_count
                    p = pool[i]
                    pname = str(getattr(p, 'name'))
                    if pname not in assigned:
                        teams[idx].append(
                            f"{pname} ({getattr(p, 'position')})")
                        t_rates[idx] += float(getattr(p, 'rating', 5))
                        assigned.add(pname)

            # 1. Goalies, 2. Tactical Core (DEF, MID, FWD)
            pick_and_assign(
                [p for p in present if bool(getattr(p, 'is_goalie'))], t_count)
            for pos in ["DEF", "MID", "FWD"]:
                available = [
                    p for p in present if str(getattr(p, 'position')) == pos
                    and str(getattr(p, 'name')) not in assigned
                ]
                pick_and_assign(available, t_count)

            # 3. Remaining (Balanced)
            remaining = [
                p for p in present if str(getattr(p, 'name')) not in assigned
            ]
            random.shuffle(remaining)
            groups, processed = [], set()
            for p in remaining:
                pn = str(getattr(p, 'name'))
                if pn in processed: continue
                pl = getattr(p, 'linked_to', None)
                partner = next(
                    (c for c in remaining if str(getattr(c, 'name')) != pn
                     and str(getattr(c, 'name')) not in processed and (
                         getattr(c, 'linked_to', '') == pn
                         or pl == getattr(c, 'name'))), None)
                if partner:
                    groups.append({
                        "n": [(pn, str(getattr(p, 'position'))),
                              (str(getattr(partner, 'name')),
                               str(getattr(partner, 'position')))],
                        "r":
                        float(getattr(p, 'rating')) +
                        float(getattr(partner, 'rating'))
                    })
                    processed.update([pn, str(getattr(partner, 'name'))])
                else:
                    groups.append({
                        "n": [(pn, str(getattr(p, 'position')))],
                        "r": float(getattr(p, 'rating'))
                    })
                    processed.add(pn)

            if "Fair" in match_logic:
                groups.sort(key=lambda x: x["r"], reverse=True)
            for g in groups:
                low = t_rates.index(min(t_rates))
                for nt in g["n"]:
                    teams[low].append(f"{nt[0]} ({nt[1]})")
                t_rates[low] += g["r"]

            for i, lbl in enumerate(['tA', 'tB', 'tC'][:t_count]):
                st.session_state[lbl] = {
                    "p":
                    "\n".join([f"{j+1}. {n}" for j, n in enumerate(teams[i])]),
                    "r": t_rates[i]
                }
            st.rerun()

    if "tA" in st.session_state:
        msg = f"🔴 TEAM A (Rating: {st.session_state.tA['r']})\n{st.session_state.tA['p']}\n\n🔵 TEAM B (Rating: {st.session_state.tB['r']})\n{st.session_state.tB['p']}"
        if t_count == 3 and "tC" in st.session_state:
            msg += f"\n\n🟢 TEAM C (Rating: {st.session_state.tC['r']})\n{st.session_state.tC['p']}"
        st.code(msg)
        st.markdown(
            f"[✈️ Share to Telegram](https://t.me/share/url?url={urllib.parse.quote(msg)})"
        )

# --- 5. WATCH REF MODE ---
else:
    st.title("⏱️ Watch Ref v3.0")
    if st.session_state.ref_3_teams is None:
        c1, c2 = st.columns(2)
        if c1.button("2 Teams Mode"):
            st.session_state.ref_3_teams = False
            st.rerun()
        if c2.button("3 Teams Mode"):
            st.session_state.ref_3_teams = True
            st.rerun()
    else:
        rots = [("RED", "BLUE", "GREEN"), ("BLUE", "GREEN", "RED"),
                ("GREEN", "RED", "BLUE")]
        cur = rots[st.session_state.rotation_idx %
                   3] if st.session_state.ref_3_teams else ("RED", "BLUE",
                                                            "WAIT")
        col1, col2, col3 = st.columns([2, 1, 2])
        with col1:
            st.subheader(cur[0])
            st.markdown(f"## {st.session_state.score_a}")
            if st.button("➕ Goal", key="ga"):
                st.session_state.score_a += 1
                st.rerun()
        with col2:
            if st.button("🔄"):
                st.session_state.score_a = 0
                st.session_state.score_b = 0
                st.rerun()
        with col3:
            st.subheader(cur[1])
            st.markdown(f"## {st.session_state.score_b}")
            if st.button("➕ Goal", key="gb"):
                st.session_state.score_b += 1
                st.rerun()
        if st.session_state.ref_3_teams:
            st.info(f"Waiting: {cur[2]}")
            if st.button("🔄 Next Match"):
                st.session_state.rotation_idx += 1
                st.session_state.score_a = 0
                st.session_state.score_b = 0
                st.rerun()
        if st.button("⚙️ Exit"):
            st.session_state.ref_3_teams = None
            st.rerun()
