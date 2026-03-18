import streamlit as st
import pandas as pd
import math
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet

# -----------------------------
# PAGE CONFIG
# -----------------------------
st.set_page_config(
    page_title="DeltaPro Electrical Design AI Assistant - Final",
    page_icon="⚡",
    layout="wide"
)

# -----------------------------
# CUSTOM CSS
# -----------------------------
st.markdown("""
<style>
.main-title {
    font-size: 36px;
    font-weight: 900;
    color: #00d4ff;
}
.sub-title {
    font-size: 18px;
    color: #cbd5e1;
    margin-bottom: 6px;
}
.tag-line {
    font-size: 13px;
    color: #94a3b8;
    margin-bottom: 18px;
}
.block {
    background-color: #0f172a;
    padding: 14px;
    border-radius: 12px;
    border: 1px solid #334155;
}
</style>
""", unsafe_allow_html=True)

# -----------------------------
# DATA TABLES
# -----------------------------
COPPER_CABLE_TABLE = [
    {"size": 1.5, "ampacity": 14, "mv_per_amp_m": 29},
    {"size": 2.5, "ampacity": 24, "mv_per_amp_m": 18},
    {"size": 4, "ampacity": 32, "mv_per_amp_m": 11},
    {"size": 6, "ampacity": 40, "mv_per_amp_m": 7.3},
    {"size": 10, "ampacity": 55, "mv_per_amp_m": 4.4},
    {"size": 16, "ampacity": 75, "mv_per_amp_m": 2.8},
    {"size": 25, "ampacity": 100, "mv_per_amp_m": 1.75},
    {"size": 35, "ampacity": 125, "mv_per_amp_m": 1.25},
    {"size": 50, "ampacity": 150, "mv_per_amp_m": 0.93},
    {"size": 70, "ampacity": 190, "mv_per_amp_m": 0.68},
    {"size": 95, "ampacity": 230, "mv_per_amp_m": 0.50},
]

ALUMINIUM_CABLE_TABLE = [
    {"size": 2.5, "ampacity": 18, "mv_per_amp_m": 29},
    {"size": 4, "ampacity": 24, "mv_per_amp_m": 18},
    {"size": 6, "ampacity": 31, "mv_per_amp_m": 12},
    {"size": 10, "ampacity": 42, "mv_per_amp_m": 7.5},
    {"size": 16, "ampacity": 57, "mv_per_amp_m": 4.7},
    {"size": 25, "ampacity": 76, "mv_per_amp_m": 3.0},
    {"size": 35, "ampacity": 94, "mv_per_amp_m": 2.1},
    {"size": 50, "ampacity": 114, "mv_per_amp_m": 1.6},
    {"size": 70, "ampacity": 145, "mv_per_amp_m": 1.2},
    {"size": 95, "ampacity": 175, "mv_per_amp_m": 0.9},
]

STANDARD_BREAKERS = [6, 10, 16, 20, 25, 32, 40, 50, 63, 80, 100, 125, 160, 200, 250, 315, 400, 630]
TRANSFORMER_RATINGS = [25, 63, 100, 160, 250, 315, 400, 500, 630, 800, 1000, 1250, 1600, 2000]

# -----------------------------
# FUNCTIONS
# -----------------------------
def calculate_current(power_kw, voltage, pf, phase_type):
    if pf <= 0:
        return 0
    if phase_type == "1-Phase":
        return (power_kw * 1000) / (voltage * pf)
    return (power_kw * 1000) / (math.sqrt(3) * voltage * pf)

def calculate_demand_load(connected_load_kw, demand_factor):
    return connected_load_kw * demand_factor

def calculate_kva(demand_load_kw, pf):
    if pf <= 0:
        return 0
    return demand_load_kw / pf

def get_cable_table(material):
    return COPPER_CABLE_TABLE if material == "Copper" else ALUMINIUM_CABLE_TABLE

def calculate_voltage_drop(current, distance_m, voltage, mv_per_amp_m):
    vd_volts = (mv_per_amp_m * current * distance_m) / 1000
    vd_percent = (vd_volts / voltage) * 100 if voltage > 0 else 0
    return vd_volts, vd_percent

def select_cable(current, distance_m, voltage, allowable_vd_percent, material, derating_factor=1.0):
    cable_table = get_cable_table(material)
    for cable in cable_table:
        derated_ampacity = cable["ampacity"] * derating_factor
        if derated_ampacity >= current:
            vd_volts, vd_percent = calculate_voltage_drop(current, distance_m, voltage, cable["mv_per_amp_m"])
            if vd_percent <= allowable_vd_percent:
                return cable, derated_ampacity, vd_volts, vd_percent, "SAFE"
    largest = cable_table[-1]
    derated_ampacity = largest["ampacity"] * derating_factor
    vd_volts, vd_percent = calculate_voltage_drop(current, distance_m, voltage, largest["mv_per_amp_m"])
    return largest, derated_ampacity, vd_volts, vd_percent, "CHECK / UPSIZE"

