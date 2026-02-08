import streamlit as st
import pandas as pd
import yfinance as yf
import requests
from ta.trend import EMAIndicator, ADXIndicator
from ta.volatility import AverageTrueRange
from streamlit_autorefresh import st_autorefresh
import datetime
import json
import os
import base64
from zoneinfo import ZoneInfo

# ─────────────────────────────────────────────
# PERSISTANCE : SYNC AUTOMATIQUE GITHUB
# ─────────────────────────────────────────────
def sync_to_github(file_path, data):
    try:
        if "GITHUB_TOKEN" not in st.secrets:
            return

        token = st.secrets["GITHUB_TOKEN"]
        repo = st.secrets["GITHUB_REPO"]
        url = f"https://api.github.com/repos/{repo}/contents/{file_path}"

        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }

        res = requests.get(url, headers=headers)
        sha = res.json().get("sha") if res.status_code == 200 else None

        content = base64.b64encode(json.dumps(data, indent=4).encode()).decode()
        payload = {
            "message": f"Update {file_path} via Sniper Auto-Backup",
            "content": content
        }

        if sha:
            payload["sha"] = sha

        requests.put(url, headers=headers, json=payload)
    except:
        pass

# ─────────────────────────────────────────────
# FICHIERS
# ─────────────────────────────────────────────
DB_FILE = "active_trades_db.json"
HISTORY_FILE = "trade_history_db.json"

if "sent_signals" not in st.session_state:
    st.session_state["sent_signals"] = set()

def load_json(file):
    if os.path.exists(file):
        try:
            with open(file, "r") as f:
                return json.load(f)
        except:
            return {} if file == DB_FILE else []
    # Si le fichier n'existe pas, on renvoie une structure vide propre
    return {} if file == DB_FILE else []

def save_json(file, data):
    with open(file, "w") as f:
        json.dump(data, f)
    sync_to_github(file, data)

# ─────────────────────────────────────────────
# TELEGRAM
# ─────────────────────────────────────────────
if "TOKEN_TELEGRAM" not in st.session_state:
    st.session_state["TOKEN_TELEGRAM"] = "8150058407:AAFg44ySihFKBO1UW69QZqi07otqeB2IK5s"
if "CHAT_ID" not in st.session_state:
    st.session_state["CHAT_ID"] = "1148025596"

def send_telegram_msg(message):
    try:
        requests.get(
            f"https://api.telegram.org/bot{st.session_state['TOKEN_TELEGRAM']}/sendMessage",
            params={"chat_id": st.session_state["CHAT_ID"], "text": message},
            timeout=10
        )
    except:
        pass

# ─────────────────────────────────────────────
# SESSION TRADING
# ─────────────────────────────────────────────
def is_trading_session(category):
    if category == "CRYPTO":
        return True

    now = datetime.datetime.now(ZoneInfo("Europe/Paris"))
    if now.weekday() >= 5:
        return False
    return 8 <= now.hour < 20

# ─────────────────────────────────────────────
# PIP FACTOR
# ─────────────────────────────────────────────
def pip_factor(pair):
    if "BTC" in pair:
        return 1
    return 100 if "JPY" in pair else 10000

# ─────────────────────────────────────────────
# CONFIG STREAMLIT
# ─────────────────────────────────────────────
st.set_page_config(page_title="Sniper V17.1 — High Winrate Engine", layout="wide")
st_autorefresh(interval=180000, key="refresh")

# Chargement initial des fichiers
active_trades = load_json(DB_FILE)
history_trades = load_json(HISTORY_FILE)

# ─────────────────────────────────────────────
# ACTIFS
# ─────────────────────────────────────────────
ASSETS = {
    "FOREX": [
        "EURUSD=X","GBPUSD=X","USDJPY=X","AUDUSD=X","USDCAD=X","USDCHF=X","NZDUSD=X",
        "EURGBP=X","EURJPY=X","GBPJPY=X","EURAUD=X","EURCAD=X","EURCHF=X","EURNZD=X",
        "GBPAUD=X","GBPCAD=X","GBPCHF=X","GBPNZD=X",
        "AUDJPY=X","AUDCAD=X","AUDCHF=X","AUDNZD=X",
        "CADJPY=X","CADCHF=X","CHFJPY=X",
        "NZDJPY=X","NZDCAD=X","NZDCHF=X"
    ],
    "CRYPTO": ["BTC-USD"]
}

