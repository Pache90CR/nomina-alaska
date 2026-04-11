import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta
import urllib.parse

# Configuración de página
st.set_page_config(page_title="Nómina Alaska", layout="wide")
st.title("🕒 Nómina Alaska / La Chinita")

TARIFA_POR_HORA = 1300
DIAS_ESPANOL = {
    "Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles",
    "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sábado", "Sunday": "Domingo"
}

# --- LÓGICA DE SEMANA (INICIA VIERNES) ---
ahora_cr = datetime.now() - timedelta(hours=6)
hoy_cr = ahora_cr.date()

# Si hoy es viernes (weekday 4), el inicio es hoy. 
# Si no, busca el viernes pasado.
dias_desde_viernes = (hoy_cr.weekday() - 4) % 7
inicio_semana = hoy_cr - timedelta(days=dias_desde_viernes)
fin_semana = inicio_semana + timedelta(days=6)

# Conexión
conn = st.connection("gsheets", type=GSheetsConnection)

def cargar_datos_seguro():
    try:
        df = conn.read(ttl=0)
        if df is not None and not df.empty:
            # Unificamos el formato de fecha para que lea tanto YYYY-MM-DD como DD/MM/YYYY
            df['Fecha'] = pd.to_datetime(df['Fecha'], dayfirst=True, errors='coerce').dt.date
            df = df.dropna(subset=['Fecha'])
            return df
        return pd.DataFrame(columns=["Fecha", "Trabajador", "Entrada", "Salida", "Horas", "Pago Total"])
    except:
        return pd.DataFrame(columns=["Fecha", "Trabajador", "Entrada", "Salida", "Horas", "Pago Total"])

db_pagos = cargar_datos_seguro()

# --- REGISTRO ---
st.sidebar.header("📝 Nuevo Registro")
with st.sidebar.form("form_registro", clear_on_submit=True):
    nombre_reg = st.text_input("Trabajador")
    fecha_reg = st.date_input("Fecha", hoy_cr)
    c1, c2 = st.columns(2)
    h_in = c1.time_input("Entrada", datetime.strptime("15:00", "%H:%M"))
    h_out = c2.time_input("Salida", datetime.strptime("22:00", "%H:%M"))
    guardar = st.form_submit_button("💾 Guardar Registro")

if guardar and nombre_reg:
    db_fresca = cargar_datos_seguro()
    dt_in = datetime.combine(fecha_reg, h_in)
    dt_out = datetime.combine(fecha_reg, h_out)
    if dt_out <= dt_in: dt_out += timedelta(days=1)
    
    cant_horas = (dt_out - dt_in).total_seconds() / 3600
    pago_dia = cant_horas * TARIFA_POR_HORA
    
    nuevo = pd.DataFrame([{
        "Fecha": fecha_reg.strftime("%d/%m/%Y"),
        "Trabajador": nombre_reg.strip().title(),
        "Entrada": h_in.strftime("%H:%M"),
        "Salida": h_out.strftime("%H:%M"),
        "Horas": round(cant_horas, 2),
        "Pago Total": round(pago_dia, 2)
    }])
    
    try:
        # Pasamos todo a string antes de subir para no perder el formato
        db_fresca['Fecha'] = pd.to_datetime(db_fresca['Fecha']).dt.strftime("%d/%m/%Y")
        updated = pd.concat([db_fresca, nuevo], ignore_index=True)
        conn.update(data=updated)
        st.cache_data.clear()
        st.sidebar.success(f"✅ Guardado: {nombre_reg}")
        st.rerun()
    except Exception as e:
        st.error(f"Error: {e}")

# --- REPORTE SEMANAL ---
st.header(f"📊 Reporte: Viernes {inicio_semana.strftime('%d/%m/%Y')} al Jueves {fin_semana.strftime('%d/%m/%Y')}")

if not db_pagos.empty:
    empleados = sorted(db_pagos["Trabajador"].unique())
    emp_sel = st.selectbox("Seleccionar Empleado", empleados)
    
    # Filtro de fechas (Desde el viernes detectado)
    mask = (db_pagos["Trabajador"] == emp_sel) & \
           (db_pagos["Fecha"] >= inicio_semana) & \
           (db_pagos["Fecha"] <= fin_semana)
    
    df_sem = db_pagos.loc[mask].copy()

    if not df_sem.empty:
        total_h = df_sem["Horas"].sum()
        total_p = df_sem["Pago Total"].sum()
        
        # --- MENSAJE DE WHATSAPP (DISEÑO ORIGINAL) ---
        detalle_texto = ""
        for _, r in df_sem.iterrows():
            f_obj = pd.to_datetime(r['Fecha'])
            dia_nombre = DIAS_ESPANOL[f_obj.strftime('%A')]
            detalle_texto += f"• {dia_nombre} {f_obj.strftime('%d/%m/%Y')}: {r['Entrada']} a {r['Salida']} ({r['Horas']}h) -> c{r['Pago Total']}\n"

        msg_final = (
            f"*COMPROBANTE DE PAGO - ALASKA*\n"
            f"👤 *Trabajador:* {emp_sel}\n"
            f"📅 *Periodo:* {inicio_semana.strftime('%d/%m/%Y')} al {fin_semana.strftime('%d/%m/%Y')}\n"
            f"--------------------------\n"
            f"*Detalle de turnos:*\n{detalle_texto}"
            f"--------------------------\n"
            f"⏳ *Total Horas:* {total_h:.2f} hrs\n"
            f"💰 *TOTAL A PAGAR: c{total_p:,.2f}*\n"
            f"--------------------------"
        )
        
        st.link_button(f"📲 Enviar Comprobante de {emp_sel} por WhatsApp", f"https://wa.me/?text={urllib.parse.quote(msg_final)}")
        st.dataframe(df_sem[["Fecha", "Entrada", "Salida", "Horas", "Pago Total"]], use_container_width=True)
    else:
        st.warning(f"No hay registros para {emp_sel} en esta semana laboral (inicia viernes {inicio_semana.strftime('%d/%m')}).")

# --- ADMINISTRACIÓN ---
with st.expander("🗑️ Administración: Eliminar Registros"):
    st.dataframe(db_pagos)
    id_borrar = st.number_input("ID a borrar", 0, len(db_pagos)-1 if not db_pagos.empty else 0, step=1)
    if st.button("❌ Eliminar Registro"):
        db_pagos = db_pagos.drop(id_borrar).reset_index(drop=True)
        db_pagos['Fecha'] = pd.to_datetime(db_pagos['Fecha']).dt.strftime("%d/%m/%Y")
        conn.update(data=db_pagos)
        st.cache_data.clear()
        st.rerun()



