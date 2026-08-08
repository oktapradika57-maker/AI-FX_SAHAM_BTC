import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
import google.generativeai as genai
import pandas as pd
import sqlite3
import json
from datetime import datetime

# ==========================================
# 1. KONFIGURASI HALAMAN & CUSTOM CSS
# ==========================================
st.set_page_config(
    page_title="Pro Trading AI Analyzer & Win Rate Tracker",
    page_icon="📈",
    layout="wide"
)

# Custom Styling untuk Tampilan Elegan & Modern
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .stMetric {
        background-color: #1e222d;
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #2a2e39;
    }
    .signal-buy {
        background-color: #134e4a;
        color: #2dd4bf;
        padding: 10px 20px;
        border-radius: 8px;
        font-weight: bold;
        font-size: 20px;
        text-align: center;
    }
    .signal-sell {
        background-color: #7f1d1d;
        color: #f87171;
        padding: 10px 20px;
        border-radius: 8px;
        font-weight: bold;
        font-size: 20px;
        text-align: center;
    }
    .signal-neutral {
        background-color: #374151;
        color: #9ca3af;
        padding: 10px 20px;
        border-radius: 8px;
        font-weight: bold;
        font-size: 20px;
        text-align: center;
    }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. DATABASE UNTUK HISTORY & WIN RATE (SQLite)
