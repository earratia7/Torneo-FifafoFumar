import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
from PIL import Image
import json
import time

st.set_page_config(page_title="FC26 Pro Tracker", page_icon="🏆", layout="wide")

# --- ESTILOS CSS ---
st.markdown("""
    <style>
    /* Estilo para los botones que parecen tarjetas */
    div.stButton > button {
        width: 100%;
        background-color: #1E1E1E;
        color: white;
        border: 1px solid #333;
        border-radius: 12px;
        padding: 20px;
        transition: all 0.3s ease;
        box-shadow: 3px 3px 10px rgba(0,0,0,0.5);
    }
    div.stButton > button:hover {
        border-color: #FFA500;
        background-color: #252525;
        transform: translateY(-2px);
    }
    .match-card-played {
        background-color: #1E1E1E;
        border-left: 6px solid #00FF00;
        border-radius: 12px;
        padding: 20px;
        text-align: center;
        margin-bottom: 12px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- INICIALIZAR MEMORIA DE SELECCIÓN ---
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

# 1. CONEXIÓN A GOOGLE SHEETS
conn = st.connection("gsheets", type=GSheetsConnection)

try:
    df_partidos = conn.read(worksheet="Partidos", usecols=[0, 1, 2, 3, 4, 5, 6], ttl=60).dropna(how="all")
    df_goleadores = conn.read(worksheet="Goleadores", usecols=[0, 1, 2, 3, 4], ttl=60).dropna(how="all")
    df_equipos = conn.read(worksheet="Equipos", usecols=[0, 1], ttl=60).dropna(how="all")
    df_transferencias = conn.read(worksheet="Transferencias", usecols=[0, 1, 2, 3, 4], ttl=60).dropna(how="all")
except:
    st.error("⚠️ Error de conexión.")
    df_partidos = pd.DataFrame()
    df_equipos = pd.DataFrame()

# --- LÓGICA CALENDARIO ---
def generar_calendario(equipos_lista, semana):
    if len(equipos_lista) < 6: return []
    plantilla = [[(0,1), (2,3)], [(4,5), (0,2)], [(1,3), (4,2)], [(0,4), (1,5)], [(2,5), (3,0)], [(1,4), (3,5)], [(0,5), (1,2)], [(3,4)]]
    calendario = []
    for j_idx, jornada in enumerate(plantilla):
        for partido in jornada:
            loc_idx, vis_idx = partido
            if semana % 2 == 0: loc_idx, vis_idx = vis_idx, loc_idx
            calendario.append({"Jornada": f"S{semana}J{j_idx+1}", "Local": equipos_lista[loc_idx], "Visitante": equipos_lista[vis_idx]})
    return calendario

def detectar_semana_pendiente(equipos_activos, df_partidos, torneo):
    if not equipos_activos or df_partidos.empty: return 1
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
    
    if st.button("🔄 Forzar Actualización"):
        st.cache_data.clear()
        st.rerun()

st.title(f"🏆 Torneo FifafoFumar FC26")

tab_registro, tab_tabla, tab_goleo, tab_transf, tab_config = st.tabs(["📝 Calendario y Registro", "📊 Posiciones", "⚽ Goleo", "🔄 Transferencias", "⚙️ Configuración"])

# --- PESTAÑA CALENDARIO ---
with tab_registro:
    if len(equipos_activos) == 6:
        st.subheader(f"📅 Calendario Semana {semana_actual}")
        partidos_semana = generar_calendario(equipos_activos, semana_actual)
        pendientes_para_dropdown = []
        
        col_cal1, col_cal2 = st.columns(2)
        for idx, p in enumerate(partidos_semana):
            jugado = df_partidos[(df_partidos['Torneo'] == torneo_actual) & (df_partidos['Jornada'] == p['Jornada']) & (df_partidos['Local'] == p['Local'])]
            
            with (col_cal1 if idx < 4 else col_cal2):
                if not jugado.empty:
                    gl, gv = int(jugado.iloc[0]['Goles_L']), int(jugado.iloc[0]['Goles_V'])
                    st.markdown(f"""<div class="match-card-played"><small>✅ {p['Jornada']}</small><br><b>{p['Local']} vs {p['Visitante']}</b><br><span style="font-size:24px; color:#00FF00;">{gl} - {gv}</span></div>""", unsafe_allow_html=True)
                else:
                    pendientes_para_dropdown.append(p)
                    # BOTÓN QUE PARECE TARJETA
                    label_boton = f"⏳ {p['Jornada']}\n{p['Local']} vs {p['Visitante']}\nPendiente"
                    if st.button(label_boton, key=f"btn_{p['Jornada']}_{idx}"):
                        st.session_state["partido_seleccionado_click"] = f"{p['Jornada']}: {p['Local']} vs {p['Visitante']}"
                        # Pequeño truco para bajar la página al formulario
                        st.rerun()
                    
        st.divider()
        st.subheader("📝 Registrar Resultado")
        
        if not pendientes_para_dropdown:
            st.success(f"¡Semana {semana_actual} completada!")
        else:
            opciones = [f"{p['Jornada']}: {p['Local']} vs {p['Visitante']}" for p in pendientes_para_dropdown]
            
            # Sincronizar el selectbox con el clic de la tarjeta
            indice_defecto = 0
            if st.session_state["partido_seleccionado_click"] in opciones:
                indice_defecto = opciones.index(st.session_state["partido_seleccionado_click"])

            partido_sel = st.selectbox("Partido a registrar:", opciones, index=indice_defecto)
            
            # Extraer datos del seleccionado
            datos_sel = next(p for p in pendientes_para_dropdown if f"{p['Jornada']}: {p['Local']} vs {p['Visitante']}" == partido_sel)
            local, visita, jornada_act = datos_sel['Local'], datos_sel['Visitante'], datos_sel['Jornada']

            # --- SECCIÓN IA ---
            with st.expander("📸 Autocompletar con IA"):
                fotos = st.file_uploader("Fotos marcador", type=["png", "jpg", "jpeg"], accept_multiple_files=True, key=f"foto_{st.session_state['fk']}")
                if st.button("🤖 Analizar"):
                    if fotos and ia_lista:
                        with st.spinner("IA trabajando..."):
                            try:
                                prompt = f"Extrae resultado JSON de {local} vs {visita}."
                                imgs = [Image.open(f) for f in fotos]
                                res = modelo_ia.generate_content([prompt] + imgs)
                                d = json.loads(res.text.replace("```json", "").replace("```", "").strip())
                                st.session_state[f"gl_{st.session_state['fk']}"] = d.get("goles_local", 0)
                                st.session_state[f"gv_{st.session_state['fk']}"] = d.get("goles_visitante", 0)
                                for i, j in enumerate(d.get("goleadores_local", [])): st.session_state[f"jl_{i}_{st.session_state['fk']}"] = j
                                for i, j in enumerate(d.get("goleadores_visitante", [])): st.session_state[f"jv_{i}_{st.session_state['fk']}"] = j
                                st.rerun()
                            except: st.error("Error IA")

            # --- FORMULARIO ---
            c1, c2 = st.columns(2)
            with c1: gl = st.number_input(f"Goles {local}", min_value=0, key=f"gl_{st.session_state['fk']}")
            with c2: gv = st.number_input(f"Goles {visita}", min_value=0, key=f"gv_{st.session_state['fk']}")

            if st.button("Guardar Resultado Oficial", type="primary"):
                conn.update(worksheet="Partidos", data=pd.concat([df_partidos, pd.DataFrame([{"Torneo": torneo_actual, "Jornada": jornada_act, "Local": local, "Goles_L": gl, "Goles_V": gv, "Visitante": visita, "WO": False}])], ignore_index=True))
                st.session_state["fk"] += 1
                st.session_state["partido_seleccionado_click"] = None # Limpiar selección
                st.cache_data.clear()
                st.success("✅ ¡Guardado!"); time.sleep(1); st.rerun()

# (Las demás pestañas se mantienen igual...)