import streamlit as st
import pandas as pd
import snowflake.connector
import requests
import pydeck as pdk
from datetime import datetime



# -----------------------------
# CONFIG
# -----------------------------
BASE_URL = "http://127.0.0.1:5000"

def get_connection():
    return snowflake.connector.connect(
        user='NIKITA2411',
        password='Nikitamahajan2411**',
        account='NCGTNVJ-UF51495',
        warehouse='COMPUTE_WH',
        database='LOGISTICS_DB1',
        schema='LOGISTICS_SCHEMA1'
    )

st.set_page_config(layout="wide")

col1, col2 = st.columns([6, 2])
with col1:
    st.title("🚚Enterprise Logistics Control Tower")
    st.markdown("✨Real-time visibility. Smarter logistics.")

with col2:
    now = datetime.now()
    st.title(f"🕒{now.strftime('%I:%M %p')}")
    st.markdown(f"📅{now.strftime("%d %b %Y")}")

st.divider()

# -----------------------------
# SAFE API
# -----------------------------
def safe_get(endpoint, params=None):
    try:
        res = requests.get(f"{BASE_URL}{endpoint}", params=params)
        if res.status_code != 200:
            return None
        return res.json()
    except:
        return None

# -----------------------------
# LOAD LOCATIONS
# -----------------------------
def load_locations():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT CITY FROM LOCATIONS")
    data = [r[0] for r in cur.fetchall()]
    cur.close()
    conn.close()
    return data

locations = load_locations()

# -----------------------------
# SIDEBAR
# -----------------------------
st.sidebar.header("🔍 Route Filters")

source = st.sidebar.selectbox("Source", [""] + locations)
destination = st.sidebar.selectbox("Destination", [""] + locations)

analyze_btn = st.sidebar.button("🚀 Analyze Route")

