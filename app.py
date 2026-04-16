import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection

st.set_page_config(page_title="FC26 Pro Tracker", page_icon="🏆", layout="wide")

# 1. CONEXIÓN A GOOGLE SHEETS
conn = st.connection("gsheets", type=GSheetsConnection)

try:
    df_partidos = conn.read(worksheet="Partidos", usecols=[0, 1, 2, 3, 4, 5, 6], ttl=5).dropna(how="all")
    df_goleadores = conn.read(worksheet="Goleadores", usecols=[0, 1, 2, 3, 4], ttl=5).dropna(how="all")
    df_equipos = conn.read(worksheet="Equipos", usecols=[0, 1], ttl=5).dropna(how="all")
    # Nueva tabla de transferencias
    df_transferencias = conn.read(worksheet="Transferencias", usecols=[0, 1, 2, 3, 4], ttl=5).dropna(how="all")
except Exception as e:
    st.error(f"⚠️ Atención: Verifica tu conexión a Google Sheets o las pestañas.")
    df_partidos = pd.DataFrame(columns=["Torneo", "Jornada", "Local", "Goles_L", "Goles_V", "Visitante", "WO"])
    df_goleadores = pd.DataFrame(columns=["Torneo", "Jornada", "Equipo", "Jugador", "Goles"])
    df_equipos = pd.DataFrame(columns=["Torneo", "Equipo"])
    df_transferencias = pd.DataFrame(columns=["Torneo", "Jornada", "Equipo", "Toma", "Cede"])

# --- LÓGICA DEL CALENDARIO MATEMÁTICO ---
def generar_calendario(equipos_lista, semana):
    if len(equipos_lista) < 6:
        return []
    plantilla = [
        [(0,1), (2,3)], [(4,5), (0,2)], [(1,3), (4,2)], [(0,4), (1,5)], 
        [(2,5), (3,0)], [(1,4), (3,5)], [(0,5), (1,2)], [(3,4)]
    ]
    calendario = []
    for j_idx, jornada in enumerate(plantilla):
        for partido in jornada:
            loc_idx, vis_idx = partido
            if semana % 2 == 0:
                loc_idx, vis_idx = vis_idx, loc_idx
            calendario.append({
                "Jornada": f"S{semana}J{j_idx+1}",
                "Local": equipos_lista[loc_idx],
                "Visitante": equipos_lista[vis_idx]
            })
    return calendario

# --- BARRA LATERAL ---
with st.sidebar:
    st.header("⚙️ Configuración Actual")
    lista_torneos = df_equipos['Torneo'].unique().tolist() if not df_equipos.empty else ["Sin Torneos"]
    torneo_actual = st.selectbox("Torneo Activo:", lista_torneos)
    semana_actual = st.number_input("Semana de Juego:", min_value=1, max_value=20, value=1)

st.title(f"🏆 Torneo FifafoFumar FC26 - {torneo_actual}")

equipos_activos = df_equipos[df_equipos['Torneo'] == torneo_actual]['Equipo'].tolist() if not df_equipos.empty else []

# Ahora tenemos 5 pestañas
tab_registro, tab_tabla, tab_goleo, tab_transf, tab_config = st.tabs(["📝 Calendario", "📊 Posiciones", "⚽ Goleo", "🔄 Transferencias", "⚙️ Configuración"])

# --- PESTAÑA 5: CONFIGURACIÓN ---
with tab_config:
    st.subheader("Alta de Torneos y Jugadores")
    col_t, col_e = st.columns(2)
    with col_t: nuevo_torneo = st.text_input("Nombre del Torneo:")
    with col_e: nuevo_equipo = st.text_input("Emoji + Equipo + (Manager):")
        
    if st.button("Inscribir Jugador"):
        if nuevo_torneo and nuevo_equipo:
            duplicado = df_equipos[(df_equipos['Torneo'] == nuevo_torneo) & (df_equipos['Equipo'] == nuevo_equipo)]
            if not duplicado.empty:
                st.error("Ese equipo ya está inscrito.")
            else:
                nuevo_registro = pd.DataFrame([{"Torneo": nuevo_torneo, "Equipo": nuevo_equipo}])
                df_equipos_actualizado = pd.concat([df_equipos, nuevo_registro], ignore_index=True)
                conn.update(worksheet="Equipos", data=df_equipos_actualizado)
                st.success(f"✅ Registrado exitosamente.")
                st.rerun()

