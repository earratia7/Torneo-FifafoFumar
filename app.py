import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
from PIL import Image
import json
import time

st.set_page_config(page_title="FC26 Pro Tracker", page_icon="🏆", layout="wide")

# --- ESTILOS CSS PERSONALIZADOS ---
st.markdown("""
    <style>
    .match-card {
        background-color: #1E1E1E;
        border: 1px solid #333;
        border-radius: 10px;
        padding: 15px;
        margin-bottom: 10px;
        text-align: center;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.3);
    }
    .match-teams {
        font-size: 14px;
        font-weight: bold;
        color: #FFFFFF;
        margin-bottom: 5px;
    }
    .match-status-pending {
        font-size: 16px;
        color: #FFA500;
        font-style: italic;
    }
    .match-status-played {
        font-size: 20px;
        font-weight: 800;
        color: #00FF00;
        letter-spacing: 2px;
    }
    .jornada-tag {
        font-size: 10px;
        color: #888;
        text-transform: uppercase;
    }
    </style>
    """, unsafe_allow_html=True)

# --- SISTEMA DE RESETEO ---
if "fk" not in st.session_state:
    st.session_state["fk"] = 0
fk = st.session_state["fk"]

# --- CONFIGURACIÓN DE IA ---
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    modelo_ia = genai.GenerativeModel('gemini-2.5-flash')
    ia_lista = True
except Exception as e:
    ia_lista = False

# 1. CONEXIÓN A GOOGLE SHEETS
conn = st.connection("gsheets", type=GSheetsConnection)

try:
    df_partidos = conn.read(worksheet="Partidos", usecols=[0, 1, 2, 3, 4, 5, 6], ttl=60).dropna(how="all")
    df_goleadores = conn.read(worksheet="Goleadores", usecols=[0, 1, 2, 3, 4], ttl=60).dropna(how="all")
    df_equipos = conn.read(worksheet="Equipos", usecols=[0, 1], ttl=60).dropna(how="all")
    df_transferencias = conn.read(worksheet="Transferencias", usecols=[0, 1, 2, 3, 4], ttl=60).dropna(how="all")
except Exception as e:
    st.error(f"⚠️ Error de conexión: {e}")
    df_partidos = pd.DataFrame(columns=["Torneo", "Jornada", "Local", "Goles_L", "Goles_V", "Visitante", "WO"])
    df_goleadores = pd.DataFrame(columns=["Torneo", "Jornada", "Equipo", "Jugador", "Goles"])
    df_equipos = pd.DataFrame(columns=["Torneo", "Equipo"])
    df_transferencias = pd.DataFrame(columns=["Torneo", "Jornada", "Equipo", "Toma", "Cede"])

# --- LÓGICA DEL CALENDARIO ---
def generar_calendario(equipos_lista, semana):
    if len(equipos_lista) < 6: return []
    plantilla = [
        [(0,1), (2,3)], [(4,5), (0,2)], [(1,3), (4,2)], [(0,4), (1,5)], 
        [(2,5), (3,0)], [(1,4), (3,5)], [(0,5), (1,2)], [(3,4)]
    ]
    calendario = []
    for j_idx, jornada in enumerate(plantilla):
        for partido in jornada:
            loc_idx, vis_idx = partido
            if semana % 2 == 0: loc_idx, vis_idx = vis_idx, loc_idx
            calendario.append({"Jornada": f"S{semana}J{j_idx+1}", "Local": equipos_lista[loc_idx], "Visitante": equipos_lista[vis_idx]})
    return calendario

# --- AUTO-DETECCIÓN DE SEMANA ---
def detectar_semana_pendiente(equipos_activos, df_partidos, torneo):
    if not equipos_activos: return 1
    for sem in range(1, 21):
        partidos_sem = generar_calendario(equipos_activos, sem)
        for p in partidos_sem:
            jugado = df_partidos[(df_partidos['Torneo'] == torneo) & (df_partidos['Jornada'] == p['Jornada']) & (df_partidos['Local'] == p['Local'])]
            if jugado.empty: return sem
    return 1

