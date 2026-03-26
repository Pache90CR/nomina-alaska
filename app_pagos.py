import streamlit as st
import pandas as pd
import os
from datetime import datetime, timedelta
import urllib.parse

# Configuración
DB_FILE = "registro_pagos_alaska.xlsx"
TARIFA_POR_HORA = 1300

# Diccionario para traducir días al español
DIAS_ESPANOL = {
    "Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles",
    "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sábado", "Sunday": "Domingo"
}

def cargar_datos():
    if os.path.exists(DB_FILE):
        try:
            df = pd.read_excel(DB_FILE)
            columnas_correctas = ["Fecha", "Trabajador", "Entrada", "Salida", "Horas", "Pago Total"]
            df = df[[c for c in columnas_correctas if c in df.columns]]
            df['Fecha'] = pd.to_datetime(df['Fecha']).dt.date
            return df
        except:
            return pd.DataFrame(columns=["Fecha", "Trabajador", "Entrada", "Salida", "Horas", "Pago Total"])
    return pd.DataFrame(columns=["Fecha", "Trabajador", "Entrada", "Salida", "Horas", "Pago Total"])

st.set_page_config(page_title="Nómina Alaska", layout="wide")
st.title("🕒 Gestión de Pagos: Alaska")

if 'db_pagos' not in st.session_state:
    st.session_state.db_pagos = cargar_datos()

# --- REGISTRO DIARIO ---
st.sidebar.header("📝 Registrar Turno")
with st.sidebar.form("form_registro", clear_on_submit=True):
    nombre_reg = st.text_input("Nombre del Trabajador")
    fecha_reg = st.date_input("Fecha", datetime.now())
    col1, col2 = st.columns(2)
    h_in = col1.time_input("Entrada", datetime.strptime("08:00", "%H:%M"))
    h_out = col2.time_input("Salida", datetime.strptime("17:00", "%H:%M"))
    guardar = st.form_submit_button("💾 Guardar Día")

if guardar and nombre_reg:
    dt_in = datetime.combine(fecha_reg, h_in)
    dt_out = datetime.combine(fecha_reg, h_out)
    if dt_out <= dt_in: dt_out += timedelta(days=1)
    
    cant_horas = (dt_out - dt_in).total_seconds() / 3600
    pago_dia = cant_horas * TARIFA_POR_HORA
    
    nuevo = pd.DataFrame([{
        "Fecha": fecha_reg,
        "Trabajador": nombre_reg.strip().title(),
        "Entrada": h_in.strftime("%H:%M"),
        "Salida": h_out.strftime("%H:%M"),
        "Horas": round(cant_horas, 2),
        "Pago Total": round(pago_dia, 2)
    }])
    
    st.session_state.db_pagos = pd.concat([st.session_state.db_pagos, nuevo], ignore_index=True)
    st.session_state.db_pagos.to_excel(DB_FILE, index=False)
    st.sidebar.success("✅ Guardado")
    st.rerun()

# --- REPORTE Y ENVÍO POR WHATSAPP ---
st.header("📊 Comprobante de Pago (WhatsApp)")
if not st.session_state.db_pagos.empty:
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        emp_sel = st.selectbox("Seleccionar Empleado", sorted(st.session_state.db_pagos["Trabajador"].unique()))
    with col_b:
        f_inicio = st.date_input("Desde", datetime.now() - timedelta(days=7))
    with col_c:
        f_fin = st.date_input("Hasta", datetime.now())

    mask = (st.session_state.db_pagos["Trabajador"] == emp_sel) & \
           (st.session_state.db_pagos["Fecha"] >= f_inicio) & \
           (st.session_state.db_pagos["Fecha"] <= f_fin)
    
    df_resumen = st.session_state.db_pagos.loc[mask].copy()

    if not df_resumen.empty:
        total_h = df_resumen["Horas"].sum()
        total_p = df_resumen["Pago Total"].sum()
        
        # Detalle de texto
        detalle_texto = ""
        for _, r in df_resumen.iterrows():
            dia_nombre = DIAS_ESPANOL[r['Fecha'].strftime('%A')]
            detalle_texto += f"* {dia_nombre} {r['Fecha']}: {r['Entrada']} a {r['Salida']} ({r['Horas']}h) -> c{r['Pago Total']}\n"

        msg_final = (
            f"*COMPROBANTE DE PAGO - ALASKA*\n"
            f"Trabajador: {emp_sel}\n"
            f"Periodo: {f_inicio} al {f_fin}\n"
            f"--------------------------\n"
            f"Detalle de turnos:\n{detalle_texto}"
            f"--------------------------\n"
            f"Total Horas: {total_h:.2f} hrs\n"
            f"TOTAL A PAGAR: c{total_p:,.2f}\n"
            f"--------------------------"
        )
        
        # Botón de WhatsApp
        url_whatsapp = f"https://wa.me/?text={urllib.parse.quote(msg_final)}"
        st.link_button(f"📲 Enviar Reporte de {emp_sel} por WhatsApp", url_whatsapp)

        # Mostrar tabla
        df_resumen['Día'] = df_resumen['Fecha'].apply(lambda x: DIAS_ESPANOL[x.strftime('%A')])
        st.dataframe(df_resumen[["Fecha", "Día", "Entrada", "Salida", "Horas", "Pago Total"]], use_container_width=True)
    else:
        st.warning("No hay registros para este periodo.")

# --- ADMINISTRACIÓN ---
st.markdown("---")
with st.expander("🗑️ Borrar Registros"):
    st.dataframe(st.session_state.db_pagos)
    id_borrar = st.number_input("ID para borrar", min_value=0, max_value=len(st.session_state.db_pagos)-1 if len(st.session_state.db_pagos)>0 else 0, step=1)
    if st.button("Eliminar Permanente"):
        st.session_state.db_pagos = st.session_state.db_pagos.drop(id_borrar).reset_index(drop=True)
        st.session_state.db_pagos.to_excel(DB_FILE, index=False)
        st.rerun()