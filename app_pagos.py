import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta
import urllib.parse
import plotly.express as px

# Configuración de página
st.set_page_config(page_title="Nómina Alaska", layout="wide")
st.title("🕒 Sistema de Nómina: Alaska / La Chinita")

TARIFA_POR_HORA = 1300
DIAS_ESPANOL = {
    "Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles",
    "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sábado", "Sunday": "Domingo"
}

# --- LÓGICA DE TIEMPO COSTA RICA ---
ahora_cr = datetime.now() - timedelta(hours=6)
hoy_cr = ahora_cr.date()

# Filtro por defecto: Viernes de la semana actual
dias_desde_viernes = (hoy_cr.weekday() - 4) % 7
viernes_defecto = hoy_cr - timedelta(days=dias_desde_viernes)

conn = st.connection("gsheets", type=GSheetsConnection)

def cargar_datos_limpios():
    try:
        df = conn.read(ttl=0)
        if df is not None and not df.empty:
            df['Fecha'] = pd.to_datetime(df['Fecha'], format='%d/%m/%Y', errors='coerce').dt.date
            df.loc[df['Fecha'].isna(), 'Fecha'] = pd.to_datetime(df['Fecha'], errors='coerce').dt.date
            df = df.dropna(subset=['Fecha', 'Trabajador'])
            return df
        return pd.DataFrame(columns=["Fecha", "Trabajador", "Entrada", "Salida", "Horas", "Pago Total"])
    except:
        return pd.DataFrame(columns=["Fecha", "Trabajador", "Entrada", "Salida", "Horas", "Pago Total"])

db_pagos = cargar_datos_limpios()

# --- BARRA LATERAL: REGISTRO ---
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
    
    nueva_fila = {
        "Fecha": f"{fecha_reg.day:02d}/{fecha_reg.month:02d}/{fecha_reg.year}",
        "Trabajador": nombre_reg.strip().title(),
        "Entrada": h_in.strftime("%H:%M"),
        "Salida": h_out.strftime("%H:%M"),
        "Horas": round(cant_horas, 2),
        "Pago Total": round(pago_dia, 2)
    }
    
    try:
        db_fresca['Fecha'] = db_fresca['Fecha'].apply(lambda x: x.strftime("%d/%m/%Y") if hasattr(x, 'strftime') else x)
        updated = pd.concat([db_fresca, pd.DataFrame([nueva_fila])], ignore_index=True)
        conn.update(data=updated)
        st.cache_data.clear()
        st.sidebar.success(f"✅ Registrado con éxito")
        st.rerun()
    except Exception as e:
        st.error(f"Error al guardar: {e}")

# --- PESTAÑAS PRINCIPALES ---
tab1, tab2, tab3 = st.tabs(["📊 Comprobante de Pago", "📈 Gráficas y Estadísticas", "🎄 Cálculo de Aguinaldo"])

# --- TAB 1: COMPROBANTE DE PAGO ---
with tab1:
    if not db_pagos.empty:
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            emp_sel = st.selectbox("Empleado", sorted(db_pagos["Trabajador"].unique()))
        with col_b:
            f_inicio = st.date_input("Desde", viernes_defecto)
        with col_c:
            f_fin = st.date_input("Hasta", hoy_cr)

        mask = (db_pagos["Trabajador"] == emp_sel) & \
               (db_pagos["Fecha"] >= f_inicio) & \
               (db_pagos["Fecha"] <= f_fin)
        
        df_res = db_pagos.loc[mask].sort_values('Fecha').copy()

        if not df_res.empty:
            total_h, total_p = df_res["Horas"].sum(), df_res["Pago Total"].sum()
            
            detalle = ""
            for _, r in df_res.iterrows():
                dia_nombre = DIAS_ESPANOL[pd.to_datetime(r['Fecha']).strftime('%A')]
                detalle += f"• {dia_nombre} {r['Fecha'].strftime('%d/%m/%Y')}: {r['Entrada']} a {r['Salida']} ({r['Horas']}h) -> ₡{r['Pago Total']}\n"

            msg = (f"*COMPROBANTE DE PAGO - ALASKA*\n👤 *Trabajador:* {emp_sel}\n"
                   f"📅 *Periodo:* {f_inicio.strftime('%d/%m/%Y')} al {f_fin.strftime('%d/%m/%Y')}\n"
                   f"--------------------------\n*Detalle de turnos:*\n{detalle}"
                   f"--------------------------\n⏳ *Total Horas:* {total_h:.2f} hrs\n"
                   f"💰 *TOTAL A PAGAR: ₡{total_p:,.2f}*\n--------------------------")
            
            st.link_button("📲 Enviar Comprobante por WhatsApp", f"https://wa.me/?text={urllib.parse.quote(msg)}")
            st.dataframe(df_res[["Fecha", "Entrada", "Salida", "Horas", "Pago Total"]], use_container_width=True)
        else:
            st.warning("No hay registros en el rango seleccionado.")
    else:
        st.info("No hay datos en la base de datos.")

