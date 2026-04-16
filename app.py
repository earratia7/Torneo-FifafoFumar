import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
from PIL import Image
import json
import time

st.set_page_config(page_title="FC26 Pro Tracker", page_icon="🏆", layout="wide")

# --- ESTILOS CSS REPARADOS PARA LOS BOTONES ---
st.markdown("""
    <style>
    /* Estilo para los BOTONES de partidos PENDIENTES */
    div.stButton > button {
        width: 100% !important;
        background-color: #1E1E1E !important;
        color: white !important;
        border: 1px solid #333 !important;
        border-left: 6px solid #FFA500 !important; /* Borde naranja idéntico a la tarjeta verde */
        border-radius: 12px !important;
        padding: 15px !important;
        margin-bottom: 10px !important;
        display: block !important;
        transition: all 0.2s ease;
        box-shadow: 3px 3px 10px rgba(0,0,0,0.5) !important;
    }
    div.stButton > button:hover {
        border-color: #FFB732 !important;
        transform: scale(1.02);
    }
    /* El truco maestro para apilar y centrar el texto dentro del botón */
    div.stButton > button p {
        text-align: center !important;
        width: 100% !important;
        white-space: pre-line !important; /* Obliga a respetar los saltos de línea */
        font-size: 16px !important;
        line-height: 1.6 !important;
    }
    
    /* Estilo para las TARJETAS de partidos JUGADOS */
    .match-card-played {
        background-color: #1E1E1E;
        border: 1px solid #333;
        border-left: 6px solid #00FF00;
        border-radius: 12px;
        padding: 15px;
        text-align: center;
        margin-bottom: 12px;
        box-shadow: 3px 3px 10px rgba(0,0,0,0.5);
    }
    .jornada-tag { font-size: 14px; color: #AAA; font-weight: bold; margin-bottom: 5px; }
    .teams-text { font-size: 16px; font-weight: 600; margin-bottom: 5px; color: white;}
    .score-text { font-size: 24px; font-weight: 900; color: #00FF00; letter-spacing: 2px; }
    </style>
    """, unsafe_allow_html=True)

# --- MEMORIA DE SELECCIÓN Y SCROLL ---
if "partido_seleccionado_click" not in st.session_state:
    st.session_state["partido_seleccionado_click"] = None
if "scroll_trigger" not in st.session_state:
    st.session_state["scroll_trigger"] = False
if "fk" not in st.session_state:
    st.session_state["fk"] = 0

# --- IA ---
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    modelo_ia = genai.GenerativeModel('gemini-2.5-flash')
    ia_lista = True
except:
    ia_lista = False

conn = st.connection("gsheets", type=GSheetsConnection)

try:
    df_partidos = conn.read(worksheet="Partidos", usecols=[0, 1, 2, 3, 4, 5, 6], ttl=60).dropna(how="all")
    df_equipos = conn.read(worksheet="Equipos", usecols=[0, 1], ttl=60).dropna(how="all")
    df_goleadores = conn.read(worksheet="Goleadores", usecols=[0, 1, 2, 3, 4], ttl=60).dropna(how="all")
    df_transferencias = conn.read(worksheet="Transferencias", usecols=[0, 1, 2, 3, 4], ttl=60).dropna(how="all")
except:
    df_partidos = pd.DataFrame(columns=["Torneo", "Jornada", "Local", "Goles_L", "Goles_V", "Visitante", "WO"])
    df_equipos = pd.DataFrame(columns=["Torneo", "Equipo"])

def generar_calendario(equipos_lista, semana):
    if len(equipos_lista) < 6: return []
    plantilla = [[(0,1), (2,3)], [(4,5), (0,2)], [(1,3), (4,2)], [(0,4), (1,5)], [(2,5), (3,0)], [(1,4), (3,5)], [(0,5), (1,2)], [(3,4)]]
    cal = []
    for j_idx, jornada in enumerate(plantilla):
        for p in jornada:
            loc_idx, vis_idx = p
            if semana % 2 == 0: loc_idx, vis_idx = vis_idx, loc_idx
            cal.append({"Jornada": f"S{semana}J{j_idx+1}", "Local": equipos_lista[loc_idx], "Visitante": equipos_lista[vis_idx]})
    return cal

def detectar_semana(eq_act, df_p, torneo):
    if not eq_act or df_p.empty: return 1
    for sem in range(1, 21):
        for p in generar_calendario(eq_act, sem):
            j = df_p[(df_p['Torneo'] == torneo) & (df_p['Jornada'] == p['Jornada']) & (df_p['Local'] == p['Local'])]
            if j.empty: return sem
    return 1

with st.sidebar:
    st.header("⚙️ Configuración")
    torneo_actual = st.selectbox("Torneo Activo:", df_equipos['Torneo'].unique() if not df_equipos.empty else ["Sin Torneos"])
    eq_activos = df_equipos[df_equipos['Torneo'] == torneo_actual]['Equipo'].tolist() if not df_equipos.empty else []
    sem_sug = detectar_semana(eq_activos, df_partidos, torneo_actual)
    sem_act = st.number_input("Semana de Juego:", min_value=1, max_value=20, value=sem_sug, key="memoria_semana")
    if st.button("🔄 Forzar Actualización"):
        st.cache_data.clear()
        st.rerun()

st.title("🏆 Torneo FifafoFumar FC26")

