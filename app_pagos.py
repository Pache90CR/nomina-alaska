import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta
import urllib.parse

# Configuración básica
TARIFA_POR_HORA = 1300
DIAS_ESPANOL = {
    "Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miercoles",
    "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sabado", "Sunday": "Domingo"
}

st.set_page_config(page_title="Nomina Alaska", layout="wide")
st.title("🕒 Pagos: Alaska")

# Conexión a Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

# Función para leer datos sin que se queden "pegados"
def cargar_datos():
    return conn.read(ttl=0)

db_pagos = cargar_datos()

# --- FORMULARIO DE REGISTRO ---
st.sidebar.header("📝 Nuevo Turno")
with st.sidebar.form("form_registro", clear_on_submit=True):
    nombre_reg = st.text_input("Nombre del Trabajador")
    fecha_reg = st.date_input("Fecha", datetime.now())
    col1, col2 = st.columns(2)
    h_in = col1.time_input("Entrada", datetime.strptime("08:00", "%H:%M"))
    h_out = col2.time_input("Salida", datetime.strptime("17:00", "%H:%M"))
    guardar = st.form_submit_button("💾 GUARDAR REGISTRO")

if guardar and nombre_reg:
    # Cálculo de horas (maneja madrugada)
    dt_in = datetime.combine(fecha_reg, h_in)
    dt_out = datetime.combine(fecha_reg, h_out)
    if dt_out <= dt_in:
        dt_out += timedelta(days=1)
    
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
    
    # Actualizar la hoja (IMPORTANTE: Usamos el método directo)
    try:
        updated_df = pd.concat([db_pagos, nuevo_dato], ignore_index=True)
        conn.update(data=updated_df)
        st.sidebar.success("✅ Guardado en la Nube")
        st.cache_data.clear() # Limpia la memoria para ver el cambio
        st.rerun()
    except Exception as e:
        st.error(f"Error al guardar: {e}")

# --- FILTROS Y WHATSAPP ---
st.header("📊 Generar Comprobante")
if not db_pagos.empty:
    lista_emp = sorted(db_pagos["Trabajador"].unique())
    emp_sel = st.selectbox("Seleccionar Empleado", lista_emp)
    
    # Filtrar solo el empleado seleccionado
    df_emp = db_pagos[db_pagos["Trabajador"] == emp_sel].copy()
    
    if not df_emp.empty:
        total_h = df_emp["Horas"].sum()
        total_p = df_emp["Pago Total"].sum()
        
        # Crear mensaje para WhatsApp
        msg = f"*PAGO ALASKA*\nTrabajador: {emp_sel}\nTotal Horas: {total_h:.2f}\nTotal: c{total_p:,.2f}"
        url_wa = f"https://wa.me/?text={urllib.parse.quote(msg)}"
        
        st.link_button(f"📲 Enviar a {emp_sel} por WhatsApp", url_wa)
        st.dataframe(df_emp[["Fecha", "Entrada", "Salida", "Horas", "Pago Total"]], use_container_width=True)
    
# --- OPCIÓN PARA BORRAR ---
st.markdown("---")
with st.expander("🗑️ Borrar ultimo registro"):
    if st.button("Eliminar ultima fila"):
        if not db_pagos.empty:
            df_borrar = db_pagos.drop(db_pagos.index[-1])
            conn.update(data=df_borrar)
            st.cache_data.clear()
            st.rerun()
