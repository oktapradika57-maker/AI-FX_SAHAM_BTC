import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
import google.generativeai as genai
import pandas as pd
import sqlite3
import json
from datetime import datetime

# ==========================================
# 1. KONFIGURASI TAMPILAN HALAMAN
# ==========================================
st.set_page_config(page_title="AI Pro Trading Assistant", page_icon="📈", layout="wide")

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
    conn = sqlite3.connect("trading_db.sqlite")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS history 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, symbol TEXT, signal TEXT, 
                  entry REAL, tp REAL, sl REAL, timeframe TEXT, status TEXT DEFAULT 'PENDING')''')
    conn.commit()
    conn.close()

def save_signal(symbol, signal, entry, tp, sl, timeframe):
    conn = sqlite3.connect("trading_db.sqlite")
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT INTO history (date, symbol, signal, entry, tp, sl, timeframe) VALUES (?, ?, ?, ?, ?, ?, ?)",
              (now, symbol, signal, entry, tp, sl, timeframe))
    conn.commit()
    conn.close()

def get_history():
    conn = sqlite3.connect("trading_db.sqlite")
    df = pd.read_sql_query("SELECT * FROM history ORDER BY id DESC", conn)
    conn.close()
    return df

def update_status(row_id, status):
    conn = sqlite3.connect("trading_db.sqlite")
    c = conn.cursor()
    c.execute("UPDATE history SET status = ? WHERE id = ?", (status, row_id))
    conn.commit()
    conn.close()

init_db()

# ==========================================
# 3. SIDEBAR: PENGATURAN & API KEY
# ==========================================
st.sidebar.title("⚙️ AI Trading Setup")
api_key = st.sidebar.text_input("Gemini API Key", type="password", placeholder="Masukkan API Key (AIza... atau AQ...)")

kategori = st.sidebar.selectbox("Kategori Market", ["Forex", "Gold / Komoditas", "Crypto", "Saham"])
daftar_aset = {
    "Forex": {"EUR/USD": "EURUSD=X", "GBP/USD": "GBPUSD=X", "USD/JPY": "JPY=X"},
    "Gold / Komoditas": {"Emas (Gold)": "GC=F", "Minyak (WTI)": "CL=F"},
    "Crypto": {"Bitcoin": "BTC-USD", "Ethereum": "ETH-USD"},
    "Saham": {"Apple": "AAPL", "NVIDIA": "NVDA", "Tesla": "TSLA"}
}
nama_aset = st.sidebar.selectbox("Pilih Instrumen", list(daftar_aset[kategori].keys()))
ticker = daftar_aset[kategori][nama_aset]

tf_pilihan = st.sidebar.selectbox("Timeframe Acuan", ["1 Jam (H1)", "4 Jam (H4)", "1 Hari (D1)"], index=1)
tf_config = {"1 Jam (H1)": ("1mo", "1h"), "4 Jam (H4)": ("3mo", "1h"), "1 Hari (D1)": ("1y", "1d")}

# ==========================================
# 4. AMBIL DATA MARKET REAL-TIME
# ==========================================
@st.cache_data(ttl=300)
def fetch_data(symbol, period, interval):
    df = yf.download(symbol, period=period, interval=interval, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df.dropna()

data = fetch_data(ticker, tf_config[tf_pilihan][0], tf_config[tf_pilihan][1])

if data.empty:
    st.error("Gagal menarik data pasar. Coba ganti instrumen atau timeframe.")
    st.stop()

# Hitung Indikator (RSI & SMA 20)
delta = data['Close'].diff()
gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
rs = gain / loss
data['RSI'] = 100 - (100 / (1 + rs))
data['SMA_20'] = data['Close'].rolling(window=20).mean()

harga_sekarang = float(data['Close'].iloc[-1])
rsi_sekarang = float(data['RSI'].iloc[-1]) if not pd.isna(data['RSI'].iloc[-1]) else 50
sma_sekarang = float(data['SMA_20'].iloc[-1]) if not pd.isna(data['SMA_20'].iloc[-1]) else harga_sekarang

# ==========================================
# 5. FUNGSI ANALISA AI (DENGAN FALLBACK)
# ==========================================
def analisa_ai(api_key, symbol, harga, rsi, sma, tf):
    genai.configure(api_key=api_key)
    
    # AI akan mencoba model-model ini secara berurutan agar tahan banting (anti error 404)
    model_list = ['gemini-1.5-flash', 'gemini-1.5-flash-latest', 'gemini-pro']
    
    prompt = f"""
    Anda adalah analis trading institusional. Analisa {symbol} di harga {harga}.
    Indikator: RSI(14)={rsi:.2f}, SMA(20)={sma:.2f}. Timeframe: {tf}.
    
    Tugas Anda:
    1. Buat rekomendasi BUY, SELL, atau NEUTRAL berdasarkan perpaduan teknikal & berita fundamental terbaru.
    2. Tentukan harga Entry, Take Profit (TP), dan Stop Loss (SL).
    
    WAJIB BALAS DENGAN FORMAT JSON VALID SEPERTI INI SAJA (TANPA ```json ATAU TEKS LAINNYA):
    {{
      "signal": "BUY",
      "entry_price": {harga},
      "tp_price": 0.0,
      "sl_price": 0.0,
      "risk_percent": "1-2",
      "est_time": "12-24 Jam",
      "news": "Ringkasan berita makro/fundamental terbaru",
      "reason": "Alasan teknikal konkrit"
    }}
    """
    
    for m in model_list:
        try:
            model = genai.GenerativeModel(m)
            response = model.generate_content(prompt)
            # Bersihkan format jika AI masih membandel memberikan markdown
            clean_text = response.text.replace("```json", "").replace("```", "").strip()
            return json.loads(clean_text)
        except Exception as e:
            if "404" in str(e):
                continue # Coba model berikutnya
            else:
                return {"error": str(e)}
    return {"error": "API Key tidak mendukung model AI yang tersedia. Pastikan API key aktif."}

# ==========================================
# 6. HEADER & DASHBOARD UTAMA
# ==========================================
st.title(f"📊 Dashboard AI: {nama_aset}")
c1, c2, c3 = st.columns(3)
c1.metric("Harga Saat Ini", f"${harga_sekarang:,.4f}" if harga_sekarang < 10 else f"${harga_sekarang:,.2f}")
c2.metric("Indikator RSI (14)", f"{rsi_sekarang:.1f}")
c3.metric("Indikator SMA (20)", f"${sma_sekarang:,.2f}")

if st.button("🚀 MULAI ANALISA AI SEKARANG", type="primary", use_container_width=True):
    if not api_key:
        st.warning("Silakan masukkan Gemini API Key di menu samping kiri terlebih dahulu!")
    else:
        with st.spinner("AI sedang membaca berita pasar dan menghitung level teknikal..."):
            hasil = analisa_ai(api_key, nama_aset, harga_sekarang, rsi_sekarang, sma_sekarang, tf_pilihan)
            
            if "error" in hasil:
                st.error(f"Terjadi kesalahan: {hasil['error']}")
            else:
                st.session_state['hasil_ai'] = hasil
                save_signal(nama_aset, hasil['signal'], hasil['entry_price'], hasil['tp_price'], hasil['sl_price'], tf_pilihan)
                st.success("Analisa selesai & direkam ke sistem!")

# ==========================================
# 7. TAMPILAN HASIL ANALISA & CHART
# ==========================================
if 'hasil_ai' in st.session_state:
    res = st.session_state['hasil_ai']
    st.divider()
    
    # 7A. Panel Sinyal
    s1, s2, s3 = st.columns([1, 1, 1])
    sig = res.get('signal', 'NEUTRAL').upper()
    
    with s1:
        if sig == 'BUY': st.markdown("<div class='sig-buy'>🟢 BUY SIGNAL</div>", unsafe_allow_html=True)
        elif sig == 'SELL': st.markdown("<div class='sig-sell'>🔴 SELL SIGNAL</div>", unsafe_allow_html=True)
        else: st.markdown("<div class='sig-neutral'>⚪ NEUTRAL</div>", unsafe_allow_html=True)
        st.write("")
        st.metric("Estimasi Waktu", res.get('est_time', '-'))
        st.metric("Saran Risiko Modal", f"{res.get('risk_percent', '1')}%")
        
    with s2:
        st.metric("🎯 Titik Entry", f"${res.get('entry_price', 0):,.4f}")
        st.metric("📈 Take Profit (TP)", f"${res.get('tp_price', 0):,.4f}")
        st.metric("🛑 Stop Loss (SL)", f"${res.get('sl_price', 0):,.4f}")
        
    with s3:
        st.info(f"📰 **Fundamental/Berita:**\n\n{res.get('news', '-')}")
        st.success(f"💡 **Analisa Teknikal:**\n\n{res.get('reason', '-')}")

    # 7B. Grafik Interaktif
    st.subheader("📈 Visualisasi Target TP / SL")
    fig = go.Figure(data=[go.Candlestick(
        x=data.index, open=data['Open'], high=data['High'], low=data['Low'], close=data['Close'], name="Candle"
    )])
    
    fig.add_hline(y=res.get('entry_price', 0), line_dash="dash", line_color="blue", annotation_text="Entry")
    fig.add_hline(y=res.get('tp_price', 0), line_dash="solid", line_color="green", annotation_text="TP")
    fig.add_hline(y=res.get('sl_price', 0), line_dash="solid", line_color="red", annotation_text="SL")
    
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
    w1.metric("Total Analisa AI", total)
    w2.metric("Target Tercapai (WIN)", win)
    w3.metric("Gagal (LOSS)", loss)
    w4.metric("Akurasi (Win Rate %)", f"{winrate:.1f}%")
    
    st.markdown("### Histori & Update Status Sinyal")
    for _, row in df_hist.head(10).iterrows(): # Tampilkan 10 terakhir
        with st.expander(f"{row['date']} | {row['symbol']} - {row['signal']} (Status: {row['status']})"):
            st.write(f"Entry: **{row['entry']}** | TP: **{row['tp']}** | SL: **{row['sl']}**")
            if row['status'] == 'PENDING':
                b1, b2 = st.columns(2)
                if b1.button("✅ Kena TP (WIN)", key=f"w_{row['id']}"):
                    update_status(row['id'], 'WIN')
                    st.rerun()
                if b2.button("❌ Kena SL (LOSS)", key=f"l_{row['id']}"):
                    update_status(row['id'], 'LOSS')
                    st.rerun()
else:
    st.info("Belum ada histori. Analisa market untuk memulai rekaman data.")
