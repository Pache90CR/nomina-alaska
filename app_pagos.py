import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta
import urllib.parse
import plotly.express as px

# Configuración de página
st.set_page_config(page_title="Asistencia y Nómina Alaska", layout="wide")

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
            
            # Limpieza especial de PINs (convierte 1806.0 a "1806")
            if "PIN" in df.columns:
                df["PIN"] = df["PIN"].astype(str).str.replace(".0", "", regex=False).str.strip()
            
            if "Trabajador" in df.columns:
                df["Trabajador"] = df["Trabajador"].astype(str).str.strip()
                
            return df
        return pd.DataFrame()
    except:
        return pd.DataFrame()

db_pagos = cargar_datos_limpios("Hoja 1")
db_vales = cargar_datos_limpios("Vales")
db_pines = cargar_datos_limpios("Pines")

if db_pagos.empty:
    db_pagos = pd.DataFrame(columns=["Fecha", "Trabajador", "Entrada", "Salida", "Horas", "Pago Total"])
if db_vales.empty:
    db_vales = pd.DataFrame(columns=["Fecha", "Trabajador", "Monto", "Concepto", "Estado"])
if db_pines.empty:
    db_pines = pd.DataFrame([
        {"Trabajador": "Administrador", "PIN": "1806", "Rol": "Admin"},
        {"Trabajador": "Gladys", "PIN": "1234", "Rol": "Empleado"}
    ])

# --- INICIALIZAR SESIÓN DE USUARIO ---
if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False
    st.session_state["usuario"] = ""
    st.session_state["rol"] = ""

# --- PANTALLA DE INICIO DE SESIÓN (LOGIN) ---
if not st.session_state["autenticado"]:
    st.title("🔒 Control de Acceso: Bar Restaurante Alaska")
    st.subheader("Ingresa tu PIN para acceder al sistema")
    
    lista_usuarios = sorted(db_pines["Trabajador"].unique()) if not db_pines.empty else ["Administrador"]
    usuario_sel = st.selectbox("Selecciona tu Nombre", lista_usuarios)
    pin_ingresado = st.text_input("PIN de 4 dígitos", type="password", max_chars=4).strip()
    
    if st.button("🔓 Entrar"):
        usuario_info = db_pines[db_pines["Trabajador"] == usuario_sel]
        if not usuario_info.empty:
            pin_real = str(usuario_info["PIN"].values[0]).replace(".0", "").strip()
            rol_real = str(usuario_info["Rol"].values[0]).strip() if "Rol" in usuario_info.columns else ("Admin" if usuario_sel == "Administrador" else "Empleado")
            
            if pin_ingresado == pin_real:
                st.session_state["autenticado"] = True
                st.session_state["usuario"] = usuario_sel
                st.session_state["rol"] = rol_real
                st.success(f"Bienvenido/a {usuario_sel}")
                st.rerun()
            else:
                st.error("❌ PIN incorrecto.")
        else:
            st.error("Usuario no encontrado.")

