import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta
import urllib.parse

# TARIFA FIJA
TARIFA_POR_HORA = 1300

st.set_page_config(page_title="Nómina Alaska Cloud", layout="wide")
st.title("🕒 Pagos: Alaska / La Chinita")

# Conexión a Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

def cargar_datos():
    try:
        # Cargamos los datos limpios de la hoja
        return conn.read(ttl="0s")
    except:
        return pd.DataFrame(columns=["Fecha", "Trabajador", "Entrada", "Salida", "Horas", "Pago Total"])

db_pagos = cargar_datos()

# --- REGISTRO ---
st.sidebar.header("📝 Nuevo Turno")
with st.sidebar.form("form_registro", clear_on_submit=True):
    nombre_reg = st.text_input("Trabajador")
    fecha_reg = st.date_input("Fecha", datetime.now())
    col1, col2 = st.columns(2)
    h_in = col1.time_input("Entrada", datetime.strptime("08:00", "%H:%M"))
    h_out = col2.time_input("Salida", datetime.strptime("17:00", "%H:%M"))
    guardar = st.form_submit_button("💾 Guardar")

if guardar and nombre_reg:
    dt_in = datetime.combine(fecha_reg, h_in)
    dt_out = datetime.combine(fecha_reg, h_out)
    if dt_out <= dt_in: dt_out += timedelta(days=1)
    
    cant_horas = (dt_out - dt_in).total_seconds() / 3600
    pago_dia = cant_horas * TARIFA_POR_HORA
    
    nuevo_dato = pd.DataFrame([{
        "Fecha": str(fecha_reg),
        "Trabajador": nombre_reg.strip().title(),
        "Entrada": h_in.strftime("%H:%M"),
        "Salida": h_out.strftime("%H:%M"),
        "Horas": round(cant_horas, 2),
        "Pago Total": round(pago_dia, 2)
    }])
    
    # Actualizar la hoja de cálculo
    updated_df = pd.concat([db_pagos, nuevo_dato], ignore_index=True)
    conn.update(data=updated_df)
    st.sidebar.success("✅ Guardado en la Nube")
    st.rerun()

# --- COMPROBANTE ---
st.header("📊 Comprobante de Pago")
if not db_pagos.empty:
    emp_sel = st.selectbox("Seleccionar Empleado", sorted(db_pagos["Trabajador"].unique()))
    
    # Filtrar datos del empleado
    df_emp = db_pagos[db_pagos["Trabajador"] == emp_sel].copy()
    t_h = df_emp["Horas"].sum()
    t_p = df_emp["Pago Total"].sum()
    
    msg = (f"*PAGO ALASKA*\nTrabajador: {emp_sel}\n"
           f"Total Horas: {t_h:.2f}\nTotal: c{t_p:,.2f}")
    
    st.link_button(f"📲 Enviar a {emp_sel} por WhatsApp", f"https://wa.me/?text={urllib.parse.quote(msg)}")
    st.dataframe(df_emp, use_container_width=True)

with st.expander("🗑️ Borrar"):
    id_borrar = st.number_input("ID", 0, len(db_pagos)-1 if not db_pagos.empty else 0)
    if st.button("Eliminar"):
        db_pagos = db_pagos.drop(id_borrar).reset_index(drop=True)
        conn.update(data=db_pagos)
        st.rerun()