def recommend_breaker(current, load_type):
    if load_type == "Motor":
        design_current = current * 1.5
        curve = "D Curve (Motor Starting)"
    elif load_type == "Lighting":
        design_current = current * 1.2
        curve = "B Curve"
    else:
        design_current = current * 1.25
        curve = "C Curve"

    breaker = STANDARD_BREAKERS[-1]
    for b in STANDARD_BREAKERS:
        if b >= design_current:
            breaker = b
            break
    return breaker, design_current, curve

def get_pole_selection(phase_type):
    return "DP" if phase_type == "1-Phase" else "TPN"

def generate_boq(light_points, fan_points, socket_points, ac_points, db_count):
    total_wire_m = (light_points * 8) + (fan_points * 10) + (socket_points * 12) + (ac_points * 18)
    conduit_m = total_wire_m * 0.75
    switches = light_points + fan_points
    sockets = socket_points + ac_points
    mcb_count = max(4, db_count * 8)

    return {
        "Light Points": light_points,
        "Fan Points": fan_points,
        "Socket Points": socket_points,
        "AC Points": ac_points,
        "DB Count": db_count,
        "Estimated Wire Length (m)": round(total_wire_m, 2),
        "Estimated Conduit Length (m)": round(conduit_m, 2),
        "Estimated Switch Count": switches,
        "Estimated Socket Count": sockets,
        "Estimated MCB Count": mcb_count
    }

def recommend_transformer(total_kva):
    design_kva = total_kva * 1.2
    selected = TRANSFORMER_RATINGS[-1]
    for rating in TRANSFORMER_RATINGS:
        if rating >= design_kva:
            selected = rating
            break
    return selected, design_kva

def generate_custom_load_table(load_names, load_values):
    rows = []
    total = 0
    for name, val in zip(load_names, load_values):
        rows.append({"Load Name": name, "Load (kW)": val})
        total += val
    return pd.DataFrame(rows), total

def generate_feeder_schedule_from_inputs(feeder_names, feeder_loads, voltage, pf, phase_type):
    rows = []
    for name, load_kw in zip(feeder_names, feeder_loads):
        current = calculate_current(load_kw, voltage, pf, phase_type)
        breaker, design_current, curve = recommend_breaker(current, "Power")
        rows.append({
            "Feeder": name,
            "Load (kW)": round(load_kw, 2),
            "Current (A)": round(current, 2),
            "Design Current (A)": round(design_current, 2),
            "Breaker (A)": breaker,
            "Curve": curve
        })
    return pd.DataFrame(rows)

def estimate_costs(boq, wire_rate, conduit_rate, switch_rate, socket_rate, mcb_rate):
    wire_cost = boq["Estimated Wire Length (m)"] * wire_rate
    conduit_cost = boq["Estimated Conduit Length (m)"] * conduit_rate
    switch_cost = boq["Estimated Switch Count"] * switch_rate
    socket_cost = boq["Estimated Socket Count"] * socket_rate
    mcb_cost = boq["Estimated MCB Count"] * mcb_rate
    total_cost = wire_cost + conduit_cost + switch_cost + socket_cost + mcb_cost

    return {
        "Wire Cost": round(wire_cost, 2),
        "Conduit Cost": round(conduit_cost, 2),
        "Switch Cost": round(switch_cost, 2),
        "Socket Cost": round(socket_cost, 2),
        "MCB Cost": round(mcb_cost, 2),
        "Total Estimated Cost": round(total_cost, 2)
    }

