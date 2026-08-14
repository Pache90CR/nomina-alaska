import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta
import urllib.parse
import plotly.express as px

# Configuración de página
st.set_page_config(page_title="Nómina Bar Restaurante Alaska", layout="wide")

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

# --- ACCESO DE ADMINISTRADOR ---
st.title("🕒 Nómina y Control de Horas: Alaska / La Chinita")

pin_admin = st.sidebar.text_input("🔑 PIN de Administrador", type="password", max_chars=4).strip()

if pin_admin == "1806":
    st.sidebar.success("Acceso concedido")
    
    # --- MENÚ LATERAL DE REGISTROS ---
    st.sidebar.header("📝 Menú de Registro")
    tipo_registro = st.sidebar.radio("¿Qué deseas registrar?", ["Turno de Trabajo", "Vale / Adelanto"])

    if tipo_registro == "Turno de Trabajo":
        with st.sidebar.form("form_turno", clear_on_submit=True):
            st.subheader("Registrar Turno")
            nombre_reg = st.text_input("Nombre del Trabajador")
            fecha_reg = st.date_input("Fecha", hoy_cr)
            c1, c2 = st.columns(2)
            h_in = c1.time_input("Hora Entrada", datetime.strptime("15:00", "%H:%M"))
            h_out = c2.time_input("Hora Salida", datetime.strptime("22:00", "%H:%M"))
            guardar_t = st.form_submit_button("💾 Guardar Turno")

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
                st.sidebar.success(f"✅ Turno guardado para {nombre_reg}")
                st.rerun()
            except Exception as e:
                st.error("Error al guardar turno.")

    else:
        with st.sidebar.form("form_vale", clear_on_submit=True):
            st.subheader("Registrar Vale / Adelanto")
            nombre_vale = st.text_input("Nombre del Trabajador")
            fecha_vale = st.date_input("Fecha", hoy_cr)
            monto_vale = st.number_input("Monto (₡)", min_value=500, step=500)
            concepto_vale = st.text_input("Concepto", "Adelanto / Vale")
            guardar_v = st.form_submit_button("💸 Guardar Vale")

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
                st.sidebar.success(f"✅ Vale guardado para {nombre_vale}")
                st.rerun()
            except Exception as e:
                st.error("Error al guardar vale.")

    # --- PESTAÑAS PRINCIPALES ---
    tab1, tab2, tab3 = st.tabs(["📊 Comprobantes de Pago", "📈 Gráficas y Estadísticas", "🎄 Cálculo de Aguinaldo"])

    # TAB 1: COMPROBANTES DE PAGO
    with tab1:
        if not db_pagos.empty:
            col_a, col_b, col_c = st.columns(3)
            emp_lista = sorted(db_pagos["Trabajador"].unique())
            
            with col_a:
                emp_sel = st.selectbox("Empleado", emp_lista)
            with col_b:
                f_inicio = st.date_input("Desde", viernes_defecto)
            with col_c:
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

                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    st.link_button("📲 Enviar Comprobante por WhatsApp", f"https://wa.me/?text={urllib.parse.quote(msg)}")
                
                with col_btn2:
                    if not df_v_res.empty:
                        if st.button("✅ Liquidar y Cerrar Vales de este Pago"):
                            try:
                                db_v_completa = conn.read(worksheet="Vales", ttl=0)
                                indices_a_liquidar = df_v_res.index
                                db_v_completa.loc[indices_a_liquidar, "Estado"] = "Liquidado"
                                db_v_completa['Fecha'] = pd.to_datetime(db_v_completa['Fecha'], dayfirst=True, errors='coerce').dt.strftime("%d/%m/%Y")
                                conn.update(worksheet="Vales", data=db_v_completa)
                                st.cache_data.clear()
                                st.success("🎉 ¡Vales liquidados exitosamente!")
                                st.rerun()
                            except Exception as e:
                                st.error("Error al liquidar vales.")

                st.subheader("📋 Resumen de Turnos")
                if not df_res.empty:
                    st.dataframe(df_res[["Fecha", "Entrada", "Salida", "Horas", "Pago Total"]], use_container_width=True)
                
                if not df_v_res.empty:
                    st.subheader("💸 Vales Aplicados (Pendientes)")
                    st.dataframe(df_v_res[["Fecha", "Concepto", "Monto", "Estado"]], use_container_width=True)
            else:
                st.warning("No hay turnos ni vales registrados en este rango de fechas.")
        else:
            st.info("No hay registros en la base de datos.")

    # TAB 2: GRÁFICAS
    with tab2:
        st.header("📈 Resumen Gráfico de Planilla")
        if not db_pagos.empty:
            c_g1, c_g2 = st.columns(2)
            with c_g1:
                pagos_emp = db_pagos.groupby("Trabajador")["Pago Total"].sum().reset_index()
                fig_bar = px.bar(pagos_emp, x="Trabajador", y="Pago Total", text_auto='.2s', color="Trabajador", title="Bruto Devengado por Empleado (₡)")
                st.plotly_chart(fig_bar, use_container_width=True)
            with c_g2:
                horas_emp = db_pagos.groupby("Trabajador")["Horas"].sum().reset_index()
                fig_pie = px.pie(horas_emp, values="Horas", names="Trabajador", title="Distribución de Horas Trabajadas")
                st.plotly_chart(fig_pie, use_container_width=True)

    # TAB 3: AGUINALDO
    with tab3:
        st.header("🎄 Cálculo de Aguinaldo (Normativa Costa Rica)")
        if not db_pagos.empty:
            emp_agui = st.selectbox("Trabajador", sorted(db_pagos["Trabajador"].unique()), key="agui_emp")
            anio_actual = hoy_cr.year
            anio_agui = st.number_input("Año del Aguinaldo", min_value=2024, max_value=2030, value=anio_actual)
            
            f_inicio_agui = datetime(anio_agui - 1, 12, 1).date()
            f_fin_agui = datetime(anio_agui, 11, 30).date()
            
            mask_agui = (db_pagos["Trabajador"] == emp_agui) & (db_pagos["Fecha"] >= f_inicio_agui) & (db_pagos["Fecha"] <= f_fin_agui)
            df_agui = db_pagos.loc[mask_agui]
            
            total_acumulado = df_agui["Pago Total"].sum() if not df_agui.empty else 0.0
            monto_aguinaldo = total_acumulado / 12.0
            
            st.markdown("---")
            m1, m2, m3 = st.columns(3)
            m1.metric("Periodo Evaluar", f"{f_inicio_agui.strftime('%d/%m/%Y')} a {f_fin_agui.strftime('%d/%m/%Y')}")
            m2.metric("Total Salarios Devengados", f"₡{total_acumulado:,.2f}")
            m3.metric("🎄 AGUINALDO A PAGAR", f"₡{monto_aguinaldo:,.2f}")

    # ADMINISTRACIÓN
    st.markdown("---")
    with st.expander("🗑️ Administración: Eliminar Registros / Vales"):
        st.subheader("Turnos Trabajados")
        df_ver = db_pagos.copy()
        if not df_ver.empty:
            df_ver['Fecha'] = df_ver['Fecha'].apply(lambda x: x.strftime("%d/%m/%Y") if hasattr(x, 'strftime') else x)
            st.dataframe(df_ver)
            id_b = st.number_input("ID de Turno a borrar", 0, len(db_pagos)-1 if not db_pagos.empty else 0, key="id_turn")
            if st.button("❌ Eliminar Turno"):
                db_pagos = db_pagos.drop(id_b).reset_index(drop=True)
                db_pagos['Fecha'] = db_pagos['Fecha'].apply(lambda x: x.strftime("%d/%m/%Y"))
                conn.update(worksheet="Hoja 1", data=db_pagos)
                st.cache_data.clear()
                st.rerun()

        st.markdown("---")
        st.subheader("Vales y Adelantos")
        df_v_ver = db_vales.copy()
        if not df_v_ver.empty:
            df_v_ver['Fecha'] = df_v_ver['Fecha'].apply(lambda x: x.strftime("%d/%m/%Y") if hasattr(x, 'strftime') else x)
            st.dataframe(df_v_ver)
            id_bv = st.number_input("ID de Vale a borrar", 0, len(db_vales)-1 if not db_vales.empty else 0, key="id_val")
            if st.button("❌ Eliminar Vale"):
                db_vales = db_vales.drop(id_bv).reset_index(drop=True)
                db_vales['Fecha'] = db_vales['Fecha'].apply(lambda x: x.strftime("%d/%m/%Y"))
                conn.update(worksheet="Vales", data=db_vales)
                st.cache_data.clear()
                st.rerun()

else:
    st.warning("🔒 Por favor, ingresa el PIN de Administrador en el menú lateral para acceder.")