# -----------------------------
# ROUTE ANALYSIS
# -----------------------------
def analyze_route(source, destination):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT ROUTE_ID, SOURCE_CITY, DESTINATION_CITY, DISTANCE, ESTIMATED_TIME
        FROM ROUTES
        WHERE LOWER(SOURCE_CITY)=LOWER(%s)
        AND LOWER(DESTINATION_CITY)=LOWER(%s)
    """, (source, destination))

    data = cur.fetchone()
    if not data:
        return None

    route_id, src, dest, distance, time = data

    cur.execute("""
        SELECT FROM_CITY, TO_CITY
        FROM ROUTE_SEGMENTS
        WHERE ROUTE_ID=%s
        ORDER BY SEQUENCE
    """, (route_id,))

    segs = cur.fetchall()

    path = [s[0] for s in segs]
    if segs:
        path.append(segs[-1][1])

    intermediate = list(dict.fromkeys(path[1:-1]))

    hubs = []
    seen = set()

    for city in intermediate:
        cur.execute("""
            SELECT H.HUB_ID, H.HUB_NAME, H.CITY,
                   COALESCE(I.AVAILABLE_QUANTITY,0)
            FROM HUBS H
            LEFT JOIN INVENTORY I ON H.HUB_ID = I.HUB_ID
            WHERE LOWER(H.CITY)=LOWER(%s)
        """, (city,))

        for h in cur.fetchall():
            hub_id, name, city_name, inv = h

            if hub_id in seen:
                continue
            seen.add(hub_id)

            cur.execute("""
                SELECT COUNT(*),
                       SUM(CASE WHEN STATUS='AVAILABLE' THEN 1 ELSE 0 END),
                       SUM(CASE WHEN STATUS='INUSE' THEN 1 ELSE 0 END)
                FROM VEHICLES
                WHERE HUB_ID=%s
            """, (hub_id,))

            total, available, inuse = cur.fetchone()

            hubs.append({
                "Hub": name,
                "City": city_name,
                "Inventory": inv,
                "Vehicles": total,
                "Available": available,
                "In Use": inuse
            })

    # MAP DATA
    cur.execute("SELECT CITY, LATITUDE, LONGITUDE FROM LOCATIONS")
    loc_df = pd.DataFrame(cur.fetchall(), columns=["City", "lat", "lon"])

    route_map = loc_df[loc_df["City"].isin(path)].copy()
    route_map["type"] = "Route"

    hub_map = loc_df[loc_df["City"].isin(intermediate)].copy()
    hub_map["type"] = "Hub"

    final_map = pd.concat([route_map, hub_map])

    cur.close()
    conn.close()

    return {
        "route": f"{src} → {dest}",
        "distance": distance,
        "time": time,
        "hubs": hubs,
        "path": path,
        "map": final_map
    }

# -----------------------------
# MAIN PANEL
# -----------------------------
result = None

if analyze_btn and source and destination:
    result = analyze_route(source, destination)

    if result:
        with st.container(border=True):
            c1, c2, c3 = st.columns(3)
            c1.metric("📍 Route", result["route"])
            c2.metric("📏 Distance", f"{result['distance']} km")
            c3.metric("⏱ Time", f"{result['time']} hrs")

        
        st.subheader("🛣 Route Path")
        with st.container(border=True):
            st.success(" → ".join(result["path"]))

        # ---------------- HUB CARDS ----------------
        st.subheader("🏢 Intermediate Hubs")

        if result["hubs"]:
            cols = st.columns(3)

            for i, hub in enumerate(result["hubs"]):
                with cols[i % 3]:
                    with st.container(border=True):
                        st.markdown(f"### 📦 {hub['Hub']}")
                        st.caption(f"📍 {hub['City']}")

                        st.divider()

                # First row metrics
                        col1, col2 = st.columns(2)
                        col1.metric("Inventory", hub["Inventory"])
                        col2.metric("Total Vehicles", hub["Vehicles"])

                # Second row metrics
                        col3, col4 = st.columns(2)
                        col3.success(f"✅ Available Vehicles: {hub['Available']}")
                        col4.error(f"🔴 In Use Vehicles: {hub['In Use']}")

        else:
            st.info("No intermediate hubs")

# -----------------------------
# 🗺 PYDECK MAP
# -----------------------------
st.subheader("🗺 Smart Route Visualization")

if result:
    map_df = result["map"]

    if not map_df.empty:

        # COLOR LOGIC
        def assign_color(row):
            if row["City"] == result["path"][0]:
                return [0, 200, 0]  # Source
            elif row["City"] == result["path"][-1]:
                return [255, 165, 0]  # Destination
            elif row["type"] == "Hub":
                return [255, 0, 0]  # Hub
            else:
                return [0, 128, 255]  # Route

        map_df["color"] = map_df.apply(assign_color, axis=1)

        # SIZE LOGIC
        def assign_radius(row):
            if row["City"] in [result["path"][0], result["path"][-1]]:
                return 80000
            return 50000

        map_df["radius"] = map_df.apply(assign_radius, axis=1)

        # ORDERED LINE
        ordered_coords = []
        for city in result["path"]:
            row = map_df[map_df["City"] == city]
            if not row.empty:
                ordered_coords.append([row.iloc[0]["lon"], row.iloc[0]["lat"]])

        line_data = pd.DataFrame({"path": [ordered_coords]})

        # LAYERS
        scatter = pdk.Layer(
            "ScatterplotLayer",
            data=map_df,
            get_position='[lon, lat]',
            get_color='color',
            get_radius='radius',
            pickable=True
        )

        line = pdk.Layer(
            "PathLayer",
            data=line_data,
            get_path="path",
            get_color=[0, 128, 255],  # BLUE LINE
            width_scale=20,
            width_min_pixels=2
        )

        view = pdk.ViewState(
            latitude=map_df["lat"].mean(),
            longitude=map_df["lon"].mean(),
            zoom=5,
            pitch=30
        )

        tooltip = {
            "html": "<b>City:</b> {City}<br/><b>Type:</b> {type}",
            "style": {"backgroundColor": "black", "color": "white"}
        }

        st.pydeck_chart(pdk.Deck(
            layers=[scatter, line],
            initial_view_state=view,
            tooltip=tooltip
        ))

    else:
        st.warning("No map data available")

# -----------------------------
# KPI DASHBOARD
# -----------------------------
st.subheader("📊 KPI Dashboard")

dashboard = safe_get("/dashboard_data")
orders = safe_get("/active_orders")

# -------- MAIN LAYOUT --------
left, right = st.columns([1, 2])

# -----------------------------
# LEFT SIDE → KPI (CONTAINERS)
# -----------------------------
with left:
    if dashboard:
        with st.container(border=True):
         st.markdown("### 📈 KPIs")

         pending = (
             dashboard["status"]["PLACED"] +
             dashboard["status"]["PROCESSING"] +
             dashboard["status"]["READY_FOR_DISPATCH"]
         )

        # Row 1
         r1c1, r1c2 = st.columns(2)
         with r1c1:
             with st.container(border=True):
                 st.metric("Total Orders", dashboard["total"])

         with r1c2:
             with st.container(border=True):
                 st.metric("In Transit", dashboard["status"]["IN_TRANSIT"])

        # Row 2
         r2c1, r2c2 = st.columns(2)
         with r2c1:
             with st.container(border=True):
                 st.metric("Delivered", dashboard["status"]["DELIVERED"])

         with r2c2:
             with st.container(border=True):
                 st.metric("Pending", pending)

    else:
        st.info("No KPI data")

# -----------------------------
# RIGHT SIDE → ACTIVE ORDERS
# -----------------------------
with right:
    with st.container(border=True):
        st.markdown("### 📦 Active Orders")

        if orders:
            st.dataframe(pd.DataFrame(orders), use_container_width=True)
        else:
            st.info("No active orders")

# -----------------------------
# CHARTS
# -----------------------------
st.subheader("📈 Analytics")

if dashboard:
    status_df = pd.DataFrame(
        list(dashboard["status"].items()),
        columns=["Status", "Count"]
    )

    hub_df = pd.DataFrame(dashboard["hubs"])

    col1, col2 = st.columns(2)

    with col1:
        st.write("Order Status")
        st.bar_chart(status_df.set_index("Status"))

    with col2:
        st.write("Hub Inventory")
        if not hub_df.empty:
            st.bar_chart(hub_df.set_index("hub"))
        else:
            st.info("No hub data")