# --- TAB 2: GRÁFICAS ---
with tab2:
    st.header("📈 Resumen Gráfico de Pagos")
    if not db_pagos.empty:
        col_g1, col_g2 = st.columns(2)
        
        with col_g1:
            st.subheader("Total Pagado por Trabajador")
            pagos_emp = db_pagos.groupby("Trabajador")["Pago Total"].sum().reset_index()
            fig_bar = px.bar(pagos_emp, x="Trabajador", y="Pago Total", text_auto='.2s',
                             color="Trabajador", title="Inversión total en Planilla (₡)")
            st.plotly_chart(fig_bar, use_container_width=True)
            
        with col_g2:
            st.subheader("Distribución de Horas Trabajadas")
            horas_emp = db_pagos.groupby("Trabajador")["Horas"].sum().reset_index()
            fig_pie = px.pie(horas_emp, values="Horas", names="Trabajador", title="Porcentaje de Horas por Empleado")
            st.plotly_chart(fig_pie, use_container_width=True)
            
        st.subheader("Evolución de Pagos en el Tiempo")
        df_linea = db_pagos.groupby("Fecha")["Pago Total"].sum().reset_index()
        fig_line = px.line(df_linea, x="Fecha", y="Pago Total", markers=True, title="Gasto Diario en Planilla (₡)")
        st.plotly_chart(fig_line, use_container_width=True)
    else:
        st.info("Registra datos para generar estadísticas.")

# --- TAB 3: AGUINALDO ---
with tab3:
    st.header("🎄 Cálculo de Aguinaldo (Normativa Costa Rica)")
    st.caption("Periodo legal: 1 de Diciembre del año anterior al 30 de Noviembre del año actual.")
    
    if not db_pagos.empty:
        emp_agui = st.selectbox("Seleccionar Empleado para Aguinaldo", sorted(db_pagos["Trabajador"].unique()), key="agui_emp")
        
        # Selección del año a calcular
        anio_actual = hoy_cr.year
        anio_agui = st.number_input("Año del Aguinaldo", min_value=2024, max_value=2030, value=anio_actual)
        
        f_inicio_agui = datetime(anio_agui - 1, 12, 1).date()
        f_fin_agui = datetime(anio_agui, 11, 30).date()
        
        # Filtrar datos del periodo legal
        mask_agui = (db_pagos["Trabajador"] == emp_agui) & \
                    (db_pagos["Fecha"] >= f_inicio_agui) & \
                    (db_pagos["Fecha"] <= f_fin_agui)
        
        df_agui = db_pagos.loc[mask_agui]
        
        total_acumulado = df_agui["Pago Total"].sum() if not df_agui.empty else 0.0
        monto_aguinaldo = total_acumulado / 12.0
        
        st.markdown("---")
        m1, m2, m3 = st.columns(3)
        m1.metric("Periodo Evaluar", f"{f_inicio_agui.strftime('%d/%m/%Y')} a {f_fin_agui.strftime('%d/%m/%Y')}")
        m2.metric("Total Salarios Devengados", f"₡{total_acumulado:,.2f}")
        m3.metric("🎄 AGUINALDO A PAGAR", f"₡{monto_aguinaldo:,.2f}")
        st.markdown("---")
        
        if not df_agui.empty:
            st.subheader(f"Detalle de turnos sumados para {emp_agui}")
            st.dataframe(df_agui[["Fecha", "Horas", "Pago Total"]], use_container_width=True)
            
            msg_agui = (f"*CÁLCULO DE AGUINALDO - ALASKA*\n"
                        f"👤 *Trabajador:* {emp_agui}\n"
                        f"📅 *Periodo:* {f_inicio_agui.strftime('%d/%m/%Y')} al {f_fin_agui.strftime('%d/%m/%Y')}\n"
                        f"--------------------------\n"
                        f"💵 *Total acumulado:* ₡{total_acumulado:,.2f}\n"
                        f"🎄 *MONTO AGUINALDO:* ₡{monto_aguinaldo:,.2f}\n"
                        f"--------------------------")
            st.link_button(f"📲 Enviar Resumen de Aguinaldo por WhatsApp", f"https://wa.me/?text={urllib.parse.quote(msg_agui)}")
        else:
            st.warning(f"No hay registros de {emp_agui} dentro del periodo de aguinaldo ({f_inicio_agui} al {f_fin_agui}).")

# --- ADMINISTRACIÓN ---
st.markdown("---")
with st.expander("🗑️ Administración: Eliminar Registros"):
    df_ver = db_pagos.copy()
    df_ver['Fecha'] = df_ver['Fecha'].apply(lambda x: x.strftime("%d/%m/%Y") if hasattr(x, 'strftime') else x)
    st.dataframe(df_ver)
    
    id_b = st.number_input("ID a borrar", 0, len(db_pagos)-1 if not db_pagos.empty else 0)
    if st.button("❌ Eliminar Registro"):
        db_pagos = db_pagos.drop(id_b).reset_index(drop=True)
        db_pagos['Fecha'] = db_pagos['Fecha'].apply(lambda x: x.strftime("%d/%m/%Y"))
        conn.update(data=db_pagos)
        st.cache_data.clear()
        st.rerun()