else:
    # BOTÓN DE CERRAR SESIÓN EN LA BARRA LATERAL
    st.sidebar.write(f"👤 **Usuario:** {st.session_state['usuario']}")
    st.sidebar.write(f"🔑 **Rol:** {st.session_state['rol']}")
    if st.sidebar.button("🔒 Cerrar Sesión"):
        st.session_state["autenticado"] = False
        st.session_state["usuario"] = ""
        st.session_state["rol"] = ""
        st.rerun()

    # =========================================================================
    # VISTA 1: PANTALLA EXCLUSIVA DE EMPLEADO (SOLO MARCAJE DE ENTRADA/SALIDA)
    # =========================================================================
    if st.session_state["rol"] == "Empleado":
        st.title(f"🕒 Marcaje de Asistencia: {st.session_state['usuario']}")
        st.info("Utiliza esta pantalla para marcar el inicio o fin de tu turno de trabajo.")
        
        tipo_marcaje = st.radio("Acción a realizar", ["Marcar Entrada", "Marcar Salida"], horizontal=True)
        
        if st.button("⏱️ Confirmar Marcaje Ahora", use_container_width=True):
            hora_actual_str = ahora_cr.strftime("%H:%M")
            fecha_actual_str = f"{hoy_cr.day:02d}/{hoy_cr.month:02d}/{hoy_cr.year}"
            emp_marcaje = st.session_state['usuario']
            
            db_fresca = cargar_datos_limpios("Hoja 1")
            
            mask_hoy = (db_fresca["Trabajador"] == emp_marcaje) & (db_fresca["Fecha"] == hoy_cr) & (db_fresca["Salida"] == "Pendiente") if not db_fresca.empty else pd.Series([False])
            
            if tipo_marcaje == "Marcar Entrada":
                if not db_fresca.empty and mask_hoy.any():
                    st.warning("⚠️ Ya tienes una entrada marcada para hoy sin cerrar salida.")
                else:
                    nueva_entrada = {
                        "Fecha": fecha_actual_str,
                        "Trabajador": emp_marcaje,
                        "Entrada": hora_actual_str,
                        "Salida": "Pendiente",
                        "Horas": 0.0,
                        "Pago Total": 0.0
                    }
                    if not db_fresca.empty:
                        db_fresca['Fecha'] = db_fresca['Fecha'].apply(lambda x: x.strftime("%d/%m/%Y") if hasattr(x, 'strftime') else x)
                    updated = pd.concat([db_fresca, pd.DataFrame([nueva_entrada])], ignore_index=True)
                    conn.update(worksheet="Hoja 1", data=updated)
                    st.cache_data.clear()
                    st.success(f"✅ ¡Entrada registrada a las {hora_actual_str}!")

            elif tipo_marcaje == "Marcar Salida":
                if not db_fresca.empty and mask_hoy.any():
                    idx = db_fresca[mask_hoy].index[-1]
                    h_in_str = db_fresca.loc[idx, "Entrada"]
                    
                    dt_in = datetime.combine(hoy_cr, datetime.strptime(h_in_str, "%H:%M").time())
                    dt_out = datetime.combine(hoy_cr, ahora_cr.time())
                    if dt_out <= dt_in: dt_out += timedelta(days=1)
                    
                    cant_horas = (dt_out - dt_in).total_seconds() / 3600
                    pago_dia = cant_horas * TARIFA_POR_HORA
                    
                    db_fresca.loc[idx, "Salida"] = hora_actual_str
                    db_fresca.loc[idx, "Horas"] = round(cant_horas, 2)
                    db_fresca.loc[idx, "Pago Total"] = round(pago_dia, 2)
                    
                    db_fresca['Fecha'] = db_fresca['Fecha'].apply(lambda x: x.strftime("%d/%m/%Y") if hasattr(x, 'strftime') else x)
                    conn.update(worksheet="Hoja 1", data=db_fresca)
                    st.cache_data.clear()
                    st.success(f"🏁 ¡Salida registrada a las {hora_actual_str}! ({round(cant_horas, 2)} hrs trabajadas)")
                else:
                    st.error("⚠️ No se encontró una entrada pendiente para hoy.")

    # =========================================================================
    # VISTA 2: PANTALLA COMPLETA DE ADMINISTRADOR
    # =========================================================================
    elif st.session_state["rol"] == "Admin":
        st.title("🛡️ Panel de Administración: Bar Restaurante Alaska")
        
        st.sidebar.header("📝 Menú de Gestión")
        opcion_registro = st.sidebar.radio("Opciones", ["Registrar Vale / Adelanto", "Gestionar PINs y Usuarios"])

        if opcion_registro == "Registrar Vale / Adelanto":
            with st.sidebar.form("form_vale", clear_on_submit=True):
                st.subheader("Registrar Vale / Adelanto")
                nombre_vale = st.text_input("Trabajador")
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
                    st.sidebar.success("✅ Vale guardado")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al guardar vale: {e}")

        else:
            with st.sidebar.form("form_pin", clear_on_submit=True):
                st.subheader("Asignar PIN y Rol")
                emp_pin = st.text_input("Nombre del Empleado")
                num_pin = st.text_input("Asignar PIN (4 dígitos)", max_chars=4)
                rol_sel = st.selectbox("Rol de Acceso", ["Empleado", "Admin"])
                guardar_p = st.form_submit_button("🔐 Guardar Usuario")

            if guardar_p and emp_pin and len(num_pin) == 4:
                db_p_fresca = cargar_datos_limpios("Pines")
                nuevo_p = {"Trabajador": emp_pin.strip().title(), "PIN": str(num_pin).strip(), "Rol": rol_sel}
                try:
                    if not db_p_fresca.empty:
                        db_p_fresca = db_p_fresca[db_p_fresca["Trabajador"] != emp_pin.strip().title()]
                    updated_p = pd.concat([db_p_fresca, pd.DataFrame([nuevo_p])], ignore_index=True)
                    conn.update(worksheet="Pines", data=updated_p)
                    st.cache_data.clear()
                    st.sidebar.success(f"✅ Usuario {emp_pin} guardado como {rol_sel}")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al guardar usuario: {e}")

        # PESTAÑAS ADMINISTRATIVAS
        tab1, tab2, tab3 = st.tabs(["📊 Comprobantes de Pago", "📈 Gráficas y Estadísticas", "🎄 Aguinaldos"])

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
                            salida_lbl = r['Salida'] if r['Salida'] != "Pendiente" else "Sin marcar"
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

                    st.dataframe(df_res[["Fecha", "Entrada", "Salida", "Horas", "Pago Total"]], use_container_width=True)
                    if not df_v_res.empty:
                        st.subheader("💸 Vales Aplicados (Pendientes)")
                        st.dataframe(df_v_res[["Fecha", "Concepto", "Monto", "Estado"]], use_container_width=True)
                else:
                    st.warning("No hay datos en el rango seleccionado.")

        with tab2:
            st.header("📈 Resumen Gráfico")
            if not db_pagos.empty:
                c_g1, c_g2 = st.columns(2)
                with c_g1:
                    pagos_emp = db_pagos.groupby("Trabajador")["Pago Total"].sum().reset_index()
                    fig_bar = px.bar(pagos_emp, x="Trabajador", y="Pago Total", text_auto='.2s', color="Trabajador", title="Bruto Devengado (₡)")
                    st.plotly_chart(fig_bar, use_container_width=True)
                with c_g2:
                    horas_emp = db_pagos.groupby("Trabajador")["Horas"].sum().reset_index()
                    fig_pie = px.pie(horas_emp, values="Horas", names="Trabajador", title="Porcentaje de Horas")
                    st.plotly_chart(fig_pie, use_container_width=True)

        with tab3:
            st.header("🎄 Cálculo de Aguinaldo")
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
