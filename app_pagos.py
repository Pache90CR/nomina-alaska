import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta
import urllib.parse

# Configuración de la App
st.set_page_config(page_title="Nómina Alaska Cloud", layout="wide")
st.title("🕒 Gestión de Pagos: Alaska / La Chinita")

# TARIFA FIJA
TARIFA_POR_HORA = 1300

# Diccionario de días
DIAS_ESPANOL = {
    "Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles",
    "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sábado", "Sunday": "Domingo"
}

# Conexión a Google Sheets
# Nota: La URL de la hoja se configura en el paso de "Secrets" en Streamlit Cloud
conn = st.connection("gsheets", type=GSheetsConnection)

def cargar_datos():
    try:
        return conn.read(ttl="0s") # ttl=0 para que siempre refresque los datos
    except:
        return pd.DataFrame(columns=["Fecha", "Trabajador", "Entrada", "Salida", "Horas", "Pago Total"])

db_pagos = cargar_datos()

# --- REGISTRO DIARIO (BARRA LATERAL) ---
st.sidebar.header("📝 Registrar Turno")
with st.sidebar.form("form_registro", clear_on_submit=True):
    nombre_reg = st.text_input("Nombre del Trabajador")
    fecha_reg = st.date_input("Fecha", datetime.now())
    col1, col2 = st.columns(2)
    h_in = col1.time_input("Entrada", datetime.strptime("08:00", "%H:%M"))
    h_out = col2.time_input("Salida", datetime.strptime("17:00", "%H:%M"))
    guardar = st.form_submit_button("💾 Guardar en la Nube")

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
    
    # Actualizar Google Sheets
    updated_df = pd.concat([db_pagos, nuevo_dato], ignore_index=True)
    conn.update(data=updated_df)
    st.sidebar.success("✅ ¡Guardado en Google Sheets!")
    st.rerun()

# --- REPORTE Y WHATSAPP ---
st.header("📊 Comprobante de Pago")
if not db_pagos.empty:
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        empleados = sorted(db_pagos["Trabajador"].unique())
        emp_sel = st.selectbox("Empleado", empleados)
    with col_b:
        f_ini = st.date_input("Desde", datetime.now() - timedelta(days=7))
    with col_c:
        f_fin = st.date_input("Hasta", datetime.now())

    # Filtrar
    db_pagos['Fecha_dt'] = pd.to_datetime(db_pagos['Fecha']).dt.date
    mask = (db_pagos["Trabajador"] == emp_sel) & (db_pagos["Fecha_dt"] >= f_ini) & (db_pagos["Fecha_dt"] <= f_fin)
    resumen = db_pagos.loc[mask].copy()

    if not resumen.empty:
        t_h = resumen["Horas"].sum()
        t_p = resumen["Pago Total"].sum()
        
        # Texto para WhatsApp
        detalle = ""
        for _, r in resumen.iterrows():
            dia_n = DIAS_ESPANOL[pd.to_datetime(r['Fecha']).strftime('%A')]
            detalle += f"* {dia_n} {r['Fecha']}: {r['Entrada']} a {r['Salida']} ({r['Horas']}h) -> c{r['Pago Total']}\n"

        msg = (f"*COMPROBANTE - ALASKA*\nTrabajador: {emp_sel}\nPeriodo: {f_ini} al {f_fin}\n"
               f"--------------------------\n{detalle}--------------------------\n"
               f"Total Horas: {t_h:.2f}\nTOTAL: c{t_p:,.2f}")
        
        st.link_button(f"📲 Enviar a {emp_sel} por WhatsApp", f"https://wa.me/?text={urllib.parse.quote(msg)}")
        st.dataframe(resumen[["Fecha", "Entrada", "Salida", "Horas", "Pago Total"]], use_container_width=True)
    else:
        st.warning("Sin datos para este periodo.")

# --- BORRAR REGISTROS ---
with st.expander("🗑️ Borrar Registros"):
    st.write("Cuidado: Esto borra datos de Google Sheets")
    id_borrar = st.number_input("ID a borrar", 0, len(db_pagos)-1 if len(db_pagos)>0 else 0)
    if st.button("Confirmar Borrado"):
        db_pagos = db_pagos.drop(id_borrar).reset_index(drop=True)
        conn.update(data=db_pagos)
        st.rerun()
