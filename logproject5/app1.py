from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
import snowflake.connector
import uuid
from datetime import datetime
import math
from flask import redirect




app = Flask(__name__)
CORS(app)


# -------------------------------
# SNOWFLAKE CONNECTION
# -------------------------------
def get_connection():
    return snowflake.connector.connect(
        user='NIKITA2411',
        password='Nikitamahajan2411**',
        account='NCGTNVJ-UF51495',
        warehouse='COMPUTE_WH',
        database='LOGISTICS_DB1',
        schema='LOGISTICS_SCHEMA1'
    )

# -------------------------------
# PAGES
# -------------------------------
@app.route('/')
def dashboard():
    return render_template('home.html')

@app.route('/create')
def create_page():
    return render_template('create.html')

@app.route('/orders')
def orders_page():
    return render_template('orders.html')

@app.route('/process/<order_id>')
def process_page(order_id):
    return render_template('process.html', order_id=order_id)

@app.route('/inventory/<order_id>')
def inventory_page(order_id):
    return render_template('inventory.html', order_id=order_id)

# ✅ Tracking with Order ID
@app.route('/tracking/<order_id>')
def tracking_with_id(order_id):
    return render_template('tracking.html', order_id=order_id)


# ✅ Tracking without ID (from navbar)
@app.route('/tracking')
def tracking_without_id():
    return render_template('tracking.html', order_id=None)


@app.route('/dashboard')
def dashboard_page():
     return redirect("http://localhost:8501")


# -------------------------------
# CREATE ORDER
# -------------------------------
@app.route('/create_order', methods=['POST'])
def create_order():
    try:
        data = request.json
        order_id = "ORD_" + str(uuid.uuid4())[:8]

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO ORDERS VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            order_id,
            data['org_id'],
            data['source'],
            data['destination'],
            int(data['load']),
            data['date'],
            data['priority'],
            "PLACED",
            datetime.now()
        ))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"success": True, "order_id": order_id})

    except Exception as e:
        return jsonify({"error": str(e)})
    

# -------------------------------
# GET ORDERS
# -------------------------------
@app.route('/get_orders')
def get_orders():
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM ORDERS")
        rows = cursor.fetchall()

        orders = []
        for row in rows:
            orders.append({
                "ORDER_ID": row[0],
                "SOURCE": row[2],
                "DESTINATION": row[3],
                "LOAD": row[4],
                "STATUS": row[7]
            })

        cursor.close()
        conn.close()

        return jsonify(orders)

    except Exception as e:
        return jsonify({"error": str(e)})

# -------------------------------
# PROCESS ORDER
# -------------------------------
@app.route('/process_order/<order_id>')
def process_order(order_id):
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # ORDER
        cursor.execute("""
            SELECT SOURCE_LOCATION, DESTINATION_LOCATION, LOAD_QUANTITY
            FROM ORDERS WHERE ORDER_ID = %s
        """, (order_id,))
        order = cursor.fetchone()

        if not order:
            return jsonify({"error": "Order not found"})

        source, destination, quantity = order

        # ROUTE
        cursor.execute("""
            SELECT ROUTE_ID, DISTANCE, ESTIMATED_TIME
            FROM ROUTES
            WHERE SOURCE_CITY = %s AND DESTINATION_CITY = %s
            LIMIT 1
        """, (source, destination))
        route = cursor.fetchone()

        if not route:
            return jsonify({"error": "No route found"})

        route_id, distance, time = route

        # HUB
        cursor.execute("""
            SELECT HUB_ID, HUB_NAME FROM HUBS WHERE CITY=%s LIMIT 1
        """, (destination,))
        hub = cursor.fetchone()

        if not hub:
            cursor.execute("SELECT HUB_ID, HUB_NAME FROM HUBS LIMIT 1")
            hub = cursor.fetchone()

        hub_id, hub_name = hub

        # INVENTORY
        cursor.execute("""
            SELECT AVAILABLE_QUANTITY FROM INVENTORY WHERE HUB_ID=%s
        """, (hub_id,))
        inv = cursor.fetchone()
        inventory = inv[0] if inv else 0

        # PREDICTION
        incoming = 20
        total_available = inventory + incoming

        # DECISION
        decision = "FULL" if total_available >= quantity else "PARTIAL"

        # VEHICLES (FIXED)
        cursor.execute("""
            SELECT CAPACITY FROM VEHICLES
            WHERE HUB_ID=%s AND STATUS='AVAILABLE'
            ORDER BY CAPACITY DESC
        """, (hub_id,))
        vehicles = cursor.fetchall()

        if not vehicles:
            vehicles_required = math.ceil(quantity / 10)
        else:
            remaining = quantity
            vehicles_required = 0
            for v in vehicles:
                if remaining <= 0:
                    break
                remaining -= v[0]
                vehicles_required += 1

        # STATUS UPDATE
        status = "READY_FOR_DISPATCH" if decision == "FULL" else "PARTIAL"

        cursor.execute("""
            UPDATE ORDERS SET ORDER_STATUS=%s WHERE ORDER_ID=%s
        """, (status, order_id))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            "route_id": route_id,
            "route": f"{source} → {destination}",
            "distance": distance,
            "time": time,
            "hub_name": hub_name,
            "inventory": inventory,
            "incoming": incoming,
            "total_available": total_available,
            "decision": decision,
            "vehicles_required": vehicles_required
        })

    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/get_inventory/<order_id>')