# --- PESTAÑA 1: CALENDARIO Y REGISTRO ---
with tab_registro:
    if len(equipos_activos) != 6:
        st.error("⚠️ Inscribe exactamente 6 equipos en Configuración para usar el calendario.")
    else:
        st.subheader(f"📅 Calendario Semana {semana_actual}")
        partidos_semana = generar_calendario(equipos_activos, semana_actual)
        partidos_registrados_torneo = df_partidos[df_partidos['Torneo'] == torneo_actual]
        pendientes_para_dropdown = []
        
        col_cal1, col_cal2 = st.columns(2)
        for idx, p in enumerate(partidos_semana):
            jugado = partidos_registrados_torneo[
                (partidos_registrados_torneo['Jornada'] == p['Jornada']) & 
                (partidos_registrados_torneo['Local'] == p['Local']) & 
                (partidos_registrados_torneo['Visitante'] == p['Visitante'])
            ]
            texto_partido = f"**{p['Jornada']}**: {p['Local']} vs {p['Visitante']}"
            col_destino = col_cal1 if idx < 8 else col_cal2
            with col_destino:
                if not jugado.empty:
                    gl, gv = int(jugado.iloc[0]['Goles_L']), int(jugado.iloc[0]['Goles_V'])
                    st.success(f"✅ {texto_partido} | **{gl} - {gv}**")
                else:
                    st.info(f"⏳ {texto_partido} | Pendiente")
                    pendientes_para_dropdown.append(p)
                    
        st.divider()
        st.subheader("📝 Registrar Resultado")
        if not pendientes_para_dropdown:
            st.success("¡Todos los partidos de esta semana han sido jugados!")
        else:
            opciones_partidos = {f"{p['Jornada']}: {p['Local']} vs {p['Visitante']}": p for p in pendientes_para_dropdown}
            partido_seleccionado = st.selectbox("Selecciona el partido:", list(opciones_partidos.keys()))
            datos_partido = opciones_partidos[partido_seleccionado]
            local, visita, jornada_act = datos_partido['Local'], datos_partido['Visitante'], datos_partido['Jornada']
            
            col_r1, col_r2 = st.columns(2)
            with col_r1:
                st.write(f"**Local:** {local}")
                goles_l = st.number_input("Goles Local", min_value=0, max_value=20, value=0, key="gl_in")
            with col_r2:
                st.write(f"**Visitante:** {visita}")
                goles_v = st.number_input("Goles Visitante", min_value=0, max_value=20, value=0, key="gv_in")

            wo = st.checkbox("¿Victoria por W.O. (3-0 automático)?")
            if wo:
                ganador_wo = st.radio("¿Quién gana por W.O.?", [local, visita])
                goles_l, goles_v = (3, 0) if ganador_wo == local else (0, 3)

            goleadores_data = []
            if not wo:
                col_g1, col_g2 = st.columns(2)
                with col_g1:
                    if goles_l > 0:
                        st.write(f"⚽ Goleadores de {local}")
                        for i in range(goles_l):
                            j = st.text_input(f"Gol L {i+1}", key=f"g_l_{i}")
                            if j: goleadores_data.append({"Torneo": torneo_actual, "Jornada": jornada_act, "Equipo": local, "Jugador": j, "Goles": 1})
                with col_g2:
                    if goles_v > 0:
                        st.write(f"⚽ Goleadores de {visita}")
                        for i in range(goles_v):
                            j = st.text_input(f"Gol V {i+1}", key=f"g_v_{i}")
                            if j: goleadores_data.append({"Torneo": torneo_actual, "Jornada": jornada_act, "Equipo": visita, "Jugador": j, "Goles": 1})

            # --- SISTEMA DE TRANSFERENCIAS ---
            transferencia_data = None
            if not wo:
                ganador = None
                if goles_l > goles_v: ganador = local
                elif goles_v > goles_l: ganador = visita

                if ganador:
                    st.divider()
                    st.write(f"### 🔄 Mercado: Victoria de {ganador}")
                    if st.checkbox(f"¿Registrar un refuerzo para {ganador}?"):
                        col_t1, col_t2 = st.columns(2)
                        with col_t1: toma = st.text_input("🟢 Jugador que TOMA (Refuerzo):")
                        with col_t2: cede = st.text_input("🔴 Jugador que CEDE:", value="J.G.")
                        
                        if toma:
                            transferencia_data = {"Torneo": torneo_actual, "Jornada": jornada_act, "Equipo": ganador, "Toma": toma, "Cede": cede if cede else "J.G."}

            if st.button("Guardar Resultado Oficial", type="primary"):
                nuevo_partido = pd.DataFrame([{"Torneo": torneo_actual, "Jornada": jornada_act, "Local": local, "Goles_L": goles_l, "Goles_V": goles_v, "Visitante": visita, "WO": wo}])
                conn.update(worksheet="Partidos", data=pd.concat([df_partidos, nuevo_partido], ignore_index=True))
                
                if goleadores_data:
                    conn.update(worksheet="Goleadores", data=pd.concat([df_goleadores, pd.DataFrame(goleadores_data)], ignore_index=True))
                
                if transferencia_data:
                    conn.update(worksheet="Transferencias", data=pd.concat([df_transferencias, pd.DataFrame([transferencia_data])], ignore_index=True))

                st.success("✅ ¡Partido y datos guardados exitosamente!")
                st.rerun()

