import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta
import urllib.parse

# Configuración de página
st.set_page_config(page_title="Nómina Alaska - Control Total", layout="wide")
st.title("🕒 Nómina Alaska")

TARIFA_POR_HORA = 1300
DIAS_ESPANOL = {
    "Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles",
    "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sábado", "Sunday": "Domingo"
}

# --- AJUSTE DE HORA COSTA RICA (FORZADO) ---
# Usamos un método más robusto para la fecha de hoy
fecha_actual_cr = (datetime.now() - timedelta(hours=6)).date()

# Conexión a Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

def cargar_datos_seguro():
    try:
        df = conn.read(ttl=0)
        if df is not None and not df.empty:
            # Convertimos la columna Fecha a objetos de fecha reales, sin importar el formato original
            df['Fecha'] = pd.to_datetime(df['Fecha'], errors='coerce').dt.date
            # Eliminamos filas que hayan quedado vacías por error
            df = df.dropna(subset=['Fecha', 'Trabajador'])
            return df
        return pd.DataFrame(columns=["Fecha", "Trabajador", "Entrada", "Salida", "Horas", "Pago Total"])
    except Exception as e:
        return pd.DataFrame(columns=["Fecha", "Trabajador", "Entrada", "Salida", "Horas", "Pago Total"])

# LECTURA DE DATOS
db_pagos = cargar_datos_seguro()

# --- BARRA LATERAL: REGISTRO ---
st.sidebar.header("📝 Registrar Turno")
with st.sidebar.form("form_registro", clear_on_submit=True):
    nombre_reg = st.text_input("Nombre del Trabajador")
    # Aseguramos que el calendario inicie en la fecha correcta de CR
    fecha_reg = st.date_input("Fecha", fecha_actual_cr)
    col1, col2 = st.columns(2)
    h_in = col1.time_input("Entrada", datetime.strptime("15:00", "%H:%M"))
    h_out = col2.time_input("Salida", datetime.strptime("00:00", "%H:%M"))
    guardar = st.form_submit_button("💾 Guardar Registro")

if guardar and nombre_reg:
    # Recargar datos antes de guardar para evitar sobrescribir
    db_fresca = cargar_datos_seguro()
    
    dt_in = datetime.combine(fecha_reg, h_in)
    dt_out = datetime.combine(fecha_reg, h_out)
    if dt_out <= dt_in: dt_out += timedelta(days=1)
    
    cant_horas = (dt_out - dt_in).total_seconds() / 3600
    pago_dia = cant_horas * TARIFA_POR_HORA
    
    nuevo_dato = pd.DataFrame([{
        "Fecha": fecha_reg, # Guardamos como objeto de fecha
        "Trabajador": nombre_reg.strip().title(),
        "Entrada": h_in.strftime("%H:%M"),
        "Salida": h_out.strftime("%H:%M"),
        "Horas": round(cant_horas, 2),
        "Pago Total": round(pago_dia, 2)
    }])
    
    try:
        updated_df = pd.concat([db_fresca, nuevo_dato], ignore_index=True)
        # Convertimos todo a string antes de subir para que Google Sheets no lo altere
        updated_df['Fecha'] = updated_df['Fecha'].apply(lambda x: x.strftime("%Y-%m-%d") if isinstance(x, datetime) or hasattr(x, 'strftime') else x)
        
        conn.update(data=updated_df)
        st.cache_data.clear()
        st.sidebar.success(f"✅ Guardado: {nombre_reg}")
        st.rerun()
    except Exception as e:
        st.error(f"Error al guardar: {e}")

# --- SECCIÓN DE COMPROBANTE ---
st.header("📊 Comprobante Acumulado")
if not db_pagos.empty:
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        emp_sel = st.selectbox("Seleccionar Empleado", sorted(db_pagos["Trabajador"].unique()))
    with col_b:
        # Ponemos el inicio del filtro un poco más atrás para que encuentre registros viejos
        f_inicio = st.date_input("Fecha Inicio", fecha_actual_cr - timedelta(days=30))
    with col_c:
        f_fin = st.date_input("Fecha Fin", fecha_actual_cr)

    # FILTRADO ROBUSTO
    # Convertimos los inputs a date para comparar manzanas con manzanas
    mask = (db_pagos["Trabajador"] == emp_sel) & \
           (db_pagos["Fecha"] >= f_inicio) & \
           (db_pagos["Fecha"] <= f_fin)
    
    df_resumen = db_pagos.loc[mask].copy()

    if not df_resumen.empty:
        total_h = df_resumen["Horas"].sum()
        total_p = df_resumen["Pago Total"].sum()
        
        detalle_texto = ""
        for _, r in df_resumen.iterrows():
            # Obtener nombre del día
            dia_nombre = DIAS_ESPANOL[pd.to_datetime(r['Fecha']).strftime('%A')]
            detalle_texto += f"• {dia_nombre} {r['Fecha'].strftime('%d/%m/%Y')}: {r['Entrada']} a {r['Salida']} ({r['Horas']}h) -> c{r['Pago Total']}\n"

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
        
        st.link_button(f"📲 Enviar a {emp_sel} por WhatsApp", f"https://wa.me/?text={urllib.parse.quote(msg_final)}")
        st.dataframe(df_resumen[["Fecha", "Entrada", "Salida", "Horas", "Pago Total"]], use_container_width=True)
    else:
        st.warning(f"No hay registros para {emp_sel} entre el {f_inicio.strftime('%d/%m/%Y')} y el {f_fin.strftime('%d/%m/%Y')}.")

# --- ADMINISTRACIÓN ---
st.markdown("---")
with st.expander("🗑️ Administración: Eliminar Registros"):
    st.write("Registros actuales en la base de datos:")
    # Recargar para asegurar ver lo último
    db_admin = cargar_datos_seguro()
    st.dataframe(db_admin)
    
    id_borrar = st.number_input("ID a borrar (número a la izquierda)", 0, len(db_admin)-1 if not db_admin.empty else 0, step=1)
    if st.button("❌ Eliminar Registro Seleccionado"):
        db_admin = db_admin.drop(id_borrar).reset_index(drop=True)
        # Convertir fechas a string para guardar limpio
        db_admin['Fecha'] = db_admin['Fecha'].apply(lambda x: x.strftime("%Y-%m-%d") if hasattr(x, 'strftime') else x)
        conn.update(data=db_admin)
        st.cache_data.clear()
        st.success("Registro eliminado.")
        st.rerun()


