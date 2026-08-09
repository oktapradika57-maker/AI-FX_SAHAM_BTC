import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import yfinance as yf
from datetime import datetime

# ==========================================
# 1. KONFIGURASI HALAMAN & PROTEKSI KODE
# ==========================================
st.set_page_config(page_title="Pro Quant Trading System", page_icon="⚡", layout="wide")

# CSS Untuk menyembunyikan menu Streamlit (Manage App, Github, Footer) dan memastikan sidebar hilang
hide_st_style = """
    <style>
    /* Sembunyikan menu 'tiga titik' di kanan atas (Manage App & Deploy) */
    [data-testid="stToolbar"] {visibility: hidden !important;}
    
    /* Sembunyikan footer bawaan Streamlit */
    footer {visibility: hidden !important;}
    
    /* Sembunyikan badge GitHub jika masih muncul */
    .viewerBadge_container__1QSob {display: none !important;}
    
    /* CSS Tampilan Metrik & Sinyal */
    .stMetric { background-color: #1e222d; padding: 15px; border-radius: 8px; border: 1px solid #2a2e39; }
    .sig-buy { background-color: #064e3b; color: #34d399; padding: 15px; border-radius: 8px; font-size: 24px; font-weight: bold; text-align: center; border: 1px solid #059669; }
    .sig-sell { background-color: #7f1d1d; color: #f87171; padding: 15px; border-radius: 8px; font-size: 24px; font-weight: bold; text-align: center; border: 1px solid #dc2626; }
    .sig-neutral { background-color: #374151; color: #d1d5db; padding: 15px; border-radius: 8px; font-size: 24px; font-weight: bold; text-align: center; border: 1px solid #6b7280; }
    </style>
"""
st.markdown(hide_st_style, unsafe_allow_html=True)