def generate_pdf_report(project_name, summary_rows, boq_rows, cost_rows, feeder_df, custom_load_df):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph("DeltaPro Electrical Design AI Assistant - Final Report", styles["Title"]))
    elements.append(Spacer(1, 10))
    elements.append(Paragraph(f"Project: {project_name}", styles["Heading2"]))
    elements.append(Spacer(1, 10))

    # Summary
    elements.append(Paragraph("Engineering Summary", styles["Heading2"]))
    summary_table_data = [["Parameter", "Value"]] + summary_rows
    summary_table = Table(summary_table_data, repeatRows=1)
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.grey),
        ("TEXTCOLOR", (0,0), (-1,0), colors.whitesmoke),
        ("GRID", (0,0), (-1,-1), 0.5, colors.black),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("BACKGROUND", (0,1), (-1,-1), colors.beige),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 12))

    # Custom Loads
    elements.append(Paragraph("Custom Load Schedule", styles["Heading2"]))
    custom_load_data = [list(custom_load_df.columns)] + custom_load_df.values.tolist()
    custom_load_table = Table(custom_load_data, repeatRows=1)
    custom_load_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.darkblue),
        ("TEXTCOLOR", (0,0), (-1,0), colors.whitesmoke),
        ("GRID", (0,0), (-1,-1), 0.5, colors.black),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
    ]))
    elements.append(custom_load_table)
    elements.append(Spacer(1, 12))

    # Feeder Schedule
    elements.append(Paragraph("Feeder Schedule", styles["Heading2"]))
    feeder_data = [list(feeder_df.columns)] + feeder_df.values.tolist()
    feeder_table = Table(feeder_data, repeatRows=1)
    feeder_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.green),
        ("TEXTCOLOR", (0,0), (-1,0), colors.whitesmoke),
        ("GRID", (0,0), (-1,-1), 0.5, colors.black),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
    ]))
    elements.append(feeder_table)
    elements.append(Spacer(1, 12))

    # BOQ
    elements.append(Paragraph("BOQ Summary", styles["Heading2"]))
    boq_table_data = [["Item", "Value"]] + boq_rows
    boq_table = Table(boq_table_data, repeatRows=1)
    boq_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.purple),
        ("TEXTCOLOR", (0,0), (-1,0), colors.whitesmoke),
        ("GRID", (0,0), (-1,-1), 0.5, colors.black),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
    ]))
    elements.append(boq_table)
    elements.append(Spacer(1, 12))

    # Cost
    elements.append(Paragraph("Cost Estimation", styles["Heading2"]))
    cost_table_data = [["Item", "Value"]] + cost_rows
    cost_table = Table(cost_table_data, repeatRows=1)
    cost_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.orange),
        ("TEXTCOLOR", (0,0), (-1,0), colors.black),
        ("GRID", (0,0), (-1,-1), 0.5, colors.black),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
    ]))
    elements.append(cost_table)
    elements.append(Spacer(1, 12))

    elements.append(Paragraph("Disclaimer: Preliminary engineering / portfolio tool only. Final design validation required.", styles["Normal"]))

    doc.build(elements)
    buffer.seek(0)
    return buffer

# -----------------------------
# HEADER
# -----------------------------
st.markdown('<div class="main-title">⚡ DeltaPro Electrical Design AI Assistant - Version 4 FINAL</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">Freelance Demo + Recruiter Magnet + Real Workflow Thinking</div>', unsafe_allow_html=True)
st.markdown('<div class="tag-line">Electrical Engineering + Automation + Reporting + Estimation + Portfolio Power</div>', unsafe_allow_html=True)

# -----------------------------
# SIDEBAR INPUTS
# -----------------------------
st.sidebar.header("⚙️ Main Design Inputs")
project_name = st.sidebar.text_input("Project Name", "DeltaPro Sample Building")
phase_type = st.sidebar.selectbox("Phase Type", ["1-Phase", "3-Phase"])
default_voltage = 230.0 if phase_type == "1-Phase" else 415.0
voltage = st.sidebar.number_input("System Voltage (V)", min_value=1.0, value=default_voltage, step=1.0)
power_factor = st.sidebar.slider("Power Factor (PF)", 0.1, 1.0, 0.8, 0.05)
connected_load_kw = st.sidebar.number_input("Connected Load (kW)", min_value=0.1, value=25.0, step=0.5)
demand_factor = st.sidebar.slider("Demand Factor", 0.1, 1.0, 0.8, 0.05)
distance_m = st.sidebar.number_input("Cable Run Distance (m)", min_value=1.0, value=30.0, step=1.0)
allowable_vd_percent = st.sidebar.number_input("Allowable Voltage Drop (%)", min_value=0.5, value=5.0, step=0.5)
cable_material = st.sidebar.selectbox("Cable Material", ["Copper", "Aluminium"])
load_type = st.sidebar.selectbox("Load Type", ["Power", "Lighting", "Motor"])
derating_factor = st.sidebar.slider("Cable Derating Factor", 0.5, 1.0, 0.9, 0.05)

st.sidebar.markdown("---")
st.sidebar.header("📦 BOQ Inputs")
light_points = st.sidebar.number_input("Light Points", min_value=0, value=12, step=1)
fan_points = st.sidebar.number_input("Fan Points", min_value=0, value=6, step=1)
socket_points = st.sidebar.number_input("Socket Points", min_value=0, value=10, step=1)
ac_points = st.sidebar.number_input("AC Points", min_value=0, value=2, step=1)
db_count = st.sidebar.number_input("DB Count", min_value=1, value=1, step=1)

