import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
from PIL import Image
import json
import time
import io

st.set_page_config(page_title="FC26 Pro Tracker", page_icon="🏆", layout="wide")

# --- ESTILOS CSS ---
st.markdown("""
    <style>
    div.stButton > button {
        width: 100% !important;
        background-color: #1E1E1E !important;
        color: white !important;
        border: 1px solid #333 !important;
        border-left: 6px solid #FFA500 !important;
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
    div.stButton > button p {
        text-align: center !important;
        width: 100% !important;
        white-space: pre-line !important; 
        font-size: 16px !important;
        line-height: 1.6 !important;
    }
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

with tab_config:
    st.subheader("Alta de Torneos y Jugadores")
    col_t, col_e = st.columns(2)
    with col_t: nuevo_torneo = st.text_input("Nombre del Torneo:")
    with col_e: nuevo_equipo = st.text_input("Emoji + Equipo + (Manager):")
    if st.button("Inscribir Jugador"):
        if nuevo_torneo and nuevo_equipo:
            conn.update(worksheet="Equipos", data=pd.concat([df_equipos, pd.DataFrame([{"Torneo": nuevo_torneo, "Equipo": nuevo_equipo}])], ignore_index=True))
            st.cache_data.clear()
            st.success("✅ Registrado exitosamente.")
            st.rerun()

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
                    label = f"⏳ {p['Jornada']}\n{p['Local']} vs {p['Visitante']}\nPendiente"
                    key_unica = f"btn_{p['Jornada']}_{p['Local'].split()[0]}_{idx}"
                    if st.button(label, key=key_unica):
                        st.session_state["partido_seleccionado_click"] = f"{p['Jornada']}: {p['Local']} vs {p['Visitante']}"
                        st.session_state["scroll_trigger"] = True
                        st.rerun()
                    
        st.divider()
        st.markdown("<div id='registro_ancla'></div>", unsafe_allow_html=True)
        st.subheader("📝 Registrar Resultado")
        
        if st.session_state["scroll_trigger"]:
            js_script = f"""
            <script>
                var ancla = window.parent.document.getElementById('registro_ancla');
                if(ancla) ancla.scrollIntoView({{behavior: 'smooth'}});
            </script>
            """
            st.components.v1.html(js_script, height=0)
            st.session_state["scroll_trigger"] = False
        
        if st.session_state["partido_seleccionado_click"]:
             st.info(f"📍 Registrando: {st.session_state['partido_seleccionado_click']}")

        if pendientes:
            opciones = [f"{p['Jornada']}: {p['Local']} vs {p['Visitante']}" for p in pendientes]
            idx_def = opciones.index(st.session_state["partido_seleccionado_click"]) if st.session_state["partido_seleccionado_click"] in opciones else 0
            partido_sel = st.selectbox("Selecciona partido:", opciones, index=idx_def)
            
            p_data = next(p for p in pendientes if f"{p['Jornada']}: {p['Local']} vs {p['Visitante']}" == partido_sel)
            loc, vis, jorn = p_data['Local'], p_data['Visitante'], p_data['Jornada']

            usar_ia = st.toggle("🤖 Activar Escáner de IA (Autocompletado)")
            if usar_ia:
                st.markdown(f"###### 📸 Sube las fotos del marcador final")
                fotos = st.file_uploader("", type=["png","jpg","jpeg"], accept_multiple_files=True, key=f"f_{st.session_state['fk']}")
                
                if fotos:
                    if st.button("👁️ Analizar Imágenes", type="secondary"):
                        if ia_lista:
                            with st.spinner("Transcribiendo datos (Optimizando para exactitud)..."):
                                try:
                                    imgs_para_ia = []
                                    for f in fotos:
                                        img = Image.open(f)
                                        img.thumbnail((1200, 1200))
                                        buffer = io.BytesIO()
                                        img.convert("RGB").save(buffer, format="JPEG", quality=80)
                                        imgs_para_ia.append(Image.open(buffer))

                                    # --- PROMPT "TRANSCRIPTOR CIEGO" A PRUEBA DE BALAS ---
                                    prompt_ia = f"""
                                    Eres un transcriptor. No pienses en quién es local o visitante.
                                    Tienes 2 OPCIONES EXACTAS de nombres de equipos:
                                    Opción A: "{loc}"
                                    Opción B: "{vis}"
                                    
                                    PASO 1 (MARCADOR):
                                    - Mira la parte superior. Identifica al equipo de la IZQUIERDA en la TV. Asignale exactamente el texto de la "Opción A" o la "Opción B" que corresponda a su nombre.
                                    - ¿Cuántos goles tiene el equipo de la IZQUIERDA en el marcador?
                                    - Identifica al equipo de la DERECHA en la TV. Asignale exactamente la "Opción A" o la "Opción B" que le corresponda.
                                    - ¿Cuántos goles tiene el equipo de la DERECHA en el marcador?
                                    
                                    PASO 2 (GOLEADORES E IGNORAR DUPLICADOS):
                                    - Hay varias fotos, por lo que un mismo evento puede salir repetido. 
                                    - Revisa los minutos (ej. 45', 71') de cada jugador para extraer una lista ÚNICA de goles. No cuentes el mismo gol (mismo jugador, mismo minuto) dos veces.
                                    - SOLO extrae nombres con un icono de BALÓN BLANCO (⚽). IGNORA tarjetas o flechas de cambios.
                                    - Haz la lista final para el lado IZQUIERDO.
                                    - Haz la lista final para el lado DERECHO.
                                    
                                    PASO 3 (AUDITORÍA):
                                    - Asegúrate de que el total de nombres en la lista IZQUIERDA sea igual a sus goles. Si un jugador anotó goles distintos (minutos distintos), escríbelo 2 veces. Haz lo mismo en la DERECHA.
                                    
                                    Devuelve ÚNICAMENTE este JSON:
                                    {{
                                      "equipo_tv_izq": "TEXTO EXACTO DE OPCION A O B",
                                      "goles_tv_izq": numero,
                                      "goleadores_tv_izq": ["Nombre"],
                                      "equipo_tv_der": "TEXTO EXACTO DE OPCION A O B",
                                      "goles_tv_der": numero,
                                      "goleadores_tv_der": ["Nombre"]
                                    }}
                                    """
                                    res = modelo_ia.generate_content([prompt_ia] + imgs_para_ia)
                                    
                                    texto_puro = res.text
                                    inicio_json = texto_puro.find('{')
                                    fin_json = texto_puro.rfind('}')
                                    
                                    if inicio_json != -1 and fin_json != -1:
                                        texto_json = texto_puro[inicio_json:fin_json+1]
                                        d = json.loads(texto_json)
                                        
                                        if "error" in d:
                                            st.error(f"❌ {d['error']}")
                                        else:
                                            # --- PYTHON HACE EL CRUCE INFALIBLE Y DIRECTO ---
                                            eq_izq = d.get("equipo_tv_izq", "").strip()
                                            
                                            if eq_izq == loc:
                                                # La TV y el formulario están del mismo lado
                                                st.session_state[f"gl_{st.session_state['fk']}"] = d.get("goles_tv_izq", 0)
                                                st.session_state[f"gv_{st.session_state['fk']}"] = d.get("goles_tv_der", 0)
                                                jugadores_l = d.get("goleadores_tv_izq", [])
                                                jugadores_v = d.get("goleadores_tv_der", [])
                                            elif eq_izq == vis:
                                                # La TV y el formulario están invertidos
                                                st.session_state[f"gl_{st.session_state['fk']}"] = d.get("goles_tv_der", 0)
                                                st.session_state[f"gv_{st.session_state['fk']}"] = d.get("goles_tv_izq", 0)
                                                jugadores_l = d.get("goleadores_tv_der", [])
                                                jugadores_v = d.get("goleadores_tv_izq", [])
                                            else:
                                                # Rescate en caso de que la IA olvide escribir el texto exacto
                                                if loc.lower() in eq_izq.lower():
                                                    st.session_state[f"gl_{st.session_state['fk']}"] = d.get("goles_tv_izq", 0)
                                                    st.session_state[f"gv_{st.session_state['fk']}"] = d.get("goles_tv_der", 0)
                                                    jugadores_l = d.get("goleadores_tv_izq", [])
                                                    jugadores_v = d.get("goleadores_tv_der", [])
                                                else:
                                                    st.session_state[f"gl_{st.session_state['fk']}"] = d.get("goles_tv_der", 0)
                                                    st.session_state[f"gv_{st.session_state['fk']}"] = d.get("goles_tv_izq", 0)
                                                    jugadores_l = d.get("goleadores_tv_der", [])
                                                    jugadores_v = d.get("goleadores_tv_izq", [])

                                            # Llenar las variables del formulario
                                            for i, jug in enumerate(jugadores_l): 
                                                st.session_state[f"jug_l_{i}_{st.session_state['fk']}"] = jug
                                            for i, jug in enumerate(jugadores_v): 
                                                st.session_state[f"jug_v_{i}_{st.session_state['fk']}"] = jug
                                            
                                            st.success("✅ ¡Datos leídos y cruzados correctamente!")
                                            time.sleep(1)
                                            st.rerun() 
                                    else:
                                        st.error(f"❌ Respuesta inválida de la IA: {texto_puro}")
                                        
                                except Exception as e:
                                    st.error(f"❌ Error al procesar: {e}")
                        else:
                            st.warning("⚠️ La IA no está configurada.")

            st.write("") 
            col1, col2 = st.columns(2)
            with col1: 
                gl = st.number_input(f"Goles {loc}", min_value=0, key=f"gl_{st.session_state['fk']}")
            with col2: 
                gv = st.number_input(f"Goles {vis}", min_value=0, key=f"gv_{st.session_state['fk']}")

            wo = st.checkbox("¿Victoria por W.O.?", key=f"wo_{st.session_state['fk']}")
            if wo:
                ganador_wo = st.radio("Ganador W.O.:", [loc, vis], key=f"g_wo_{st.session_state['fk']}")
                gl, gv = (3, 0) if ganador_wo == loc else (0, 3)

            goleadores_data = []
            if not wo:
                c_g1, c_g2 = st.columns(2)
                with c_g1:
                    if gl > 0:
                        for i in range(gl):
                            j = st.text_input(f"Gol L {i+1}", key=f"jug_l_{i}_{st.session_state['fk']}")
                            if j and j.strip(): 
                                goleadores_data.append({"Torneo": torneo_actual, "Jornada": jorn, "Equipo": loc, "Jugador": j.strip(), "Goles": 1})
                with c_g2:
                    if gv > 0:
                        for i in range(gv):
                            j = st.text_input(f"Gol V {i+1}", key=f"jug_v_{i}_{st.session_state['fk']}")
                            if j and j.strip(): 
                                goleadores_data.append({"Torneo": torneo_actual, "Jornada": jorn, "Equipo": vis, "Jugador": j.strip(), "Goles": 1})

            transferencia_data = None
            if not wo:
                ganador = loc if gl > gv else (vis if gv > gl else None)
                if ganador:
                    if st.checkbox(f"¿Refuerzo para {ganador}?", key=f"chk_t_{st.session_state['fk']}"):
                        ct1, ct2 = st.columns(2)
                        with ct1: 
                            toma = st.text_input("🟢 Toma:", key=f"toma_{st.session_state['fk']}")
                        with ct2: 
                            cede = st.text_input("🔴 Cede:", value="J.G.", key=f"cede_{st.session_state['fk']}")
                        if toma: 
                            transferencia_data = {"Torneo": torneo_actual, "Jornada": jorn, "Equipo": ganador, "Toma": toma, "Cede": cede if cede else "J.G."}

            if st.button("Guardar Resultado Oficial", type="primary"):
                # --- CANDADO DE SEGURIDAD ---
                goles_totales_esperados = gl + gv if not wo else 0
                if not wo and len(goleadores_data) < goles_totales_esperados:
                    st.error("⚠️ ¡Alto ahí! Te faltan goleadores por registrar. Llena todas las casillas de goles antes de guardar.")
                else:
                    with st.spinner("Guardando..."):
                        conn.update(worksheet="Partidos", data=pd.concat([df_partidos, pd.DataFrame([{"Torneo": torneo_actual, "Jornada": jorn, "Local": loc, "Goles_L": gl, "Goles_V": gv, "Visitante": vis, "WO": wo}])], ignore_index=True))
                        time.sleep(1)
                        
                        if goleadores_data: 
                            conn.update(worksheet="Goleadores", data=pd.concat([df_goleadores, pd.DataFrame(goleadores_data)], ignore_index=True))
                            time.sleep(1)
                            
                        if transferencia_data: 
                            conn.update(worksheet="Transferencias", data=pd.concat([df_transferencias, pd.DataFrame([transferencia_data])], ignore_index=True))
                        
                        st.session_state["fk"] += 1
                        st.session_state["partido_seleccionado_click"] = None
                        st.cache_data.clear()
                        st.success("✅ ¡Guardado!")
                        time.sleep(1)
                        st.rerun()

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