tab_registro, tab_tabla, tab_goleo, tab_transf, tab_config = st.tabs(["📝 Calendario", "📊 Posiciones", "⚽ Goleo", "🔄 Transferencias", "⚙️ Configuración"])

with tab_registro:
    if len(eq_activos) == 6:
        st.subheader(f"📅 Calendario Semana {sem_act}")
        partidos_sem = generar_calendario(eq_activos, sem_act)
        pendientes = []
        
        c_cal1, c_cal2 = st.columns(2)
        for idx, p in enumerate(partidos_sem):
            j = df_partidos[(df_partidos['Torneo'] == torneo_actual) & (df_partidos['Jornada'] == p['Jornada']) & (df_partidos['Local'] == p['Local'])]
            
            with (c_cal1 if idx < 4 else c_cal2):
                if not j.empty:
                    gl, gv = int(j.iloc[0]['Goles_L']), int(j.iloc[0]['Goles_V'])
                    st.markdown(f"""<div class="match-card-played"><div class="jornada-tag">✅ {p['Jornada']}</div><div class="teams-text">{p['Local']} vs {p['Visitante']}</div><div class="score-text">{gl} - {gv}</div></div>""", unsafe_allow_html=True)
                else:
                    pendientes.append(p)
                    # El texto con saltos de línea explícitos para que el CSS lo apile
                    label = f"⏳ {p['Jornada']}\n{p['Local']} vs {p['Visitante']}\nPendiente"
                    key_unica = f"btn_{p['Jornada']}_{p['Local'].split()[0]}_{idx}"
                    if st.button(label, key=key_unica):
                        st.session_state["partido_seleccionado_click"] = f"{p['Jornada']}: {p['Local']} vs {p['Visitante']}"
                        st.session_state["scroll_trigger"] = True # Activamos la orden de bajar
                        st.rerun()
                    
        st.divider()
        st.markdown("<div id='registro_ancla'></div>", unsafe_allow_html=True)
        st.subheader("📝 Registrar Resultado")
        
        # --- LÓGICA DE SCROLL INFALIBLE ---
        if st.session_state["scroll_trigger"]:
            # Usamos time.time() para que el bloque HTML sea único y siempre se ejecute
            js_script = f"""
            <script>
                // Marca de tiempo: {time.time()}
                window.parent.document.getElementById('registro_ancla').scrollIntoView({{behavior: 'smooth'}});
            </script>
            """
            st.components.v1.html(js_script, height=0)
            st.session_state["scroll_trigger"] = False # Apagamos el trigger para que no se atore
        
        if st.session_state["partido_seleccionado_click"]:
             st.info(f"📍 Registrando: {st.session_state['partido_seleccionado_click']}")

        if pendientes:
            opciones = [f"{p['Jornada']}: {p['Local']} vs {p['Visitante']}" for p in pendientes]
            idx_def = opciones.index(st.session_state["partido_seleccionado_click"]) if st.session_state["partido_seleccionado_click"] in opciones else 0
            partido_sel = st.selectbox("Selecciona partido:", opciones, index=idx_def)
            
            p_data = next(p for p in pendientes if f"{p['Jornada']}: {p['Local']} vs {p['Visitante']}" == partido_sel)
            loc, vis, jorn = p_data['Local'], p_data['Visitante'], p_data['Jornada']

            with st.expander("📸 Autocompletar con IA"):
                fotos = st.file_uploader("Subir fotos", type=["png","jpg","jpeg"], accept_multiple_files=True, key=f"f_{st.session_state['fk']}")
                if st.button("🤖 Analizar"):
                    if fotos and ia_lista:
                        with st.spinner("Analizando..."):
                            try:
                                imgs = [Image.open(f) for f in fotos]
                                res = modelo_ia.generate_content([f"Resultado JSON {loc} vs {vis}", imgs[0]])
                                d = json.loads(res.text.replace("```json","").replace("```","").strip())
                                st.session_state[f"gl_{st.session_state['fk']}"] = d.get("goles_local", 0)
                                st.session_state[f"gv_{st.session_state['fk']}"] = d.get("goles_visitante", 0)
                                st.rerun()
                            except: st.error("Error IA")

            col1, col2 = st.columns(2)
            with col1: gl = st.number_input(f"Goles {loc}", min_value=0, key=f"gl_{st.session_state['fk']}")
            with col2: gv = st.number_input(f"Goles {vis}", min_value=0, key=f"gv_{st.session_state['fk']}")

            if st.button("Guardar Resultado Oficial", type="primary"):
                conn.update(worksheet="Partidos", data=pd.concat([df_partidos, pd.DataFrame([{"Torneo": torneo_actual, "Jornada": jorn, "Local": loc, "Goles_L": gl, "Goles_V": gv, "Visitante": vis, "WO": False}])], ignore_index=True))
                st.session_state["fk"] += 1
                st.session_state["partido_seleccionado_click"] = None
                st.cache_data.clear()
                st.success("✅ ¡Guardado!"); time.sleep(1); st.rerun()

# --- LAS OTRAS PESTAÑAS (IGUAL) ---
with tab_tabla:
    partidos_torneo = df_partidos[df_partidos['Torneo'] == torneo_actual]
    if not partidos_torneo.empty:
        stats = {eq: {'PJ': 0, 'G': 0, 'E': 0, 'P': 0, 'GF': 0, 'GC': 0, 'Pts': 0} for eq in eq_activos}
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