# --- PESTAÑA 2: TABLA DE POSICIONES ---
with tab_tabla:
    partidos_torneo = df_partidos[df_partidos['Torneo'] == torneo_actual]
    if not partidos_torneo.empty:
        stats = {eq: {'PJ': 0, 'G': 0, 'E': 0, 'P': 0, 'GF': 0, 'GC': 0, 'Pts': 0} for eq in equipos_activos}
        for _, p in partidos_torneo.iterrows():
            loc, vis, gl, gv = p['Local'], p['Visitante'], int(p['Goles_L']), int(p['Goles_V'])
            if loc not in stats: stats[loc] = {'PJ': 0, 'G': 0, 'E': 0, 'P': 0, 'GF': 0, 'GC': 0, 'Pts': 0}
            if vis not in stats: stats[vis] = {'PJ': 0, 'G': 0, 'E': 0, 'P': 0, 'GF': 0, 'GC': 0, 'Pts': 0}
            
            stats[loc]['PJ'] += 1; stats[vis]['PJ'] += 1
            stats[loc]['GF'] += gl; stats[loc]['GC'] += gv
            stats[vis]['GF'] += gv; stats[vis]['GC'] += gl
            
            if gl > gv: stats[loc]['G'] += 1; stats[loc]['Pts'] += 3; stats[vis]['P'] += 1
            elif gv > gl: stats[vis]['G'] += 1; stats[vis]['Pts'] += 3; stats[loc]['P'] += 1
            else: stats[loc]['E'] += 1; stats[vis]['E'] += 1; stats[loc]['Pts'] += 1; stats[vis]['Pts'] += 1
                
        df_tabla = pd.DataFrame.from_dict(stats, orient='index')
        df_tabla['DG'] = df_tabla['GF'] - df_tabla['GC']
        df_tabla = df_tabla[['PJ', 'G', 'E', 'P', 'GF', 'GC', 'DG', 'Pts']].sort_values(by=['Pts', 'DG', 'GF'], ascending=[False, False, False])
        st.dataframe(df_tabla, use_container_width=True)
    else:
        st.write("Aún no hay partidos jugados.")

# --- PESTAÑA 3: TABLA DE GOLEO ---
with tab_goleo:
    goles_torneo = df_goleadores[df_goleadores['Torneo'] == torneo_actual]
    if not goles_torneo.empty:
        goles_torneo['Goles'] = pd.to_numeric(goles_torneo['Goles'])
        tabla_goleo = goles_torneo.groupby(['Jugador', 'Equipo'])['Goles'].sum().reset_index().sort_values(by='Goles', ascending=False).reset_index(drop=True)
        tabla_goleo.index += 1 
        st.dataframe(tabla_goleo, use_container_width=True, column_config={"Goles": st.column_config.NumberColumn("Goles", width="small")})
    else:
        st.write("Aún no hay goles.")

# --- PESTAÑA 4: TRANSFERENCIAS ---
with tab_transf:
    transf_torneo = df_transferencias[df_transferencias['Torneo'] == torneo_actual]
    if not transf_torneo.empty:
        st.subheader("Historial de Fichajes")
        # Mostrar la tabla bonita
        st.dataframe(transf_torneo[["Jornada", "Equipo", "Toma", "Cede"]], use_container_width=True)
    else:
        st.write("Aún no hay transferencias registradas.")