st.sidebar.markdown("---")
st.sidebar.header("💰 Cost Inputs (₹)")
wire_rate = st.sidebar.number_input("Wire Rate per meter", min_value=1.0, value=55.0, step=1.0)
conduit_rate = st.sidebar.number_input("Conduit Rate per meter", min_value=1.0, value=35.0, step=1.0)
switch_rate = st.sidebar.number_input("Switch Rate per unit", min_value=1.0, value=120.0, step=1.0)
socket_rate = st.sidebar.number_input("Socket Rate per unit", min_value=1.0, value=180.0, step=1.0)
mcb_rate = st.sidebar.number_input("MCB Rate per unit", min_value=1.0, value=350.0, step=1.0)

# -----------------------------
# CUSTOM LOADS INPUT
# -----------------------------
st.sidebar.markdown("---")
st.sidebar.header("📋 Custom Load Schedule")
num_custom_loads = st.sidebar.number_input("Number of Custom Loads", min_value=1, max_value=8, value=4, step=1)

custom_load_names = []
custom_load_values = []
for i in range(int(num_custom_loads)):
    custom_load_names.append(st.sidebar.text_input(f"Load Name {i+1}", value=f"Load-{i+1}", key=f"lname_{i}"))
    custom_load_values.append(st.sidebar.number_input(f"Load {i+1} (kW)", min_value=0.1, value=float(i+1)*2.5, step=0.5, key=f"lval_{i}"))

# -----------------------------
# FEEDER INPUTS
# -----------------------------
st.sidebar.markdown("---")
st.sidebar.header("⚙️ Feeder Schedule Inputs")
num_feeders = st.sidebar.number_input("Number of Feeders", min_value=1, max_value=8, value=4, step=1)

feeder_names = []
feeder_loads = []
for i in range(int(num_feeders)):
    feeder_names.append(st.sidebar.text_input(f"Feeder Name {i+1}", value=f"F{i+1}", key=f"fname_{i}"))
    feeder_loads.append(st.sidebar.number_input(f"Feeder Load {i+1} (kW)", min_value=0.1, value=float(i+1)*3.0, step=0.5, key=f"fload_{i}"))

# -----------------------------
# MAIN CALCULATIONS
# -----------------------------
demand_load_kw = calculate_demand_load(connected_load_kw, demand_factor)
kva = calculate_kva(demand_load_kw, power_factor)
current = calculate_current(demand_load_kw, voltage, power_factor, phase_type)

selected_cable, derated_ampacity, vd_volts, vd_percent, cable_status = select_cable(
    current, distance_m, voltage, allowable_vd_percent, cable_material, derating_factor
)

breaker, design_current, curve = recommend_breaker(current, load_type)
pole = get_pole_selection(phase_type)
boq = generate_boq(light_points, fan_points, socket_points, ac_points, db_count)
transformer_rating, design_kva = recommend_transformer(kva)
custom_load_df, total_custom_load = generate_custom_load_table(custom_load_names, custom_load_values)
feeder_df = generate_feeder_schedule_from_inputs(feeder_names, feeder_loads, voltage, power_factor, phase_type)
costs = estimate_costs(boq, wire_rate, conduit_rate, switch_rate, socket_rate, mcb_rate)

# -----------------------------
# TABS
# -----------------------------
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Dashboard", "📋 Custom Loads", "⚙️ Feeder Schedule", "💰 BOQ & Costing", "📁 Export PDF"
])