def get_inventory(order_id):
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Get order
        cursor.execute("""
            SELECT SOURCE_LOCATION, DESTINATION_LOCATION, LOAD_QUANTITY
            FROM ORDERS WHERE ORDER_ID = %s
        """, (order_id,))
        order = cursor.fetchone()

        if not order:
            return jsonify({"error": "Order not found"})

        source, destination, quantity = order

        # Get hub
        cursor.execute("""
            SELECT HUB_ID, HUB_NAME FROM HUBS WHERE CITY=%s LIMIT 1
        """, (destination,))
        hub = cursor.fetchone()

        hub_id, hub_name = hub

        # Get inventory
        cursor.execute("""
            SELECT AVAILABLE_QUANTITY FROM INVENTORY WHERE HUB_ID=%s
        """, (hub_id,))
        inv = cursor.fetchone()

        inventory = inv[0] if inv else 0

        # Prediction
        incoming = 20
        total = inventory + incoming

        decision = "FULL" if total >= quantity else "PARTIAL"

        cursor.close()
        conn.close()

        return jsonify({
            "order_id": order_id,
            "source": source,
            "destination": destination,
            "hub": hub_name,
            "required": quantity,
            "available": inventory,
            "incoming": incoming,
            "total": total,
            "decision": decision
        })

    except Exception as e:
        return jsonify({"error": str(e)})

# -------------------------------
# DISPATCH
# -------------------------------
@app.route('/dispatch/<order_id>')
def dispatch_order(order_id):
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT DESTINATION_LOCATION FROM ORDERS WHERE ORDER_ID=%s", (order_id,))
        destination = cursor.fetchone()[0]

        cursor.execute("SELECT HUB_ID FROM HUBS WHERE CITY=%s LIMIT 1", (destination,))
        hub_id = cursor.fetchone()[0]

        cursor.execute("""
            SELECT VEHICLE_ID, CAPACITY FROM VEHICLES
            WHERE HUB_ID=%s AND STATUS='AVAILABLE'
            ORDER BY CAPACITY DESC
        """, (hub_id,))
        vehicles = cursor.fetchall()

        cursor.execute("SELECT LOAD_QUANTITY FROM ORDERS WHERE ORDER_ID=%s", (order_id,))
        load = cursor.fetchone()[0]

        remaining = load
        assigned = []

        for v in vehicles:
            if remaining <= 0:
                break

            vehicle_id, cap = v
            remaining -= cap
            assigned.append(vehicle_id)

            dispatch_id = "DSP_" + str(uuid.uuid4())[:6]

            cursor.execute("""
                INSERT INTO DISPATCH VALUES (%s,%s,%s,%s,%s,%s)
            """, (dispatch_id, order_id, hub_id, vehicle_id, "IN_TRANSIT", datetime.now()))

            cursor.execute("""
                UPDATE VEHICLES SET STATUS='IN_USE' WHERE VEHICLE_ID=%s
            """, (vehicle_id,))

        cursor.execute("""
            UPDATE ORDERS SET ORDER_STATUS='IN_TRANSIT' WHERE ORDER_ID=%s
        """, (order_id,))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"message": "Dispatched", "vehicles": assigned})

    except Exception as e:
        return jsonify({"error": str(e)})

