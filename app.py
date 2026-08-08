import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import sqlite3
from datetime import datetime

# ==========================================
# 1. KONFIGURASI TAMPILAN HALAMAN
# ==========================================
st.set_page_config(page_title="Pro Quant Trading System", page_icon="⚡", layout="wide")

st.markdown("""
    <style>
    .stMetric { background-color: #1e222d; padding: 15px; border-radius: 8px; border: 1px solid #2a2e39; }
    .sig-buy { background-color: #064e3b; color: #34d399; padding: 15px; border-radius: 8px; font-size: 24px; font-weight: bold; text-align: center; border: 1px solid #059669; }
    .sig-sell { background-color: #7f1d1d; color: #f87171; padding: 15px; border-radius: 8px; font-size: 24px; font-weight: bold; text-align: center; border: 1px solid #dc2626; }
    .sig-neutral { background-color: #374151; color: #d1d5db; padding: 15px; border-radius: 8px; font-size: 24px; font-weight: bold; text-align: center; border: 1px solid #6b7280; }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. DATABASE UNTUK HISTORY & WIN RATE
# ==========================================
def init_db():
    try:
        conn = sqlite3.connect("trading_db.sqlite", timeout=5)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS history 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, symbol TEXT, signal TEXT, 
                      entry REAL, tp REAL, sl REAL, timeframe TEXT, status TEXT DEFAULT 'PENDING')''')
        conn.commit()
        conn.close()
    except Exception:
        pass

def save_signal(symbol, signal, entry, tp, sl, timeframe):
    try:
        conn = sqlite3.connect("trading_db.sqlite", timeout=5)
        c = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("INSERT INTO history (date, symbol, signal, entry, tp, sl, timeframe) VALUES (?, ?, ?, ?, ?, ?, ?)",
                  (now, symbol, signal, entry, tp, sl, timeframe))
        conn.commit()
        conn.close()
    except Exception:
        pass

def get_history():
    try:
        conn = sqlite3.connect("trading_db.sqlite", timeout=5)
        df = pd.read_sql_query("SELECT * FROM history ORDER BY id DESC", conn)
        conn.close()
        return df
    except Exception:
        return pd.DataFrame(columns=['id', 'date', 'symbol', 'signal', 'entry', 'tp', 'sl', 'timeframe', 'status'])

def update_status(row_id, status):
    try:
        conn = sqlite3.connect("trading_db.sqlite", timeout=5)
        c = conn.cursor()
        c.execute("UPDATE history SET status = ? WHERE id = ?", (status, row_id))
        conn.commit()
        conn.close()
    except Exception:
        pass

init_db()

# ==========================================
# 3. PENGATURAN INSTRUMEN (SIDEBAR)
# ==========================================
st.sidebar.title("⚡ Quant Analyzer")
kategori = st.sidebar.selectbox("Kategori Market", ["Forex", "Gold / Komoditas", "Crypto", "Saham"])
daftar_aset = {
    "Forex": {"EUR/USD": "EURUSD=X", "GBP/USD": "GBPUSD=X", "USD/JPY": "JPY=X"},
    "Gold / Komoditas": {"Emas (Gold)": "GC=F", "Perak (Silver)": "SI=F", "Minyak WTI": "CL=F"},
    "Crypto": {"Bitcoin": "BTC-USD", "Ethereum": "ETH-USD"},
    "Saham": {"Apple": "AAPL", "Tesla": "TSLA", "NVIDIA": "NVDA"}
}
nama_aset = st.sidebar.selectbox("Pilih Instrumen", list(daftar_aset[kategori].keys()))
ticker = daftar_aset[kategori][nama_aset]

tf_pilihan = st.sidebar.selectbox("Timeframe Acuan", ["1 Jam (H1)", "4 Jam (H4)", "1 Hari (D1)"], index=1)
tf_config = {"1 Jam (H1)": ("1mo", "1h"), "4 Jam (H4)": ("3mo", "1h"), "1 Hari (D1)": ("1y", "1d")}

# ==========================================
# 4. AMBIL DATA DENGAN AMAN (ANTI-HANG)
# ==========================================
@st.cache_data(ttl=300, show_spinner="Menghubungkan ke server data pasar...")
def fetch_market_data(symbol, period, interval):
    try:
        # Menggunakan timeout terselubung agar tidak nge-hang selamanya
        df = yf.download(symbol, period=period, interval=interval, progress=False, timeout=10)
        if df is None or df.empty:
            return pd.DataFrame()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df.dropna()
    except Exception:
        return pd.DataFrame()

# Indikator Loading khusus untuk data
with st.spinner(f"Memuat grafik dan data {nama_aset}..."):
    data = fetch_market_data(ticker, tf_config[tf_pilihan][0], tf_config[tf_pilihan][1])

if data.empty:
    st.error(f"Gagal menarik data untuk {nama_aset}. Kemungkinan koneksi internet terganggu atau server Yahoo Finance sedang sibuk. Silakan ubah instrumen atau klik tombol *Reload* di browser.")
    st.stop()

# Perhitungan Indikator Kuantitatif
data['SMA_20'] = data['Close'].rolling(window=20).mean()
data['SMA_50'] = data['Close'].rolling(window=50).mean()
data['ATR'] = data['High'].rolling(14).max() - data['Low'].rolling(14).min()

delta = data['Close'].diff()
gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
rs = gain / loss
data['RSI'] = 100 - (100 / (1 + rs))

# Ambil Nilai Terakhir
harga_now = float(data['Close'].iloc[-1])
rsi_now = float(data['RSI'].iloc[-1]) if not pd.isna(data['RSI'].iloc[-1]) else 50
sma20_now = float(data['SMA_20'].iloc[-1]) if not pd.isna(data['SMA_20'].iloc[-1]) else harga_now
sma50_now = float(data['SMA_50'].iloc[-1]) if not pd.isna(data['SMA_50'].iloc[-1]) else harga_now
atr_now = float(data['ATR'].iloc[-1]) if not pd.isna(data['ATR'].iloc[-1]) else harga_now * 0.01

# ==========================================
# 5. ALGORITMA PENGAMBIL KEPUTUSAN
# ==========================================
def analisa_kuantitatif(harga, rsi, sma20, sma50, atr):
    trend_up = harga > sma20 and sma20 > sma50
    trend_down = harga < sma20 and sma20 < sma50
    
    if trend_up and rsi < 70:
        signal = "BUY"
        sl = harga - (atr * 1.5)
        tp = harga + (atr * 3.0)
        reason = f"Harga bergerak di atas SMA 20 & 50 menandakan Uptrend yang kuat. RSI ({rsi:.1f}) masih memiliki ruang naik."
    elif trend_down and rsi > 30:
        signal = "SELL"
        sl = harga + (atr * 1.5)
        tp = harga - (atr * 3.0)
        reason = f"Harga berada di bawah SMA 20 & 50 menandakan Downtrend. RSI ({rsi:.1f}) menunjukkan tekanan jual masih dominan."
    else:
        signal = "NEUTRAL"
        sl = harga
        tp = harga
        reason = "Market sedang konsolidasi atau sideway. Disarankan wait and see karena belum ada konfirmasi tren yang kuat."

    # Berita aman (tanpa blocking request berat)
    news = f"Analisis sentimen berbasis momentum harga terkini untuk {nama_aset} pada timeframe {tf_pilihan}."

    return {
        "signal": signal,
        "entry_price": harga,
        "tp_price": tp,
        "sl_price": sl,
        "risk_percent": "1.5 - 2",
        "est_time": "1 - 3 Hari Kedepan",
        "news": news,
        "reason": reason
    }

# ==========================================
# 6. HEADER & DASHBOARD
# ==========================================
st.title(f"📊 Live Market Analysis: {nama_aset}")
c1, c2, c3 = st.columns(3)
c1.metric("Harga Live", f"${harga_now:,.4f}" if harga_now < 10 else f"${harga_now:,.2f}")
c2.metric("RSI (14)", f"{rsi_now:.1f}")
c3.metric("Volatilitas (ATR)", f"${atr_now:,.4f}" if atr_now < 10 else f"${atr_now:,.2f}")

if st.button("🚀 JALANKAN ANALISA SEKARANG", type="primary", use_container_width=True):
    with st.spinner("Mengalkulasi indikator teknikal & level harga..."):
        hasil = analisa_kuantitatif(harga_now, rsi_now, sma20_now, sma50_now, atr_now)
        st.session_state['hasil_analisa'] = hasil
        if hasil['signal'] != "NEUTRAL":
            save_signal(nama_aset, hasil['signal'], hasil['entry_price'], hasil['tp_price'], hasil['sl_price'], tf_pilihan)
        st.success("Analisa selesai & direkam!")

# ==========================================
# 7. TAMPILAN HASIL ANALISA & CHART
# ==========================================
if 'hasil_analisa' in st.session_state:
    res = st.session_state['hasil_analisa']
    st.divider()
    
    s1, s2, s3 = st.columns([1, 1, 1])
    sig = res['signal']
    
    with s1:
        if sig == 'BUY': st.markdown("<div class='sig-buy'>🟢 BUY SIGNAL</div>", unsafe_allow_html=True)
        elif sig == 'SELL': st.markdown("<div class='sig-sell'>🔴 SELL SIGNAL</div>", unsafe_allow_html=True)
        else: st.markdown("<div class='sig-neutral'>⚪ NEUTRAL</div>", unsafe_allow_html=True)
        st.write("")
        st.metric("Estimasi Waktu", res['est_time'])
        st.metric("Saran Risiko Modal", f"{res['risk_percent']}%")
        
    with s2:
        st.metric("🎯 Titik Entry", f"${res['entry_price']:,.4f}")
        st.metric("📈 Take Profit (TP)", f"${res['tp_price']:,.4f}" if sig != "NEUTRAL" else "-")
        st.metric("🛑 Stop Loss (SL)", f"${res['sl_price']:,.4f}" if sig != "NEUTRAL" else "-")
        
    with s3:
        st.info(f"📰 **Sentimen Makro:**\n\n{res['news']}")
        st.success(f"💡 **Alasan Algoritma:**\n\n{res['reason']}")

    st.subheader("📈 Visualisasi Target TP / SL di Market")
    fig = go.Figure(data=[go.Candlestick(
        x=data.index, open=data['Open'], high=data['High'], low=data['Low'], close=data['Close'], name="Candle"
    )])
    
    if sig != "NEUTRAL":
        fig.add_hline(y=res['entry_price'], line_dash="dash", line_color="blue", annotation_text="Entry")
        fig.add_hline(y=res['tp_price'], line_dash="solid", line_color="green", annotation_text="TP")
        fig.add_hline(y=res['sl_price'], line_dash="solid", line_color="red", annotation_text="SL")
    
    fig.update_layout(template='plotly_dark', height=500, xaxis_rangeslider_visible=False, margin=dict(l=0, r=0, t=10, b=0))
    st.plotly_chart(fig, use_container_width=True)

# ==========================================
# 8. SISTEM WIN RATE & RECORD TRACKER
# ==========================================
st.divider()
st.subheader("🏆 Jurnal Trading & Win Rate Tracker")

df_hist = get_history()
if not df_hist.empty:
    total = len(df_hist)
    win = len(df_hist[df_hist['status'] == 'WIN'])
    loss = len(df_hist[df_hist['status'] == 'LOSS'])
    selesai = win + loss
    winrate = (win / selesai * 100) if selesai > 0 else 0
    
    w1, w2, w3, w4 = st.columns(4)
    w1.metric("Total Sinyal Terekam", total)
    w2.metric("Target Tercapai (WIN)", win)
    w3.metric("Gagal (LOSS)", loss)
    w4.metric("Akurasi (Win Rate %)", f"{winrate:.1f}%")
    
    st.markdown("### Histori & Update Status Sinyal")
    for _, row in df_hist.head(10).iterrows():
        with st.expander(f"{row['date']} | {row['symbol']} - {row['signal']} (Status: {row['status']})"):
            st.write(f"Entry: **{row['entry']:.4f}** | TP: **{row['tp']:.4f}** | SL: **{row['sl']:.4f}**")
            if row['status'] == 'PENDING':
                b1, b2 = st.columns(2)
                if b1.button("✅ Kena TP (WIN)", key=f"w_{row['id']}"):
                    update_status(row['id'], 'WIN')
                    st.rerun()
                if b2.button("❌ Kena SL (LOSS)", key=f"l_{row['id']}"):
                    update_status(row['id'], 'LOSS')
                    st.rerun()
else:
    st.info("Belum ada histori sinyal. Tekan tombol analisa di atas untuk mulai merekam data.")