# ─────────────────────────────────────────────
# MOTEUR PRINCIPAL
# ─────────────────────────────────────────────
def run_engine():
    results = []
    tickers = [t for cat in ASSETS.values() for t in cat]

    data_m15 = yf.download(tickers, period="7d", interval="15m", group_by="ticker", progress=False, threads=False)
    data_h1  = yf.download(tickers, period="30d", interval="1h", group_by="ticker", progress=False, threads=False)
    data_d1  = yf.download(tickers, period="200d", interval="1d", group_by="ticker", progress=False, threads=False)

    for category, symbols in ASSETS.items():
        for ticker in symbols:
            try:
                name = ticker.replace("=X","").replace("-USD","USD")

                df_m15 = data_m15[ticker].dropna()
                df_h1  = data_h1[ticker].dropna()
                df_d1  = data_d1[ticker].dropna()

                close = float(df_m15["Close"].iloc[-1])
                open_ = float(df_m15["Open"].iloc[-1])
                high = float(df_m15["High"].iloc[-1])
                low  = float(df_m15["Low"].iloc[-1])

                # --- GESTION DES SORTIES (POUR L'HISTORIQUE) ---
                if name in active_trades:
                    trade = active_trades[name]
                    is_win, is_loss = False, False
                    if trade["type"] == "ACHAT 🚀":
                        if close >= trade["tp"]: is_win = True
                        elif close <= trade["sl"]: is_loss = True
                    else:
                        if close <= trade["tp"]: is_win = True
                        elif close >= trade["sl"]: is_loss = True
                    
                    if is_win or is_loss:
                        # Re-charger le contenu actuel du fichier avant d'ajouter
                        current_hist = load_json(HISTORY_FILE)
                        current_hist.append({
                            "Date": datetime.datetime.now().strftime("%d/%m %H:%M"),
                            "Actif": name, "Type": trade["type"], "Résultat": "✅ WIN" if is_win else "❌ LOSS", "RR": trade["rr"] if is_win else -1.0
                        })
                        save_json(HISTORY_FILE, current_hist)
                        del active_trades[name]
                        save_json(DB_FILE, active_trades)
                    continue 

                # Initialisation par défaut pour affichage
                signal = "ATTENDRE"
                comment = "Analyse..."
                sl = tp = rr = None

                atr_m15 = AverageTrueRange(df_m15["High"], df_m15["Low"], df_m15["Close"], 14).average_true_range().iloc[-1]

                # === CONTEXTE DAILY ===
                ema200_d1 = EMAIndicator(df_d1["Close"], 200).ema_indicator().iloc[-1]
                daily_trend_up = close > ema200_d1
                daily_trend_dn = close < ema200_d1

                # === CONTEXTE H1 ===
                ema200_h1 = EMAIndicator(df_h1["Close"], 200).ema_indicator().iloc[-1]
                ema50_h1  = EMAIndicator(df_h1["Close"], 50).ema_indicator().iloc[-1]
                close_h1  = df_h1["Close"].iloc[-1]

                trend_up = close_h1 > ema200_h1 and ema50_h1 > ema200_h1
                trend_dn = close_h1 < ema200_h1 and ema50_h1 < ema200_h1

                adx_h1 = ADXIndicator(df_h1["High"], df_h1["Low"], df_h1["Close"]).adx().iloc[-1]
                
                # === EMA M15 ===
                ema20_m15 = EMAIndicator(df_m15["Close"], 20).ema_indicator().iloc[-1]
                ema50_m15 = EMAIndicator(df_m15["Close"], 50).ema_indicator().iloc[-1]

                # === PULLBACK ZONE ===
                pullback_buy = low <= ema50_m15 and close > ema20_m15
                pullback_sell = high >= ema50_m15 and close < ema20_m15

                bullish_rejection = close > open_ and (close - low) / (high - low + 1e-6) > 0.6
                bearish_rejection = close < open_ and (high - close) / (high - low + 1e-6) > 0.6

                # LOGIQUE DE DÉCISION
                if not is_trading_session(category):
                    comment = "Hors session"
                elif adx_h1 < 18 or adx_h1 > 35:
                    comment = f"ADX Faible/Fort ({round(adx_h1,1)})"
                elif trend_up and daily_trend_up:
                    if pullback_buy and bullish_rejection:
                        signal = "ACHAT 🚀"
                        comment = "Pullback + Daily OK"
                        lowest_pullback = df_m15["Low"].iloc[-5:].min()
                        sl = lowest_pullback - atr_m15 * 0.8
                        tp = close + (close - sl) * 1.2
                    else:
                        comment = "Attente Pullback Haussier"
                elif trend_dn and daily_trend_dn:
                    if pullback_sell and bearish_rejection:
                        signal = "VENTE 🔻"
                        comment = "Pullback + Daily OK"
                        highest_pullback = df_m15["High"].iloc[-5:].max()
                        sl = highest_pullback + atr_m15 * 0.8
                        tp = close - (sl - close) * 1.2
                    else:
                        comment = "Attente Pullback Baissier"
                else:
                    comment = "Tendance D1/H1 non alignée"

                if signal != "ATTENDRE":
                    rr = abs(tp - close) / abs(close - sl)

                factor = pip_factor(name)

                results.append({
                    "Actif": name,
                    "Catégorie": category,
                    "Signal": signal,
                    "Fiabilité": "🟢 High Winrate" if signal != "ATTENDRE" else "-",
                    "Prix": round(close, 2 if category=="CRYPTO" else 5),
                    "SL Prix": round(sl,5) if sl else "-",
                    "SL Pips": round(abs(close-sl)*factor,1) if sl else "-",
                    "TP Prix": round(tp,5) if tp else "-",
                    "TP Pips": round(abs(tp-close)*factor,1) if tp else "-",
                    "Commentaire": comment
                })

                if signal in ["ACHAT 🚀", "VENTE 🔻"] and name not in active_trades:
                    active_trades[name] = {
                        "type": signal, "entry": round(close,5), "sl": round(sl,5), "tp": round(tp,5), "rr": round(rr,2), "timestamp": datetime.datetime.now().isoformat()
                    }
                    save_json(DB_FILE, active_trades)
                    send_telegram_msg(f"🦅 SNIPER V17.1\n{name} {signal}\nAlignement: H1+D1 OK\nEntry: {close}\nSL: {sl}\nTP: {tp}\nRR: {round(rr,2)}")

            except:
                continue
    return results