# -------------------------------
# TRACK API
# -------------------------------
@app.route('/track/<order_id>')
def track_order(order_id):
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT ORDER_STATUS FROM ORDERS WHERE ORDER_ID=%s", (order_id,))
        status = cursor.fetchone()[0]

        cursor.execute("""
            SELECT VEHICLE_ID, STATUS, CREATED_AT
            FROM DISPATCH WHERE ORDER_ID=%s
        """, (order_id,))
        rows = cursor.fetchall()

        vehicles = []
        for r in rows:
            vehicles.append({
                "vehicle_id": r[0],
                "status": r[1],
                "time": str(r[2])
            })

        cursor.close()
        conn.close()

        return jsonify({
            "order_id": order_id,
            "status": status,
            "vehicles": vehicles
        })

    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/mark_delivered/<order_id>')
def mark_delivered(order_id):
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE ORDERS 
            SET ORDER_STATUS='DELIVERED'
            WHERE ORDER_ID=%s
        """, (order_id,))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"message": "Delivered"})

    except Exception as e:
        return jsonify({"error": str(e)})


@app.route('/get_coordinates/<order_id>')
def get_coordinates(order_id):
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Get order cities
        cursor.execute("""
            SELECT SOURCE_LOCATION, DESTINATION_LOCATION 
            FROM ORDERS WHERE ORDER_ID=%s
        """, (order_id,))
        order = cursor.fetchone()

        if not order:
            return jsonify({"error": "Order not found"})

        source, dest = order

        # 🔥 Case-insensitive match (VERY IMPORTANT)
        cursor.execute("""
            SELECT LATITUDE, LONGITUDE 
            FROM LOCATIONS 
            WHERE LOWER(CITY) = LOWER(%s)
        """, (source,))
        src = cursor.fetchone()

        cursor.execute("""
            SELECT LATITUDE, LONGITUDE 
            FROM LOCATIONS 
            WHERE LOWER(CITY) = LOWER(%s)
        """, (dest,))
        dst = cursor.fetchone()

        # 🔥 Handle missing locations
        if not src or not dst:
            return jsonify({"error": "Location not found in LOCATIONS table"})

        return jsonify({
            "source": [float(src[0]), float(src[1])],
            "destination": [float(dst[0]), float(dst[1])]
        })

    except Exception as e:
        return jsonify({"error": str(e)})

# -------------------------------
# ROUTE ANALYZER (NEW)
# -------------------------------
@app.route('/get_locations')
def get_locations():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT DISTINCT CITY FROM LOCATIONS")
    locations = [r[0] for r in cursor.fetchall()]

    cursor.close()
    conn.close()

    return jsonify(locations)

#----------------------------------------------------------

#----------------------------------------------------------
@app.route('/analyze_route')
def analyze_route():
    try:
        source = request.args.get('source')
        destination = request.args.get('destination')

        conn = get_connection()
        cursor = conn.cursor()

        routes = []

        # -----------------------
        # 1️⃣ GET ROUTE FROM ROUTES TABLE
        # -----------------------
        cursor.execute("""
            SELECT ROUTE_ID, SOURCE_CITY, DESTINATION_CITY, DISTANCE, ESTIMATED_TIME
            FROM ROUTES
            WHERE LOWER(SOURCE_CITY)=LOWER(%s)
            AND LOWER(DESTINATION_CITY)=LOWER(%s)
        """, (source, destination))

        route_data = cursor.fetchone()

        if not route_data:
            return jsonify({
                "routes": [],
                "hubs": [],
                "distance": 0,
                "time": "N/A"
            })

        route_id, src, dest, distance, time = route_data

        routes.append({
            "type": "Best Route",
            "route": f"{src} → {dest}",
            "distance": distance,
            "time": time
        })

        # -----------------------
        # 2️⃣ GET FULL PATH FROM ROUTE_SEGMENTS
        # -----------------------
        cursor.execute("""
            SELECT FROM_CITY, TO_CITY
            FROM ROUTE_SEGMENTS
            WHERE ROUTE_ID=%s
            ORDER BY SEQUENCE
        """, (route_id,))

        segments = cursor.fetchall()

        # -----------------------
        # 3️⃣ EXTRACT ONLY INTERMEDIATE HUBS
        # -----------------------
        path = []

        for seg in segments:
            path.append(seg[0])
        if segments:
            path.append(segments[-1][1])

        # remove source & destination
        intermediate_cities = path[1:-1] if len(path) > 2 else []

        # remove duplicates but keep order
        intermediate_cities = list(dict.fromkeys(intermediate_cities))

        # -----------------------
        # 4️⃣ FETCH HUB DETAILS
        # -----------------------
        hubs = []
        seen_hubs = set()

        for city in intermediate_cities:

            cursor.execute("""
                SELECT 
                    H.HUB_ID, 
                    H.HUB_NAME, 
                    H.CITY,
                    COALESCE(I.AVAILABLE_QUANTITY,0)
                FROM HUBS H
                LEFT JOIN INVENTORY I ON H.HUB_ID = I.HUB_ID
                WHERE LOWER(H.CITY)=LOWER(%s)
            """, (city,))

            for h in cursor.fetchall():
                hub_id, name, city_name, inventory = h

                if hub_id in seen_hubs:
                    continue
                seen_hubs.add(hub_id)

                # -----------------------
                # VEHICLE STATS
                # -----------------------
                cursor.execute("""
                    SELECT 
                        COUNT(*) AS TOTAL,
                        SUM(CASE WHEN STATUS='AVAILABLE' THEN 1 ELSE 0 END),
                        SUM(CASE WHEN STATUS='INUSE' THEN 1 ELSE 0 END)
                    FROM VEHICLES
                    WHERE HUB_ID=%s
                """, (hub_id,))

                total, available, inuse = cursor.fetchone()

                hubs.append({
                    "name": name,
                    "city": city_name,
                    "inventory": inventory or 0,
                    "total_vehicles": total or 0,
                    "available_vehicles": available or 0,
                    "inuse_vehicles": inuse or 0
                })

        cursor.close()
        conn.close()

        return jsonify({
            "routes": routes,
            "hubs": hubs,
            "distance": distance,
            "time": time
        })

    except Exception as e:
        return jsonify({"error": str(e)})
# -------------------------------

# DASHBOARD DATA
# -------------------------------
@app.route('/dashboard_data')
def dashboard_data():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM ORDERS")
    total = cursor.fetchone()[0]

    status = {
        "PLACED": 0,
        "PROCESSING": 0,
        "READY_FOR_DISPATCH": 0,
        "IN_TRANSIT": 0,
        "DELIVERED": 0
    }

    cursor.execute("""
        SELECT ORDER_STATUS, COUNT(*)
        FROM ORDERS
        GROUP BY ORDER_STATUS
    """)

    for s, c in cursor.fetchall():
        if s in status:
            status[s] = c

    cursor.execute("""
        SELECT H.HUB_NAME, I.AVAILABLE_QUANTITY
        FROM HUBS H
        JOIN INVENTORY I ON H.HUB_ID = I.HUB_ID
    """)

    hubs = [{"hub": h, "inventory": q} for h, q in cursor.fetchall()]

    cursor.close()
    conn.close()

    return jsonify({
        "total": total,
        "status": status,
        "hubs": hubs
    })


# -------------------------------
# ALERTS
# -------------------------------
@app.route('/alerts')
def alerts():
    conn = get_connection()
    cursor = conn.cursor()

    alerts = []

    cursor.execute("""
        SELECT HUB_ID, AVAILABLE_QUANTITY
        FROM INVENTORY
        WHERE AVAILABLE_QUANTITY < 60
    """)

    for hub, qty in cursor.fetchall():
        alerts.append(f"⚠ Low inventory at {hub} ({qty})")

    cursor.execute("""
        SELECT ORDER_ID, LOAD_QUANTITY
        FROM ORDERS
        WHERE LOAD_QUANTITY > 70
    """)

    for oid, load in cursor.fetchall():
        alerts.append(f"⚠ High load order {oid} ({load} tons)")

    cursor.close()
    conn.close()

    return jsonify(alerts)


# -------------------------------
# ACTIVE ORDERS
# -------------------------------
@app.route('/active_orders')
def active_orders():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT ORDER_ID, SOURCE_LOCATION, DESTINATION_LOCATION, LOAD_QUANTITY, ORDER_STATUS
        FROM ORDERS
        ORDER BY CREATED_AT DESC
        LIMIT 5
    """)

    data = []
    for row in cursor.fetchall():
        data.append({
            "id": row[0],
            "source": row[1],
            "dest": row[2],
            "load": row[3],
            "status": row[4]
        })

    cursor.close()
    conn.close()

    return jsonify(data)


# -------------------------------
# RUN
# -------------------------------
if __name__ == '__main__':
    app.run(debug=True)