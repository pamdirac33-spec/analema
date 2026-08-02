import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import math
import folium
from streamlit_folium import st_folium
import time
import streamlit.components.v1 as components
from streamlit_js_eval import streamlit_js_eval

# ---------------------------------------------------------
# CONFIGURACIÓN GENERAL
# ---------------------------------------------------------
st.set_page_config(
    page_title="Analema Solar",
    page_icon="☀️",
    layout="wide",
)
# 1. Inicializar estado por defecto
if "lat" not in st.session_state:
    st.session_state.lat = 48.77568
    st.session_state.lon = 11.48840
    st.session_state.poblacion = "Mailing"

if "zoom" not in st.session_state:
    st.session_state.zoom = 12

# Capturar si la URL trae nuevas coordenadas enviadas por el mapa JS
params = st.query_params
if "lat" in params and "lon" in params:
    try:
        new_lat = float(params["lat"])
        new_lon = float(params["lon"])
        if new_lat != st.session_state.lat or new_lon != st.session_state.lon:
            st.session_state.lat = new_lat
            st.session_state.lon = new_lon
            st.session_state.poblacion = obtener_nombre_por_coordenadas(new_lat, new_lon)
    except ValueError:
        pass

# 2. Capturar eventos de coordenadas enviados desde el mapa HTML
coords = streamlit_js_eval(
    js_expressions="JSON.stringify(window.streamlitReceivedMessage)",
    key="coords_eval"
)

if coords:
    try:
        data = eval(coords)
        if data and "lat" in data and "lon" in data:
            # Comprobamos si las coordenadas realmente cambiaron para evitar bucles
            if data["lat"] != st.session_state.lat or data["lon"] != st.session_state.lon:
                st.session_state.lat = data["lat"]
                st.session_state.lon = data["lon"]
                st.session_state.poblacion = obtener_nombre_por_coordenadas(
                    st.session_state.lat,
                    st.session_state.lon
                )
                # Forzar recarga inmediata para actualizar barra lateral y pestañas
                st.rerun()
    except Exception:
        pass

if "lat_comp" not in st.session_state:
    st.session_state.lat_comp = 41.6333  # Por defecto Valladolid o cualquier otra
    st.session_state.lon_comp = -4.7167
    st.session_state.poblacion_comp = "Valladolid (España)"


