import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
from PIL import Image
import json
import time
import io
import unicodedata
from difflib import SequenceMatcher

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

# --- LECTURA DE DATOS ---
# Leemos la columna nueva "Estado" de la hoja "Equipos".
# Usamos usecols=[0,1,2] para traer: Torneo, Equipo, Estado.
try:
    df_partidos = conn.read(worksheet="Partidos", usecols=[0, 1, 2, 3, 4, 5, 6], ttl=60).dropna(how="all")
    df_equipos = conn.read(worksheet="Equipos", usecols=[0, 1, 2], ttl=60).dropna(how="all")
    df_goleadores = conn.read(worksheet="Goleadores", usecols=[0, 1, 2, 3, 4], ttl=60).dropna(how="all")
    df_transferencias = conn.read(worksheet="Transferencias", usecols=[0, 1, 2, 3, 4], ttl=60).dropna(how="all")
except:
    df_partidos = pd.DataFrame(columns=["Torneo", "Jornada", "Local", "Goles_L", "Goles_V", "Visitante", "WO"])
    df_equipos = pd.DataFrame(columns=["Torneo", "Equipo", "Estado"])
    df_goleadores = pd.DataFrame(columns=["Torneo", "Jornada", "Equipo", "Jugador", "Goles"])
    df_transferencias = pd.DataFrame(columns=["Torneo", "Jornada", "Equipo", "Toma", "Cede"])

# --- PROTECCIÓN: si la hoja todavía no tiene la columna "Estado", la creamos vacía ---
# Esto evita que la app truene si abres antes de agregar la columna en Google Sheets.
if "Estado" not in df_equipos.columns:
    df_equipos["Estado"] = "Activo"

# Rellenamos vacíos con un valor seguro por defecto.
df_equipos["Estado"] = df_equipos["Estado"].fillna("Activo")


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


# --- DETECCIÓN DE GOLEADORES PARECIDOS (para no contar el mismo dos veces) ---
def normalizar_nombre(texto):
    """Pasa a minúsculas, quita acentos y espacios sobrantes.
    Así 'Mbappé', 'mbappe' y 'MBAPPÉ' se vuelven todos iguales."""
    texto = str(texto).strip().lower()
    texto = ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')
    return texto


def buscar_parecido(nombre_escrito, lista_existentes, umbral=0.82):
    """Revisa si lo que el usuario escribió se parece mucho a un nombre ya guardado.
    Devuelve:
      - ('identico', nombre)  si es exactamente el mismo (ignorando acentos/mayúsculas)
      - ('parecido', nombre)  si se parece mucho pero no es idéntico (para avisar)
      - ('nuevo', None)       si no se parece a ninguno
    """
    if not nombre_escrito or not str(nombre_escrito).strip():
        return ('nuevo', None)
    norm_escrito = normalizar_nombre(nombre_escrito)
    mejor_nombre = None
    mejor_score = 0.0
    for existente in lista_existentes:
        score = SequenceMatcher(None, norm_escrito, normalizar_nombre(existente)).ratio()
        if score > mejor_score:
            mejor_score = score
            mejor_nombre = existente
    if mejor_nombre is None:
        return ('nuevo', None)
    if normalizar_nombre(mejor_nombre) == norm_escrito:
        return ('identico', mejor_nombre)
    if mejor_score >= umbral:
        return ('parecido', mejor_nombre)
    return ('nuevo', None)


# --- SEPARACIÓN DE TORNEOS: ACTIVOS vs ARCHIVADOS ---
# Comparamos en minúsculas para que "Activo", "activo" o "ACTIVO" funcionen igual.
if not df_equipos.empty:
    estado_norm = df_equipos["Estado"].astype(str).str.strip().str.lower()
    torneos_activos = df_equipos[estado_norm == "activo"]['Torneo'].unique().tolist()
    torneos_archivados = df_equipos[estado_norm == "archivado"]['Torneo'].unique().tolist()
    # Cualquier torneo sin estado reconocido lo tratamos como activo, para no esconderlo por error.
    torneos_otros = df_equipos[~estado_norm.isin(["activo", "archivado"])]['Torneo'].unique().tolist()
    for t in torneos_otros:
        if t not in torneos_activos:
            torneos_activos.append(t)
