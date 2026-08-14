import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta
import urllib.parse
import plotly.express as px

# --- CONFIGURACIÓN DE PÁGINA PREMIUM ---
st.set_page_config(
    page_title="Nómina & Gestión | Bar Restaurante Alaska",
    page_icon="🍺",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilo CSS personalizado para bordes, sombras y tarjetas
st.markdown("""
    <style>
    .main {
        background-color: #0e1117;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.8rem !important;
        font-weight: 700 !important;
        color: #00E676 !important;
    }
    div[data-testid="stMetric"] {
        background-color: #1e222d;
        padding: 15px;
        border-radius: 12px;
        border: 1px solid #2e3440;
        box-shadow: 0px 4px 10px rgba(0, 0, 0, 0.2);
    }
    .stButton>button {
        border-radius: 8px;
        font-weight: 600;
        transition: all 0.3s ease;
    }
    </style>
""", unsafe_allow_html=True)

TARIFA_POR_HORA = 1300
DIAS_ESPANOL = {
    "Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles",
    "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sábado", "Sunday": "Domingo"
}

# --- LÓGICA DE TIEMPO COSTA RICA ---
ahora_cr = datetime.now() - timedelta(hours=6)
hoy_cr = ahora_cr.date()

dias_desde_viernes = (hoy_cr.weekday() - 4) % 7
viernes_defecto = hoy_cr - timedelta(days=dias_desde_viernes)

conn = st.connection("gsheets", type=GSheetsConnection)

def cargar_datos_limpios(worksheet_name="Hoja 1"):
    try:
        df = conn.read(worksheet=worksheet_name, ttl=0)
        if df is not None and not df.empty:
            if "Fecha" in df.columns:
                df['Fecha'] = pd.to_datetime(df['Fecha'], format='%d/%m/%Y', errors='coerce').dt.date
                df.loc[df['Fecha'].isna(), 'Fecha'] = pd.to_datetime(df['Fecha'], errors='coerce').dt.date
                df = df.dropna(subset=['Fecha'])
            
            if "Trabajador" in df.columns:
                df["Trabajador"] = df["Trabajador"].astype(str).str.strip()
                
            return df
        return pd.DataFrame()
    except:
        return pd.DataFrame()

db_pagos = cargar_datos_limpios("Hoja 1")
db_vales = cargar_datos_limpios("Vales")

if db_pagos.empty:
    db_pagos = pd.DataFrame(columns=["Fecha", "Trabajador", "Entrada", "Salida", "Horas", "Pago Total"])
if db_vales.empty:
    db_vales = pd.DataFrame(columns=["Fecha", "Trabajador", "Monto", "Concepto", "Estado"])

# --- BARRA LATERAL ADMINISTRATIVA ---
st.sidebar.image("https://img.icons8.com/color/96/restaurant-building.png", width=70)
st.sidebar.title("Alaska Control")
st.sidebar.caption("Sistema de Control de Planilla v2.5")

pin_admin = st.sidebar.text_input("🔑 PIN de Acceso", type="password", max_chars=4).strip()

if pin_admin == "1806":
    st.sidebar.success("● Conectado como Administrador")
    st.sidebar.divider()
    
    # --- FORMULARIOS ORGANIZADOS ---
    st.sidebar.subheader("📌 Registro Rápido")
    tipo_registro = st.sidebar.radio("Selecciona Tipo", ["⏱️ Turno Laboral", "💸 Vale / Adelanto"])

    if tipo_registro == "⏱️ Turno Laboral":
        with st.sidebar.form("form_turno", clear_on_submit=True):
            nombre_reg = st.text_input("Trabajador", placeholder="Ej: Gladys")
            fecha_reg = st.date_input("Fecha de Turno", hoy_cr)
            col_h1, col_h2 = st.columns(2)
            h_in = col_h1.time_input("Entrada", datetime.strptime("15:00", "%H:%M"))
            h_out = col_h2.time_input("Salida", datetime.strptime("22:00", "%H:%M"))
            guardar_t = st.form_submit_button("💾 Guardar Turno", use_container_width=True)

        if guardar_t and nombre_reg:
            db_fresca = cargar_datos_limpios("Hoja 1")
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
                if not db_fresca.empty:
                    db_fresca['Fecha'] = db_fresca['Fecha'].apply(lambda x: x.strftime("%d/%m/%Y") if hasattr(x, 'strftime') else x)
                updated = pd.concat([db_fresca, pd.DataFrame([nueva_fila])], ignore_index=True)
                conn.update(worksheet="Hoja 1", data=updated)
                st.cache_data.clear()
                st.toast(f"✅ Turno guardado para {nombre_reg}", icon="🎉")
                st.rerun()
            except Exception as e:
                st.error("Error al guardar turno.")

    else:
        with st.sidebar.form("form_vale", clear_on_submit=True):
            nombre_vale = st.text_input("Trabajador", placeholder="Ej: Gladys")
            fecha_vale = st.date_input("Fecha", hoy_cr)
            monto_vale = st.number_input("Monto (₡)", min_value=500, step=500)
            concepto_vale = st.text_input("Concepto", "Adelanto / Vale")
            guardar_v = st.form_submit_button("💸 Registrar Vale", use_container_width=True)

        if guardar_v and nombre_vale and monto_vale > 0:
            db_v_fresca = cargar_datos_limpios("Vales")
            nueva_fila_v = {
                "Fecha": f"{fecha_vale.day:02d}/{fecha_vale.month:02d}/{fecha_vale.year}",
                "Trabajador": nombre_vale.strip().title(),
                "Monto": float(monto_vale),
                "Concepto": concepto_vale.strip(),
                "Estado": "Pendiente"
            }
            try:
                if not db_v_fresca.empty:
                    db_v_fresca['Fecha'] = db_v_fresca['Fecha'].apply(lambda x: x.strftime("%d/%m/%Y") if hasattr(x, 'strftime') else x)
                updated_v = pd.concat([db_v_fresca, pd.DataFrame([nueva_fila_v])], ignore_index=True)
                conn.update(worksheet="Vales", data=updated_v)
                st.cache_data.clear()
                st.toast(f"✅ Vale guardado para {nombre_vale}", icon="💸")
                st.rerun()
            except Exception as e:
                st.error("Error al guardar vale.")

    # --- CABECERA PRINCIPAL ---
    st.title("🍹 Bar Restaurante Alaska")
    st.caption("Panel de Control Financiero y Gestión de Planilla")
    st.divider()

    # --- PESTAÑAS PRINCIPALES ---
    tab1, tab2, tab3 = st.tabs(["📄 Comprobantes de Pago", "📈 Dashboard Estadístico", "🎄 Módulo de Aguinaldo"])

    # TAB 1: COMPROBANTES DE PAGO
    with tab1:
        if not db_pagos.empty:
            with st.container():
                c_a, c_b, c_c = st.columns([2, 1, 1])
                emp_lista = sorted(db_pagos["Trabajador"].unique())
                
                with c_a:
                    emp_sel = st.selectbox("👤 Seleccionar Colaborador", emp_lista)
                with c_b:
                    f_inicio = st.date_input("📅 Desde", viernes_defecto)
                with c_c:
                    f_fin = st.date_input("📅 Hasta", hoy_cr)

            mask = (db_pagos["Trabajador"] == emp_sel) & (db_pagos["Fecha"] >= f_inicio) & (db_pagos["Fecha"] <= f_fin)
            df_res = db_pagos.loc[mask].sort_values('Fecha').copy()

            if not db_vales.empty:
                if "Estado" not in db_vales.columns:
                    db_vales["Estado"] = "Pendiente"
                mask_v = (db_vales["Trabajador"] == emp_sel) & (db_vales["Fecha"] >= f_inicio) & (db_vales["Fecha"] <= f_fin) & (db_vales["Estado"] == "Pendiente")
                df_v_res = db_vales.loc[mask_v].sort_values('Fecha').copy()
            else:
                df_v_res = pd.DataFrame()

            if not df_res.empty or not df_v_res.empty:
                total_h = df_res["Horas"].sum() if not df_res.empty else 0.0
                total_p = df_res["Pago Total"].sum() if not df_res.empty else 0.0
                total_v = df_v_res["Monto"].sum() if not df_v_res.empty else 0.0
                neto_pagar = total_p - total_v

                st.subheader(f"Resumen de Pago: {emp_sel}")
                
                # METRIC CARDS (DASHBOARD)
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("⏳ Horas Totales", f"{total_h:.2f} hrs")
                m2.metric("💵 Bruto Devengado", f"₡{total_p:,.0f}")
                m3.metric("🔻 Vales / Adelantos", f"₡{total_v:,.0f}")
                m4.metric("💰 NETO A PAGAR", f"₡{neto_pagar:,.0f}")
                
                st.divider()

                # CONSTRUCCIÓN DE MENSAJE WHATSAPP
                detalle = ""
                if not df_res.empty:
                    for _, r in df_res.iterrows():
                        dia_nombre = DIAS_ESPANOL[pd.to_datetime(r['Fecha']).strftime('%A')]
                        detalle += f"• {dia_nombre} {r['Fecha'].strftime('%d/%m/%Y')}: {r['Entrada']} a {r['Salida']} ({r['Horas']}h) -> ₡{r['Pago Total']:,.2f}\n"

                detalle_vales = ""
                if not df_v_res.empty:
                    for _, rv in df_v_res.iterrows():
                        detalle_vales += f"• {rv['Fecha'].strftime('%d/%m/%Y')}: {rv['Concepto']} -> -₡{rv['Monto']:,.2f}\n"

                msg = (f"*COMPROBANTE DE PAGO - ALASKA*\n👤 *Trabajador:* {emp_sel}\n"
                       f"📅 *Periodo:* {f_inicio.strftime('%d/%m/%Y')} al {f_fin.strftime('%d/%m/%Y')}\n"
                       f"--------------------------\n*Detalle de turnos:*\n{detalle}"
                       f"--------------------------\n"
                       f"⏳ *Total Horas:* {total_h:.2f} hrs\n"
                       f"💵 *Bruto Devengado:* ₡{total_p:,.2f}\n")

                if not df_v_res.empty:
                    msg += f"--------------------------\n*Rebajo de Vales/Adelantos:*\n{detalle_vales}"
                    msg += f"🔻 *Total Vales/Adelantos:* -₡{total_v:,.2f}\n"

                msg += f"--------------------------\n💰 *NETO A PAGAR: ₡{neto_pagar:,.2f}*\n--------------------------"

                col_b1, col_b2 = st.columns([2, 1])
                with col_b1:
                    st.link_button("📲 Enviar Comprobante por WhatsApp", f"https://wa.me/?text={urllib.parse.quote(msg)}", use_container_width=True)
                
                with col_b2:
                    if not df_v_res.empty:
                        if st.button("✅ Liquidar Vales de este Periodo", use_container_width=True):
                            try:
                                db_v_completa = conn.read(worksheet="Vales", ttl=0)
                                indices_a_liquidar = df_v_res.index
                                db_v_completa.loc[indices_a_liquidar, "Estado"] = "Liquidado"
                                db_v_completa['Fecha'] = pd.to_datetime(db_v_completa['Fecha'], dayfirst=True, errors='coerce').dt.strftime("%d/%m/%Y")
                                conn.update(worksheet="Vales", data=db_v_completa)
                                st.cache_data.clear()
                                st.toast("Vales liquidados exitosamente", icon="✅")
                                st.rerun()
                            except Exception as e:
                                st.error("Error al liquidar vales.")

                st.subheader("📋 Detalle de Turnos Registrados")
                if not df_res.empty:
                    st.dataframe(df_res[["Fecha", "Entrada", "Salida", "Horas", "Pago Total"]], use_container_width=True)
                
                if not df_v_res.empty:
                    st.subheader("💸 Vales y Adelantos Aplicados")
                    st.dataframe(df_v_res[["Fecha", "Concepto", "Monto", "Estado"]], use_container_width=True)
            else:
                st.info("No hay registros en el rango de fechas seleccionado.")
        else:
            st.info("No hay registros de planilla guardados en la base de datos.")

    # TAB 2: GRÁFICAS Y DASHBOARD
    with tab2:
        st.subheader("📊 Análisis y Estadísticas de Planilla")
        if not db_pagos.empty:
            c_g1, c_g2 = st.columns(2)
            with c_g1:
                pagos_emp = db_pagos.groupby("Trabajador")["Pago Total"].sum().reset_index()
                fig_bar = px.bar(
                    pagos_emp, x="Trabajador", y="Pago Total", text_auto='.2s', color="Trabajador",
                    title="Monto Invertido por Colaborador (₡)",
                    color_discrete_sequence=px.colors.qualitative.Dark24
                )
                fig_bar.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig_bar, use_container_width=True)
            
            with c_g2:
                horas_emp = db_pagos.groupby("Trabajador")["Horas"].sum().reset_index()
                fig_pie = px.pie(
                    horas_emp, values="Horas", names="Trabajador", title="Distribución Relativa de Horas",
                    hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel
                )
                fig_pie.update_layout(paper_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.info("Registra turnos para visualizar las gráficas.")

    # TAB 3: AGUINALDO
    with tab3:
        st.subheader("🎄 Cálculo Legal de Aguinaldo (Costa Rica)")
        st.caption("Cálculo sobre el acumulado de salarios devengados entre el 1 de Diciembre y el 30 de Noviembre.")
        
        if not db_pagos.empty:
            emp_agui = st.selectbox("Seleccionar Colaborador", sorted(db_pagos["Trabajador"].unique()), key="agui_emp")
            anio_actual = hoy_cr.year
            anio_agui = st.number_input("Año del Cálculo", min_value=2024, max_value=2030, value=anio_actual)
            
            f_inicio_agui = datetime(anio_agui - 1, 12, 1).date()
            f_fin_agui = datetime(anio_agui, 11, 30).date()
            
            mask_agui = (db_pagos["Trabajador"] == emp_agui) & (db_pagos["Fecha"] >= f_inicio_agui) & (db_pagos["Fecha"] <= f_fin_agui)
            df_agui = db_pagos.loc[mask_agui]
            
            total_acumulado = df_agui["Pago Total"].sum() if not df_agui.empty else 0.0
            monto_aguinaldo = total_acumulado / 12.0
            
            st.divider()
            a1, a2, a3 = st.columns(3)
            a1.metric("Periodo Evaluado", f"{f_inicio_agui.strftime('%d/%m/%Y')} al {f_fin_agui.strftime('%d/%m/%Y')}")
            a2.metric("Acumulado Devengado", f"₡{total_acumulado:,.2f}")
            a3.metric("🎄 AGUINALDO PROYECTADO", f"₡{monto_aguinaldo:,.2f}")
            st.divider()

    # --- SECCIÓN DE ADMINISTRACIÓN / ELIMINACIÓN ---
    st.divider()
    with st.expander("🗑️ Centro de Mantenimiento (Eliminar Registros Error)"):
        col_del1, col_del2 = st.columns(2)
        
        with col_del1:
            st.write("**Turnos de Trabajo**")
            df_ver = db_pagos.copy()
            if not df_ver.empty:
                df_ver['Fecha'] = df_ver['Fecha'].apply(lambda x: x.strftime("%d/%m/%Y") if hasattr(x, 'strftime') else x)
                st.dataframe(df_ver, use_container_width=True)
                id_b = st.number_input("ID de Turno a borrar", 0, len(db_pagos)-1 if not db_pagos.empty else 0, key="id_turn")
                if st.button("❌ Eliminar Turno", use_container_width=True):
                    db_pagos = db_pagos.drop(id_b).reset_index(drop=True)
                    db_pagos['Fecha'] = db_pagos['Fecha'].apply(lambda x: x.strftime("%d/%m/%Y"))
                    conn.update(worksheet="Hoja 1", data=db_pagos)
                    st.cache_data.clear()
                    st.toast("Turno eliminado", icon="🗑️")
                    st.rerun()

        with col_del2:
            st.write("**Vales y Adelantos**")
            df_v_ver = db_vales.copy()
            if not df_v_ver.empty:
                df_v_ver['Fecha'] = df_v_ver['Fecha'].apply(lambda x: x.strftime("%d/%m/%Y") if hasattr(x, 'strftime') else x)
                st.dataframe(df_v_ver, use_container_width=True)
                id_bv = st.number_input("ID de Vale a borrar", 0, len(db_vales)-1 if not db_vales.empty else 0, key="id_val")
                if st.button("❌ Eliminar Vale", use_container_width=True):
                    db_vales = db_vales.drop(id_bv).reset_index(drop=True)
                    db_vales['Fecha'] = db_vales['Fecha'].apply(lambda x: x.strftime("%d/%m/%Y"))
                    conn.update(worksheet="Vales", data=db_vales)
                    st.cache_data.clear()
                    st.toast("Vale eliminado", icon="🗑️")
                    st.rerun()

else:
    # PANTALLA DE ACCESO PROTEGIDO
    st.markdown("<br><br>", unsafe_allow_html=True)
    c_login1, c_login2, c_login3 = st.columns([1, 2, 1])
    with c_login2:
        st.info("🔒 Sistema de Control Interno Protegido. Ingresa tu PIN de Administrador en la barra lateral izquierda para acceder.")