# Estilos CSS (se mantienen igual)
st.markdown("""
<style>
body { font-size: 20px; }
button, input, select, textarea { font-size: 22px !important; }
.block-container { padding-top: 1rem; }
.card { background: #f8f9fa; padding: 1.5rem; border-radius: 15px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); margin-bottom: 2rem; }
h1, h2, h3 { text-align: center; }
iframe { background: transparent !important; }
.stApp iframe { border: none !important; box-shadow: none !important; }
.st-folium { padding: 0 !important; margin: 0 !important; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# FUNCIONES (spa, obtener_coordenadas, etc.)
# ---------------------------------------------------------
def obtener_coordenadas(nombre):
    url = f"https://geocoding-api.open-meteo.com/v1/search?name={nombre}&count=1&language=es&format=json"
    try:
        r = requests.get(url, timeout=10)
        datos = r.json()

        if "results" not in datos or len(datos["results"]) == 0:
            return None, None

        lat = datos["results"][0]["latitude"]
        lon = datos["results"][0]["longitude"]
        return lat, lon

    except Exception:
        return None, None

def obtener_nombre_por_coordenadas(lat, lon):
    url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}&zoom=10&accept-language=es"
    headers = {"User-Agent": "AnalemaSolarApp/1.0"}
    try:
        r = requests.get(url, headers=headers, timeout=5)
        datos = r.json()
        if "address" in datos:
            addr = datos["address"]
            # Buscamos de forma jerárquica el mejor nombre disponible
            poblacion = (
                addr.get("city") or 
                addr.get("town") or 
                addr.get("village") or 
                addr.get("municipality") or 
                addr.get("county") or
                addr.get("state")
            )
            pais = addr.get("country", "")
            if poblacion and pais:
                return f"{poblacion} ({pais})"
            elif poblacion:
                return poblacion
    except Exception:
        pass
    
    # Si falla la API externa, devolvemos un formato limpio de respaldo
    return f"Ubicación ({lat:.3f}, {lon:.3f})"

def actualizar_ubicacion(lat, lon):
    st.session_state.lat = lat
    st.session_state.lon = lon
    st.session_state.poblacion = obtener_nombre_por_coordenadas(lat, lon)
    
def spa(fecha, lat, lon, hora):
    n = fecha.timetuple().tm_yday
    decl = 23.45 * math.sin(math.radians(360/365 * (284 + n)))
    B = math.radians(360/365 * (n - 81))
    EoT = 9.87 * math.sin(2*B) - 7.53 * math.cos(B) - 1.5 * math.sin(B)
    solar_time = hora + EoT/60 + lon/15
    H = 15 * (solar_time - 12)

    elev = math.degrees(math.asin(
        math.sin(math.radians(lat)) * math.sin(math.radians(decl)) +
        math.cos(math.radians(lat)) * math.cos(math.radians(decl)) * math.cos(math.radians(H))
    ))

    azim = math.degrees(math.atan2(
        -math.sin(math.radians(H)),
        math.cos(math.radians(lat)) * math.tan(math.radians(decl)) -
        math.sin(math.radians(lat)) * math.cos(math.radians(H))
    ))
    azim = (azim + 360) % 360

    return elev, azim

def generar_analema(lat, lon, year, hora):
    fechas = [datetime(year, 1, 1) + timedelta(days=i) for i in range(365)]
    elevaciones = []
    azimuths = []
    for fecha in fechas:
        elev, azim = spa(fecha, lat, lon, hora)
        elevaciones.append(elev)
        azimuths.append(azim)
    return pd.DataFrame({"fecha": fechas, "elev": elevaciones, "azim": azimuths})

def calcular_curvas_solares(lat, lon, usar_dst=True):
    dias = np.arange(1, 366)
    amanecer_horas = []
    atardecer_horas = []
    
    lat_rad = np.radians(lat)
    
    # Huso horario estándar según longitud (ej. Europa Central = 1 -> CET UTC+1)
    # Si la longitud es negativa (oeste), tenderá a UTC 0 o negativos.
    huso_base = int(round(lon / 15.0))
    if -7.5 <= lon <= 7.5:
        huso_base = 0
    elif 7.5 < lon <= 22.5:
        huso_base = 1
    elif lon > 22.5:
        huso_base = int(np.floor((lon + 7.5) / 15.0))
    elif lon < -7.5:
        huso_base = int(np.ceil((lon - 7.5) / 15.0))

    for dia in dias:
        # Fecha real del año 2026 para comprobar el DST europeo exacto (último domingo de marzo a último de octubre)
        fecha_actual = datetime(2026, 1, 1) + timedelta(days=int(dia) - 1)
        
        # Comprobación estricta de horario de verano en la Unión Europea / Europa Central
        # (último domingo de marzo a último domingo de octubre)
        es_dst_activo = False
        if usar_dst:
            mes = fecha_actual.month
            dia_mes = fecha_actual.day
            dia_semana = fecha_actual.weekday() # 0: Lunes, 6: Domingo
            
            # Último domingo de marzo
            ultimo_domingo_marzo = 31 - (datetime(2026, 3, 31).weekday() + 1) % 7
            # Último domingo de octubre
            ultimo_domingo_octubre = 31 - (datetime(2026, 10, 31).weekday() + 1) % 7
            
            if (mes > 3 and mes < 10):
                es_dst_activo = True
            elif mes == 3 and dia_mes >= ultimo_domingo_marzo:
                es_dst_activo = True
            elif mes == 10 and dia_mes < ultimo_domingo_octubre:
                es_dst_activo = True

        # Cálculos orbitales de la NOAA
        gamma = 2.0 * np.pi * (dia - 1) / 365.0
        eqtime = 229.18 * (0.000075 + 0.001868 * np.cos(gamma) - 0.032077 * np.sin(gamma) - 
                           0.014615 * np.cos(2 * gamma) - 0.040849 * np.sin(2 * gamma))
        
        decl = (0.006918 - 0.399912 * np.cos(gamma) + 0.070257 * np.sin(gamma) - 
                0.006758 * np.cos(2 * gamma) - 0.000907 * np.sin(2 * gamma) - 
                0.002697 * np.cos(3 * gamma) + 0.00148 * np.sin(3 * gamma))
        
        cos_ha = (np.cos(np.radians(90.833)) / (np.cos(lat_rad) * np.cos(decl))) - (np.tan(lat_rad) * np.tan(decl))
        cos_ha = np.clip(cos_ha, -1.0, 1.0)
        ha = np.degrees(np.arccos(cos_ha))
        
        # Mediodía solar verdadero en UTC (minutos)
        mediodia_utc_minutos = 720 - (4 * lon) - eqtime
        
        amanecer_utc_min = mediodia_utc_minutos - (ha * 4)
        atardecer_utc_min = mediodia_utc_minutos + (ha * 4)
        
        # Desplazamiento horario total (Huso base + hora extra si el DST está activo)
        offset_total = huso_base + (1 if es_dst_activo else 0)
        
        h_amanecer = (amanecer_utc_min / 60.0) + offset_total
        h_atardecer = (atardecer_utc_min / 60.0) + offset_total
            
        amanecer_horas.append(h_amanecer % 24)
        atardecer_horas.append(h_atardecer % 24)
        
    return dias, amanecer_horas, atardecer_horas

def es_horario_verano(dia_del_año):
    # Simplificación: días 85 (aprox 31 marzo) a 300 (aprox 27 octubre)
    return 85 <= dia_del_año <= 300


# ---------------------------------------------------------
# BARRA LATERAL FIJA (Pintada DESPUÉS de actualizar el estado)
# ---------------------------------------------------------
st.sidebar.success("📍 Ubicación seleccionada")

st.sidebar.markdown(
    f"""
**Ciudad:** {st.session_state.poblacion}  
**Lat:** {st.session_state.lat:.5f}  
**Lon:** {st.session_state.lon:.5f}
"""
)

year = st.sidebar.number_input("Año", value=datetime.now().year, step=1)
hora = st.sidebar.slider("Hora del día", 0, 23, 12)

# ---------------------------------------------------------
# TÍTULO PRINCIPAL Y PESTAÑAS
# ---------------------------------------------------------
st.markdown("<div class='card'><h1>🌞 Analema Solar Interactiva</h1></div>", unsafe_allow_html=True)
tab1, tab2, tab3, tab4, tab5 = st.tabs(["Mapa", "Analema animada", "Comparación", "Funciones avanzadas", "Horas de sol"])

# ---------------------------------------------------------
# TAB 1 – MAPA INTERACTIVO (Dos capas: Satélite con nombres y Street)
# ---------------------------------------------------------
with tab1:
    st.markdown("<div class='card'><h2>🗺️ Selección de ubicación</h2></div>", unsafe_allow_html=True)

    # 1. Gestionar el estado del buscador
    if "busqueda_query" not in st.session_state:
        st.session_state.busqueda_query = ""

    # Buscador de ciudades
    col_busq, col_vacio = st.columns([2, 3])
    with col_busq:
        busqueda_input = st.text_input(
            "🔍 Buscar ciudad o lugar:", 
            value=st.session_state.busqueda_query,
            placeholder="Ej: Madrid, Múnich, París..."
        )

        if busqueda_input and busqueda_input != st.session_state.busqueda_query:
            st.session_state.busqueda_query = busqueda_input
            lat_b, lon_b = obtener_coordenadas(busqueda_input)
            if lat_b and lon_b:
                if lat_b != st.session_state.lat or lon_b != st.session_state.lon:
                    actualizar_ubicacion(lat_b, lon_b)
                    st.session_state.zoom = 13
                    st.rerun()

    # 2. Creamos el mapa centrado en las coordenadas actuales
    mapa_tab1 = folium.Map(
        location=[st.session_state.lat, st.session_state.lon],
        zoom_start=st.session_state.zoom,
        tiles=None
    )

    # 3. CAPA 1: Satélite (Grupo que une las imágenes de la tierra y los nombres/etiquetas)
    satelite_group = folium.FeatureGroup(name="Satélite", control=True, overlay=False)
    
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri World Imagery",
        control=False
    ).add_to(satelite_group)
    
    folium.TileLayer(
        tiles="https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
        attr="Esri Boundaries",
        control=False
    ).add_to(satelite_group)
    
    satelite_group.add_to(mapa_tab1)

    # 4. CAPA 2: Street (Modo Calles clásico y limpio)
    folium.TileLayer(
        tiles="openstreetmap",
        name="Street",
        control=True,
        overlay=False
    ).add_to(mapa_tab1)

    # 5. Marcador de la ubicación seleccionada
    folium.Marker(
        [st.session_state.lat, st.session_state.lon],
        popup=st.session_state.poblacion,
        icon=folium.Icon(color="red", icon="info-sign")
    ).add_to(mapa_tab1)

    # 6. Coordenadas del cursor
    from folium.plugins import MousePosition
    formatter = "function(num) {return L.Util.formatNum(num, 5);};"
    MousePosition(
        position="bottomleft",
        separator=" | ",
        prefix="Lat: ",
        lat_formatter=formatter,
        lng_formatter=formatter
    ).add_to(mapa_tab1)

    # 7. Control de capas desplegable
    folium.LayerControl(collapsed=False).add_to(mapa_tab1)

    # 8. Renderizado del mapa con st_folium
    output_mapa = st_folium(
        mapa_tab1, 
        width="100%", 
        height=600, 
        key="mapa_interactivo_tab1",
        returned_objects=["last_clicked", "zoom", "center"]
    )

    # 9. Control de eventos (Prioridad al clic en el mapa)
    if output_mapa:
        if output_mapa.get("zoom"):
            st.session_state.zoom = output_mapa["zoom"]

        if output_mapa.get("last_clicked"):
            clicked_lat = output_mapa["last_clicked"]["lat"]
            clicked_lon = output_mapa["last_clicked"]["lng"]

            if clicked_lat != st.session_state.lat or clicked_lon != st.session_state.lon:
                st.session_state.busqueda_query = ""
                actualizar_ubicacion(clicked_lat, clicked_lon)
                st.rerun()
                
# ---------------------------------------------------------
# TAB 2 – ANALEMA ANIMADA POR HORAS
# ---------------------------------------------------------
with tab2:
    st.markdown("<div class='card'><h2>Evolución analema por horas</h2></div>", unsafe_allow_html=True)

    import plotly.express as px
    import plotly.graph_objects as go

    analemas = []
    for h in range(4, 23):
        df_h = generar_analema(st.session_state.lat, st.session_state.lon, year, h).copy()
        df_h["hora"] = h
        df_h["fecha"] = pd.to_datetime(f"{year}-01-01") + pd.to_timedelta(df_h.index, unit="D")
        df_h["mes"] = df_h["fecha"].dt.month
        df_h["mes_nombre"] = df_h["fecha"].dt.month_name(locale="es_ES")
        df_h["dia_del_ano"] = df_h.index
        analemas.append(df_h)

    df_all = pd.concat(analemas)

    fig = px.line(
        df_all,
        x="azim",
        y="elev",
        color="mes_nombre",
        animation_frame="hora",
        labels={
            "azim": "Azimuth (°)",
            "elev": "Elevación (°)",
            "mes_nombre": "Mes",
            "hora": "Hora del día"
        },
        color_discrete_sequence=px.colors.qualitative.Set3
    )

    fig.update_traces(
        hovertemplate=
        "<b>Hora %{customdata[0]}:00</b><br>" +
        "Día del año: %{customdata[1]}<br>" +
        "Mes: %{customdata[2]}<br>" +
        "Azimuth: %{x:.2f}°<br>" +
        "Elevación: %{y:.2f}°<extra></extra>",
        customdata=df_all[["hora", "dia_del_ano", "mes_nombre"]]
    )

    puntos_max = []
    for h in range(4, 23):
        df_h = df_all[df_all["hora"] == h]
        idx_max = df_h["elev"].idxmax()
        puntos_max.append(df_h.loc[idx_max])

    df_max = pd.DataFrame(puntos_max).sort_values("hora")

    fig.add_trace(go.Scatter(
        x=df_max["azim"],
        y=df_max["elev"],
        mode="lines+markers",
        line=dict(color="orange", width=1, dash="dash"),
        marker=dict(size=4, color="orange"),
        showlegend=False,
        hovertemplate=
            "<b>Hora %{customdata}:00</b><br>" +
            "Día del año: %{text}<br>" +
            "Azimuth: %{x:.2f}°<br>" +
            "Elevación máxima: %{y:.2f}°<extra></extra>",
        customdata=df_max["hora"],
        text=df_max["dia_del_ano"]
    ))

    puntos_min = []
    for h in range(4, 23):
        df_h = df_all[df_all["hora"] == h]
        idx_min = df_h["elev"].idxmin()
        puntos_min.append(df_h.loc[idx_min])

    df_min = pd.DataFrame(puntos_min).sort_values("hora")

    fig.add_trace(go.Scatter(
        x=df_min["azim"],
        y=df_min["elev"],
        mode="lines+markers",
        line=dict(color="gray", width=1, dash="dash"),
        marker=dict(size=4, color="gray"),
        showlegend=False,
        hovertemplate=
            "<b>Hora %{customdata}:00</b><br>" +
            "Día del año: %{text}<br>" +
            "Azimuth: %{x:.2f}°<br>" +
            "Elevación mínima: %{y:.2f}°<extra></extra>",
        customdata=df_min["hora"],
        text=df_min["dia_del_ano"]
    ))

    fig.add_shape(
        type="rect",
        xref="paper",
        yref="y",
        x0=0,
        x1=1,
        y0=df_all["elev"].min() - 5,
        y1=0,
        fillcolor="rgba(200,0,0,0.10)",
        line_width=0,
        layer="below"
    )

    fig.update_layout(
        height=550,
        plot_bgcolor="#f7f7f7",
        paper_bgcolor="#f7f7f7",
        font=dict(size=13, color="#333"),
        title=dict(
            text=f"Analemas por mes",
            x=0,
            xanchor="left",
            font=dict(size=22)
        ),
        showlegend=True,
        legend=dict(
            x=1.05,
            y=1,
            bgcolor="rgba(255,255,255,0.8)"
        )
    )

    st.plotly_chart(fig, width="stretch")

# ---------------------------------------------------------
# TAB 3 – COMPARACIÓN ENTRE CIUDADES
# ---------------------------------------------------------
with tab3:
    st.markdown("<div class='card'><h2>📊 Comparación de analemas por ciudades</h2></div>", unsafe_allow_html=True)

    ciudades = st.text_area("Introduce ciudades separadas por comas:", "Ingolstadt, Valladolid, El Cairo")
    lista = [c.strip() for c in ciudades.split(",") if c.strip()]

    plt.style.use("seaborn-v0_8-darkgrid")
    fig, ax = plt.subplots(figsize=(6, 6))

    for ciudad in lista:
        lat2, lon2 = obtener_coordenadas(ciudad)
        if lat2:
            df2 = generar_analema(lat2, lon2, year, hora)
            ax.scatter(
                df2["azim"],
                df2["elev"],
                s=12,
                label=ciudad
            )

    ax.set_xlabel("Azimuth (°)", fontsize=14)
    ax.set_ylabel("Elevación (°)", fontsize=14)
    ax.set_title(f"Comparación – {hora}:00 h – {year}", fontsize=18)
    ax.legend()

    st.pyplot(fig)

# ---------------------------------------------------------
# TAB 4 – MAPA INTERACTIVO
# ---------------------------------------------------------
with tab4:
    st.markdown("<div class='card'><h2>🌍 Funciones avanzadas solares</h2></div>", unsafe_allow_html=True)

    # --- POSICIÓN DEL SOL AHORA ---
    ahora = datetime.now()
    elev_sol, azim_sol = spa(ahora, st.session_state.lat, st.session_state.lon, ahora.hour + ahora.minute/60)

    # --- Cálculo de punto hacia donde está el sol ---
    dist_km = 20
    R = 6371

    lat_rad = math.radians(st.session_state.lat)
    lon_rad = math.radians(st.session_state.lon)
    az_rad = math.radians(azim_sol)

    lat_sol = math.degrees(
        math.asin(
            math.sin(lat_rad)*math.cos(dist_km/R) +
            math.cos(lat_rad)*math.sin(dist_km/R)*math.cos(az_rad)
        )
    )

    lon_sol = math.degrees(
        lon_rad + math.atan2(
            math.sin(az_rad)*math.sin(dist_km/R)*math.cos(lat_rad),
            math.cos(dist_km/R) - math.sin(lat_rad)*math.sin(math.radians(lat_sol))
        )
    )

    # --- MAPA SATÉLITE ---
    mapa4 = folium.Map(
        location=[st.session_state.lat, st.session_state.lon],
        zoom_start=10,
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri World Imagery"
    )

    # --- MARCADOR DEL SOL ---
    folium.Marker(
        [lat_sol, lon_sol],
        popup=f"Sol ahora\nAzimut: {azim_sol:.1f}°\nElevación: {elev_sol:.1f}°",
        icon=folium.Icon(color="orange", icon="sun", prefix="fa")
    ).add_to(mapa4)

    # --- SOMBRA REAL PROYECTADA ---
    # Longitud de la sombra en metros
    if elev_sol > 0:
        sombra_m = 1 / math.tan(math.radians(elev_sol))
    else:
        sombra_m = 0

    # Convertimos sombra a coordenadas
    dist_sombra = sombra_m / 1000
    lat_sombra = math.degrees(
        math.asin(
            math.sin(lat_rad)*math.cos(dist_sombra/R) +
            math.cos(lat_rad)*math.sin(dist_sombra/R)*math.cos(az_rad)
        )
    )
    lon_sombra = math.degrees(
        lon_rad + math.atan2(
            math.sin(az_rad)*math.sin(dist_sombra/R)*math.cos(lat_rad),
            math.cos(dist_sombra/R) - math.sin(lat_rad)*math.sin(math.radians(lat_sombra))
        )
    )

    folium.PolyLine(
        locations=[[st.session_state.lat, st.session_state.lon], [lat_sombra, lon_sombra]],
        color="black",
        weight=4,
        tooltip="Sombra proyectada"
    ).add_to(mapa4)

    # --- TRAYECTORIA SOLAR DEL DÍA ---
    puntos_tray = []
    for h in range(0, 24):
        elev_h, azim_h = spa(ahora, st.session_state.lat, st.session_state.lon, h)
        az_rad_h = math.radians(azim_h)
        dist_km_h = 20

        lat_h = math.degrees(
            math.asin(
                math.sin(lat_rad)*math.cos(dist_km_h/R) +
                math.cos(lat_rad)*math.sin(dist_km_h/R)*math.cos(az_rad_h)
            )
        )
        lon_h = math.degrees(
            lon_rad + math.atan2(
                math.sin(az_rad_h)*math.sin(dist_km_h/R)*math.cos(lat_rad),
                math.cos(dist_km_h/R) - math.sin(lat_rad)*math.sin(math.radians(lat_h))
            )
        )
        puntos_tray.append([lat_h, lon_h])

    folium.PolyLine(
        locations=puntos_tray,
        color="yellow",
        weight=3,
        tooltip="Trayectoria solar del día"
    ).add_to(mapa4)

    # --- CAPA DÍA/NOCHE NASA ---
    folium.raster_layers.TileLayer(
        tiles="https://tiles.stadiamaps.com/tiles/alidade_smooth_dark/{z}/{x}/{y}.png",
        name="Noche",
        attr="NASA / Stadia Maps",
        overlay=True,
        control=True,
        opacity=0.5
    ).add_to(mapa4)

    folium.LayerControl().add_to(mapa4)

    st_folium(mapa4, width=900, height=600)

# ---------------------------------------------------------
# TAB 5 – HORAS DE LUZ
# ---------------------------------------------------------
with tab5:
    st.markdown("<div class='card'><h2>📈 Comparativa Anual de Luz Solar</h2></div>", unsafe_allow_html=True)

    # 1. Cálculo de horas actuales (Local y CET) para ambas poblaciones con sus nombres encima
    from datetime import datetime
    import pytz

    tz_cet = pytz.timezone('Etc/GMT-1')
    ahora_utc = datetime.now(pytz.utc)
    ahora_cet = ahora_utc.astimezone(tz_cet)
    
    # Hora local estimada para la población principal y la de comparación (usando zonas horarias aproximadas o UTC+1 con DST)
    ahora_local_1 = ahora_utc.astimezone(pytz.timezone('Europe/Berlin'))
    ahora_local_2 = ahora_utc.astimezone(pytz.timezone('Europe/Madrid'))

    col_info1, col_info2, col_vacia = st.columns([2, 2, 2])
    with col_info1:
        st.markdown(f"**📍 {st.session_state.poblacion}**")
        st.metric(label="Hora Local / CET", value=f"{ahora_local_1.strftime('%H:%M:%S')} (CET: {ahora_cet.strftime('%H:%M:%S')})")
    with col_info2:
        st.markdown(f"**⚖️ {st.session_state.poblacion_comp}**")
        st.metric(label="Hora Local / CET", value=f"{ahora_local_2.strftime('%H:%M:%S')} (CET: {ahora_cet.strftime('%H:%M:%S')})")

    st.markdown("---")

    # 2. Opciones y Buscador de la segunda población
    col_op1, col_busq2 = st.columns([2, 3])
    with col_op1:
        mostrar_dst = st.checkbox("Incluir cambio de horario de verano (DST)", value=True, key="dst_comp")
    
    with col_busq2:
        busqueda_comparativa = st.text_input("⚖️ Comparar con otra ciudad:", placeholder="Ej: Barcelona, Roma, Tokio...")
        if busqueda_comparativa:
            lat_c, lon_c = obtener_coordenadas(busqueda_comparativa)
            if lat_c and lon_c:
                if lat_c != st.session_state.lat_comp or lon_c != st.session_state.lon_comp:
                    st.session_state.lat_comp = lat_c
                    st.session_state.lon_comp = lon_c
                    st.session_state.poblacion_comp = obtener_nombre_por_coordenadas(lat_c, lon_c)
                    st.rerun()

    # Generar el eje X con fechas reales (DD.MM) para un año no bisiesto (ej. 2026)
    fechas_dt = [datetime(2026, 1, 1) + pd.Timedelta(days=i) for i in range(365)]
    fechas_str = [f"{d.day:02d}.{d.month:02d}" for d in fechas_dt]

    # Cálculos anuales corregidos
    dias, amanecer_1, atardecer_1 = calcular_curvas_solares(
        lat=st.session_state.lat, lon=st.session_state.lon, usar_dst=mostrar_dst
    )
    _, amanecer_2, atardecer_2 = calcular_curvas_solares(
        lat=st.session_state.lat_comp, lon=st.session_state.lon_comp, usar_dst=mostrar_dst
    )

    # Funciones auxiliares para formato HH:MM y estadísticas
    def decimal_a_hhmm(h_decimal):
        h = int(h_decimal % 24)
        m = int(round((h_decimal % 24 - h) * 60))
        if m == 60:
            h = (h + 1) % 24
            m = 0
        return f"{h:02d}:{m:02d}"

    def calcular_estadisticas(fechas_arr, am_arr, at_arr):
        duraciones = []
        for am, at in zip(am_arr, at_arr):
            duracion = at - am if at >= am else (24.0 - am) + at
            duraciones.append(duracion)
            
        duraciones = np.array(duraciones)
        idx_max = np.argmax(duraciones)
        idx_min = np.argmin(duraciones)
        
        luz_max = duraciones[idx_max]
        osc_max = 24.0 - luz_max
        luz_min = duraciones[idx_min]
        osc_min = 24.0 - luz_min
        
        # Porcentajes diarios (respecto a 24 horas)
        porc_luz_max = (luz_max / 24.0) * 100
        porc_osc_max = (osc_max / 24.0) * 100
        porc_luz_min = (luz_min / 24.0) * 100
        porc_osc_min = (osc_min / 24.0) * 100
        
        # Totales anuales considerando si el año es bisiesto o no
        num_dias = len(fechas_arr)
        horas_totales_ano = 24.0 * num_dias
        
        total_luz_horas = sum(duraciones)
        total_osc_horas = horas_totales_ano - total_luz_horas
        
        porc_total_luz = (total_luz_horas / horas_totales_ano) * 100
        porc_total_osc = (total_osc_horas / horas_totales_ano) * 100
        
        return {
            "max_fecha": fechas_arr[idx_max].strftime("%d de %B"),
            "max_luz": f"{int(luz_max)}h {int(round((luz_max%1)*60))}m ({porc_luz_max:.1f}%)",
            "max_osc": f"{int(osc_max)}h {int(round((osc_max%1)*60))}m ({porc_osc_max:.1f}%)",
            "min_fecha": fechas_arr[idx_min].strftime("%d de %B"),
            "min_luz": f"{int(luz_min)}h {int(round((luz_min%1)*60))}m ({porc_luz_min:.1f}%)",
            "min_osc": f"{int(osc_min)}h {int(round((osc_min%1)*60))}m ({porc_osc_min:.1f}%)",
            "total_luz": f"{int(total_luz_horas):,} horas ({porc_total_luz:.1f}%)".replace(",", "."),
            "total_osc": f"{int(total_osc_horas):,} horas ({porc_total_osc:.1f}%)".replace(",", ".")
        }

    stats_1 = calcular_estadisticas(fechas_dt, amanecer_1, atardecer_1)
    stats_2 = calcular_estadisticas(fechas_dt, amanecer_2, atardecer_2)

    # Construcción gráfica Plotly con eje X formateado como DD.MM y hover en HH:MM
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=fechas_str, y=amanecer_1, mode='lines', 
        name=f'Amanecer - {st.session_state.poblacion}', 
        line=dict(color='orange', width=2),
        hovertemplate="Fecha: %{x}<br>Amanecer: " + np.vectorize(decimal_a_hhmm)(amanecer_1) + "<extra></extra>"
    ))
    fig.add_trace(go.Scatter(
        x=fechas_str, y=atardecer_1, mode='lines', 
        name=f'Atardecer - {st.session_state.poblacion}', 
        line=dict(color='darkorange', width=2),
        hovertemplate="Fecha: %{x}<br>Atardecer: " + np.vectorize(decimal_a_hhmm)(atardecer_1) + "<extra></extra>"
    ))
    fig.add_trace(go.Scatter(
        x=fechas_str, y=amanecer_2, mode='lines', 
        name=f'Amanecer - {st.session_state.poblacion_comp}', 
        line=dict(color='deepskyblue', width=2, dash='dash'),
        hovertemplate="Fecha: %{x}<br>Amanecer: " + np.vectorize(decimal_a_hhmm)(amanecer_2) + "<extra></extra>"
    ))
    fig.add_trace(go.Scatter(
        x=fechas_str, y=atardecer_2, mode='lines', 
        name=f'Atardecer - {st.session_state.poblacion_comp}', 
        line=dict(color='blue', width=2, dash='dash'),
        hovertemplate="Fecha: %{x}<br>Atardecer: " + np.vectorize(decimal_a_hhmm)(atardecer_2) + "<extra></extra>"
    ))

    fig.update_layout(
        title=f"Comparativa de luz solar: {st.session_state.poblacion} vs {st.session_state.poblacion_comp}",
        xaxis_title="Fecha (Día.Mes)",
        yaxis_title="Hora del día",
        template="plotly_white",
        hovermode="x unified",
        yaxis=dict(range=[0, 24], dtick=2),
        xaxis=dict(nticks=12) # Muestra etiquetas espaciadas a lo largo del año
    )

    st.plotly_chart(fig, width="stretch")

    # 3. Paneles de información detallada debajo de la gráfica
    st.markdown("---")
    col_info_A, col_info_B = st.columns(2)

    with col_info_A:
        st.markdown(f"### 📍 {st.session_state.poblacion}")
        st.markdown(f"☀️ **Día más largo:** {stats_1['max_fecha']}")
        st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;• Horas de luz: `{stats_1['max_luz']}` | Oscuridad: `{stats_1['max_osc']}`")
        st.markdown(f"🌙 **Día más corto:** {stats_1['min_fecha']}")
        st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;• Horas de luz: `{stats_1['min_luz']}` | Oscuridad: `{stats_1['min_osc']}`")
        st.markdown(f"⏳ **Totales anuales:** Luz: `{stats_1['total_luz']}` | Oscuridad: `{stats_1['total_osc']}`")

    with col_info_B:
        st.markdown(f"### ⚖️ {st.session_state.poblacion_comp}")
        st.markdown(f"☀️ **Día más largo:** {stats_2['max_fecha']}")
        st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;• Horas de luz: `{stats_2['max_luz']}` | Oscuridad: `{stats_2['max_osc']}`")
        st.markdown(f"🌙 **Día más corto:** {stats_2['min_fecha']}")
        st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;• Horas de luz: `{stats_2['min_luz']}` | Oscuridad: `{stats_2['min_osc']}`")
        st.markdown(f"⏳ **Totales anuales:** Luz: `{stats_2['total_luz']}` | Oscuridad: `{stats_2['total_osc']}`")