else:
    torneos_activos = []
    torneos_archivados = []

# --- ENCABEZADO CON BOTÓN DE ACTUALIZAR EN LA ESQUINA SUPERIOR DERECHA ---
col_titulo, col_refresh = st.columns([10, 1])
with col_titulo:
    st.title("🏆 Torneo FifafoFumar FC26")
with col_refresh:
    st.write("")  # pequeño espacio para alinear el botón con el título
    if st.button("🔄", help="Forzar actualización de datos", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# --- MENÚ ÚNICO DE TORNEO (activos primero, luego archivados, todos con su estado) ---
# Construimos una lista de etiquetas legibles y un diccionario para saber qué hay detrás.
opciones_torneo = []          # lo que ve el usuario, ej: "FC26#6 ✅ Activo"
mapa_torneo = {}              # etiqueta -> (nombre_real, es_archivado)

for t in torneos_activos:
    etiqueta = f"{t} ✅ Activo"
    opciones_torneo.append(etiqueta)
    mapa_torneo[etiqueta] = (t, False)

for t in torneos_archivados:
    etiqueta = f"{t} 🗄️ Archivado"
    opciones_torneo.append(etiqueta)
    mapa_torneo[etiqueta] = (t, True)

# Si no hay ningún torneo, evitamos que truene.
if not opciones_torneo:
    opciones_torneo = ["Sin Torneos"]
    mapa_torneo["Sin Torneos"] = ("Sin Torneos", False)

col_torneo, col_semana = st.columns(2)
with col_torneo:
    # index=0 hace que por defecto cargue el primero de la lista, que es el torneo activo.
    etiqueta_sel = st.selectbox("Torneo", opciones_torneo, index=0, key="sel_torneo")

# Traducimos la etiqueta elegida al nombre real del torneo y si es archivado o no.
torneo_actual, es_archivado = mapa_torneo[etiqueta_sel]
eq_activos = df_equipos[df_equipos['Torneo'] == torneo_actual]['Equipo'].tolist() if not df_equipos.empty else []

# La semana solo tiene sentido en el torneo activo (donde registras resultados).
if not es_archivado:
    sem_sug = detectar_semana(eq_activos, df_partidos, torneo_actual)
    with col_semana:
        sem_act = st.number_input("Semana", min_value=1, max_value=20, value=sem_sug, key="memoria_semana")
else:
    sem_act = 1  # valor por defecto, no se usa en modo consulta

# --- VISTA DE CONSULTA DE ARCHIVADOS ---
# Si elegiste un torneo archivado, mostramos su calendario y tablas en modo solo lectura.
if es_archivado:
    st.info(f"🗄️ Estás consultando el torneo archivado: **{torneo_actual}** (solo lectura)")

    eq_arch = eq_activos  # ya calculado arriba para este torneo
    partidos_arch = df_partidos[df_partidos['Torneo'] == torneo_actual]

    tab_a_cal, tab_a_tabla, tab_a_goleo, tab_a_transf = st.tabs(["📝 Calendario", "📊 Posiciones", "⚽ Goleo", "🔄 Transferencias"])

    # --- Calendario con resultados (solo lectura) ---
    with tab_a_cal:
        if len(eq_arch) == 6 and not partidos_arch.empty:
            # Recorremos todas las semanas que tengan partidos registrados.
            semanas_con_juegos = sorted(set(
                int(str(j).split('J')[0].replace('S', ''))
                for j in partidos_arch['Jornada']
                if str(j).startswith('S') and 'J' in str(j)
            ))
            for sem in semanas_con_juegos:
                st.markdown(f"#### 📅 Semana {sem}")
                partidos_sem = generar_calendario(eq_arch, sem)
                cc1, cc2 = st.columns(2)
                for idx, p in enumerate(partidos_sem):
                    j = partidos_arch[(partidos_arch['Jornada'] == p['Jornada']) & (partidos_arch['Local'] == p['Local'])]
                    with (cc1 if idx < 4 else cc2):
                        if not j.empty:
                            gl, gv = int(j.iloc[0]['Goles_L']), int(j.iloc[0]['Goles_V'])
                            st.markdown(f"""<div class="match-card-played"><div class="jornada-tag">✅ {p['Jornada']}</div><div class="teams-text">{p['Local']} vs {p['Visitante']}</div><div class="score-text">{gl} - {gv}</div></div>""", unsafe_allow_html=True)
        else:
            st.write("Sin partidos registrados en este torneo.")

    with tab_a_tabla:
        if not partidos_arch.empty:
            stats = {eq: {'PJ': 0, 'G': 0, 'E': 0, 'P': 0, 'GF': 0, 'GC': 0, 'Pts': 0} for eq in eq_arch}
            for _, p in partidos_arch.iterrows():
                loc, vis, gl, gv = p['Local'], p['Visitante'], int(p['Goles_L']), int(p['Goles_V'])
                if loc in stats and vis in stats:
                    stats[loc]['PJ'] += 1; stats[vis]['PJ'] += 1
                    stats[loc]['GF'] += gl; stats[loc]['GC'] += gv
                    stats[vis]['GF'] += gv; stats[vis]['GC'] += gl
                    if gl > gv: stats[loc]['G'] += 1; stats[loc]['Pts'] += 3; stats[vis]['P'] += 1
                    elif gv > gl: stats[vis]['G'] += 1; stats[vis]['Pts'] += 3; stats[loc]['P'] += 1
                    else: stats[loc]['E'] += 1; stats[vis]['E'] += 1; stats[loc]['Pts'] += 1; stats[vis]['Pts'] += 1
            df_t = pd.DataFrame.from_dict(stats, orient='index').reset_index()
            df_t = df_t.rename(columns={'index': 'Equipo'})
            df_t['DG'] = df_t['GF'] - df_t['GC']
            st.dataframe(df_t[['Equipo', 'PJ', 'G', 'E', 'P', 'GF', 'GC', 'DG', 'Pts']].sort_values(by=['Pts', 'DG'], ascending=False), use_container_width=True, hide_index=True)
        else:
            st.write("Sin partidos registrados en este torneo.")

    with tab_a_goleo:
        goles_arch = df_goleadores[df_goleadores['Torneo'] == torneo_actual]
        if not goles_arch.empty:
            st.dataframe(goles_arch.groupby(['Jugador', 'Equipo'])['Goles'].sum().reset_index().sort_values(by='Goles', ascending=False), use_container_width=True, hide_index=True)
        else:
            st.write("Sin goleadores registrados.")

    with tab_a_transf:
        transf_arch = df_transferencias[df_transferencias['Torneo'] == torneo_actual]
        if not transf_arch.empty:
            st.dataframe(transf_arch[["Jornada", "Equipo", "Toma", "Cede"]], use_container_width=True, hide_index=True)
        else:
            st.write("Sin transferencias registradas.")

    st.stop()  # Cortamos aquí para no mostrar las pestañas de edición del torneo activo.

# --- VISTA NORMAL (TORNEO ACTIVO) ---
tab_registro, tab_tabla, tab_goleo, tab_transf, tab_config = st.tabs(["📝 Calendario", "📊 Posiciones", "⚽ Goleo", "🔄 Transferencias", "⚙️ Configuración"])

with tab_config:
    st.subheader("Alta de Torneos y Jugadores")
    col_t, col_e = st.columns(2)
    with col_t: nuevo_torneo = st.text_input("Nombre del Torneo:")
    with col_e: nuevo_equipo = st.text_input("Emoji + Equipo + (Manager):")
    if st.button("Inscribir Jugador"):
        if nuevo_torneo and nuevo_equipo:
            # Los jugadores nuevos nacen en estado "Activo".
            nueva_fila = pd.DataFrame([{
                "Torneo": nuevo_torneo,
                "Equipo": nuevo_equipo,
                "Estado": "Activo"
            }])
            conn.update(worksheet="Equipos", data=pd.concat([df_equipos, nueva_fila], ignore_index=True))
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
                            with st.spinner("Transcribiendo datos visuales..."):
                                try:
                                    imgs_para_ia = []
                                    for f in fotos:
                                        img = Image.open(f)
                                        img.thumbnail((1200, 1200))
                                        buffer = io.BytesIO()
                                        img.convert("RGB").save(buffer, format="JPEG", quality=80)
                                        imgs_para_ia.append(Image.open(buffer))

                                    prompt_ia = """
                                    Eres un transcriptor de datos crudos de EA FC.
                                    NO FILTRES NADA. Transcribe TODOS los eventos de la línea de tiempo.
                                    
                                    PASO 1 (LADO IZQUIERDO):
                                    - Nombre exacto del equipo en el marcador superior izquierdo.
                                    - Goles de ese equipo en el marcador.
                                    - Lista TODOS los eventos que aparecen del lado izquierdo. Para cada evento indica: "nombre" del jugador, el "minuto" (ej. 45'), y el "icono" que tiene al lado (escribe "balon", "amarilla", "roja" o "cambio").
                                    
                                    PASO 2 (LADO DERECHO):
                                    - Nombre exacto del equipo en el marcador superior derecho.
                                    - Goles de ese equipo en el marcador.
                                    - Lista TODOS los eventos que aparecen del lado derecho con su nombre, minuto e icono.
                                    
                                    Devuelve ÚNICAMENTE este JSON:
                                    {
                                      "tv_izq": {
                                        "nombre": "Nombre textual",
                                        "goles": numero,
                                        "eventos": [
                                          {"nombre": "Jugador1", "minuto": "10'", "icono": "balon"}
                                        ]
                                      },
                                      "tv_der": {
                                        "nombre": "Nombre textual",
                                        "goles": numero,
                                        "eventos": [
                                          {"nombre": "Jugador3", "minuto": "45'", "icono": "cambio"}
                                        ]
                                      }
                                    }
                                    """
                                    
                                    max_intentos = 3
                                    res = None
                                    for intento in range(max_intentos):
                                        try:
                                            res = modelo_ia.generate_content([prompt_ia] + imgs_para_ia)
                                            break
                                        except Exception as e_api:
                                            if "429" in str(e_api) and intento < max_intentos - 1:
                                                st.warning(f"⏳ Límite alcanzado. Esperando 8s para reintentar... (Intento {intento+1}/{max_intentos})")
                                                time.sleep(8)
                                            else:
                                                raise e_api
                                    
                                    texto_puro = res.text
                                    inicio_json = texto_puro.find('{')
                                    fin_json = texto_puro.rfind('}')
                                    
                                    if inicio_json != -1 and fin_json != -1:
                                        texto_json = texto_puro[inicio_json:fin_json+1]
                                        d = json.loads(texto_json)
                                        
                                        if "error" in d:
                                            st.error(f"❌ {d['error']}")
                                        else:
                                            def extraer_goleadores(eventos):
                                                goles_unicos = []
                                                vistos = set()
                                                for ev in eventos:
                                                    icono = str(ev.get("icono", "")).lower()
                                                    if "balon" in icono or "balón" in icono or "gol" in icono or "ball" in icono:
                                                        nombre = str(ev.get("nombre", "")).strip()
                                                        minuto = str(ev.get("minuto", "")).strip()
                                                        clave = f"{nombre}_{minuto}"
                                                        if clave not in vistos:
                                                            vistos.add(clave)
                                                            goles_unicos.append(nombre)
                                                return goles_unicos

                                            goleadores_tv_izq = extraer_goleadores(d['tv_izq'].get('eventos', []))
                                            goleadores_tv_der = extraer_goleadores(d['tv_der'].get('eventos', []))

                                            eq_izq = d.get("tv_izq", {}).get("nombre", "")
                                            def clean_words(text):
                                                return [w for w in ''.join(c.lower() if c.isalnum() else ' ' for c in text).split() if len(w) > 2]
                                            
                                            loc_words = clean_words(loc)
                                            izq_words = clean_words(eq_izq)
                                            es_local_izq = any(w in izq_words for w in loc_words)
                                            
                                            if es_local_izq:
                                                st.session_state[f"gl_{st.session_state['fk']}"] = d['tv_izq'].get("goles", 0)
                                                st.session_state[f"gv_{st.session_state['fk']}"] = d['tv_der'].get("goles", 0)
                                                jugadores_l = goleadores_tv_izq
                                                jugadores_v = goleadores_tv_der
                                            else:
                                                st.session_state[f"gl_{st.session_state['fk']}"] = d['tv_der'].get("goles", 0)
                                                st.session_state[f"gv_{st.session_state['fk']}"] = d['tv_izq'].get("goles", 0)
                                                jugadores_l = goleadores_tv_der
                                                jugadores_v = goleadores_tv_izq

                                            for i, jug in enumerate(jugadores_l): 
                                                st.session_state[f"jug_l_{i}_{st.session_state['fk']}"] = jug
                                            for i, jug in enumerate(jugadores_v): 
                                                st.session_state[f"jug_v_{i}_{st.session_state['fk']}"] = jug
                                            
                                            st.success("✅ ¡Datos extraídos, filtrados y cruzados perfectamente por Python!")
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

            # Lista de TODOS los goleadores históricos (de todos los torneos),
            # sin repetir, para comparar lo que se escribe contra lo ya existente.
            if not df_goleadores.empty and 'Jugador' in df_goleadores.columns:
                goleadores_historicos = sorted(set(
                    str(n).strip() for n in df_goleadores['Jugador'].dropna() if str(n).strip()
                ))
            else:
                goleadores_historicos = []

            def campo_goleador(etiqueta, key_base, indice):
                """Dibuja un cuadro de texto para un goleador y, debajo,
                avisa si el nombre se parece a uno ya existente."""
                campo_key = f"{key_base}_{indice}_{st.session_state['fk']}"
                # Si en la pasada anterior se pidió corregir este campo, lo aplicamos
                # ANTES de dibujar el cuadro (así Streamlit sí lo permite).
                correccion_key = f"corregir_{campo_key}"
                if correccion_key in st.session_state:
                    st.session_state[campo_key] = st.session_state[correccion_key]
                    del st.session_state[correccion_key]

                nombre = st.text_input(etiqueta, key=campo_key)
                if nombre and nombre.strip():
                    tipo, parecido_a = buscar_parecido(nombre, goleadores_historicos)
                    if tipo == 'parecido':
                        c_aviso, c_boton = st.columns([3, 2])
                        with c_aviso:
                            st.warning(f"¿Quisiste decir **{parecido_a}**? Ya existe.")
                        with c_boton:
                            if st.button(f"Usar '{parecido_a}'", key=f"fix_{campo_key}"):
                                # Guardamos la corrección para aplicarla en la siguiente pasada.
                                st.session_state[correccion_key] = parecido_a
                                st.rerun()
                return nombre

            goleadores_data = []
            if not wo:
                c_g1, c_g2 = st.columns(2)
                with c_g1:
                    if gl > 0:
                        for i in range(gl):
                            j = campo_goleador(f"Gol L {i+1}", "jug_l", i)
                            if j and j.strip(): 
                                goleadores_data.append({"Torneo": torneo_actual, "Jornada": jorn, "Equipo": loc, "Jugador": j.strip(), "Goles": 1})
                with c_g2:
                    if gv > 0:
                        for i in range(gv):
                            j = campo_goleador(f"Gol V {i+1}", "jug_v", i)
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
    else:
        # Mensaje claro cuando el torneo no tiene exactamente 6 jugadores.
        st.warning(f"⚠️ Este torneo tiene {len(eq_activos)} jugador(es). El calendario actual está diseñado para 6 jugadores. El soporte para 5 jugadores llegará en la siguiente actualización.")

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
        
        df_t = pd.DataFrame.from_dict(stats, orient='index').reset_index()
        df_t = df_t.rename(columns={'index': 'Equipo'})
        df_t['DG'] = df_t['GF'] - df_t['GC']
        st.dataframe(df_t[['Equipo', 'PJ', 'G', 'E', 'P', 'GF', 'GC', 'DG', 'Pts']].sort_values(by=['Pts', 'DG'], ascending=False), use_container_width=True, hide_index=True)

with tab_goleo:
    goles_t = df_goleadores[df_goleadores['Torneo'] == torneo_actual]
    if not goles_t.empty:
        st.dataframe(goles_t.groupby(['Jugador', 'Equipo'])['Goles'].sum().reset_index().sort_values(by='Goles', ascending=False), use_container_width=True, hide_index=True)

with tab_transf:
    t_t = df_transferencias[df_transferencias['Torneo'] == torneo_actual]
    if not t_t.empty: 
        st.dataframe(t_t[["Jornada", "Equipo", "Toma", "Cede"]], use_container_width=True, hide_index=True)