# --- BARRA LATERAL ---
with st.sidebar:
    st.header("⚙️ Configuración")
    lista_torneos = df_equipos['Torneo'].unique().tolist() if not df_equipos.empty else ["Sin Torneos"]
    torneo_actual = st.selectbox("Torneo Activo:", lista_torneos)
    equipos_activos = df_equipos[df_equipos['Torneo'] == torneo_actual]['Equipo'].tolist() if not df_equipos.empty else []
    
    semana_sugerida = detectar_semana_pendiente(equipos_activos, df_partidos, torneo_actual)
    semana_actual = st.number_input("Semana de Juego:", min_value=1, max_value=20, value=semana_sugerida, key="memoria_semana")
    
    st.divider()
    if st.button("🔄 Forzar Actualización", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

st.title(f"🏆 Torneo FifafoFumar FC26 - {torneo_actual}")

tab_registro, tab_tabla, tab_goleo, tab_transf, tab_config = st.tabs(["📝 Calendario y Registro", "📊 Posiciones", "⚽ Goleo", "🔄 Transferencias", "⚙️ Configuración"])

# --- PESTAÑA 5: CONFIGURACIÓN ---
with tab_config:
    st.subheader("Alta de Torneos y Jugadores")
    col_t, col_e = st.columns(2)
    with col_t: nuevo_torneo = st.text_input("Nombre del Torneo:")
    with col_e: nuevo_equipo = st.text_input("Emoji + Equipo + (Manager):")
    if st.button("Inscribir Jugador"):
        if nuevo_torneo and nuevo_equipo:
            conn.update(worksheet="Equipos", data=pd.concat([df_equipos, pd.DataFrame([{"Torneo": nuevo_torneo, "Equipo": nuevo_equipo}])], ignore_index=True))
            st.cache_data.clear()
            st.success("✅ Registrado."); st.rerun()

# --- PESTAÑA 1: CALENDARIO Y REGISTRO ---
with tab_registro:
    if len(equipos_activos) != 6:
        st.error("⚠️ Inscribe 6 equipos.")
    else:
        st.subheader(f"📅 Calendario Semana {semana_actual}")
        partidos_semana = generar_calendario(equipos_activos, semana_actual)
        pendientes_para_dropdown = []
        
        col_cal1, col_cal2 = st.columns(2)
        for idx, p in enumerate(partidos_semana):
            jugado = df_partidos[(df_partidos['Torneo'] == torneo_actual) & (df_partidos['Jornada'] == p['Jornada']) & (df_partidos['Local'] == p['Local'])]
            
            # --- CONSTRUCCIÓN DE LA TARJETA ---
            if not jugado.empty:
                gl, gv = int(jugado.iloc[0]['Goles_L']), int(jugado.iloc[0]['Goles_V'])
                html_card = f"""
                <div class="match-card" style="border-left: 5px solid #00FF00;">
                    <div class="jornada-tag">⏳ {p['Jornada']}</div>
                    <div class="match-teams">⚽ {p['Local']} vs {p['Visitante']}</div>
                    <div class="match-status-played">{gl} - {gv}</div>
                </div>
                """
            else:
                pendientes_para_dropdown.append(p)
                html_card = f"""
                <div class="match-card" style="border-left: 5px solid #FFA500;">
                    <div class="jornada-tag">⏳ {p['Jornada']}</div>
                    <div class="match-teams">⚽ {p['Local']} vs {p['Visitante']}</div>
                    <div class="match-status-pending">Pendiente</div>
                </div>
                """
            
            with (col_cal1 if idx < 4 else col_cal2):
                st.markdown(html_card, unsafe_allow_html=True)
                    
        st.divider()
        st.subheader("📝 Registrar Resultado")
        if not pendientes_para_dropdown:
            st.success(f"¡Semana {semana_actual} completada!")
        else:
            opciones_partidos = {f"{p['Jornada']}: {p['Local']} vs {p['Visitante']}": p for p in pendientes_para_dropdown}
            partido_seleccionado = st.selectbox("Selecciona el partido:", list(opciones_partidos.keys()))
            datos_partido = opciones_partidos[partido_seleccionado]
            local, visita, jornada_act = datos_partido['Local'], datos_partido['Visitante'], datos_partido['Jornada']
            
            with st.expander("📸 Autocompletar con IA", expanded=False):
                fotos_subidas = st.file_uploader("Fotos del marcador", type=["png", "jpg", "jpeg"], accept_multiple_files=True, key=f"foto_{fk}")
                if st.button("🤖 Analizar con IA"):
                    if fotos_subidas and ia_lista:
                        with st.spinner("IA analizando..."):
                            try:
                                prompt_ia = f"Arbitro EA FC. Local: {local}, Visitante: {visita}. Extrae goles y goleadores en JSON."
                                imagenes_pil = [Image.open(f) for f in fotos_subidas]
                                respuesta = modelo_ia.generate_content([prompt_ia] + imagenes_pil)
                                datos_ia = json.loads(respuesta.text.replace("```json", "").replace("```", "").strip())
                                st.session_state[f"gl_{fk}"] = datos_ia.get("goles_local", 0)
                                st.session_state[f"gv_{fk}"] = datos_ia.get("goles_visitante", 0)
                                for i, jug in enumerate(datos_ia.get("goleadores_local", [])): st.session_state[f"jug_l_{i}_{fk}"] = jug
                                for i, jug in enumerate(datos_ia.get("goleadores_visitante", [])): st.session_state[f"jug_v_{i}_{fk}"] = jug
                                st.rerun()
                            except: st.error("Error IA")

            col_r1, col_r2 = st.columns(2)
            with col_r1: goles_l = st.number_input(f"Goles {local}", min_value=0, value=0, key=f"gl_{fk}")
            with col_r2: goles_v = st.number_input(f"Goles {visita}", min_value=0, value=0, key=f"gv_{fk}")

            if st.button("Guardar Resultado Oficial", type="primary"):
                conn.update(worksheet="Partidos", data=pd.concat([df_partidos, pd.DataFrame([{"Torneo": torneo_actual, "Jornada": jornada_act, "Local": local, "Goles_L": goles_l, "Goles_V": goles_v, "Visitante": visita, "WO": False}])], ignore_index=True))
                st.session_state["fk"] += 1
                st.cache_data.clear()
                st.success("✅ Guardado!"); time.sleep(1); st.rerun()

# --- TABLAS DE POSICIONES Y GOLEO (Sin cambios) ---
with tab_tabla:
    partidos_torneo = df_partidos[df_partidos['Torneo'] == torneo_actual]
    if not partidos_torneo.empty:
        stats = {eq: {'PJ': 0, 'G': 0, 'E': 0, 'P': 0, 'GF': 0, 'GC': 0, 'Pts': 0} for eq in equipos_activos}
        for _, p in partidos_torneo.iterrows():
            loc, vis, gl, gv = p['Local'], p['Visitante'], int(p['Goles_L']), int(p['Goles_V'])
            if loc in stats and vis in stats:
                stats[loc]['PJ'] += 1; stats[vis]['PJ'] += 1; stats[loc]['GF'] += gl; stats[loc]['GC'] += gv; stats[vis]['GF'] += gv; stats[vis]['GC'] += gl
                if gl > gv: stats[loc]['G'] += 1; stats[loc]['Pts'] += 3; stats[vis]['P'] += 1
                elif gv > gl: stats[vis]['G'] += 1; stats[vis]['Pts'] += 3; stats[loc]['P'] += 1
                else: stats[loc]['E'] += 1; stats[vis]['E'] += 1; stats[loc]['Pts'] += 1; stats[vis]['Pts'] += 1
        df_t = pd.DataFrame.from_dict(stats, orient='index')
        df_t['DG'] = df_t['GF'] - df_t['GC']
        st.dataframe(df_t[['PJ', 'G', 'E', 'P', 'GF', 'GC', 'DG', 'Pts']].sort_values(by=['Pts', 'DG'], ascending=False), use_container_width=True)

with tab_goleo:
    goles_t = df_goleadores[df_goleadores['Torneo'] == torneo_actual]
    if not goles_t.empty:
        st.dataframe(goles_t.groupby(['Jugador', 'Equipo'])['Goles'].sum().reset_index().sort_values(by='Goles', ascending=False), use_container_width=True)

with tab_transf:
    t_t = df_transferencias[df_transferencias['Torneo'] == torneo_actual]
    if not t_t.empty: st.dataframe(t_t[["Jornada", "Equipo", "Toma", "Cede"]], use_container_width=True)