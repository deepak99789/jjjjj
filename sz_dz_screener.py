import streamlit as st
from tvDatafeed import TvDatafeed, Interval
import pandas as pd
import plotly.graph_objects as go

# --- Candle Type Function ---
def candle_type(row):
    body = abs(row['close'] - row['open'])
    candle_range = row['high'] - row['low']
    if candle_range == 0:
        return "neutral"
    body_ratio = body / candle_range
    if row['close'] > row['open'] and body_ratio >= 0.8:
        return "rally"
    elif row['close'] < row['open'] and body_ratio >= 0.8:
        return "drop"
    elif body_ratio <= 0.5:
        return "base"
    else:
        return "neutral"

# --- Zone Detection ---
def detect_sz_dz(df, num_base=1):
    zones = []
    for i in range(len(df) - num_base - 1):
        leg_in = candle_type(df.iloc[i])
        base_candles = df.iloc[i+1:i+1+num_base]
        leg_out = candle_type(df.iloc[i+1+num_base])

        if all(candle_type(row) == "base" for _, row in base_candles.iterrows()):
            if leg_in == "drop" and leg_out == "rally":
                entry = df['high'].iloc[i+1+num_base]
                sl = df['low'].iloc[i]
                target = entry + (entry - sl) * 2
                zones.append({
                    "type":"DZ",
                    "entry": entry,
                    "sl": sl,
                    "target": target,
                    "risk_reward": round((target - entry) / (entry - sl),2),
                    "status": "FRESH",
                    "time": df.index[i+1],
                })
            elif leg_in == "rally" and leg_out == "drop":
                entry = df['low'].iloc[i+1+num_base]
                sl = df['high'].iloc[i]
                target = entry - (sl - entry) * 2
                zones.append({
                    "type":"SZ",
                    "entry": entry,
                    "sl": sl,
                    "target": target,
                    "risk_reward": round((entry - target) / (sl - entry),2),
                    "status": "FRESH",
                    "time": df.index[i+1],
                })
    return zones

# --- Update Zone Status ---
def update_zone_status(df, df_price):
    for idx, zone in df.iterrows():
        price_after_zone = df_price[df_price.index >= zone['time']]
        touched_target = any(price_after_zone['high'] >= zone['target'])
        touched_sl = any(price_after_zone['low'] <= zone['sl'])

        if touched_target:
            df.at[idx,'status'] = 'TARGET'
        elif touched_sl:
            df.at[idx,'status'] = 'STOPLOSS'
        else:
            df.at[idx,'status'] = 'FRESH'
    return df

# --- Zone Color Mapping ---
def get_zone_color(zone_type, status):
    if status == "STOPLOSS":
        return "gray"
    if zone_type == "DZ":
        return "green" if status=="FRESH" else "darkgreen"
    if zone_type == "SZ":
        return "red" if status=="FRESH" else "darkred"
    return "blue"

# --- Streamlit GUI ---
st.title("Advanced Supply & Demand Zone Screener")

script_type = st.selectbox("Select Script Type", ["FNO NIFTY50","NIFTY100","NIFTY200","NIFTY500"])
num_base = st.slider("Number of Base Candles", 1, 6, 1)

interval_option = st.selectbox("Select Interval", ["1min","5min","15min","30min","60min","1H","2H","4H","Daily","Weekly"])
interval_dict = {"1min": Interval.in_1_minute,"5min": Interval.in_5_minute,"15min": Interval.in_15_minute,"30min": Interval.in_30_minute,
                 "60min": Interval.in_1_hour,"1H": Interval.in_1_hour,"2H": Interval.in_2_hour,"4H": Interval.in_4_hour,
                 "Daily": Interval.in_daily,"Weekly": Interval.in_weekly}
selected_interval = interval_dict[interval_option]

zone_type = st.selectbox("Zone Type", ["All","Supply","Demand"])
zone_status = st.selectbox("Zone Status", ["All","FRESH","TARGET","STOPLOSS"])

stock_lists = {"FNO NIFTY50":["RELIANCE","TCS","INFY"],"NIFTY100":["RELIANCE","TCS","INFY","WIPRO"]}

if st.button("Scan & Update Status"):
    tv = TvDatafeed()
    all_zones = []

    for stock in stock_lists[script_type]:
        df_hist = tv.get_hist(symbol=stock, exchange="NSE", interval=selected_interval, n_bars=500)
        zones = detect_sz_dz(df_hist, num_base=num_base)
        for z in zones:
            z['symbol'] = stock
            all_zones.append(z)

    df_zones = pd.DataFrame(all_zones)

    for stock in df_zones['symbol'].unique():
        df_stock = tv.get_hist(symbol=stock, exchange="NSE", interval=selected_interval, n_bars=500)
        df_stock = df_stock.sort_index()
        df_zones_stock = df_zones[df_zones['symbol']==stock]
        df_zones.loc[df_zones_stock.index] = update_zone_status(df_zones_stock, df_stock)

    if zone_type != "All":
        df_zones = df_zones[df_zones['type'][:2] == zone_type[:2]]
    if zone_status != "All":
        df_zones = df_zones[df_zones['status'] == zone_status]

    st.subheader("Zones with Updated Status")
    st.dataframe(df_zones)

    if not df_zones.empty:
        first_stock = df_zones['symbol'].iloc[0]
        df_plot = tv.get_hist(symbol=first_stock, exchange="NSE", interval=selected_interval, n_bars=500)
        fig = go.Figure(data=[go.Candlestick(
            x=df_plot.index,
            open=df_plot['open'],
            high=df_plot['high'],
            low=df_plot['low'],
            close=df_plot['close']
        )])

        for idx, row in df_zones[df_zones['symbol']==first_stock].iterrows():
            color = get_zone_color(row['type'], row['status'])
            fig.add_shape(
                type="rect",
                x0=row['time'], x1=row['time'],
                y0=row['sl'], y1=row['target'],
                line=dict(color=color),
                fillcolor=color,
                opacity=0.3
            )
        st.plotly_chart(fig)
