import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
from PIL import Image
import json
import time

st.set_page_config(page_title="FC26 Pro Tracker", page_icon="🏆", layout="wide")

# --- ESTILOS CSS RECUPERADOS Y MEJORADOS ---
st.markdown("""
    <style>
    /* Recuperamos el look de tarjeta centrada */
    div.stButton > button {
        width: 100%;
        background-color: #1E1E1E !important;
        color: white !important;
        border: 1px solid #333 !important;
        border-radius: 12px !important;
        padding: 15px !important;
        margin-bottom: 10px !important;
        display: block !important;
        transition: all 0.2s ease;
    }
    div.stButton > button:hover {
        border-color: #FFA500 !important;
        transform: scale(1.02);
    }
    /* Estilo para las tarjetas ya jugadas */
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
    .teams-text { font-size: 16px; font-weight: 600; margin-bottom: 5px; }
    .status-text { font-size: 18px; color: #FFA500; font-style: italic; font-weight: bold; }
    .score-text { font-size: 24px; font-weight: 900; color: #00FF00; letter-spacing: 2px; }
    </style>
    """, unsafe_allow_html=True)

# --- MEMORIA DE SELECCIÓN ---
if "partido_seleccionado_click" not in st.session_state:
    st.session_state["partido_seleccionado_click"] = None
if "fk" not in st.session_state:
    st.session_state["fk"] = 0

# --- CONFIGURACIÓN DE IA ---
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
    df_partidos = pd.DataFrame()
    df_equipos = pd.DataFrame()

# --- FUNCIONES ---
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

def detectar_semana(equipos_activos, df_partidos, torneo):
    if not equipos_activos or df_partidos.empty: return 1
    for sem in range(1, 21):
        for p in generar_calendario(equipos_activos, sem):
            j = df_partidos[(df_partidos['Torneo'] == torneo) & (df_partidos['Jornada'] == p['Jornada']) & (df_partidos['Local'] == p['Local'])]
            if j.empty: return sem
    return 1

# --- BARRA LATERAL ---
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
                    # El botón ahora contiene el diseño centrado anterior
                    label = f"⏳ {p['Jornada']}\n{p['Local']} vs {p['Visitante']}\nPendiente"
                    if st.button(label, key=f"btn_{p['Jornada']}"):
                        st.session_state["partido_seleccionado_click"] = f"{p['Jornada']}: {p['Local']} vs {p['Visitante']}"
                        st.rerun()
                    
        st.divider()
        # --- ANCLA PARA EL SALTO ---
        st.markdown("<div id='registro_ancla'></div>", unsafe_allow_html=True)
        st.subheader("📝 Registrar Resultado")
        
        # Si se hizo clic, avisamos al usuario y preparamos el salto
        if st.session_state["partido_seleccionado_click"]:
             st.info(f"📍 Registrando: {st.session_state['partido_seleccionado_click']}")
             # Pequeño script para bajar al formulario
             st.components.v1.html("""<script>window.parent.document.getElementById('registro_ancla').scrollIntoView({behavior: 'smooth'});</script>""", height=0)

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