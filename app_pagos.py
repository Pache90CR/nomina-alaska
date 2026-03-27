import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta
import urllib.parse

# Configuración de página
st.set_page_config(page_title="Nómina Alaska", layout="wide")
st.title("🕒 Gestión de Pagos: Alaska / La Chinita")

TARIFA_POR_HORA = 1300
DIAS_ESPANOL = {
    "Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles",
    "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sábado", "Sunday": "Domingo"
}

# Conexión a Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

def cargar_datos():
    try:
        df = conn.read(ttl=0)
        # Convertir a datetime y luego formatear para mostrar
        df['Fecha'] = pd.to_datetime(df['Fecha'], dayfirst=True)
        return df
    except:
        return pd.DataFrame(columns=["Fecha", "Trabajador", "Entrada", "Salida", "Horas", "Pago Total"])

db_pagos = cargar_datos()

# --- BARRA LATERAL: REGISTRO ---
st.sidebar.header("📝 Registrar Turno")
with st.sidebar.form("form_registro", clear_on_submit=True):
    nombre_reg = st.text_input("Nombre del Trabajador")
    # Ajuste de fecha para que por defecto sea hoy 26/03/2026
    fecha_reg = st.date_input("Fecha", datetime.now())
    col1, col2 = st.columns(2)
    h_in = col1.time_input("Entrada", datetime.strptime("08:00", "%H:%M"))
    h_out = col2.time_input("Salida", datetime.strptime("17:00", "%H:%M"))
    guardar = st.form_submit_button("💾 Guardar Registro")

if guardar and nombre_reg:
    dt_in = datetime.combine(fecha_reg, h_in)
    dt_out = datetime.combine(fecha_reg, h_out)
    if dt_out <= dt_in: dt_out += timedelta(days=1)
    
    cant_horas = (dt_out - dt_in).total_seconds() / 3600
    pago_dia = cant_horas * TARIFA_POR_HORA
    
    # GUARDAR EN FORMATO DD/MM/YYYY
    fecha_formateada = fecha_reg.strftime("%d/%m/%Y")
    
    nuevo_dato = pd.DataFrame([{
        "Fecha": fecha_formateada,
        "Trabajador": nombre_reg.strip().title(),
        "Entrada": h_in.strftime("%H:%M"),
        "Salida": h_out.strftime("%H:%M"),
        "Horas": round(cant_horas, 2),
        "Pago Total": round(pago_dia, 2)
    }])
    
    try:
        updated_df = pd.concat([db_pagos, nuevo_dato], ignore_index=True)
        # Limpiar formatos antes de subir
        updated_df['Fecha'] = pd.to_datetime(updated_df['Fecha'], dayfirst=True).dt.strftime("%d/%m/%Y")
        conn.update(data=updated_df)
        st.cache_data.clear()
        st.sidebar.success(f"✅ Guardado con fecha {fecha_formateada}")
        st.rerun()
    except Exception as e:
        st.error(f"Error al guardar: {e}")

# --- SECCIÓN DE COMPROBANTE ---
st.header("📊 Generar Comprobante Acumulado")
if not db_pagos.empty:
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        emp_sel = st.selectbox("Seleccionar Empleado", sorted(db_pagos["Trabajador"].unique()))
    with col_b:
        f_inicio = st.date_input("Fecha Inicio", datetime.now() - timedelta(days=7))
    with col_c:
        f_fin = st.date_input("Fecha Fin", datetime.now())

    # Asegurar que el filtro funcione con el nuevo formato de fecha
    db_pagos['Fecha_filtro'] = pd.to_datetime(db_pagos['Fecha'], dayfirst=True).dt.date
    mask = (db_pagos["Trabajador"] == emp_sel) & \
           (db_pagos["Fecha_filtro"] >= f_inicio) & \
           (db_pagos["Fecha_filtro"] <= f_fin)
    
    df_resumen = db_pagos.loc[mask].copy()

    if not df_resumen.empty:
        total_h = df_resumen["Horas"].sum()
        total_p = df_resumen["Pago Total"].sum()
        
        detalle_texto = ""
        for _, r in df_resumen.iterrows():
            f_obj = pd.to_datetime(r['Fecha'], dayfirst=True)
            dia_nombre = DIAS_ESPANOL[f_obj.strftime('%A')]
            # Texto para WhatsApp en formato DD/MM/YYYY
            fecha_str = f_obj.strftime("%d/%m/%Y")
            detalle_texto += f"• {dia_nombre} {fecha_str}: {r['Entrada']} a {r['Salida']} ({r['Horas']}h) -> c{r['Pago Total']}\n"

        msg_final = (
            f"*COMPROBANTE DE PAGO - ALASKA*\n"
            f"👤 *Trabajador:* {emp_sel}\n"
            f"📅 *Periodo:* {f_inicio.strftime('%d/%m/%Y')} al {f_fin.strftime('%d/%m/%Y')}\n"
            f"--------------------------\n"
            f"*Detalle de turnos:*\n{detalle_texto}"
            f"--------------------------\n"
            f"⏳ *Total Horas:* {total_h:.2f} hrs\n"
            f"💰 *TOTAL A PAGAR: c{total_p:,.2f}*\n"
            f"--------------------------"
        )
        
        url_whatsapp = f"https://wa.me/?text={urllib.parse.quote(msg_final)}"
        st.link_button(f"📲 Enviar Comprobante de {emp_sel} por WhatsApp", url_whatsapp)

        # Mostrar tabla limpia
        st.dataframe(df_resumen[["Fecha", "Entrada", "Salida", "Horas", "Pago Total"]], use_container_width=True)
    else:
        st.warning("No hay registros para este empleado en las fechas seleccionadas.")

# --- ADMINISTRACIÓN ---
st.markdown("---")
with st.expander("🗑️ Administración: Eliminar Registros"):
    st.dataframe(db_pagos[["Fecha", "Trabajador", "Horas", "Pago Total"]])
    id_borrar = st.number_input("ID a borrar", min_value=0, max_value=len(db_pagos)-1 if not db_pagos.empty else 0, step=1)
    if st.button("❌ Eliminar Registro"):
        db_pagos = db_pagos.drop(id_borrar).reset_index(drop=True)
        db_pagos['Fecha'] = pd.to_datetime(db_pagos['Fecha'], dayfirst=True).dt.strftime("%d/%m/%Y")
        conn.update(data=db_pagos)
        st.cache_data.clear()
        st.rerun()