# ==========================================
# 2. DATABASE AMAN (SQLITE) & AUTO UPDATE WIN/LOSS
# ==========================================
def init_db():
    try:
        conn = sqlite3.connect("trading_db.sqlite", timeout=3)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS history 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, symbol TEXT, signal TEXT, 
                      entry REAL, tp REAL, sl REAL, timeframe TEXT, status TEXT DEFAULT 'PENDING')''')
        conn.commit()
        conn.close()
    except:
        pass

def save_signal(symbol, signal, entry, tp, sl, timeframe):
    try:
        conn = sqlite3.connect("trading_db.sqlite", timeout=3)
        c = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("INSERT INTO history (date, symbol, signal, entry, tp, sl, timeframe) VALUES (?, ?, ?, ?, ?, ?, ?)",
                  (now, symbol, signal, entry, tp, sl, timeframe))
        conn.commit()
        conn.close()
    except:
        pass

def get_history():
    try:
        conn = sqlite3.connect("trading_db.sqlite", timeout=3)
        df = pd.read_sql_query("SELECT * FROM history ORDER BY id DESC", conn)
        conn.close()
        return df
    except:
        return pd.DataFrame(columns=['id', 'date', 'symbol', 'signal', 'entry', 'tp', 'sl', 'timeframe', 'status'])

def manual_update_status(row_id, status):
    try:
        conn = sqlite3.connect("trading_db.sqlite", timeout=3)
        c = conn.cursor()
        c.execute("UPDATE history SET status = ? WHERE id = ?", (status, row_id))
        conn.commit()
        conn.close()
    except:
        pass

def auto_update_winloss(df_market, symbol):
    try:
        conn = sqlite3.connect("trading_db.sqlite", timeout=3)
        df_pending = pd.read_sql_query(f"SELECT * FROM history WHERE status = 'PENDING' AND symbol = '{symbol}'", conn)
        
        for _, row in df_pending.iterrows():
            entry_date = pd.to_datetime(row['date'])
            df_after_entry = df_market[df_market.index >= entry_date]
            
            if not df_after_entry.empty:
                high_tertinggi = df_after_entry['High'].max()
                low_terendah = df_after_entry['Low'].min()
                
                new_status = 'PENDING'
                if row['signal'] == 'BUY':
                    if high_tertinggi >= row['tp']: new_status = 'WIN'
                    elif low_terendah <= row['sl']: new_status = 'LOSS'
                elif row['signal'] == 'SELL':
                    if low_terendah <= row['tp']: new_status = 'WIN'
                    elif high_tertinggi >= row['sl']: new_status = 'LOSS'
                
                if new_status != 'PENDING':
                    c = conn.cursor()
                    c.execute("UPDATE history SET status = ? WHERE id = ?", (new_status, row['id']))
        conn.commit()
        conn.close()
    except Exception as e:
        pass

init_db()

# ==========================================
# 3. MENU PENGATURAN DI HALAMAN UTAMA (Tanpa Sidebar)
# ==========================================
st.title("⚡ Pro Quant Trading System")
st.markdown("### ⚙️ Pengaturan Market & Instrumen")

# Membagi menu dalam 3 kolom agar rapi
col_kat, col_aset, col_tf = st.columns(3)

with col_kat:
    kategori = st.selectbox("Kategori Market", ["Forex", "Gold / Komoditas", "Crypto", "Saham"])

daftar_aset = {
    "Forex": {"EUR/USD": "EURUSD=X", "GBP/USD": "GBPUSD=X", "USD/JPY": "JPY=X"},
    "Gold / Komoditas": {"Emas (Gold)": "GC=F", "Perak (Silver)": "SI=F", "Minyak WTI": "CL=F"},
    "Crypto": {"Bitcoin": "BTC-USD", "Ethereum": "ETH-USD"},
    "Saham": {"Apple": "AAPL", "Tesla": "TSLA", "NVIDIA": "NVDA"}
}

with col_aset:
    nama_aset = st.selectbox("Pilih Instrumen", list(daftar_aset[kategori].keys()))
    ticker = daftar_aset[kategori][nama_aset]

with col_tf:
    tf_pilihan = st.selectbox("Timeframe Acuan", ["1 Jam (H1)", "4 Jam (H4)", "1 Hari (D1)"], index=1)

# ==========================================
# 4. AMBIL DATA BULLETPROOF & NEWS
# ==========================================
@st.cache_data(ttl=60)
def get_market_data(symbol):
    try:
        df = yf.download(symbol, period="3mo", interval="1h", progress=False)
        if df is not None and not df.empty:
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            return df.dropna(), False
    except:
        pass
    
    np.random.seed(hash(symbol) % 2**32)
    dates = pd.date_range(end=datetime.now(), periods=200, freq='h')
    base_price = 2000 if "Gold" in symbol else (60000 if "Bitcoin" in symbol else 1.1)
    close = base_price + np.cumsum(np.random.randn(200) * (base_price * 0.002))
    df = pd.DataFrame({
        'Open': close + np.random.randn(200) * (base_price * 0.0005),
        'High': close + abs(np.random.randn(200) * (base_price * 0.001)),
        'Low': close - abs(np.random.randn(200) * (base_price * 0.001)),
        'Close': close,
        'Volume': np.random.randint(1000, 50000, 200)
    }, index=dates)
    return df, True

data, is_fallback = get_market_data(ticker)
auto_update_winloss(data, nama_aset)

if is_fallback:
    st.warning("⚠️ Mode Simulasi Aktif. (Tidak ada koneksi server)")

data['SMA_20'] = data['Close'].rolling(window=20).mean()
data['SMA_50'] = data['Close'].rolling(window=50).mean()
data['ATR'] = data['High'].rolling(14).max() - data['Low'].rolling(14).min()

delta = data['Close'].diff()
gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
rs = gain / loss
data['RSI'] = 100 - (100 / (1 + rs))

harga_now = float(data['Close'].iloc[-1])
rsi_now = float(data['RSI'].iloc[-1]) if not pd.isna(data['RSI'].iloc[-1]) else 50
sma20_now = float(data['SMA_20'].iloc[-1]) if not pd.isna(data['SMA_20'].iloc[-1]) else harga_now
sma50_now = float(data['SMA_50'].iloc[-1]) if not pd.isna(data['SMA_50'].iloc[-1]) else harga_now
atr_now = float(data['ATR'].iloc[-1]) if not pd.isna(data['ATR'].iloc[-1]) else harga_now * 0.01

# ==========================================
# 5. LOGIKA ANALISA & OPTIMAL ENTRY
# ==========================================
def analisa_kuantitatif(harga, rsi, sma20, sma50, atr):
    trend_up = harga > sma20 and sma20 > sma50
    trend_down = harga < sma20 and sma20 < sma50
    
    if trend_up and rsi < 70:
        signal = "BUY"
        ideal_entry = sma20 if harga > sma20 + (atr * 0.2) else harga
        sl = ideal_entry - (atr * 1.5)
        tp = ideal_entry + (atr * 3.0)
        reason = (f"🚀 **Sinyal BUY Tervalidasi**\n\n"
                  f"- **Tren & Arah:** Bullish kuat (Harga memotong ke atas SMA20 & SMA50).\n"
                  f"- **Momentum:** RSI di level {rsi:.1f} (Belum overbought, ruang naik terbuka).\n"
                  f"- **Strategi Entry (Pips Maksimal):** Harga pasar saat ini **{harga:.4f}**. "
                  f"Daripada Hajar Kanan, direkomendasikan antri *Buy Limit* di area **{ideal_entry:.4f}** "
                  f"sebagai pantulan Support dinamis agar target Profit lebih lebar.")
    elif trend_down and rsi > 30:
        signal = "SELL"
        ideal_entry = sma20 if harga < sma20 - (atr * 0.2) else harga
        sl = ideal_entry + (atr * 1.5)
        tp = ideal_entry - (atr * 3.0)
        reason = (f"📉 **Sinyal SELL Tervalidasi**\n\n"
                  f"- **Tren & Arah:** Bearish (Harga tertahan di bawah SMA20 & SMA50).\n"
                  f"- **Momentum:** RSI di level {rsi:.1f} (Masih ada tekanan seller).\n"
                  f"- **Strategi Entry (Pips Maksimal):** Harga pasar saat ini **{harga:.4f}**. "
                  f"Direkomendasikan *Sell Limit* di area pullback **{ideal_entry:.4f}** "
                  f"untuk menjaga Risk:Reward rasio tetap 1:2.")
    else:
        signal = "NEUTRAL"
        ideal_entry = harga
        sl = harga
        tp = harga
        reason = ("⚖️ **Market Konsolidasi / Wait & See**\n\n"
                  "Pergerakan harga saat ini tidak memiliki tren yang jelas atau terjepit di antara garis support dan resisten. "
                  "Sangat berisiko untuk entry karena rawan terkena *whipsaw* (sinyal palsu).")

    return {
        "signal": signal,
        "market_price": harga,
        "entry_price": ideal_entry,
        "tp_price": tp,
        "sl_price": sl,
        "risk_percent": "1.5 - 2",
        "est_time": "1 - 3 Hari",
        "reason": reason
    }

# ==========================================
# 6. TAMPILAN DASHBOARD & GRAFIK LIVE
# ==========================================
st.divider()
st.subheader(f"📊 Dashboard Analisis: {nama_aset}")
c1, c2, c3 = st.columns(3)
c1.metric("Harga Market Saat Ini", f"${harga_now:,.4f}" if harga_now < 10 else f"${harga_now:,.2f}")
c2.metric("RSI (14)", f"{rsi_now:.1f}")
c3.metric("Volatilitas (ATR)", f"${atr_now:,.4f}" if atr_now < 10 else f"${atr_now:,.2f}")

st.markdown("### 📈 Live Market Chart")
import plotly.graph_objects as go
fig = go.Figure(data=[go.Candlestick(
    x=data.index, open=data['Open'], high=data['High'], low=data['Low'], close=data['Close'], name="Candle"
)])

if 'hasil_analisa' in st.session_state:
    res = st.session_state['hasil_analisa']
    if res['signal'] != "NEUTRAL":
        fig.add_hline(y=res['entry_price'], line_dash="dash", line_color="#3b82f6", annotation_text="Ideal Entry")
        fig.add_hline(y=res['tp_price'], line_dash="solid", line_color="#10b981", annotation_text="Take Profit")
        fig.add_hline(y=res['sl_price'], line_dash="solid", line_color="#ef4444", annotation_text="Stop Loss")

fig.update_layout(template='plotly_dark', height=450, xaxis_rangeslider_visible=False, margin=dict(l=0, r=0, t=10, b=0))
st.plotly_chart(fig, use_container_width=True)

if st.button("🚀 JALANKAN ANALISA AI SEKARANG", type="primary", use_container_width=True):
    hasil = analisa_kuantitatif(harga_now, rsi_now, sma20_now, sma50_now, atr_now)
    st.session_state['hasil_analisa'] = hasil
    if hasil['signal'] != "NEUTRAL":
        save_signal(nama_aset, hasil['signal'], hasil['entry_price'], hasil['tp_price'], hasil['sl_price'], tf_pilihan)
    st.rerun()

if 'hasil_analisa' in st.session_state:
    res = st.session_state['hasil_analisa']
    st.divider()
    
    s1, s2, s3 = st.columns([1, 1, 1.5])
    sig = res['signal']
    
    with s1:
        if sig == 'BUY': st.markdown("<div class='sig-buy'>🟢 BUY SIGNAL</div>", unsafe_allow_html=True)
        elif sig == 'SELL': st.markdown("<div class='sig-sell'>🔴 SELL SIGNAL</div>", unsafe_allow_html=True)
        else: st.markdown("<div class='sig-neutral'>⚪ NEUTRAL</div>", unsafe_allow_html=True)
        st.write("")
        st.metric("Estimasi Durasi", res['est_time'])
        st.metric("Risiko Kapital", f"{res['risk_percent']}%")
        
    with s2:
        st.metric("🎯 Posisi Entry Ideal", f"${res['entry_price']:,.4f}", help="Antri di harga ini untuk pips maksimal")
        st.metric("📈 Take Profit (TP)", f"${res['tp_price']:,.4f}" if sig != "NEUTRAL" else "-")
        st.metric("🛑 Stop Loss (SL)", f"${res['sl_price']:,.4f}" if sig != "NEUTRAL" else "-")
        
    with s3:
        st.info(res['reason'])

# ==========================================
# 7. BERITA (NEWS) & SENTIMEN PENGARUH HARGA
# ==========================================
st.divider()
st.subheader("📰 Market News & Sentimen AI (Faktor Fundamental)")
try:
    news_data = yf.Ticker(ticker).news[:4]
    if len(news_data) > 0:
        for n in news_data:
            title = n.get('title', 'No Title')
            link = n.get('link', '#')
            publisher = n.get('publisher', 'Unknown')
            
            title_lower = title.lower()
            bullish_kw = ['surge', 'jump', 'gain', 'high', 'up', 'bull', 'growth', 'soar', 'positive']
            bearish_kw = ['drop', 'fall', 'loss', 'low', 'down', 'bear', 'crash', 'plunge', 'negative']
            
            sentimen = "⚪ Netral (Tidak Ada Dampak Kuat)"
            if any(word in title_lower for word in bullish_kw): 
                sentimen = "🟢 Positif (Potensi Mendorong Harga Naik)"
            elif any(word in title_lower for word in bearish_kw): 
                sentimen = "🔴 Negatif (Potensi Mendorong Harga Turun)"
                
            st.markdown(f"**[{title}]({link})** — *{publisher}*")
            st.caption(f"🤖 **Dampak Pasar:** {sentimen}")
    else:
        st.write("Tidak ada berita signifikan hari ini.")
except Exception as e:
    st.write("Sedang tidak dapat memuat berita untuk aset ini.")

# ==========================================
# 8. WIN RATE & HISTORY (AUTO & MANUAL)
# ==========================================
st.divider()
st.subheader("🏆 Jurnal Trading & Win Rate Tracker (Otomatis)")

df_hist = get_history()
if not df_hist.empty:
    total = len(df_hist)
    win = len(df_hist[df_hist['status'] == 'WIN'])
    loss = len(df_hist[df_hist['status'] == 'LOSS'])
    selesai = win + loss
    winrate = (win / selesai * 100) if selesai > 0 else 0
    
    w1, w2, w3, w4 = st.columns(4)
    w1.metric("Total Sinyal Plan", total)
    w2.metric("🎯 Kena TP (WIN)", win)
    w3.metric("🛑 Kena SL (LOSS)", loss)
    w4.metric("🏆 Akurasi Win Rate", f"{winrate:.1f}%")
    
    st.write("*Catatan: Status berubah otomatis menjadi WIN/LOSS jika harga market menyentuh TP/SL setelah sinyal dikeluarkan.*")
    
    for _, row in df_hist.head(10).iterrows():
        with st.expander(f"{row['date']} | {row['symbol']} - {row['signal']} (Status: {row['status']})"):
            st.write(f"Harga Entry Plan: {row['entry']:.4f} | TP: {row['tp']:.4f} | SL: {row['sl']:.4f}")
            if row['status'] == 'PENDING':
                b1, b2 = st.columns(2)
                if b1.button("✅ Paksa Set WIN", key=f"w_{row['id']}"):
                    manual_update_status(row['id'], 'WIN')
                    st.rerun()
                if b2.button("❌ Paksa Set LOSS", key=f"l_{row['id']}"):
                    manual_update_status(row['id'], 'LOSS')
                    st.rerun()
else:
    st.info("Belum ada histori sinyal.")
