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

# --- LÓGICA DE TIEMPO ---
ahora_cr = datetime.now() - timedelta(hours=6)
hoy_cr = ahora_cr.date()

# Inicio automático (Viernes) pero modificable
dias_desde_viernes = (hoy_cr.weekday() - 4) % 7
viernes_defecto = hoy_cr - timedelta(days=dias_desde_viernes)

# Conexión
conn = st.connection("gsheets", type=GSheetsConnection)

def cargar_datos_limpios():
    try:
        df = conn.read(ttl=0)
        if df is not None and not df.empty:
            # Esta línea es la que arregla el "cuarto registro":
            # Convierte cualquier cosa (2026-04-10 o 10/04/2026) a fecha real
            df['Fecha'] = pd.to_datetime(df['Fecha'], dayfirst=True, errors='coerce').dt.date
            df = df.dropna(subset=['Fecha', 'Trabajador'])
            return df
        return pd.DataFrame(columns=["Fecha", "Trabajador", "Entrada", "Salida", "Horas", "Pago Total"])
    except:
        return pd.DataFrame(columns=["Fecha", "Trabajador", "Entrada", "Salida", "Horas", "Pago Total"])

db_pagos = cargar_datos_limpios()

# --- FORMULARIO DE REGISTRO ---
st.sidebar.header("📝 Nuevo Registro")
with st.sidebar.form("form_registro", clear_on_submit=True):
    nombre_reg = st.text_input("Trabajador")
    fecha_reg = st.date_input("Fecha", hoy_cr)
    c1, c2 = st.columns(2)
    h_in = c1.time_input("Entrada", datetime.strptime("15:00", "%H:%M"))
    h_out = c2.time_input("Salida", datetime.strptime("22:00", "%H:%M"))
    guardar = st.form_submit_button("💾 Guardar Registro")

if guardar and nombre_reg:
    db_fresca = cargar_datos_limpios()
    dt_in = datetime.combine(fecha_reg, h_in)
    dt_out = datetime.combine(fecha_reg, h_out)
    if dt_out <= dt_in: dt_out += timedelta(days=1)
    
    cant_horas = (dt_out - dt_in).total_seconds() / 3600
    pago_dia = cant_horas * TARIFA_POR_HORA
    
    # Guardamos como STRING DD/MM/YYYY para evitar que Google Sheets lo cambie
    nuevo = pd.DataFrame([{
        "Fecha": fecha_reg.strftime("%d/%m/%Y"),
        "Trabajador": nombre_reg.strip().title(),
        "Entrada": h_in.strftime("%H:%M"),
        "Salida": h_out.strftime("%H:%M"),
        "Horas": round(cant_horas, 2),
        "Pago Total": round(pago_dia, 2)
    }])
    
    try:
        # Unificamos todo a texto antes de subir
        db_fresca['Fecha'] = pd.to_datetime(db_fresca['Fecha']).dt.strftime("%d/%m/%Y")
        updated = pd.concat([db_fresca, nuevo], ignore_index=True)
        conn.update(data=updated)
        st.cache_data.clear()
        st.sidebar.success(f"✅ Guardado con éxito")
        st.rerun()
    except Exception as e:
        st.error(f"Error al guardar: {e}")

# --- REPORTE CON FILTROS MANUALES ---
st.header("📊 Comprobante de Pago")

if not db_pagos.empty:
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        emp_sel = st.selectbox("Seleccionar Empleado", sorted(db_pagos["Trabajador"].unique()))
    with col_b:
        # El filtro de inicio ahora es manual pero sugiere el viernes
        f_inicio = st.date_input("Desde", viernes_defecto)
    with col_c:
        f_fin = st.date_input("Hasta", hoy_cr + timedelta(days=1))

    # Filtrado
    mask = (db_pagos["Trabajador"] == emp_sel) & \
           (db_pagos["Fecha"] >= f_inicio) & \
           (db_pagos["Fecha"] <= f_fin)
    
    df_resumen = db_pagos.loc[mask].copy()

    if not df_resumen.empty:
        total_h = df_resumen["Horas"].sum()
        total_p = df_resumen["Pago Total"].sum()
        
        # --- MENSAJE DE WHATSAPP (DISEÑO ORIGINAL COMPLETO) ---
        detalle_texto = ""
        for _, r in df_resumen.sort_values('Fecha').iterrows():
            f_obj = pd.to_datetime(r['Fecha'])
            dia_nombre = DIAS_ESPANOL[f_obj.strftime('%A')]
            detalle_texto += f"• {dia_nombre} {f_obj.strftime('%d/%m/%Y')}: {r['Entrada']} a {r['Salida']} ({r['Horas']}h) -> c{r['Pago Total']}\n"

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
        
        st.link_button(f"📲 Enviar Comprobante por WhatsApp", f"https://wa.me/?text={urllib.parse.quote(msg_final)}")
        st.dataframe(df_resumen[["Fecha", "Entrada", "Salida", "Horas", "Pago Total"]], use_container_width=True)
    else:
        st.warning(f"No hay registros. Revisa si la fecha 'Desde' es correcta.")

# --- ADMINISTRACIÓN ---
with st.expander("🗑️ Administración: Eliminar Registros"):
    # Recargamos para ver los IDs actuales
    df_admin = cargar_datos_limpios()
    st.dataframe(df_admin)
    id_borrar = st.number_input("ID a borrar", 0, len(df_admin)-1 if not df_admin.empty else 0, step=1)
    if st.button("❌ Eliminar Registro"):
        df_admin = df_admin.drop(id_borrar).reset_index(drop=True)
        df_admin['Fecha'] = pd.to_datetime(df_admin['Fecha']).dt.strftime("%d/%m/%Y")
        conn.update(data=df_admin)
        st.cache_data.clear()
        st.rerun()