# ─────────────────────────────────────────────
# AFFICHAGE
# ─────────────────────────────────────────────
st.title("🦅 Sniper V17.1 — High Winrate Engine")

# --- SECTION HISTORIQUE ---
st.header("📊 Historique de Performance")

# Charger les données (même si le fichier n'existe pas encore, load_json gère le cas)
history_data = load_json(HISTORY_FILE)
df_hist = pd.DataFrame(history_data)

if not df_hist.empty:
    win_count = len(df_hist[df_hist["Résultat"] == "✅ WIN"])
    total_trades = len(df_hist)
    winrate = (win_count / total_trades * 100) if total_trades > 0 else 0
    total_rr = df_hist["RR"].sum()

    col1, col2, col3 = st.columns(3)
    col1.metric("Winrate", f"{round(winrate,1)}%")
    col2.metric("Trades Clôturés", total_trades)
    col3.metric("Gain Cumulé (RR)", f"{round(total_rr,2)} R")

    with st.expander("Voir le détail historique", expanded=True):
        st.table(df_hist.tail(20))
else:
    # On affiche le titre mais avec un message d'attente si vide
    st.info("L'historique apparaîtra ici dès qu'un trade actif touchera son TP ou son SL.")

# --- SECTION SIGNAUX ---
st.header("🎯 Signaux en Direct")
data_results = run_engine()
if data_results:
    st.dataframe(pd.DataFrame(data_results), use_container_width=True)

with st.sidebar:
    if st.button("📩 Test Telegram"):
        send_telegram_msg("✅ Test Telegram réussi depuis Sniper V17.1")
        st.success("Message envoyé")
    if st.button("🗑 Réinitialiser Verrous"):
        if os.path.exists(DB_FILE): os.remove(DB_FILE)
        st.success("Verrous supprimés")
    if st.button("🔴 Effacer Historique"):
        if os.path.exists(HISTORY_FILE): 
            os.remove(HISTORY_FILE)
            save_json(HISTORY_FILE, []) # Crée un fichier vide pour l'initialisation
        st.success("Historique vidé")
