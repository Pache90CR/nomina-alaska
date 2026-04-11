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

# --- LÓGICA DE TIEMPO COSTA RICA ---
ahora_cr = datetime.now() - timedelta(hours=6)
hoy_cr = ahora_cr.date()

# Por defecto, mostrar desde el viernes de la semana actual
dias_desde_viernes = (hoy_cr.weekday() - 4) % 7
viernes_defecto = hoy_cr - timedelta(days=dias_desde_viernes)

# Conexión
conn = st.connection("gsheets", type=GSheetsConnection)

def cargar_datos_limpios():
    try:
        df = conn.read(ttl=0)
        if df is not None and not df.empty:
            # CLAVE: Forzamos a que todo sea fecha real, no importa el formato
            df['Fecha'] = pd.to_datetime(df['Fecha'], dayfirst=True, errors='coerce').dt.date
            df = df.dropna(subset=['Fecha', 'Trabajador'])
            return df
        return pd.DataFrame(columns=["Fecha", "Trabajador", "Entrada", "Salida", "Horas", "Pago Total"])
    except:
        return pd.DataFrame(columns=["Fecha", "Trabajador", "Entrada", "Salida", "Horas", "Pago Total"])

db_pagos = cargar_datos_limpios()

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
    db_fresca = cargar_datos_limpios()
    dt_in = datetime.combine(fecha_reg, h_in)
    dt_out = datetime.combine(fecha_reg, h_out)
    if dt_out <= dt_in: dt_out += timedelta(days=1)
    
    cant_horas = (dt_out - dt_in).total_seconds() / 3600
    
    nuevo = pd.DataFrame([{
        "Fecha": fecha_reg.strftime("%d/%m/%Y"),
        "Trabajador": nombre_reg.strip().title(),
        "Entrada": h_in.strftime("%H:%M"),
        "Salida": h_out.strftime("%H:%M"),
        "Horas": round(cant_horas, 2),
        "Pago Total": round(cant_horas * TARIFA_POR_HORA, 2)
    }])
    
    try:
        # Unificamos antes de subir
        db_fresca['Fecha'] = pd.to_datetime(db_fresca['Fecha']).dt.strftime("%d/%m/%Y")
        updated = pd.concat([db_fresca, nuevo], ignore_index=True)
        conn.update(data=updated)
        st.cache_data.clear()
        st.sidebar.success("✅ ¡Guardado!")
        st.rerun()
    except Exception as e:
        st.error(f"Error: {e}")

# --- FILTRO Y REPORTE ---
st.header("📊 Comprobante de Pago")

if not db_pagos.empty:
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        emp_sel = st.selectbox("Empleado", sorted(db_pagos["Trabajador"].unique()))
    with col_b:
        f_inicio = st.date_input("Desde", viernes_defecto)
    with col_c:
        f_fin = st.date_input("Hasta", hoy_cr)

    # El filtro ahora compara fechas reales, no texto
    mask = (db_pagos["Trabajador"] == emp_sel) & \
           (db_pagos["Fecha"] >= f_inicio) & \
           (db_pagos["Fecha"] <= f_fin)
    
    df_res = db_pagos.loc[mask].sort_values('Fecha').copy()

    if not df_res.empty:
        t_h, t_p = df_res["Horas"].sum(), df_res["Pago Total"].sum()
        
        detalle = ""
        for _, r in df_res.iterrows():
            dia = DIAS_ESPANOL[pd.to_datetime(r['Fecha']).strftime('%A')]
            detalle += f"• {dia} {r['Fecha'].strftime('%d/%m/%Y')}: {r['Entrada']} a {r['Salida']} ({r['Horas']}h) -> ₡{r['Pago Total']}\n"

        msg = (f"*COMPROBANTE DE PAGO - ALASKA*\n👤 *Trabajador:* {emp_sel}\n"
               f"📅 *Periodo:* {f_inicio.strftime('%d/%m/%Y')} al {f_fin.strftime('%d/%m/%Y')}\n"
               f"--------------------------\n*Detalle de turnos:*\n{detalle}"
               f"--------------------------\n⏳ *Total Horas:* {t_h:.2f} hrs\n"
               f"💰 *TOTAL A PAGAR: ₡{t_p:,.2f}*\n--------------------------")
        
        st.link_button("📲 Enviar Comprobante por WhatsApp", f"https://wa.me/?text={urllib.parse.quote(msg)}")
        st.dataframe(df_res[["Fecha", "Entrada", "Salida", "Horas", "Pago Total"]], use_container_width=True)
    else:
        st.warning("No se encontraron registros en este rango.")

# --- BORRAR ---
with st.expander("🗑️ Administración: Eliminar"):
    st.dataframe(db_pagos)
    id_b = st.number_input("ID a borrar", 0, len(db_pagos)-1 if not db_pagos.empty else 0)
    if st.button("❌ Eliminar"):
        db_pagos = db_pagos.drop(id_b).reset_index(drop=True)
        db_pagos['Fecha'] = pd.to_datetime(db_pagos['Fecha']).dt.strftime("%d/%m/%Y")
        conn.update(data=db_pagos)
        st.cache_data.clear()
        st.rerun()