# ==========================================
def init_db():
    conn = sqlite3.connect("trading_history.db")
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            symbol TEXT,
            signal TEXT,
            entry_price REAL,
            tp_price REAL,
            sl_price REAL,
            timeframe TEXT,
            status TEXT DEFAULT 'PENDING'
        )
    ''')
    conn.commit()
    conn.close()

def save_prediction(symbol, signal, entry, tp, sl, timeframe):
    conn = sqlite3.connect("trading_history.db")
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('''
        INSERT INTO predictions (timestamp, symbol, signal, entry_price, tp_price, sl_price, timeframe, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING')
    ''', (now, symbol, signal, entry, tp, sl, timeframe))
    conn.commit()
    conn.close()

def get_predictions():
    conn = sqlite3.connect("trading_history.db")
    df = pd.read_sql_query("SELECT * FROM predictions ORDER BY id DESC", conn)
    conn.close()
    return df

def update_status(pred_id, new_status):
    conn = sqlite3.connect("trading_history.db")
    c = conn.cursor()
    c.execute("UPDATE predictions SET status = ? WHERE id = ?", (new_status, pred_id))
    conn.commit()
    conn.close()

init_db()

# ==========================================
# 3. SIDEBAR & PENGATURAN
# ==========================================
st.sidebar.title("⚡ AI Trading Console")

# API Key Input
api_key_input = st.sidebar.text_input(
    "Gemini API Key",
    value=st.secrets.get("GEMINI_API_KEY", "AIzaSyD9nSXbyun2PioOhsWWl5sCt5mXa4v-WOU"),
    type="password"
)

# Pemilihan Instrumen
asset_type = st.sidebar.selectbox("Kategori Instrumen", ["Forex", "Gold / Komoditas", "Crypto (Bitcoin)", "Saham"])

preset_tickers = {
    "Forex": {"EUR/USD": "EURUSD=X", "GBP/USD": "GBPUSD=X", "USD/JPY": "JPY=X"},
    "Gold / Komoditas": {"Emas (Gold)": "GC=F", "Perak (Silver)": "SI=F"},
    "Crypto (Bitcoin)": {"Bitcoin": "BTC-USD", "Ethereum": "ETH-USD"},
    "Saham": {"Apple": "AAPL", "BBCA (Indonesia)": "BBCA.JK", "NVIDIA": "NVDA"}
}

selected_name = st.sidebar.selectbox("Pilih Aset", list(preset_tickers[asset_type].keys()))
ticker_symbol = preset_tickers[asset_type][selected_name]

# Selection Timeframe Analysis
timeframe_entry = st.sidebar.selectbox("Timeframe Acuan Entry", ["M15", "H1", "H4", "D1"], index=2)
period_map = {"M15": "5d", "H1": "1mo", "H4": "3mo", "D1": "1y"}
interval_map = {"M15": "15m", "H1": "1h", "H4": "1h", "D1": "1d"}

# ==========================================
# 4. PENGAMBILAN DATA PASAR
# ==========================================
@st.cache_data(ttl=300)
def load_market_data(symbol, period, interval):
    df = yf.download(symbol, period=period, interval=interval)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df

data = load_market_data(ticker_symbol, period_map[timeframe_entry], interval_map[timeframe_entry])

if data.empty:
    st.error("Gagal mengambil data pasar. Periksa kembali koneksi atau simbol ticker.")
    st.stop()

# Kalkulasi Indikator Sederhana (RSI & Moving Average)
data['SMA_20'] = data['Close'].rolling(window=20).mean()
delta = data['Close'].diff()
gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
rs = gain / loss
data['RSI'] = 100 - (100 / (1 + rs))

latest_price = float(data['Close'].iloc[-1])
latest_rsi = float(data['RSI'].iloc[-1]) if not pd.isna(data['RSI'].iloc[-1]) else 50.0
sma_20 = float(data['SMA_20'].iloc[-1]) if not pd.isna(data['SMA_20'].iloc[-1]) else latest_price

# ==========================================
# 5. INTEGRASI GEMINI AI & ANALISA
# ==========================================
def analyze_with_gemini(api_key, symbol, price, rsi, sma, timeframe):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    prompt = f"""
    Bertindaklah sebagai Senior Financial Analyst & Pro Trader.
    Lakukan analisis gabungan teknikal & fundamental untuk instrumen {symbol}.
    
    Data Pasar Saat Ini:
    - Harga Terakhir: {price}
    - RSI (14): {rsi:.2f}
    - SMA (20): {sma:.2f}
    - Timeframe Entry: {timeframe}

    Instruksi:
    Rangkum berita global terkini, sentimen makroekonomi, dan indikator teknikal di atas.
    Kembalikan respon HANYA dalam format JSON valid tanpa format markdown tambahan seperti di bawah ini:
    {{
        "signal": "BUY" atau "SELL" atau "NEUTRAL",
        "entry_price": float_harga_entry,
        "tp_price": float_target_profit,
        "sl_price": float_stop_loss,
        "risk_percentage": float_persentase_risiko_yang_disarankan_misal_1.5,
        "target_timeframe_hours": "estimasi_waktu_mencapai_target_misal_4-12 Jam",
        "high_impact_news": "rangkuman_berita_penting_berdampak_tinggi",
        "technical_fundamental_summary": "ringkasan_analisis_final_yang_jelas"
    }}
    """
    
    try:
        response = model.generate_content(prompt)
        text_clean = response.text.replace("```json", "").replace("```", "").strip()
        res_json = json.loads(text_clean)
        return res_json
    except Exception as e:
        st.error(f"Gagal memproses analisis AI: {e}")
        return None

# Layout Header Dashboard
st.title(f"📊 Dashboard Analisis Live: {selected_name}")
col_h1, col_h2, col_h3 = st.columns(3)
prev_price = float(data['Close'].iloc[-2])
chg = ((latest_price - prev_price) / prev_price) * 100

col_h1.metric("Harga Live", f"${latest_price:,.4f}" if latest_price < 10 else f"${latest_price:,.2f}", f"{chg:.2f}%")
col_h2.metric("RSI (14)", f"{latest_rsi:.1f}")
col_h3.metric("Timeframe", timeframe_entry)

# Button Trigger Analisis
if st.button("🚀 Jalankan Live AI Analysis Sekarang", use_container_width=True):
    with st.spinner("AI sedang merangkum berita makro, sentimen pasar, dan indikator teknikal..."):
        ai_res = analyze_with_gemini(api_key_input, selected_name, latest_price, latest_rsi, sma_20, timeframe_entry)
        if ai_res:
            st.session_state['current_analysis'] = ai_res
            # Simpan ke Database
            save_prediction(
                selected_name,
                ai_res['signal'],
                ai_res['entry_price'],
                ai_res['tp_price'],
                ai_res['sl_price'],
                timeframe_entry
            )
            st.success("Analisis berhasil diperbarui dan direkam ke dalam Database History!")

# ==========================================
# 6. TAMPILAN HASIL REKOMENDASI (POINT 2, 4, 6)
# ==========================================
if 'current_analysis' in st.session_state:
    res = st.session_state['current_analysis']
    
    st.divider()
    st.subheader("🎯 Rekomendasi Sinyal & Parameter Eksekusi")
    
    col_sig, col_det1, col_det2 = st.columns([1, 1.5, 1.5])
    
    with col_sig:
        sig = res.get('signal', 'NEUTRAL').upper()
        if sig == 'BUY':
            st.markdown(f"<div class='signal-buy'>🟢 SIGNAL: BUY</div>", unsafe_allow_html=True)
        elif sig == 'SELL':
            st.markdown(f"<div class='signal-sell'>🔴 SIGNAL: SELL</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div class='signal-neutral'>⚪ SIGNAL: NEUTRAL</div>", unsafe_allow_html=True)
            
        st.write("")
        st.metric("Rekomendasi Risiko Kapital", f"{res.get('risk_percentage', 1.0)}%")
        st.metric("Estimasi Durasi Target", res.get('target_timeframe_hours', 'N/A'))

    with col_det1:
        st.metric("Entry Price", f"${res.get('entry_price'):,.4f}")
        st.metric("Take Profit (TP)", f"${res.get('tp_price'):,.4f}")

    with col_det2:
        st.metric("Stop Loss (SL)", f"${res.get('sl_price'):,.4f}")
        entry_p = res.get('entry_price', latest_price)
        tp_p = res.get('tp_price', latest_price)
        sl_p = res.get('sl_price', latest_price)
        
        reward = abs(tp_p - entry_p)
        risk = abs(entry_p - sl_p) if abs(entry_p - sl_p) > 0 else 1
        rrr = reward / risk
        st.metric("Risk-to-Reward Ratio (RRR)", f"1 : {rrr:.2f}")

    # Rangkuman Berita & Analisis Final
    col_news, col_tech = st.columns(2)
    with col_news:
        st.info(f"📰 **High-Impact News & Sentimen Makro:**\n\n{res.get('high_impact_news')}")
    with col_tech:
        st.success(f"💡 **Rangkuman Sintesis Analisis AI:**\n\n{res.get('technical_fundamental_summary')}")

# ==========================================
# 7. GRAFIK CANDLESTICK DENGAN GARIS TP/SL (POINT 5)
# ==========================================
st.divider()
st.subheader("📈 Grafik Candlestick Interaktif & Level Kunci")

fig = go.Figure(data=[go.Candlestick(
    x=data.index,
    open=data['Open'],
    high=data['High'],
    low=data['Low'],
    close=data['Close'],
    name='Candlestick'
)])

# Tambahkan garis horizontal jika ada analisis aktif
if 'current_analysis' in st.session_state:
    res = st.session_state['current_analysis']
    fig.add_hline(y=res.get('entry_price'), line_dash="dash", line_color="blue", annotation_text="Entry Level")
    fig.add_hline(y=res.get('tp_price'), line_dash="dash", line_color="green", annotation_text="Take Profit (TP)")
    fig.add_hline(y=res.get('sl_price'), line_dash="dash", line_color="red", annotation_text="Stop Loss (SL)")

fig.update_layout(
    template='plotly_dark',
    height=500,
    xaxis_rangeslider_visible=False,
    margin=dict(l=20, r=20, t=30, b=20)
)
st.plotly_chart(fig, use_container_width=True)

# ==========================================
# 8. ANALYTICS WIN RATE & HISTORY PREDIKSI (POINT 3)
# ==========================================
st.divider()
st.subheader("🏆 History Prediksi & Statistik Win Rate AI")

history_df = get_predictions()

if not history_df.empty:
    total_signals = len(history_df)
    wins = len(history_df[history_df['status'] == 'WIN'])
    losses = len(history_df[history_df['status'] == 'LOSS'])
    completed = wins + losses
    win_rate = (wins / completed * 100) if completed > 0 else 0.0

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Sinyal Direkam", total_signals)
    m2.metric("Sinyal WIN", wins)
    m3.metric("Sinyal LOSS", losses)
    m4.metric("Win Rate Persentase", f"{win_rate:.1f}%")

    st.write("### Daftar History & Evaluasi Sinyal")
    
    # Form untuk memperbarui status sinyal yang pending
    for idx, row in history_df.iterrows():
        with st.expander(f"#{row['id']} | {row['timestamp']} | {row['symbol']} - {row['signal']} | Status: {row['status']}"):
            c1, c2, c3, c4 = st.columns(4)
            c1.write(f"**Entry:** {row['entry_price']}")
            c2.write(f"**TP:** {row['tp_price']}")
            c3.write(f"**SL:** {row['sl_price']}")
            c4.write(f"**Timeframe:** {row['timeframe']}")
            
            if row['status'] == 'PENDING':
                col_btn1, col_btn2 = st.columns(2)
                if col_btn1.button("Mark as WIN 🟢", key=f"win_{row['id']}"):
                    update_status(row['id'], 'WIN')
                    st.rerun()
                if col_btn2.button("Mark as LOSS 🔴", key=f"loss_{row['id']}"):
                    update_status(row['id'], 'LOSS')
                    st.rerun()
else:
    st.info("Belum ada history analisis yang tersimpan. Klik tombol 'Jalankan Live AI Analysis' untuk memulai rekam sinyal.")