# -----------------------------
# TAB 1 - DASHBOARD
# -----------------------------
with tab1:
    st.subheader("Main Engineering Dashboard")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Demand Load", f"{demand_load_kw:.2f} kW")
    c2.metric("Apparent Power", f"{kva:.2f} kVA")
    c3.metric("Current", f"{current:.2f} A")
    c4.metric("Breaker", f"{breaker} A")
    c5.metric("Transformer", f"{transformer_rating} kVA")

    st.markdown("---")
    left, right = st.columns(2)

    with left:
        st.subheader("Cable & Protection")
        st.write(f"**Project:** {project_name}")
        st.write(f"**Cable Material:** {cable_material}")
        st.write(f"**Recommended Cable:** **{selected_cable['size']} sq.mm**")
        st.write(f"**Base Ampacity:** {selected_cable['ampacity']} A")
        st.write(f"**Derated Ampacity:** {derated_ampacity:.2f} A")
        st.write(f"**Voltage Drop:** {vd_volts:.2f} V ({vd_percent:.2f}%)")
        st.write(f"**Breaker:** {breaker} A")
        st.write(f"**Curve:** {curve}")
        st.write(f"**Pole:** {pole}")

        if cable_status == "SAFE":
            st.success("Cable Status: SAFE")
        else:
            st.warning("Cable Status: CHECK / UPSIZE")

    with right:
        st.subheader("System Summary")
        st.write(f"**Phase Type:** {phase_type}")
        st.write(f"**Voltage:** {voltage:.2f} V")
        st.write(f"**Connected Load:** {connected_load_kw:.2f} kW")
        st.write(f"**Demand Factor:** {demand_factor:.2f}")
        st.write(f"**Demand Load:** {demand_load_kw:.2f} kW")
        st.write(f"**Total Custom Load:** {total_custom_load:.2f} kW")
        st.write(f"**Transformer Design Load:** {design_kva:.2f} kVA")
        st.write(f"**Recommended Transformer:** {transformer_rating} kVA")

# -----------------------------
# TAB 2 - CUSTOM LOADS
# -----------------------------
with tab2:
    st.subheader("Custom Load Schedule")
    st.dataframe(custom_load_df, use_container_width=True)
    st.success(f"Total Custom Connected Load = {total_custom_load:.2f} kW")

# -----------------------------
# TAB 3 - FEEDER SCHEDULE
# -----------------------------
with tab3:
    st.subheader("Manual Feeder Schedule")
    st.dataframe(feeder_df, use_container_width=True)
    st.info("This feeder schedule is based on manually entered feeder loads, making the project look more realistic and practical.")

# -----------------------------
# TAB 4 - BOQ & COSTING
# -----------------------------
with tab4:
    st.subheader("BOQ Estimation")
    boq_df = pd.DataFrame({
        "BOQ Item": list(boq.keys()),
        "Value": list(boq.values())
    })
    st.dataframe(boq_df, use_container_width=True)

    st.markdown("---")
    st.subheader("Cost Estimation (₹)")
    cost_df = pd.DataFrame({
        "Cost Item": list(costs.keys()),
        "Value (₹)": list(costs.values())
    })
    st.dataframe(cost_df, use_container_width=True)
    st.success(f"Total Estimated Electrical Cost = ₹ {costs['Total Estimated Cost']:.2f}")

# -----------------------------
# TAB 5 - EXPORT PDF
# -----------------------------
with tab5:
    st.subheader("Export Final Project Report")

    summary_rows = [
        ["Project Name", project_name],
        ["Phase Type", phase_type],
        ["Voltage (V)", round(voltage, 2)],
        ["Connected Load (kW)", round(connected_load_kw, 2)],
        ["Demand Load (kW)", round(demand_load_kw, 2)],
        ["Apparent Power (kVA)", round(kva, 2)],
        ["Calculated Current (A)", round(current, 2)],
        ["Cable Material", cable_material],
        ["Recommended Cable", selected_cable["size"]],
        ["Derated Ampacity (A)", round(derated_ampacity, 2)],
        ["Voltage Drop (%)", round(vd_percent, 2)],
        ["Cable Status", cable_status],
        ["Breaker (A)", breaker],
        ["Breaker Curve", curve],
        ["Pole", pole],
        ["Transformer (kVA)", transformer_rating],
        ["Total Custom Load (kW)", round(total_custom_load, 2)],
        ["Total Estimated Cost (₹)", costs["Total Estimated Cost"]]
    ]

    summary_df = pd.DataFrame(summary_rows, columns=["Parameter", "Value"])
    st.dataframe(summary_df, use_container_width=True)

    csv_data = summary_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="⬇️ Download Engineering Summary (CSV)",
        data=csv_data,
        file_name="electrical_design_summary_final.csv",
        mime="text/csv"
    )

    boq_rows = [[k, v] for k, v in boq.items()]
    cost_rows = [[k, v] for k, v in costs.items()]

    pdf_buffer = generate_pdf_report(project_name, summary_rows, boq_rows, cost_rows, feeder_df, custom_load_df)

    st.download_button(
        label="⬇️ Download Final PDF Report",
        data=pdf_buffer,
        file_name="DeltaPro_Electrical_Design_Final_Report.pdf",
        mime="application/pdf"
    )

# -----------------------------
# FOOTER
# -----------------------------
st.markdown("---")
st.warning("⚠️ This is a portfolio/demo/preliminary engineering tool. Final design must be validated as per actual drawings, IS/IEC standards, derating, fault level, coordination studies, and site conditions.")