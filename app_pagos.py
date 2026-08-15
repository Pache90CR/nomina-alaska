import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta
import urllib.parse
import plotly.express as px

# Configuración de página
st.set_page_config(page_title="Nómina Alaska", layout="wide")

# CSS personalizado compacto
st.markdown("""
    <style>
    div[data-testid="stMetricValue"] {
        font-size: 1.2rem !important;
        font-weight: 600 !important;
        color: #ffffff !important;
    }
    div[data-testid="stMetricLabel"] {
        font-size: 0.85rem !important;
    }
    div[data-testid="stMetric"] {
        background-color: #1e222d;
        padding: 8px 12px !important;
        border-radius: 6px;
        border: 1px solid #2e3440;
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

# --- ACCESO ADMINISTRADOR ---
st.title("Nómina Alaska")

pin_admin = st.sidebar.text_input("PIN de Administrador", type="password", max_chars=4).strip()

if pin_admin == "1806":
    st.sidebar.caption("Acceso concedido")
    
    # --- BARRA LATERAL ---
    st.sidebar.subheader("Registro")
    tipo_registro = st.sidebar.radio("Tipo", ["Turno de Trabajo", "Vale / Adelanto"])

    if tipo_registro == "Turno de Trabajo":
        st.sidebar.markdown("---")
        accion_turno = st.sidebar.radio("Acción de Turno", ["Registrar Entrada", "Registrar Salida"])
        
        if accion_turno == "Registrar Entrada":
            with st.sidebar.form("form_entrada", clear_on_submit=True):
                nombre_reg = st.text_input("Trabajador")
                fecha_reg = st.date_input("Fecha", hoy_cr)
                h_in = st.time_input("Hora Entrada", ahora_cr.time())
                guardar_e = st.form_submit_button("Marcar Entrada")

            if guardar_e and nombre_reg:
                db_fresca = cargar_datos_limpios("Hoja 1")
                nueva_fila = {
                    "Fecha": f"{fecha_reg.day:02d}/{fecha_reg.month:02d}/{fecha_reg.year}",
                    "Trabajador": nombre_reg.strip().title(),
                    "Entrada": h_in.strftime("%H:%M"),
                    "Salida": "Pendiente",
                    "Horas": 0.0,
                    "Pago Total": 0.0
                }
                try:
                    if not db_fresca.empty:
                        db_fresca['Fecha'] = db_fresca['Fecha'].apply(lambda x: x.strftime("%d/%m/%Y") if hasattr(x, 'strftime') else x)
                    updated = pd.concat([db_fresca, pd.DataFrame([nueva_fila])], ignore_index=True)
                    conn.update(worksheet="Hoja 1", data=updated)
                    st.cache_data.clear()
                    st.sidebar.success(f"Entrada de {nombre_reg} guardada")
                    st.rerun()
                except Exception as e:
                    st.error("Error al guardar entrada.")

        elif accion_turno == "Registrar Salida":
            db_fresca = cargar_datos_limpios("Hoja 1")
            
            # Filtrar turnos pendientes
            if not db_fresca.empty:
                turnos_pendientes = db_fresca[db_fresca["Salida"] == "Pendiente"]
            else:
                turnos_pendientes = pd.DataFrame()

            if not turnos_pendientes.empty:
                with st.sidebar.form("form_salida", clear_on_submit=True):
                    # Seleccionar trabajador con turno abierto
                    emp_pendiente = st.selectbox("Trabajador con turno abierto", turnos_pendientes["Trabajador"].unique())
                    h_out = st.time_input("Hora Salida", ahora_cr.time())
                    guardar_s = st.form_submit_button("Cerrar Turno (Salida)")

                if guardar_s and emp_pendiente:
                    # Obtener el último turno abierto de ese empleado
                    idx = db_fresca[(db_fresca["Trabajador"] == emp_pendiente) & (db_fresca["Salida"] == "Pendiente")].index[-1]
                    
                    fecha_t = db_fresca.loc[idx, "Fecha"]
                    h_in_str = db_fresca.loc[idx, "Entrada"]
                    
                    dt_in = datetime.combine(fecha_t, datetime.strptime(h_in_str, "%H:%M").time())
                    dt_out = datetime.combine(fecha_t, h_out)
                    if dt_out <= dt_in: dt_out += timedelta(days=1)
                    
                    cant_horas = (dt_out - dt_in).total_seconds() / 3600
                    pago_dia = cant_horas * TARIFA_POR_HORA
                    
                    # Actualizar fila
                    db_fresca.loc[idx, "Salida"] = h_out.strftime("%H:%M")
                    db_fresca.loc[idx, "Horas"] = round(cant_horas, 2)
                    db_fresca.loc[idx, "Pago Total"] = round(pago_dia, 2)
                    
                    try:
                        db_fresca['Fecha'] = db_fresca['Fecha'].apply(lambda x: x.strftime("%d/%m/%Y") if hasattr(x, 'strftime') else x)
                        conn.update(worksheet="Hoja 1", data=db_fresca)
                        st.cache_data.clear()
                        st.sidebar.success(f"Salida de {emp_pendiente} registrada ({round(cant_horas, 2)}h)")
                        st.rerun()
                    except Exception as e:
                        st.error("Error al cerrar turno.")
            else:
                st.sidebar.info("No hay turnos pendientes por cerrar.")

    else:
        with st.sidebar.form("form_vale", clear_on_submit=True):
            nombre_vale = st.text_input("Trabajador")
            fecha_vale = st.date_input("Fecha", hoy_cr)
            monto_vale = st.number_input("Monto (₡)", min_value=500, step=500)
            concepto_vale = st.text_input("Concepto", "Adelanto / Vale")
            guardar_v = st.form_submit_button("Guardar Vale")

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
                st.sidebar.success("Guardado")
                st.rerun()
            except Exception as e:
                st.error("Error al guardar.")

    # --- PESTAÑAS ---
    tab1, tab2, tab3 = st.tabs(["Comprobantes", "Gráficas", "Aguinaldo"])

    # TAB 1: COMPROBANTES
    with tab1:
        if not db_pagos.empty:
            emp_lista = sorted(db_pagos["Trabajador"].unique())
            
            emp_sel = st.selectbox("Seleccionar Empleado", emp_lista)
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                f_inicio = st.date_input("Desde", viernes_defecto)
            with col_f2:
                f_fin = st.date_input("Hasta", hoy_cr)

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
                
                m_col1, m_col2 = st.columns(2)
                m_col1.metric("Horas Totales", f"{total_h:.2f} hrs")
                m_col2.metric("Bruto Devengado", f"₡{total_p:,.0f}")
                
                m_col3, m_col4 = st.columns(2)
                m_col3.metric("Vales / Adelantos", f"₡{total_v:,.0f}")
                m_col4.metric("NETO A PAGAR", f"₡{neto_pagar:,.0f}")

                # MENSAJE WHATSAPP
                detalle = ""
                if not df_res.empty:
                    for _, r in df_res.iterrows():
                        dia_nombre = DIAS_ESPANOL[pd.to_datetime(r['Fecha']).strftime('%A')]
                        salida_lbl = r['Salida'] if r['Salida'] != "Pendiente" else "Sin cerrar"
                        detalle += f"• {dia_nombre} {r['Fecha'].strftime('%d/%m/%Y')}: {r['Entrada']} a {salida_lbl} ({r['Horas']}h) -> ₡{r['Pago Total']:,.2f}\n"

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

                st.link_button("Enviar Comprobante por WhatsApp", f"https://wa.me/?text={urllib.parse.quote(msg)}")
                
                if not df_v_res.empty:
                    if st.button("Liquidar Vales de este Periodo"):
                        try:
                            db_v_completa = conn.read(worksheet="Vales", ttl=0)
                            indices_a_liquidar = df_v_res.index
                            db_v_completa.loc[indices_a_liquidar, "Estado"] = "Liquidado"
                            db_v_completa['Fecha'] = pd.to_datetime(db_v_completa['Fecha'], dayfirst=True, errors='coerce').dt.strftime("%d/%m/%Y")
                            conn.update(worksheet="Vales", data=db_v_completa)
                            st.cache_data.clear()
                            st.success("Vales liquidados")
                            st.rerun()
                        except Exception as e:
                            st.error("Error al liquidar vales.")

                st.write("**Detalle de Turnos**")
                if not df_res.empty:
                    st.dataframe(df_res[["Fecha", "Entrada", "Salida", "Horas", "Pago Total"]], use_container_width=True)
                
                if not df_v_res.empty:
                    st.write("**Vales Aplicados**")
                    st.dataframe(df_v_res[["Fecha", "Concepto", "Monto", "Estado"]], use_container_width=True)
            else:
                st.warning("No hay datos en el rango seleccionado.")
        else:
            st.info("No hay registros cargados.")

    # TAB 2: GRÁFICAS
    with tab2:
        st.subheader("Estadísticas")
        if not db_pagos.empty:
            pagos_emp = db_pagos.groupby("Trabajador")["Pago Total"].sum().reset_index()
            fig_bar = px.bar(pagos_emp, x="Trabajador", y="Pago Total", text_auto='.2s', title="Monto por Empleado (₡)")
            st.plotly_chart(fig_bar, use_container_width=True)

    # TAB 3: AGUINALDO
    with tab3:
        st.subheader("Cálculo de Aguinaldo")
        if not db_pagos.empty:
            emp_agui = st.selectbox("Trabajador", sorted(db_pagos["Trabajador"].unique()), key="agui_emp")
            anio_actual = hoy_cr.year
            anio_agui = st.number_input("Año", min_value=2024, max_value=2030, value=anio_actual)
            
            f_inicio_agui = datetime(anio_agui - 1, 12, 1).date()
            f_fin_agui = datetime(anio_agui, 11, 30).date()
            
            mask_agui = (db_pagos["Trabajador"] == emp_agui) & (db_pagos["Fecha"] >= f_inicio_agui) & (db_pagos["Fecha"] <= f_fin_agui)
            df_agui = db_pagos.loc[mask_agui]
            
            total_acumulado = df_agui["Pago Total"].sum() if not df_agui.empty else 0.0
            monto_aguinaldo = total_acumulado / 12.0
            
            st.metric("Total Devengado", f"₡{total_acumulado:,.2f}")
            st.metric("Aguinaldo Proyectado", f"₡{monto_aguinaldo:,.2f}")

    # ELIMINACIÓN
    with st.expander("Administración: Eliminar Registros"):
        st.write("Turnos")
        df_ver = db_pagos.copy()
        if not df_ver.empty:
            df_ver['Fecha'] = df_ver['Fecha'].apply(lambda x: x.strftime("%d/%m/%Y") if hasattr(x, 'strftime') else x)
            st.dataframe(df_ver, use_container_width=True)
            id_b = st.number_input("ID a borrar", 0, len(db_pagos)-1 if not db_pagos.empty else 0, key="id_turn")
            if st.button("Eliminar Turno"):
                db_pagos = db_pagos.drop(id_b).reset_index(drop=True)
                db_pagos['Fecha'] = db_pagos['Fecha'].apply(lambda x: x.strftime("%d/%m/%Y"))
                conn.update(worksheet="Hoja 1", data=db_pagos)
                st.cache_data.clear()
                st.rerun()

        st.write("Vales")
        df_v_ver = db_vales.copy()
        if not df_v_ver.empty:
            df_v_ver['Fecha'] = df_v_ver['Fecha'].apply(lambda x: x.strftime("%d/%m/%Y") if hasattr(x, 'strftime') else x)
            st.dataframe(df_v_ver, use_container_width=True)
            id_bv = st.number_input("ID Vale a borrar", 0, len(db_vales)-1 if not db_vales.empty else 0, key="id_val")
            if st.button("Eliminar Vale"):
                db_vales = db_vales.drop(id_bv).reset_index(drop=True)
                db_vales['Fecha'] = db_vales['Fecha'].apply(lambda x: x.strftime("%d/%m/%Y"))
                conn.update(worksheet="Vales", data=db_vales)
                st.cache_data.clear()
                st.rerun()

else:
    st.info("Ingresa el PIN de Administrador en la barra lateral.")
