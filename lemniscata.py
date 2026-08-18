import streamlit as st
import pandas as pd
import numpy as np
import calendar
import plotly.graph_objects as go
import plotly.express as px
import requests
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import math
import folium
from streamlit_folium import st_folium
from folium.plugins import TimestampedGeoJson
import time
import streamlit.components.v1 as components
from streamlit_js_eval import streamlit_js_eval
import pytz
from timezonefinder import TimezoneFinder

# ---------------------------------------------------------
# CONFIGURACIÓN GENERAL
# ---------------------------------------------------------
st.set_page_config(
    page_title="Analema Solar",
    page_icon="☀️",
    layout="wide",
)

meses_es = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# Estilos CSS Profesionales, Modernos y Barra Superior Fija
st.markdown("""
<style>
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
.block-container { padding-top: 1.2rem; padding-bottom: 2rem; }
.card-minimal { 
    background: #ffffff; 
    border: 1px solid #eaeaea; 
    padding: 0.8rem 1.2rem; 
    border-radius: 10px; 
    box-shadow: 0 2px 6px rgba(0,0,0,0.02); 
    margin-bottom: 1.2rem; 
    display: flex;
    align-items: center;
}
.card-minimal h1, .card-minimal h2 { 
    margin: 0; 
    font-size: 1.25rem; 
    font-weight: 600; 
    color: #1f2937;
}
iframe { background: transparent !important; }
.stApp iframe { border: none !important; box-shadow: none !important; }
.st-folium { padding: 0 !important; margin: 0 !important; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# FUNCIONES
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
    return f"Ubicación ({lat:.3f}, {lon:.3f})"

def actualizar_ubicacion(lat, lon):
    st.session_state.lat = lat
    st.session_state.lon = lon
    st.session_state.poblacion = obtener_nombre_por_coordenadas(lat, lon)
    
def spa(fecha, lat, lon, hora_utc):
    n = fecha.timetuple().tm_yday
    decl = 23.45 * math.sin(math.radians(360/365 * (284 + n)))
    B = math.radians(360/365 * (n - 81))
    EoT = 9.87 * math.sin(2*B) - 7.53 * math.cos(B) - 1.5 * math.sin(B)
    solar_time = hora_utc + EoT/60 + lon/15
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

def es_horario_verano(fecha, lon):
    year = fecha.year
    mes = fecha.month
    dia_mes = fecha.day
    ultimo_domingo_marzo = 31 - (datetime(year, 3, 31).weekday() + 1) % 7
    ultimo_domingo_octubre = 31 - (datetime(year, 10, 31).weekday() + 1) % 7
    
    if (3 < mes < 10):
        return True
    elif mes == 3 and dia_mes >= ultimo_domingo_marzo:
        return True
    elif mes == 10 and dia_mes < ultimo_domingo_octubre:
        return True
    return False

def generar_analema(lat, lon, year, hora_utc):
    fechas = [datetime(year, 1, 1) + timedelta(days=i) for i in range(365)]
    elevaciones = []
    azimuths = []
    for i, fecha in enumerate(fechas):
        elev, azim = spa(fecha, lat, lon, hora_utc)
        elevaciones.append(elev)
        azimuths.append(azim)
    return pd.DataFrame({"fecha": fechas, "elev": elevaciones, "azim": azimuths})

tf = TimezoneFinder()

def obtener_tz_dinamica(lat, lon):
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return pytz.utc
        
    tz_str = tf.timezone_at(lat=lat, lng=lon)
    return pytz.timezone(tz_str) if tz_str else pytz.utc

def calcular_curvas_solares(lat, lon, usar_dst=True):
    # Asegurar que lat y lon son numéricos
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        lat, lon = 48.77568, 11.48840

    # Obtener la zona horaria real basada en las coordenadas
    tz_str = tf.timezone_at(lat=lat, lng=lon)
    local_tz = pytz.timezone(tz_str) if tz_str else pytz.utc

    dias = np.arange(1, 366)
    amanecer_horas = []
    atardecer_horas = []
    lat_rad = np.radians(lat)

    for dia in dias:
        fecha_actual = datetime(2026, 1, 1) + timedelta(days=int(dia) - 1)
        
        # Obtener el offset exacto en horas usando pytz (maneja DST automáticamente si usar_dst=True)
        if usar_dst:
            localized_dt = local_tz.localize(fecha_actual, is_dst=None)
            offset_horas = localized_dt.utcoffset().total_seconds() / 3600.0
        else:
            # Si no se usa DST, fijamos el offset estándar de invierno (enero)
            localized_dt = local_tz.localize(datetime(fecha_actual.year, 1, 1), is_dst=False)
            offset_horas = localized_dt.utcoffset().total_seconds() / 3600.0

        gamma = 2.0 * np.pi * (dia - 1) / 365.0
        eqtime = 229.18 * (0.000075 + 0.001868 * np.cos(gamma) - 0.032077 * np.sin(gamma) - 
                           0.014615 * np.cos(2 * gamma) - 0.040849 * np.sin(2 * gamma))
        
        decl = (0.006918 - 0.399912 * np.cos(gamma) + 0.070257 * np.sin(gamma) - 
                0.006758 * np.cos(2 * gamma) - 0.000907 * np.sin(2 * gamma) - 
                0.002697 * np.cos(3 * gamma) + 0.00148 * np.sin(3 * gamma))
        
        # Evitar errores de dominio en arccos asegurando límites estrictos
        val_cos = (np.cos(np.radians(90.833)) / (np.cos(lat_rad) * np.cos(decl))) - (np.tan(lat_rad) * np.tan(decl))
        cos_ha = np.clip(val_cos, -1.0, 1.0)
        ha = np.degrees(np.arccos(cos_ha))
        
        mediodia_utc_minutos = 720 - (4 * lon) - eqtime
        amanecer_utc_min = mediodia_utc_minutos - (ha * 4)
        atardecer_utc_min = mediodia_utc_minutos + (ha * 4)
        
        # Aplicar el offset real de la zona horaria en lugar de la aproximación por longitud
        h_amanecer = (amanecer_utc_min / 60.0) + offset_horas
        h_atardecer = (atardecer_utc_min / 60.0) + offset_horas
            
        amanecer_horas.append(h_amanecer % 24)
        atardecer_horas.append(h_atardecer % 24)
        
    return dias, amanecer_horas, atardecer_horas

# ---------------------------------------------------------
# INICIALIZACIÓN DE ESTADOS
# ---------------------------------------------------------
if "lat" not in st.session_state:
    st.session_state.lat = 48.77568
    st.session_state.lon = 11.48840
    st.session_state.poblacion = "Mailing"

if "zoom" not in st.session_state:
    st.session_state.zoom = 12

if "map_tile_active" not in st.session_state:
    st.session_state.map_tile_active = "Satélite"

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

if "lat_comp" not in st.session_state:
    st.session_state.lat_comp = 41.6333
    st.session_state.lon_comp = -4.7167
    st.session_state.poblacion_comp = "Valladolid (España)"

# ---------------------------------------------------------
# BARRA LATERAL FIJA
# ---------------------------------------------------------
st.markdown(
    """
    <style>
        [data-testid="stSidebar"] {
            min-width: 50px !important;
            max-width: 250px !important;
        }
    </style>
    """,
    unsafe_allow_html=True
)
st.sidebar.success("📍 Selected Location")
    
ahora_utc_sidebar = datetime.now(pytz.utc)
es_dst_sidebar = es_horario_verano(datetime.now(), st.session_state.lon)
huso_sidebar = int(round(st.session_state.lon / 15.0))
offset_sidebar = huso_sidebar + (1 if es_dst_sidebar else 0)
ahora_local_sidebar = ahora_utc_sidebar + timedelta(hours=offset_sidebar)

# Calcular el día del año actual basado en la hora local
dia_del_ano_sidebar = ahora_local_sidebar.timetuple().tm_yday

st.sidebar.markdown(
    f"""
**City:** {st.session_state.poblacion}  
**Lat:** {st.session_state.lat:.5f}°  
**Lon:** {st.session_state.lon:.5f}°  
**Date:** {ahora_local_sidebar.strftime('%d.%m.%Y')} (Day {dia_del_ano_sidebar})  
**Local Time:** {ahora_local_sidebar.strftime('%H:%M:%S')} (UTC {offset_sidebar:+g})  
**UTC:** {ahora_utc_sidebar.strftime('%H:%M:%S')}
"""
)

# Definimos las variables de tiempo basadas en el momento actual
# Esto mantiene la compatibilidad con el resto de tu script sin controles visuales
year = ahora_local_sidebar.year
st.session_state.mes = ahora_local_sidebar.month
st.session_state.dia = ahora_local_sidebar.day
hora = ahora_utc_sidebar.hour

# Botón para refrescar la hora
if st.sidebar.button("🔄 Update local time"):
    st.rerun() # Esto refresca el script y vuelve a calcular la hora actual

# Construir la fecha global unificada para el uso en el resto del script
fecha_global = datetime(year, st.session_state.mes, st.session_state.dia)
date_val_global = fecha_global.strftime('%Y-%m-%d')
local_time_global = f"{int(hora):02d}:00"

# ---------------------------------------------------------
# TÍTULO PRINCIPAL Y PESTAÑAS
# ---------------------------------------------------------
st.markdown(
    """
    <style>
    @keyframes pulse-sun {
        0% { transform: scale(1); filter: drop-shadow(0 0 5px rgba(255, 215, 0, 0.4)); }
        50% { transform: scale(1.15); filter: drop-shadow(0 0 15px rgba(255, 215, 0, 0.8)); }
        100% { transform: scale(1); filter: drop-shadow(0 0 5px rgba(255, 215, 0, 0.4)); }
    }
    .sun-animated {
        display: inline-block;
        color: #FFD700;
        animation: pulse-sun 2.5s infinite ease-in-out;
    }
    </style>
    <div class='card-minimal' style='text-align: center; justify-content: center;'>
        <h1 style='display: flex; align-items: center; justify-content: center; gap: 10px;'>
            <span class='sun-animated'>☀️</span> Interactive Solar Analema
        </h1>
    </div>
    """,
    unsafe_allow_html=True,
)

tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(["Map", "Animated Analema", "Polar/Cartesian", "Advanced Features", "Cities Comparison", "Daylight Hours", "Resources/Info"])

# ---------------------------------------------------------
# TAB 1 – MAPA INTERACTIVO (GOOGLE MAPS STYLE)
# ---------------------------------------------------------
with tab1:
    # CSS para forzar el cursor estándar (flecha) en todo el mapa de Folium
    st.markdown("""
    <style>
    .folium-map, .folium-map *, .leaflet-container {
        cursor: default !important;
    }
    .leaflet-interactive {
        cursor: pointer !important;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("<div class='card-minimal'><h2>Location Selection</h2></div>", unsafe_allow_html=True)

    if "busqueda_query" not in st.session_state:
        st.session_state.busqueda_query = ""

    # Inicializar con Híbrido (Satélite con nombres) por defecto
    if "map_tile_active" not in st.session_state:
        st.session_state.map_tile_active = "Satellite"

    col_busq, col_vacio = st.columns([2, 3])

    with col_busq:
        busqueda_input = st.text_input(
            "🔍 Search City or Place:", 
            value=st.session_state.busqueda_query,
            placeholder="Ej: Madrid, Múnich, París...",
            key="input_busq_tab1_text",
            label_visibility="collapsed" # Ocultamos el label nativo para que no moleste
        )
        
        if busqueda_input and busqueda_input != st.session_state.busqueda_query:
            st.session_state.busqueda_query = busqueda_input
            lat_b, lon_b = obtener_coordenadas(busqueda_input)
            if lat_b and lon_b:
                if lat_b != st.session_state.lat or lon_b != st.session_state.lon:
                    actualizar_ubicacion(lat_b, lon_b)
                    st.session_state.zoom = 13
                    st.rerun()

    roadmap_checked = (st.session_state.map_tile_active == "Street View")
    hybrid_checked = (st.session_state.map_tile_active == "Satellite")

    # Si por defecto no hay ninguna activa válida, marcamos Híbrido
    if not (roadmap_checked or hybrid_checked):
        hybrid_checked = True

    mapa_tab1 = folium.Map(
        location=[st.session_state.lat, st.session_state.lon],
        zoom_start=st.session_state.zoom,
        tiles=None
    )

    # 1. Capa Estilo "Google Roadmap" (Calles / Street)
    folium.TileLayer(
        tiles="https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}",
        attr="Google Maps",
        name="Street View",
        control=True,
        show=roadmap_checked,
        overlay=False
    ).add_to(mapa_tab1)

    # 2. Capa Estilo "Google Hybrid" (Satélite + Nombres / Híbrido)
    folium.TileLayer(
        tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
        attr="Google Maps Hybrid",
        name="Satellite",
        control=True,
        show=hybrid_checked,
        overlay=False
    ).add_to(mapa_tab1)

    # Icono estándar de ubicación (marcador rojo clásico de Folium)
    folium.Marker(
        [st.session_state.lat, st.session_state.lon],
        popup=st.session_state.poblacion,
        icon=folium.Icon(color="red", icon="info-sign")
    ).add_to(mapa_tab1)

    from folium.plugins import MousePosition
    formatter = "function(num) {return L.Util.formatNum(num, 5);};"
    MousePosition(
        position="bottomleft",
        separator=" | ",
        prefix="Lat: ",
        lat_formatter=formatter,
        lng_formatter=formatter
    ).add_to(mapa_tab1)

    folium.LayerControl(collapsed=False).add_to(mapa_tab1)

    output_mapa = st_folium(
        mapa_tab1, 
        width=None, 
        height=900, 
        key="mapa_interactivo_tab1",
        center=[st.session_state.lat, st.session_state.lon],
        zoom=st.session_state.zoom,
        returned_objects=["last_clicked", "zoom", "center", "all_layers"]
    )

    if output_mapa:
        # Registrar cambios de zoom
        if output_mapa.get("zoom") and output_mapa["zoom"] != st.session_state.zoom:
            st.session_state.zoom = output_mapa["zoom"]

        # Capturar la capa activa actual para mantenerla seleccionada sin perder el estado
        all_layers = output_mapa.get("all_layers")
        if all_layers:
            for layer_name, layer_info in all_layers.items():
                if layer_info.get("active") is True:
                    if layer_name in ["Street", "Satellite"]:
                        if st.session_state.map_tile_active != layer_name:
                            st.session_state.map_tile_active = layer_name

        # Detectar clic en el mapa para cambiar la ubicación con el icono estándar
        if output_mapa.get("last_clicked"):
            clicked_lat = output_mapa["last_clicked"]["lat"]
            clicked_lon = output_mapa["last_clicked"]["lng"]

            if clicked_lat != st.session_state.lat or clicked_lon != st.session_state.lon:
                st.session_state.busqueda_query = ""
                actualizar_ubicacion(clicked_lat, clicked_lon)
                st.rerun()

# ---------------------------------------------------------
# TAB 2 – ANALEMA ANIMADA POR HORAS (UTC)
# ---------------------------------------------------------
with tab2:
    st.markdown("### Analema (UTC)")

    # 1. Obtener hora UTC actual
    ahora_utc = datetime.now(pytz.utc)
    dia_del_ano_actual = ahora_utc.timetuple().tm_yday
    hora_utc_actual = ahora_utc.hour 

    mostrar_todas_analemas = st.checkbox("Show All Analemas", value=False, key="chk_todas_analemas")

    # 2. Generar datos para las 24 horas
    analemas = []
    for h in range(0, 24):
        df_h = generar_analema(st.session_state.lat, st.session_state.lon, year, h).copy()
        df_h["hora"] = h
        df_h["fecha"] = pd.to_datetime(f"{year}-01-01") + pd.to_timedelta(df_h.index, unit="D")
        df_h["fecha_str"] = df_h["fecha"].dt.strftime("%d.%m.%Y")
        df_h["dia_del_ano"] = df_h.index
        analemas.append(df_h)

    df_all = pd.concat(analemas)

    # Preparar datos específicos del sol para cada hora
    df_sol_animado = df_all[df_all["dia_del_ano"] == dia_del_ano_actual - 1].copy()
    
    # 3. Crear figura base con animación (genera la curva de la hora activa)
    fig = px.line(
        df_all, x="azim", y="elev", animation_frame="hora",
        range_x=[0, 360], range_y=[-10, 90]
    )
   
    fig.layout.updatemenus[0].buttons[0].args[1]["frame"]["duration"] = 500
    fig.layout.sliders[0].active = hora_utc_actual

    # Estilo y hover unificado para la curva animada principal
    formato_hover_unificado = (
        "<b>UTC %{customdata[0]}:00</b><br>" 
        "Date: %{customdata[1]}<br>" 
        "Azimuth: %{x:.2f}°<br>" 
        "Elevation: %{y:.2f}°<extra></extra>"
    )

    # Actualizar el hover y customdata en todos los frames de la animación del slider
    for frame in fig.frames:
        h_frame = int(frame.name)
        df_h_frame = df_all[df_all["hora"] == h_frame]
        if frame.data:
            # Modificamos el primer trazo del frame (la línea animada)
            frame.data[0].hovertemplate = formato_hover_unificado
            frame.data[0].customdata = df_h_frame[["hora", "fecha_str"]].values
            
    fig.update_traces(
        line=dict(color="#1f77b4", width=2),
        hovertemplate=formato_hover_unificado,
        customdata=df_all[["hora", "fecha_str"]]
    )
    
    # -------------------------------------------------------------
    # FORZAR QUE EL INICIO SEA LA HORA ACTUAL
    # -------------------------------------------------------------
    df_actual_init = df_all[df_all["hora"] == hora_utc_actual]
    if not df_actual_init.empty:
        fig.data[0].x = df_actual_init["azim"]
        fig.data[0].y = df_actual_init["elev"]
        fig.data[0].customdata = df_actual_init[["hora", "fecha_str"]].values

    # 4. Analemas de fondo (Solo se muestran si el checkbox está activo)
    if mostrar_todas_analemas:
        for h in range(0, 24):
            df_h = df_all[df_all["hora"] == h].reset_index(drop=True)
            
            # Preparar los datos para el hover
            # Aseguramos que tengan la estructura que espera el template
            custom_data_h = np.stack((df_h["hora"], df_h["fecha_str"]), axis=-1)
            
            fig.add_trace(go.Scatter(
                x=df_h["azim"], 
                y=df_h["elev"], 
                mode="lines",
                line=dict(color="rgba(150, 150, 150, 0.3)", width=1),
                showlegend=False,
                # Forzamos el uso de nuestro template
                hovertemplate=formato_hover_unificado,
                customdata=custom_data_h
            ))

    # 5. Líneas punteadas (Días clave con etiquetas al lado de cada línea)
    dias_clave_lineas = {
        80: ("Spring Equinox", "green"), 172: ("Summer Solstice", "red"),
        266: ("Autumn Equinox", "orange"), 355: ("Winter Solstice", "blue"),
        111: ("21 Apr-Aug", "purple"), 52: ("21 Feb-Oct", "brown"),
        21: ("21 Jan-Nov", "pink"), 141: ("21 May-Jul", "olive")
    }

    # Renderizar días clave
    for dia_idx, (nombre, color) in dias_clave_lineas.items():
        df_dia = pd.DataFrame([df_all[df_all["hora"] == h].iloc[dia_idx] for h in range(0, 24) if dia_idx < 365])
        if not df_dia.empty:
            fig.add_trace(go.Scatter(
                x=df_dia["azim"], y=df_dia["elev"], mode="lines",
                line=dict(color=color, width=0.4, dash="dash"),
                name=nombre,
                hovertemplate=formato_hover_unificado,
                customdata=df_dia[["hora", "fecha_str"]],
                showlegend=False
            ))
            
            df_visible = df_dia[df_dia["elev"] > 0]
            punto_etiqueta = df_visible.iloc[-1] if not df_visible.empty else df_dia.iloc[len(df_dia)//2]
            fig.add_annotation(
                x=punto_etiqueta["azim"], y=punto_etiqueta["elev"],
                text=nombre, showarrow=False, font=dict(color=color, size=9),
                xanchor="left", xshift=5
            )

    # -------------------------------------------------------------
    # CURVA PUNTEADA MAGENTA PARA EL DÍA ACTUAL
    # -------------------------------------------------------------
    dia_actual_idx = dia_del_ano_actual - 1
    if 0 <= dia_actual_idx < 365:
        df_dia_actual = pd.DataFrame([df_all[df_all["hora"] == h].iloc[dia_actual_idx] for h in range(0, 24)])
        if not df_dia_actual.empty:
            fecha_hoy_str = df_dia_actual.iloc[0]["fecha_str"]
            fig.add_trace(go.Scatter(
                x=df_dia_actual["azim"], y=df_dia_actual["elev"], mode="lines",
                line=dict(color="magenta", width=0.4, dash="dash"),
                name=f"Today ({fecha_hoy_str})",
                hovertemplate=formato_hover_unificado,
                customdata=df_dia_actual[["hora", "fecha_str"]],
                showlegend=False
            ))
            
            # Usamos el mismo patrón que las demás líneas, pero cogiendo el primer punto visible (zona de los 45°)
            df_visible_hoy = df_dia_actual[df_dia_actual["elev"] > 0]
            punto_etiqueta_hoy = df_visible_hoy.iloc[0] if not df_visible_hoy.empty else df_dia_actual.iloc[0]
            
            fig.add_annotation(
                x=punto_etiqueta_hoy["azim"], 
                y=punto_etiqueta_hoy["elev"],
                text=f"Today ({fecha_hoy_str})", 
                showarrow=False, 
                font=dict(color="magenta", size=10, weight="bold"),
                xanchor="left", 
                xshift=5
            )
            
    # 6. Etiquetas de hora UTC (Situadas arriba del todo, en el pico de cada curva)
    for h in range(0, 24):
        df_h = df_all[df_all["hora"] == h].reset_index(drop=True)
        idx_max = df_h["elev"].idxmax()
        
        fig.add_annotation(
            x=df_h.iloc[idx_max]["azim"], 
            y=df_h.iloc[idx_max]["elev"],
            text=f"{h}:00", 
            showarrow=False, 
            yshift=10, 
            font=dict(size=9, color="rgba(80, 80, 80, 0.9)"),
            visible=True
        )

    # 7. ICONO SOL ACTUAL (Colocado al final para que quede por encima de todas las líneas y analemas de fondo)
    df_sol_animado = df_all[df_all["dia_del_ano"] == dia_actual_idx].set_index("hora")
    sol_init = df_sol_animado.loc[hora_utc_actual] if hora_utc_actual in df_sol_animado.index else df_sol_animado.iloc[0]

    # Obtenemos la hora (ya que está en el índice) y la fecha correctamente
    hora_val = sol_init.name if hasattr(sol_init, "name") else hora_utc_actual

    fig.add_trace(go.Scatter(
        x=[sol_init["azim"]], y=[sol_init["elev"]],
        mode="markers+text", 
        marker=dict(size=18, color="gold", symbol="circle", line=dict(color="orange", width=2)),
        text="☀️", textposition="middle center", 
        showlegend=False, 
        hovertemplate=formato_hover_unificado,
        customdata=[[hora_val, sol_init["fecha_str"]]]
    ))

    # Sincronizar el sol con los fotogramas de la animación del slider
    for frame in fig.frames:
        h_frame = int(frame.name)
        if h_frame in df_sol_animado.index:
            row = df_sol_animado.loc[h_frame]
            hora_row = row.name if hasattr(row, "name") else h_frame
            sun_trace = go.Scatter(
                x=[row["azim"]], y=[row["elev"]],
                mode="markers+text",
                marker=dict(size=18, color="gold", symbol="circle", line=dict(color="orange", width=2)),
                text="☀️", textposition="middle center",
                showlegend=False,
                hovertemplate=formato_hover_unificado,
                customdata=[[hora_row, row["fecha_str"]]]
            )
            frame.data = frame.data + (sun_trace,)
            
    # 8. Fondo gris para elevación negativa (< 0°)
    fig.add_shape(
        type="rect", xref="paper", yref="y",
        x0=0, x1=1, y0=-90, y1=0,
        fillcolor="rgba(128, 128, 128, 0.1)",
        line_width=0, layer="below"
    )

    # 9. Configuración de ejes con grid secundario y puntos cardinales
    fig.update_layout(
        height=650,
        plot_bgcolor="#f7f7f7",
        paper_bgcolor="#f7f7f7",
        showlegend=False,
        xaxis=dict(
            title="Azimuth (°)",
            range=[0, 360],
            tickvals=[0, 45, 90, 135, 180, 225, 270, 315, 360],
            ticktext=["0° (N)", "45° (NE)", "90° (E)", "135° (SE)", "180° (S)", "225° (SW)", "270° (W)", "315° (NW)", "360° (N)"],
            showgrid=True,
            gridwidth=1,
            gridcolor="rgba(200, 200, 200, 0.6)",
            zeroline=True,
            zerolinecolor="rgba(150, 150, 150, 0.8)"
        ),
        yaxis=dict(
            title="Elevation (°)",
            range=[-10, 90],
            tickvals=[-10, 0, 15, 30, 45, 60, 75, 90],
            showgrid=True,
            gridwidth=1,
            gridcolor="rgba(200, 200, 200, 0.6)",
            zeroline=True,
            zerolinecolor="rgba(150, 150, 150, 0.8)"
        ),
        margin=dict(l=40, r=80, t=40, b=40)
    )

    # 10. Añadir leyenda de información en la parte superior izquierda
    # Calculamos los tiempos
    fecha_hoy_str = ahora_utc.strftime("%d.%m.%Y")
    hora_local_str = datetime.now().strftime("%H:%M") # Hora local del sistema
    hora_utc_real_str = ahora_utc.strftime("%H:%M")   # Hora UTC real con minutos
    
    info_text = (
        f"<b>Date:</b> {fecha_hoy_str}<br>"
        f"<b>Lat:</b> {st.session_state.lat:.2f}°<br>"
        f"<b>Lon:</b> {st.session_state.lon:.2f}°<br>"
        f"<b>Local Time:</b> {hora_local_str}<br>"
        f"<b>UTC:</b> {hora_utc_real_str}"
    )

    fig.add_annotation(
        xref="paper", yref="paper",
        x=0.02, y=0.98,  # Posición superior izquierda
        text=info_text,
        showarrow=False,
        font=dict(size=12, color="black"),
        bgcolor="rgba(255, 255, 255, 0.7)", # Fondo semi-transparente para legibilidad
        bordercolor="gray",
        borderwidth=1,
        borderpad=4,
        align="left"
    )

    fig.update_traces(hovertemplate=formato_hover_unificado)

    # Personalizar los botones de Play y Pause de la animación
    if fig.layout.updatemenus and len(fig.layout.updatemenus[0].buttons) >= 2:
        fig.layout.updatemenus[0].buttons[0].label = "▶"  # Botón Play
        fig.layout.updatemenus[0].buttons[1].label = "⏸"  # Botón Pause

    # Cambiar el texto del prefijo del slider a "New Time"
    if fig.layout.sliders:
        fig.layout.sliders[0].currentvalue.prefix = "New Time: "

    # Alinear los botones a la izquierda y desplazar el slider para que empiece después de ellos
    if fig.layout.updatemenus:
        fig.layout.updatemenus[0].x = 0
        fig.layout.updatemenus[0].xanchor = "left"
        
    if fig.layout.sliders:
        fig.layout.sliders[0].x = 0.08  # Espacio reservado para los botones de reproducción
        fig.layout.sliders[0].xanchor = "left"
        
    # Finalmente renderizamos  
    st.plotly_chart(fig, use_container_width=True)

    ###################
    ###################
    st.markdown("### Analema: year evolution")

    # 1. Filtramos la analema específica de la hora UTC actual
    df_analema_fija = df_all[df_all["hora"] == hora_utc_actual].copy()

    # --- CALCULAR ZOOM CENTRADO ---
    x_min, x_max = df_analema_fija["azim"].min() - 5, df_analema_fija["azim"].max() + 5
    y_min, y_max = df_analema_fija["elev"].min() - 5, df_analema_fija["elev"].max() + 5

    # 2. Crear la figura base
    fig2 = go.Figure()
    # Preparamos el customdata con la fecha para cada punto de la analema
    custom_data_analema = np.stack((df_analema_fija["fecha_str"],), axis=-1)
    
    # Template de hover específico para la analema fija
    hovertemplate_analema = (
        "<b>Date: %{customdata[0]}</b><br>"
        "Azimuth: %{x:.2f}°<br>"
        "Elevation: %{y:.2f}°<extra></extra>"
    )

    # Añadimos la analema fija con el customdata correcto
    fig2.add_trace(go.Scatter(
        x=df_analema_fija["azim"], y=df_analema_fija["elev"], mode="lines",
        line=dict(color="#1f77b4", width=2), name="Analema Actual",
        hovertemplate=hovertemplate_analema,
        customdata=custom_data_analema
    ))

    # Estilo y hover unificado para la curva animada principal
    formato_hover_year = (
        "<b>UTC %{customdata[0]}:00</b><br>" 
        "Date: %{customdata[1]}<br>" 
        "Azimuth: %{x:.2f}°<br>" 
        "Elevation: %{y:.2f}°<extra></extra>"
    )

    # --- AÑADIR LÍNEAS HORIZONTALES PUNTEADAS (Fechas Clave) ---
    # Calculamos los límites de la gráfica para que la línea cubra todo el ancho
    x_range = [x_min, x_max] 
    
    dias_clave_lineas = {
        80: ("Spring Equinox", "green"), 172: ("Summer Solstice", "red"),
        266: ("Autumn Equinox", "orange"), 355: ("Winter Solstice", "blue"),
        111: ("21 Apr-Aug", "purple"), 52: ("21 Feb-Oct", "brown"),
        21: ("21 Jan-Nov", "pink"), 141: ("21 May-Jul", "olive")
    }

    for dia_idx, (nombre, color) in dias_clave_lineas.items():
        row_clave = df_analema_fija[df_analema_fija["dia_del_ano"] == dia_idx].iloc[0]
        elev_clave = row_clave["elev"]
        fecha_clave_str = row_clave["fecha_str"]
        
        # Customdata para los 2 puntos de la línea horizontal
        custom_data_line = np.array([[fecha_clave_str], [fecha_clave_str]])
        
        fig2.add_trace(go.Scatter(
            x=x_range, 
            y=[elev_clave, elev_clave],
            mode="lines",
            line=dict(color=color, width=0.4, dash="dash"),
            name=nombre,
            hovertemplate=hovertemplate_analema,
            customdata=custom_data_line,
            showlegend=False
        ))
        
        # Texto pegado al final de la línea punteada
        fig2.add_annotation(
            x=x_max, y=elev_clave,
            text=nombre, showarrow=False,
            font=dict(color=color, size=9, weight="bold"),
            xanchor="left", xshift=5
        )

    # 3. Preparar el slider y los frames
    def get_date_label(d):
        date_obj = pd.to_datetime(f"{year}-01-01") + pd.to_timedelta(d, unit="D")
        return date_obj.strftime("%d.%m")

    dias_internos = list(range(0, 365, 10)) 
    
    sliders = [{
        "active": dia_actual_idx // 10,
        "x": 0.20, "xanchor": "left",
        "y": -0.15, "yanchor": "top",
        "currentvalue": {"prefix": "Date: ", "visible": True},
        "steps": []
    }]

    frames = []
    for d in dias_internos:
        df_d = df_analema_fija[df_analema_fija["dia_del_ano"] == d]
        if df_d.empty: continue
        row = df_d.iloc[0]
        fecha_label = get_date_label(d)
        
        data_frame = list(fig2.data)
        
        # Customdata específico para el icono del sol en este frame
        custom_data_sun = np.stack((row["fecha_str"],), axis=-1)
        
        data_frame.append(
            go.Scatter(
                x=[row["azim"]], y=[row["elev"]], 
                mode="markers+text", text="☀️", 
                marker=dict(size=18, color="gold", line=dict(color="orange", width=2)),
                hovertemplate=hovertemplate_analema,
                customdata=custom_data_sun
            )
        )
        
        frames.append(go.Frame(name=str(d), data=data_frame))
        
        sliders[0]["steps"].append({
            "args": [[str(d)], {"frame": {"duration": 300, "redraw": True}, "mode": "immediate"}],
            "label": fecha_label, 
            "method": "animate"
        })

    fig2.frames = frames

    # 4. Sol inicial con su respectivo hovertemplate y customdata
    sol_inicio = df_analema_fija[df_analema_fija["dia_del_ano"] == dia_actual_idx].iloc[0]
    custom_data_sol_init = np.stack((sol_inicio["fecha_str"],), axis=-1)
    
    fig2.add_trace(go.Scatter(
        x=[sol_inicio["azim"]], y=[sol_inicio["elev"]],
        mode="markers+text", text="☀️",
        marker=dict(size=18, color="gold", line=dict(color="orange", width=2)),
        hovertemplate=hovertemplate_analema,
        customdata=custom_data_sol_init,
        name="Sol"
    ))
    
    # 5. Layout con ZOOM aplicado
    fig2.update_layout(
        sliders=sliders,
        height=650, plot_bgcolor="#f7f7f7", paper_bgcolor="#f7f7f7",
        xaxis=dict(range=[x_min, x_max], title="Azimuth (°)"),
        yaxis=dict(range=[y_min, y_max], title="Elevation (°)"),
        margin=dict(l=40, r=40, t=40, b=40),
        showlegend=False
    )

    fig2.update_layout(
        updatemenus=[{
            "type": "buttons",
            "direction": "left", # Esto agrupa los botones horizontalmente
            "showactive": False,
            "x": 0.0,    # Posición X inicial
            "xanchor": "left",
            "y": -0.25,  # Ambos botones comparten la misma altura
            "yanchor": "top",
            "buttons": [
                {
                    "label": "▶ Play", 
                    "method": "animate", 
                    "args": [None, {"frame": {"duration": 300, "redraw": True}, "fromcurrent": True}]
                },
                {
                    "label": "⏸ Pause", 
                    "method": "animate", 
                    "args": [[None], {"frame": {"duration": 0}, "mode": "immediate"}]
                }
            ]
        }]
    )

    st.plotly_chart(fig2, use_container_width=True)
    
# ---------------------------------------------------------
# TAB 3 – DIAGRAMA POLAR Y CARTESIANO CON CONTROLES TEMPORALES Y ANIMACIÓN
# ---------------------------------------------------------
with tab3:
    # 1. Controles superiores (Slider del Día del Año)
    ahora_utc_tab3 = datetime.now(pytz.utc)
    dia_actual_t3 = ahora_utc_tab3.timetuple().tm_yday
    hora_utc_actual = ahora_utc_tab3.hour
    minuto_utc_actual = ahora_utc_tab3.minute

    # Formatear UTC con minutos reales
    utc_time_inicial = f"{hora_utc_actual:02d}:{minuto_utc_actual:02d}"
    
    dia_del_ano_tab3 = st.slider("Day of the Year (Step: 10 days)", 1, 365, value=dia_actual_t3, step=10, key="tab3_dia_ano")
    fecha_sel_dt = pd.to_datetime(f"{year}-01-01") + pd.Timedelta(days=dia_del_ano_tab3 - 1)
    date_val_tab3 = fecha_sel_dt.strftime("%d.%m.%Y")
    fecha_sel_str = fecha_sel_dt.strftime("%d.%m.%Y")
    st.caption(f"📅 Selected Date: **{fecha_sel_str}** (Day {dia_del_ano_tab3}) — *Use the bottom slider to change the UTC time.*")

    fecha_tab3 = fecha_sel_dt.to_pydatetime()
    
    # Calcular hora local exacta sumando el offset total (en horas)
    offset_val = st.session_state.get('offset_sidebar', 1)
    dst_activo = es_horario_verano(fecha_tab3, st.session_state.lon)
    offset_total = offset_val + (1 if dst_activo else 0)

    st.divider()

    # 2. Generar datos consolidados para las 24 horas (Analemas por hora UTC)
    analemas_tab3 = []
    for h in range(0, 24):
        df_h = generar_analema(st.session_state.lat, st.session_state.lon, year, float(h)).copy()
        df_h["hora"] = h
        df_h["r"] = 90 - df_h["elev"]
        
        # Generar la fecha real para cada fila (asumiendo que las filas van del día 1 al 365)
        fecha_pts = [datetime(year, 1, 1) + timedelta(days=i) for i in range(len(df_h))]
        df_h["date"] = [f.strftime("%d.%m.%Y") for f in fecha_pts]
        
        df_h["hora_str"] = f"{h:02d}:00"
        analemas_tab3.append(df_h)
    
    df_all_tab3 = pd.concat(analemas_tab3)

    dias_polar_dict = {
        80: ("Spring Equinox", "green"),
        172: ("Summer Solstice", "red"),
        266: ("Autumn Equinox", "orange"),
        355: ("Winter Solstice", "blue"),
        111: ("21 April - Aug", "purple"),
        52: ("21 Feb - Oct", "brown"),
        21: ("21 Jan - Nov", "pink"),
        141: ("21 May - Jul", "olive")
    }

    lat_val_c = f"{st.session_state.lat:.3f}°"
    lon_val_c = f"{st.session_state.lon:.3f}°"
    
    # Convertir la hora y minutos a decimales para operar el desfase horario correctamente
    tiempo_utc_decimal = hora_utc_actual + (minuto_utc_actual / 60.0)
    tiempo_local_decimal = (tiempo_utc_decimal + offset_total) % 24
    
    hl_i = int(tiempo_local_decimal)
    ml_i = int(round((tiempo_local_decimal - hl_i) * 60))
    if ml_i >= 60:
        hl_i = (hl_i + 1) % 24
        ml_i = 0

    # Formatear Local Time con minutos reales
    local_time_inicial = f"{hl_i:02d}:{ml_i:02d}"

    info_text_comun = (
        f"<b>Date:</b> {fecha_hoy_str}<br>"
        f"<b>Lat:</b> {st.session_state.lat:.2f}°<br>"
        f"<b>Lon:</b> {st.session_state.lon:.2f}°<br>"
        f"<b>Local Time:</b> {local_time_inicial}<br>"
        f"<b>UTC:</b> {utc_time_inicial}"
    )
    
    # =========================================================
    # 3. DIAGRAMA SOLAR POLAR
    # =========================================================
    st.markdown("### 🌐 Polar Solar Diagram [UTC]")

    fig_polar = px.line_polar(
        df_all_tab3, r="r", theta="azim", animation_frame="hora",
        range_r=[0, 90],
        custom_data=["date", "hora_str", "elev"],  # Orden estricto para customdata[0], [1], [2]
        labels={"azim": "Az", "hora": "UTC", "date": "Date", "elev": "El", "hora_str": "UTC Time"}
    )

    df_init_polar = df_all_tab3[df_all_tab3["hora"] == hora_utc_actual]
    if not df_init_polar.empty:
        fig_polar.data[0].r = df_init_polar["r"]
        fig_polar.data[0].theta = df_init_polar["azim"]
        
        #Actualizar también el customdata inicial para que la fecha coincida
        fig_polar.data[0].customdata = list(zip(
            df_init_polar["date"],
            df_init_polar["hora"],
            df_init_polar["elev"]
        ))

    fig_polar.update_traces(
        line=dict(width=1.5, color="darkviolet"),
        hovertemplate="<b>UTC: %{customdata[1]:02d}:00</b><br>"
                              "Azimuth: %{theta:.2f}°<br>"
                              "Elevation: %{customdata[2]:.2f}°<br>"
                              "Date: %{customdata[0]}<extra></extra>"
    )

    # Líneas de referencia de la rejilla polar
    for angulo in range(0, 360, 10):
        fig_polar.add_trace(go.Scatterpolar(
            r=[0, 90], theta=[angulo, angulo], mode='lines',
            line=dict(color="rgba(200, 200, 200, 0.4)", width=0.5 if angulo % 90 != 0 else 1.2),
            showlegend=False, hoverinfo='skip'
        ))

    # Trazas estáticas de días clave (Más finas, sin leyenda y con etiquetas enlazadas a la derecha)
    for d_idx, (nombre_hito, color_hito) in dias_polar_dict.items():
        fecha_obj = datetime(year, 1, 1) + timedelta(days=d_idx-1)
        azimuths_t, radios_t, elevs_t = [], [], []
        for h in np.linspace(0, 24, 100):
            el, az = spa(fecha_obj, st.session_state.lat, st.session_state.lon, h)
            if el >= 0:
                azimuths_t.append(az)
                radios_t.append(90 - el)
                elevs_t.append(el)
        if azimuths_t:
            fig_polar.add_trace(go.Scatterpolar(
                r=radios_t, theta=azimuths_t, mode='lines',
                name=nombre_hito, line=dict(width=0.4, color=color_hito, dash="dash"),
                customdata=elevs_t,  # <-- Inyectamos los datos de elevación
                hovertemplate=f"<b>{nombre_hito}</b><br>Azimuth: %{{theta:.2f}}°<br>Elevation: %{{customdata:.2f}}°<extra></extra>",
                showlegend=False
            ))
            fig_polar.add_trace(go.Scatterpolar(
                r=[radios_t[0]], theta=[azimuths_t[0]], mode='text',
                text=[f"  {nombre_hito}"],
                textposition="middle right",
                textfont=dict(size=9, color=color_hito),
                showlegend=False, hoverinfo='skip'
            ))

    # Curva del día actual seleccionado (Más fina, sin leyenda y con etiqueta a la derecha)
    az_hoy_t, r_hoy_t, el_hoy_t = [], [], []
    for h in np.linspace(0, 24, 100):
        el, az = spa(fecha_tab3, st.session_state.lat, st.session_state.lon, h)
        if el >= 0:
            az_hoy_t.append(az)
            r_hoy_t.append(90 - el)
            el_hoy_t.append(el)  # <-- Guardamos la elevación real

    if az_hoy_t:
        fig_polar.add_trace(go.Scatterpolar(
            r=r_hoy_t, theta=az_hoy_t, mode='lines',
            name=f"Today ({date_val_tab3})",
            line=dict(width=0.4, color="magenta", dash="dash"),
            customdata=el_hoy_t,  # <-- Inyectamos los datos de elevación
            hovertemplate=f"<b>Today ({date_val_tab3})</b><br>Azimuth: %{{theta:.2f}}°<br>Elevation: %{{customdata:.2f}}°<extra></extra>",
            showlegend=False
        ))
        
        idx_oeste = np.argmin(np.abs(np.array(az_hoy_t) - 270))
        fig_polar.add_trace(go.Scatterpolar(
            r=[r_hoy_t[idx_oeste]], theta=[az_hoy_t[idx_oeste] + 6], mode='text',
            text=[f"Today ({date_val_tab3})"],
            textposition="top center",
            textfont=dict(size=9, color="magenta"),
            showlegend=False, hoverinfo='skip'
        ))

    # Etiquetas de hora UTC en los picos (Formato Scatterpolar text)
    hours_r, hours_theta, hours_text = [], [], []
    for h in range(0, 24):
        df_h = df_all_tab3[df_all_tab3["hora"] == h].reset_index(drop=True)
        if not df_h.empty:
            idx_max = df_h["elev"].idxmax()
            hours_r.append(df_h.iloc[idx_max]["r"])
            hours_theta.append(df_h.iloc[idx_max]["azim"])
            hours_text.append(f"{h}:00")

    fig_polar.add_trace(go.Scatterpolar(
        r=hours_r, theta=hours_theta, mode="text",
        text=hours_text, textposition="top center",
        textfont=dict(size=9, color="rgba(80, 80, 80, 0.9)"),
        showlegend=False, hoverinfo="skip"
    ))

    # Sol inicial estático
    el_sun_ini, az_sun_ini = spa(fecha_tab3, st.session_state.lat, st.session_state.lon, float(hora_utc_actual))
    
    size_sun_ini = 14 if el_sun_ini >= 0 else 0
    text_sun_ini = "☀️" if el_sun_ini >= 0 else ""
    
    fig_polar.add_trace(go.Scatterpolar(
        r=[90 - el_sun_ini if el_sun_ini >= 0 else 0], 
        theta=[az_sun_ini if el_sun_ini >= 0 else 0], 
        mode='markers',
        name="Sun Now",
        marker=dict(size=size_sun_ini, color="gold", symbol="circle", line=dict(color="orange", width=2 if el_sun_ini >= 0 else 0)),
        text=text_sun_ini, 
        textposition="middle center", 
        showlegend=False,
        hovertemplate=f"<b>Sun Now</b><br>UTC: {hora_utc_actual:02d}:00<br>Azimuth: %{{theta:.2f}}°<br>Elevation: {el_sun_ini:.2f}°<extra></extra>"
    ))

    # Creación de Frames para la animación del slider de horas
    frames = []
    for h in range(0, 24):
        df_h = df_all_tab3[df_all_tab3["hora"] == h]
        
        # Usamos zip para preservar los tipos originales (string, int, float)
        custom_data_h = list(zip(
            df_h["date"],
            df_h["hora"],      # Usamos el número entero para que funcione :02d
            df_h["elev"]       # Mantenemos el float para que funcione :.2f
        ))
        
        frame_traces = [
            go.Scatterpolar(
                r=df_h["r"],
                theta=df_h["azim"],
                mode="lines",
                customdata=custom_data_h,
                line=dict(width=1.5, color="darkviolet"),
                hovertemplate="<b>UTC:</b> %{customdata[1]:02d}:00<br>"
                                "Azimuth: %{theta:.2f}°<br>"
                                "Elevation: %{customdata[2]:.2f}°<br>"
                                "Date: %{customdata[0]}<extra></extra>"
            )
        ]
        
        # Añadir el sol correspondiente al frame (siempre presente para mantener la estructura de trazas)
        el_sun, az_sun = spa(fecha_tab3, st.session_state.lat, st.session_state.lon, float(h))
        
        size_sun = 14 if el_sun >= 0 else 0
        text_sun = "☀️" if el_sun >= 0 else ""
        
        frame_traces.append(go.Scatterpolar(
            r=[90 - el_sun if el_sun >= 0 else 0], 
            theta=[az_sun if el_sun >= 0 else 0], 
            mode='markers',
            marker=dict(size=size_sun, color="gold", symbol="circle", line=dict(color="orange", width=2 if el_sun >= 0 else 0)),
            text=text_sun, 
            textposition="middle center", 
            showlegend=False,
            hovertemplate=f"<b>Sun Now</b><br>UTC: {h:02d}:00<br>Azimuth: %{{theta:.2f}}°<br>Elevation: {el_sun:.2f}°<extra></extra>"
        ))
            
        frames.append(go.Frame(data=frame_traces, name=str(h)))

    fig_polar.frames = frames

    # Configuración de Slider y Botones de Reproducción
    sliders = [dict(
        active=hora_utc_actual,
        currentvalue={"prefix": "UTC Time="},
        pad={"t": 10, "b": 0},
        x=0.15, len=0.83, xanchor="left", y=-0.14, yanchor="top",
        steps=[dict(args=[[str(k)], {"frame": {"duration": 500, "redraw": True}, "mode": "immediate"}],
                    label=f"{k}:00", method="animate") for k in range(24)]
    )]

    updatemenus = [dict(
        type="buttons",
        showactive=False,
        x=0.0, y=-0.04, xanchor="left", yanchor="top", direction="left",
        buttons=[
            dict(label="▶", method="animate", args=[None, {"frame": {"duration": 500, "redraw": True}, "fromcurrent": True}]),
            dict(label="⏸", method="animate", args=[[None], {"frame": {"duration": 0, "redraw": False}, "mode": "immediate"}])
        ]
    )]

    fig_polar.update_layout(
        polar=dict(
            angularaxis=dict(
                direction="clockwise", period=360, rotation=90, dtick=10,
                tickvals=[0, 45, 90, 135, 180, 225, 270, 315],
                ticktext=["N", "NE", "E", "SE", "S", "SW", "W", "NW"]),
            radialaxis=dict(visible=True, range=[0, 90], dtick=10, angle=90, side="counterclockwise",
                tickvals=[0, 10, 20, 30, 40, 50, 60, 70, 80, 90],
                ticktext=["90°", "80°", "70°", "60°", "50°", "40°", "30°", "20°", "10°", "0°"],
                tickfont=dict(size=9, color="gray"),
            ),
            bgcolor="#f7f7f7"
        ),
        height=750, paper_bgcolor="#f7f7f7",
        sliders=sliders,
        updatemenus=updatemenus,
        annotations=[dict(
            text=info_text_comun, x=0.1, y=1.0, xref="paper", yref="paper",
            align="left", showarrow=False, xanchor="right", yanchor="top",
            bgcolor="rgba(255,255,255,0.85)", bordercolor="#ccc", borderwidth=1, borderpad=6,
            font=dict(size=11, color="#222")
        )],
        margin=dict(l=80, r=220, t=40, b=80)
    )

    st.plotly_chart(fig_polar, use_container_width=True, config={"scrollZoom": True, "displayModeBar": True})
    
    # =========================================================
    # 4. DIAGRAMA SOLAR CARTESIANO
    # =========================================================
    st.markdown("---")
    st.markdown("### 📈  Cartesian Solar Diagram [UTC]")


    # 1. Crea la figura usando Plotly Express
    fig_cartesiano = px.line(
        df_all_tab3, 
        x="azim", 
        y="elev", 
        animation_frame="hora",
        range_x=[0, 360], 
        range_y=[-10, 90],
        # 'hover_data' le dice a Plotly qué columnas extra incluir en el customdata
        hover_data={"date": True, "hora": True, "azim": ":.2f", "elev": ":.2f"}
    )

    # 3. Personaliza el hovertemplate para que se vea igual que en Tab 2
    fig_cartesiano.update_traces(
        hovertemplate="<b>UTC %{customdata[1]:02d}:00</b><br>"
                      "Date: %{customdata[0]}<br>"
                      "Azimuth: %{x:.2f}°<br>"
                      "Elevation: %{y:.2f}°<extra></extra>"
    )



    # Días clave cartesianos (Sin leyenda y con etiquetas a la derecha a distintas alturas usando las 15:00)
    for d_idx, (nombre_hito, color_hito) in dias_polar_dict.items():
        fecha_base_hito = datetime(year, 1, 1) + timedelta(days=d_idx-1)
        azimuths_t, elevaciones_t = [], []
        for h in np.linspace(0, 24, 100):
            el, az = spa(fecha_base_hito, st.session_state.lat, st.session_state.lon, h)
            if el >= 0:
                azimuths_t.append(az)
                elevaciones_t.append(el)
        if azimuths_t:
            fig_cartesiano.add_trace(go.Scatter(
                x=azimuths_t, y=elevaciones_t, mode='lines',
                name=nombre_hito, line=dict(width=0.4, color=color_hito, dash="dash"),
                showlegend=False
            ))
            
            # Calcular posición en la tarde (ej. 15:00) para que estén a la derecha y escalonadas
            el_et, az_et = spa(fecha_base_hito, st.session_state.lat, st.session_state.lon, 15.0)
            if el_et < 0: # Si a las 15:00 ya es de noche, usar el último punto válido
                az_et, el_et = azimuths_t[-1], elevaciones_t[-1]

            fig_cartesiano.add_trace(go.Scatter(
                x=[az_et], y=[el_et], mode='text',
                text=[f" {nombre_hito}"],
                textposition="middle right",
                textfont=dict(size=9, color=color_hito),
                showlegend=False, hoverinfo='skip'
            ))

    # Curva cartesiana del día actual seleccionado (Etiqueta a la derecha a su propia altura)
    az_hoy_c, el_hoy_c = [], []
    for h in np.linspace(0, 24, 100):
        el, az = spa(fecha_tab3, st.session_state.lat, st.session_state.lon, h)
        if el >= 0:
            az_hoy_c.append(az)
            el_hoy_c.append(el)

    if az_hoy_c:
        fig_cartesiano.add_trace(go.Scatter(
            x=az_hoy_c, y=el_hoy_c, mode='lines',
            name=f"({date_val_tab3})",
            line=dict(width=0.4, color="magenta", dash="dash"),
            showlegend=False
        ))
        
        # Posición de la etiqueta del día actual a las 15:00
        el_et_hoy, az_et_hoy = spa(fecha_tab3, st.session_state.lat, st.session_state.lon, 5.0)
        if el_et_hoy < 0:
            az_et_hoy, el_et_hoy = az_hoy_c[0], el_hoy_c[0]

        fig_cartesiano.add_trace(go.Scatter(
            x=[az_et_hoy], y=[el_et_hoy], mode='text',
            text=[f"Today ({date_val_tab3})"],
            textposition="middle right",
            textfont=dict(size=9, color="magenta"),
            showlegend=False, hoverinfo='skip'
        ))

    # Etiquetas de hora UTC en los picos
    cart_x, cart_y, cart_text = [], [], []
    for h in range(0, 24):
        df_h = df_all_tab3[df_all_tab3["hora"] == h].reset_index(drop=True)
        if not df_h.empty:
            idx_max = df_h["elev"].idxmax()
            cart_x.append(df_h.iloc[idx_max]["azim"])
            cart_y.append(df_h.iloc[idx_max]["elev"])
            cart_text.append(f"{h}:00")

    fig_cartesiano.add_trace(go.Scatter(
        x=cart_x, y=cart_y, mode="text",
        text=cart_text, textposition="top center",
        textfont=dict(size=9, color="rgba(80, 80, 80, 0.9)"),
        showlegend=False, hoverinfo="skip"
    ))

    # Sol inicial estático cartesiano
    if el_sun_ini >= 0:
        fig_cartesiano.add_trace(go.Scatter(
            x=[az_sun_ini], y=[el_sun_ini], mode='markers',
            name="Sun Now",
            marker=dict(size=14, color="gold", symbol="circle", line=dict(color="orange", width=2)),
            text="☀️", 
            textposition="middle center", 
            showlegend=False,
            hovertemplate=f"<b>Sun Now</b><br>UTC: {hora_utc_actual:02d}:00<br>Azimuth: %{{x:.1f}}°<br>Elevation: {el_sun_ini:.1f}°<extra></extra>"
        ))

    # Creación de Frames para la animación cartesiana del slider de horas
    frames_cart = []
    for h in range(0, 24):
        df_h = df_all_tab3[df_all_tab3["hora"] == h]
        custom_data_cart_h = list(zip(
            df_h["date"],
            df_h["hora"],
            df_h["azim"],
            df_h["elev"]
        ))
        
        frame_traces = [
            go.Scatter(
                x=df_h["azim"],
                y=df_h["elev"],
                mode="lines",
                customdata=custom_data_cart_h,
                line=dict(width=1.5, color="darkviolet"),
                hovertemplate="<b>Analemma Point</b><br>"
                              "Date: %{customdata[0]}<br>"
                              "UTC: %{customdata[1]:02d}:00<br>"
                              "Azimuth: %{customdata[2]:.2f}°<br>"
                              "Elevation: %{customdata[3]:.2f}°<extra></extra>"
            )
        ]
        
        el_sun, az_sun = spa(fecha_tab3, st.session_state.lat, st.session_state.lon, float(h))
        if el_sun >= 0:
            frame_traces.append(go.Scatter(
                x=[az_sun], y=[el_sun], mode='markers',
                marker=dict(size=14, color="gold", symbol="circle", line=dict(color="orange", width=2)),
                text="☀️", textposition="middle center", showlegend=False,
                hovertemplate=f"<b>Sun Now</b><br>UTC: {h:02d}:00<br>Azimuth: %{{x:.1f}}°<br>Elevation: {el_sun:.1f}°<extra></extra>"
            ))
            
        frames_cart.append(go.Frame(data=frame_traces, name=str(h)))

    fig_cartesiano.frames = frames_cart


    # Controles personalizados
    sliders_cart = [dict(active=hora_utc_actual, currentvalue={"prefix": "UTC Time="}, pad={"t": 10, "b": 0}, x=0.15, len=0.83, xanchor="left", y=-0.14, yanchor="top", steps=[dict(args=[[str(k)], {"frame": {"duration": 500, "redraw": True}, "mode": "immediate"}], label=f"{k}:00", method="animate") for k in range(24)])]
    updatemenus_cart = [dict(type="buttons", showactive=False, x=0.0, y=-0.14, xanchor="left", yanchor="top", direction="left", buttons=[dict(label="▶", method="animate", args=[None, {"frame": {"duration": 500, "redraw": True}, "fromcurrent": True}]), dict(label="⏸", method="animate", args=[[None], {"frame": {"duration": 0, "redraw": False}, "mode": "immediate"}])])]

    fig_cartesiano.update_layout(
        height=680, 
        paper_bgcolor="#f7f7f7", 
        plot_bgcolor="#f7f7f7",
        # Forzar expansión horizontal máxima reduciendo márgenes laterales
        margin=dict(l=50, r=90, t=40, b=80), 
        # Eje X: Puntos cardinales en lugar de solo grados numéricos
        xaxis=dict(
            title="Azimuth", 
            range=[0, 360], 
            tickvals=[0, 45, 90, 135, 180, 225, 270, 315, 360],
            ticktext=["0° (N)", "45° (NE)", "90° (E)", "135° (SE)", "180° (S)", "225° (SW)", "270° (W)", "315° (NW)", "360° (N)"],
            autorange=False
        ),
        
        # Eje Y: Rejilla principal cada 15° y rejilla secundaria (minor) cada 5°
        yaxis=dict(
            title="Elevation (°)", 
            range=[0, 90], 
            dtick=15,          # Líneas de cuadrícula principales cada 15°
            tick0=0,
            minor=dict(
                dtick=5,       # Rejilla secundaria horizontal cada 5°
                showgrid=True,
                gridcolor="rgba(0, 0, 0, 0.05)"  # Líneas secundarias muy tenues
            ),
            autorange=False
        ),
        sliders=sliders_cart,
        updatemenus=updatemenus_cart,
        annotations=[dict(
            text=info_text_comun, x=0.02, y=0.99, xref="paper", yref="paper",
            align="left", showarrow=False, xanchor="left", yanchor="top",
            bgcolor="rgba(255,255,255,0.85)", bordercolor="#ccc", borderwidth=1, borderpad=6,
            font=dict(size=11, color="#222")
        )]
    )

    st.plotly_chart(fig_cartesiano, use_container_width=True, config={"scrollZoom": True, "displayModeBar": True})


# ---------------------------------------------------------
# TAB 4 – ANIMACIÓN Y TRAYECTORIA SOLAR CON CONTROLES COMUNES
# ---------------------------------------------------------
with tab4:
    # 1. Controles superiores (Día del Año)
    ahora_utc_tab4 = datetime.now(pytz.utc)
    dia_actual_t4 = ahora_utc_tab4.timetuple().tm_yday

    dia_del_ano_tab4 = st.slider(
        "Day of the Year (Step: 10 days)",
        1,
        365,
        value=dia_actual_t4,
        step=10,
        key="tab4_dia_ano",
    )
    fecha_sel_dt_t4 = pd.to_datetime(f"{year}-01-01") + pd.Timedelta(
        days=dia_del_ano_tab4 - 1
    )
    date_val_tab4 = fecha_sel_dt_t4.strftime("%d.%m.%Y")
    fecha_sel_str_t4 = fecha_sel_dt_t4.strftime("%d.%m.%Y")
    st.caption(
        f"📅 Selected Date: **{fecha_sel_str_t4}** (Day {dia_del_ano_tab4})"
    )

    fecha_tab4 = fecha_sel_dt_t4.to_pydatetime()

    # Offset y ajuste por horario de verano (DST)
    offset_val = st.session_state.get("offset_sidebar", 1)
    dst_activo = es_horario_verano(fecha_tab4, st.session_state.lon)
    offset_total = offset_val + (1 if dst_activo else 0)

    st.divider()
    st.markdown("### Sun Position & Orientation")

    # Función auxiliar global para proyecciones geodésicas
    def calcular_punto_proyectado(lat_orig, lon_orig, azim_deg, distancia_km):
        rad_lat = math.radians(lat_orig)
        rad_lon = math.radians(lon_orig)
        rad_az = math.radians(azim_deg)
        R_earth = 6371.0

        lat_dest = math.degrees(
            math.asin(
                math.sin(rad_lat) * math.cos(distancia_km / R_earth)
                + math.cos(rad_lat)
                * math.sin(distancia_km / R_earth)
                * math.cos(rad_az)
            )
        )
        lon_dest = math.degrees(
            rad_lon
            + math.atan2(
                math.sin(rad_az)
                * math.sin(distancia_km / R_earth)
                * math.cos(rad_lat),
                math.cos(distancia_km / R_earth)
                - math.sin(rad_lat) * math.sin(math.radians(lat_dest)),
            )
        )
        return lat_dest, lon_dest

    lat = st.session_state.lat
    lon = st.session_state.lon
    poblacion = st.session_state.get("poblacion", "Ubicación")

    RADIO_TRAYECTORIA_KM = 6.0
    RADIO_CARDINALES_KM = 8.0

    # Precalcular elementos estáticos que no dependen de la hora del slider
    puntos_circulo = [
        calcular_punto_proyectado(lat, lon, ang_c, RADIO_CARDINALES_KM)
        for ang_c in np.linspace(0, 360, 100)
    ]

    lat_n, lon_n = calcular_punto_proyectado(lat, lon, 0, RADIO_CARDINALES_KM)
    lat_s, lon_s = calcular_punto_proyectado(lat, lon, 180, RADIO_CARDINALES_KM)
    lat_e, lon_e = calcular_punto_proyectado(lat, lon, 90, RADIO_CARDINALES_KM)
    lat_o, lon_o = calcular_punto_proyectado(lat, lon, 270, RADIO_CARDINALES_KM)

    card_lats = [lat_n, lat_s, lat_e, lat_o]
    card_lons = [lon_n, lon_s, lon_e, lon_o]
    card_texts = ["N", "S", "E", "W"]

    puntos_tray = []
    for h_loop in np.linspace(0, 24, 120):
        elev_h, azim_h = spa(fecha_tab4, lat, lon, float(h_loop))
        if elev_h >= 0:
            pt = calcular_punto_proyectado(lat, lon, azim_h, RADIO_TRAYECTORIA_KM)
            puntos_tray.append(pt)

    # Fragmento interactivo: el slider y todo lo que depende de él van dentro
    @st.fragment
    def render_interactive_sun_map():
        hora_utc_tab4_slider = st.slider(
            "UTC Hour",
            0,
            23,
            value=datetime.now(pytz.utc).hour,
            step=1,
            key="tab4_hora_utc_fragment",
        )

        h_sel = float(hora_utc_tab4_slider)
        elev_sol, azim_sol = spa(fecha_tab4, lat, lon, h_sel)

        # Cálculo hora local
        h_local = (h_sel + offset_total) % 24
        hl = int(h_local)
        ml = int(round((h_local - hl) * 60))
        if ml == 60:
            hl = (hl + 1) % 24
            ml = 0
        local_time_str = f"{hl:02d}:{ml:02d}:00"
        utc_time_str = f"{int(h_sel):02d}:00:00"

        # Orientación E/W
        if 0 <= azim_sol <= 90:
            az_ew = 90 - azim_sol
            ref_ew = "NE"
        elif 90 < azim_sol <= 180:
            az_ew = azim_sol - 90
            ref_ew = "SE"
        elif 180 < azim_sol <= 270:
            az_ew = 270 - azim_sol
            ref_ew = "SW"
        else:
            az_ew = azim_sol - 270
            ref_ew = "NW"

        lat_sol_p, lon_sol_p = calcular_punto_proyectado(
            lat, lon, azim_sol, RADIO_TRAYECTORIA_KM
        )
        color_sol = "orange" if elev_sol >= 0 else "gray"
        estado_sol = "Day" if elev_sol >= 0 else "Nigt"

        # Construcción de la figura Plotly Mapbox
        fig = go.Figure()

        # 1. Ubicación central
        fig.add_trace(
            go.Scattermapbox(
                lat=[lat],
                lon=[lon],
                mode="markers+text",
                marker=dict(size=12, color="red"),
                text=[poblacion],
                textposition="bottom right",
                name="Location",
                hoverinfo="text",
            )
        )

        # 2. Círculo de referencia y ejes cruzados
        fig.add_trace(
            go.Scattermapbox(
                lat=[p[0] for p in puntos_circulo],
                lon=[p[1] for p in puntos_circulo],
                mode="lines",
                line=dict(width=1, color="rgba(150, 150, 150, 1.5)"),
                hoverinfo="skip",
                name="Reference",
            )
        )

        fig.add_trace(
            go.Scattermapbox(
                lat=[lat_s, lat_n, None, lat, lat],
                lon=[lon_s, lon_n, None, lon_o, lon_e],
                mode="lines",
                line=dict(width=1, color="rgba(150, 150, 150, 1.5)"),
                hoverinfo="skip",
                name="Axis",
            )
        )

        fig.add_trace(
            go.Scattermapbox(
                lat=card_lats,
                lon=card_lons,
                mode="text",
                text=card_texts,
                textposition="middle center",
                textfont=dict(
                    size=18,
                    color="darkred",
                    family="Arial Black"
                ),
                name="Cardinales",
                hoverinfo="skip"
            )
        )

        # 3. Trayectoria solar estática
        if puntos_tray:
            fig.add_trace(
                go.Scattermapbox(
                    lat=[p[0] for p in puntos_tray],
                    lon=[p[1] for p in puntos_tray],
                    mode="lines",
                    line=dict(width=4, color="darkorange"),
                    name="Sun Trajectory",
                    hoverinfo="name",
                )
            )

        # 4. Línea de unión entre centro y sol actual
        fig.add_trace(
            go.Scattermapbox(
                lat=[lat, lat_sol_p],
                lon=[lon, lon_sol_p],
                mode="lines",
                line=dict(width=2, color="darkorange"),
                name="Línea Sol-Centro",
                hoverinfo="skip",
            )
        )

        # 5. Sol prominente
        fig.add_trace(
            go.Scattermapbox(
                lat=[lat_sol_p],
                lon=[lon_sol_p],
                mode="markers+text",
                marker=dict(size=32, color=color_sol),
                text=["☀️"],
                textposition="middle center",
                name="Sol",
                customdata=[[
                    utc_time_str,
                    local_time_str,
                    round(elev_sol, 1),
                    round(azim_sol, 1),
                    round(az_ew, 1),
                    ref_ew,
                    estado_sol,
                    date_val_tab4,
                ]],
                hovertemplate=(
                    "<b>Azimuth:</b> %{customdata[3]}°<br>"
                    "<b>Elevation:</b> %{customdata[2]}°<br>"
                    "<b>Angle E/W:</b> %{customdata[4]}°"
                    " %{customdata[5]}<extra></extra>"
                ),
            )
        )

        # Leyenda / Caja de información arriba a la izquierda
        fig.add_annotation(
            text=(
                f"<b>Date:</b> {date_val_tab4}<br>"
                f"<b>Lat:</b> {lat:.5f}<br>"
                f"<b>Lon:</b> {lon:.5f}<br>"
                f"<b>Local Time:</b> {local_time_str[:5]}<br>"
                f"<b>UTC:</b> {utc_time_str[:5]}"
            ),
            align="left",
            showarrow=False,
            xref="paper",
            yref="paper",
            x=0.02,
            y=0.98,
            bgcolor="rgba(255, 255, 255, 0.85)",
            bordercolor="#ccc",
            borderwidth=1,
            borderpad=6,
            font=dict(size=11, family="sans-serif", color="#222"),
        )

        fig.update_layout(
            mapbox=dict(
                style="carto-positron",
                center=dict(lat=lat, lon=lon),
                zoom=11,
            ),
            uirevision="slider_rerender_fix",  # <--- Esto evita que el mapa se reinicie al mover el slider
            height=800,
            margin=dict(l=0, r=0, t=0, b=0),
            showlegend=False,
        )

        st.plotly_chart(fig, use_container_width=True, key="plotly_map_tab4")

    # Ejecutar el fragmento
    render_interactive_sun_map()

    
    # ---------------------------------------------------------
    # SEGUNDO MAPA DE LA TAB 4 (Trayectoria Acumulada)
    # ---------------------------------------------------------
    st.markdown("---")
    st.markdown("### Sun Trajectory Animation - UTC")

    @st.fragment
    def render_mapa_animado_acumulado():
        hora_slider_utc = st.slider(
            "Select an UTC Time:",
            min_value=0,
            max_value=23,
            value=datetime.now(pytz.utc).hour,
            step=1,
            key="slider_utc_animacion_tab4",
        )

        if "map_center_t4" not in st.session_state:
            st.session_state["map_center_t4"] = [
                st.session_state.lat,
                st.session_state.lon,
            ]
        if "map_zoom_t4" not in st.session_state:
            st.session_state["map_zoom_t4"] = 12

        mapa_animado = folium.Map(
            location=st.session_state["map_center_t4"],
            zoom_start=st.session_state["map_zoom_t4"],
            tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            attr="Esri World Imagery",
        )

        info_box_anim = f"""
        <div style="position: absolute; top: 10px; left: 10px; z-index: 1000; background: rgba(255, 255, 255, 0.85); padding: 8px 12px; border-radius: 6px; border: 1px solid #ccc; font-family: sans-serif; font-size: 11px; line-height: 1.4; color: #222;">
            <b>Date:</b> {date_val_tab4}<br>
            <b>Lat:</b> {st.session_state.lat}<br>
            <b>Lon:</b> {st.session_state.lon}<br>
            <b>UTC:</b> {hora_slider_utc:02d}:00
        </div>
        """
        mapa_animado.get_root().html.add_child(folium.Element(info_box_anim))

        lat_rad = math.radians(st.session_state.lat)
        lon_rad = math.radians(st.session_state.lon)
        R = 6371.0
        dist_km = 6.0

        puntos_24h_completa = []
        for h in range(24):
            elev_h, azim_h = spa(
                fecha_tab4, st.session_state.lat, st.session_state.lon, float(h)
            )
            az_rad_h = math.radians(azim_h)
            lat_h = math.degrees(
                math.asin(
                    math.sin(lat_rad) * math.cos(dist_km / R)
                    + math.cos(lat_rad)
                    * math.sin(dist_km / R)
                    * math.cos(az_rad_h)
                )
            )
            lon_h = math.degrees(
                lon_rad
                + math.atan2(
                    math.sin(az_rad_h) * math.sin(dist_km / R) * math.cos(lat_rad),
                    math.cos(dist_km / R)
                    - math.sin(lat_rad) * math.sin(math.radians(lat_h)),
                )
            )
            puntos_24h_completa.append([lat_h, lon_h])

            if h > 0:
                folium.PolyLine(
                    locations=[puntos_24h_completa[h - 1], puntos_24h_completa[h]],
                    color="orange" if elev_h > 0 else "#888888",
                    weight=2,
                    dash_array="4, 4",
                ).add_to(mapa_animado)

        for h in range(hora_slider_utc + 1):
            elev_h, azim_h = spa(
                fecha_tab4, st.session_state.lat, st.session_state.lon, float(h)
            )
            az_rad_h = math.radians(azim_h)
            lat_h = math.degrees(
                math.asin(
                    math.sin(lat_rad) * math.cos(dist_km / R)
                    + math.cos(lat_rad)
                    * math.sin(dist_km / R)
                    * math.cos(az_rad_h)
                )
            )
            lon_h = math.degrees(
                lon_rad
                + math.atan2(
                    math.sin(az_rad_h) * math.sin(dist_km / R) * math.cos(lat_rad),
                    math.cos(dist_km / R)
                    - math.sin(lat_rad) * math.sin(math.radians(lat_h)),
                )
            )

            color_icono = "orange" if elev_h > 0 else "#888888"
            estado_txt = "Day (Sun visible)" if elev_h >= 0 else "Night"
            icono_emoji = "☀️" if elev_h >= 0 else "🌙"

            # Calcular DST para la fecha seleccionada y la longitud actual
            dst_activo_loop = es_horario_verano(fecha_tab4, st.session_state.lon)
            offset_val = st.session_state.get("offset_sidebar", 1)
            offset_total_loop = offset_val + (1 if dst_activo_loop else 0)
            
            h_local_loop = (h + offset_total_loop) % 24
            hl_h = int(h_local_loop)
            ml_h = int(round((h_local_loop - hl_h) * 60))
            if ml_h == 60:
                hl_h = (hl_h + 1) % 24
                ml_h = 0

            hora_local_loop_str = f"{hl_h:02d}:{ml_h:02d}:00"
            utc_loop_str = f"{h:02d}:00:00"
            utc_hm_label = f"{h:02d}:00"

            es_hora_actual = h == hora_slider_utc
            tam_icono = 32 if es_hora_actual else 22
            borde_icono = "3px solid red" if es_hora_actual else "2px solid #222"
            z_index_val = 1005 if es_hora_actual else 1000

            html_sol_anim = f"""
            <div style="position: relative; width: {tam_icono}px; height: {tam_icono}px; left: -{tam_icono / 2}px; top: -{tam_icono / 2}px; z-index: {z_index_val};">
                <div style="position: absolute; width: {tam_icono - 4}px; height: {tam_icono - 4}px; background-color: {color_icono};
                            border-radius: 50%; border: {borde_icono}; box-shadow: 0 2px 6px rgba(0,0,0,0.4);
                            display: flex; align-items: center; justify-content: center; font-size: 11px;">
                        {icono_emoji}
                    </div>
                    <div style="position: absolute; top: 50%; left: {tam_icono + 4}px; transform: translateY(-50%);
                            color: #222; font-size: 10px; white-space: nowrap; font-weight: bold; font-family: sans-serif;
                            text-shadow: 1px 1px 2px white, -1px -1px 2px white, 1px -1px 2px white, -1px 1px 2px white;">
                        {utc_hm_label}
                    </div>
                </div>
                """

            folium.Marker(
                [lat_h, lon_h],
                popup=folium.Popup(
                    f"""
                        <div style="font-size: 12px; font-family: sans-serif; line-height: 1.4;">
                            "<b>Status:</b> {estado_txt}<br>
                            "<b>Azimuth:</b> {azim_h:.1f}°<br>
                            "<b>Elevation:</b> {elev_h:.1f}°<br>
                        </div>
                        """,
                    max_width=300,
                ),
                icon=folium.DivIcon(
                    html=html_sol_anim,
                    icon_size=(tam_icono, tam_icono),
                    icon_anchor=(0, 0),
                ),
            ).add_to(mapa_animado)

        folium.Marker(
            [st.session_state.lat, st.session_state.lon],
            popup=st.session_state.get("poblacion", "Ubicación"),
            icon=folium.Icon(color="red", icon="info-sign"),
        ).add_to(mapa_animado)

        map_output = st_folium(
            mapa_animado, width="100%", height=700, key="mapa_animado_integrado_tab4"
        )

        if map_output and map_output.get("center"):
            st.session_state["map_center_t4"] = [
                map_output["center"]["lat"],
                map_output["center"]["lng"],
            ]
        if map_output and map_output.get("zoom"):
            st.session_state["map_zoom_t4"] = map_output["zoom"]

    # Ejecutar el segundo fragmento
    render_mapa_animado_acumulado()
  
    # ---------------------------------------------------------
    # TERCER MAPA DE LA TAB 4 (Esfera / Cúpula Polar 3D)
    # ---------------------------------------------------------
    st.markdown("---")
    st.markdown("### Solar Chart Polar Dome - Azimuth & Elevation Grid")

    @st.fragment
    def render_mapa_domo_polar():
        hora_slider_utc_dome = st.slider(
            "Select an UTC Time (Solar Chart Dome):",
            min_value=0,
            max_value=23,
            value=datetime.now(pytz.utc).hour,
            step=1,
            key="slider_utc_animacion_dome_tab4"
        )

        mapa_domo = folium.Map(
            location=[st.session_state.lat, st.session_state.lon],
            zoom_start=11,
            tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            attr="Esri World Imagery"
        )

        # Cálculo preciso de la hora local de la selección actual del slider incluyendo DST
        dst_actual_dome = es_horario_verano(fecha_tab4, st.session_state.lon)
        offset_val_dome = st.session_state.get("offset_sidebar", 1)
        offset_total_dome = offset_val_dome + (1 if dst_actual_dome else 0)
        
        h_local_actual_dome = (float(hora_slider_utc_dome) + offset_total_dome) % 24
        hl_d = int(h_local_actual_dome)
        ml_d = int(round((h_local_actual_dome - hl_d) * 60))
        if ml_d == 60:
            hl_d = (hl_d + 1) % 24
            ml_d = 0
            
        local_time_calculada = f"{hl_d:02d}:{ml_d:02d}:00"
        utc_time_calculada = f"{int(hora_slider_utc_dome):02d}:00:00"

        info_box_dome = f"""
        <div style="position: absolute; top: 10px; left: 10px; z-index: 1000; background: rgba(255, 255, 255, 0.85); padding: 8px 12px; border-radius: 6px; border: 1px solid #ccc; font-family: sans-serif; font-size: 11px; line-height: 1.4; color: #222;">
            <b>Date:</b> {date_val_tab4}<br>
            <b>Lat:</b> {st.session_state.lat}<br>
            <b>Lon:</b> {st.session_state.lon}<br>
            <b>UTC:</b> {hora_slider_utc_dome:02d}:00
        </div>
        """
        mapa_domo.get_root().html.add_child(folium.Element(info_box_dome))

        def calcular_punto_polar_domo(lat_orig, lon_orig, azim_deg, elev_deg, radio_max_km=15.0):
            elev_efectiva = max(0.0, elev_deg) if elev_deg >= 0 else 0.0
            distancia_km = radio_max_km * (1.0 - (elev_efectiva / 90.0))
            
            if distancia_km <= 0.001:
                return [lat_orig, lon_orig]

            rad_lat = math.radians(lat_orig)
            rad_lon = math.radians(lon_orig)
            rad_az = math.radians(azim_deg)
            R_earth = 6371.0

            lat_dest = math.degrees(
                math.asin(
                    math.sin(rad_lat) * math.cos(distancia_km / R_earth) +
                    math.cos(rad_lat) * math.sin(distancia_km / R_earth) * math.cos(rad_az)
                )
            )
            lon_dest = math.degrees(
                rad_lon + math.atan2(
                    math.sin(rad_az) * math.sin(distancia_km / R_earth) * math.cos(rad_lat),
                    math.cos(distancia_km / R_earth) - math.sin(rad_lat) * math.sin(math.radians(lat_dest))
                )
            )
            return [lat_dest, lon_dest]

        for elev_anillo in range(0, 90, 10):
            puntos_anillo = []
            for az in range(0, 361, 5):
                pt_anillo = calcular_punto_polar_domo(st.session_state.lat, st.session_state.lon, float(az), float(elev_anillo), radio_max_km=15.0)
                puntos_anillo.append(pt_anillo)
            
            if elev_anillo == 0:
                color_linea = "#111111"
                peso_linea = 2.2
                estilo_trazo = None
            elif elev_anillo in [30, 60]:
                color_linea = "rgba(255, 255, 224, 0.8)"
                peso_linea = 1.5
                estilo_trazo = "3, 3"
            else:
                color_linea = "rgba(255, 255, 224, 0.7)"
                peso_linea = 1.1
                estilo_trazo = "2, 2"

            folium.PolyLine(
                locations=puntos_anillo,
                color=color_linea,
                weight=peso_linea,
                dash_array=estilo_trazo,
                tooltip=f"Elevation {elev_anillo}°"
            ).add_to(mapa_domo)

            if elev_anillo > 0:
                pt_etiq_elev = calcular_punto_polar_domo(st.session_state.lat, st.session_state.lon, 0.0, float(elev_anillo), radio_max_km=15.0)
                html_etiq_elev = f"""
                <div style="font-size: 10px; color: #111; font-weight: bold; font-family: sans-serif; white-space: nowrap;
                            text-shadow: 1px 1px 2px white, -1px -1px 2px white, 1px -1px 2px white, -1px 1px 2px white;">
                    {elev_anillo}°
                </div>
                """
                folium.Marker(
                    pt_etiq_elev,
                    icon=folium.DivIcon(html=html_etiq_elev, icon_size=(30, 15), icon_anchor=(-4, 6))
                ).add_to(mapa_domo)

        for az_linea in range(0, 360, 30):
            puntos_radial = []
            for el in range(0, 91, 5):
                puntos_radial.append(calcular_punto_polar_domo(st.session_state.lat, st.session_state.lon, float(az_linea), float(el), radio_max_km=15.0))
            
            folium.PolyLine(
                locations=puntos_radial,
                color="rgba(255, 255, 224, 0.7)",
                weight=1.2,
                dash_array="2, 2"
            ).add_to(mapa_domo)

        puntos_cardinales = {
            "N": 0, "NE": 45, "E": 90, "SE": 135, "S": 180, "SW": 225, "W": 270, "NW": 315
        }
        for cardinal, az_card in puntos_cardinales.items():
            pt_card = calcular_punto_polar_domo(st.session_state.lat, st.session_state.lon, float(az_card), 0.0, radio_max_km=15.0)
            html_card = f"""
            <div style="font-size: 11px; color: #b71c1c; font-weight: bold; font-family: sans-serif; white-space: nowrap;
                        text-shadow: 1px 1px 2px white, -1px -1px 2px white, 1px -1px 2px white, -1px 1px 2px white;">
                {cardinal} ({az_card}°)
            </div>
            """
            folium.Marker(
                pt_card,
                icon=folium.DivIcon(html=html_card, icon_size=(60, 20), icon_anchor=(25, 10))
            ).add_to(mapa_domo)

        puntos_tray_dome = []
        for h_loop in np.linspace(0, 24, 120):
            elev_h, azim_h = spa(fecha_tab4, st.session_state.lat, st.session_state.lon, float(h_loop))
            if elev_h >= 0:
                pt_dome = calcular_punto_polar_domo(st.session_state.lat, st.session_state.lon, azim_h, elev_h, radio_max_km=15.0)
                puntos_tray_dome.append(pt_dome)

        if puntos_tray_dome:
            folium.PolyLine(
                locations=puntos_tray_dome,
                color="orange",
                weight=2.5,
                tooltip="Solar Trayectory"
            ).add_to(mapa_domo)

        for h in range(hora_slider_utc_dome + 1):
            elev_h, azim_h = spa(fecha_tab4, st.session_state.lat, st.session_state.lon, float(h))
            
            if elev_h >= 0:
                pt_h = calcular_punto_polar_domo(st.session_state.lat, st.session_state.lon, azim_h, elev_h, radio_max_km=15.0)

                color_icono = "orange" if elev_h > 0 else "#888888"
                estado_txt = "Day (Sun visible)" if elev_h >= 0 else "Night"
                icono_emoji = "☀️" if elev_h >= 0 else "🌙"

                # Cálculo de DST correcto para cada hora iterada en el bucle
                dst_loop = es_horario_verano(fecha_tab4, st.session_state.lon)
                offset_loop_base = st.session_state.get("offset_sidebar", 1)
                offset_total_loop = offset_loop_base + (1 if dst_loop else 0)

                h_local_loop = (h + offset_total_loop) % 24
                hl_h = int(h_local_loop)
                ml_h = int(round((h_local_loop - hl_h) * 60))
                if ml_h == 60:
                    hl_h = (hl_h + 1) % 24
                    ml_h = 0
                
                hora_local_loop_str = f"{hl_h:02d}:{ml_h:02d}:00"
                utc_loop_str = f"{h:02d}:00:00"
                utc_label_clean = f"{h:02d}:00"

                es_hora_actual = (h == hora_slider_utc_dome)
                tam_icono = 32 if es_hora_actual else 22
                borde_icono = "3px solid red" if es_hora_actual else "2px solid #222"
                z_index_val = 1005 if es_hora_actual else 1000

                html_dome_marker = f"""
                <div style="position: relative; width: {tam_icono}px; height: {tam_icono}px; left: -{tam_icono/2}px; top: -{tam_icono/2}px; z-index: {z_index_val};">
                    <div style="position: absolute; width: {tam_icono-4}px; height: {tam_icono-4}px; background-color: {color_icono};
                                border-radius: 50%; border: {borde_icono}; box-shadow: 0 2px 6px rgba(0,0,0,0.4);
                                display: flex; align-items: center; justify-content: center; font-size: 11px;">
                        {icono_emoji}
                    </div>
                    <div style="position: absolute; top: 50%; left: {tam_icono + 4}px; transform: translateY(-50%);
                                color: #111; font-size: 10px; white-space: nowrap; font-weight: bold; font-family: sans-serif;
                                text-shadow: 1px 1px 2px white, -1px -1px 2px white, 1px -1px 2px white, -1px 1px 2px white;">
                        {utc_label_clean}
                    </div>
                </div>
                """

                folium.Marker(
                    pt_h,
                    popup=folium.Popup(f"""
                    <div style="font-size: 12px; font-family: sans-serif; line-height: 1.4;">
                        <b>Status:</b> {estado_txt}<br>
                        <b>Azimuth:</b> {azim_h:.1f}°<br>
                        <b>Elevation:</b> {elev_h:.1f}°<br>
                    </div>
                    """, max_width=300),
                    icon=folium.DivIcon(
                        html=html_dome_marker, 
                        icon_size=(tam_icono, tam_icono), 
                        icon_anchor=(0, 0)
                    )
                ).add_to(mapa_domo)

        folium.Marker(
            [st.session_state.lat, st.session_state.lon],
            popup=st.session_state.poblacion,
            icon=folium.Icon(color="red", icon="info-sign")
        ).add_to(mapa_domo)

        st_folium(mapa_domo, width="100%", height=700, key="mapa_domo_polar_tab4", returned_objects=[])

    render_mapa_domo_polar()

# ---------------------------------------------------------
# TAB 5 – COMPARACIÓN ENTRE CIUDADES (UTC)
# ---------------------------------------------------------
with tab5:
    st.markdown("### Analemas Comparison by Cities (UTC)")
    
    # 1. Controles superiores (Entrada de ciudades y Slider del Día del Año con saltos de 10 días)
    col_input, col_dia = st.columns([2.5, 2.5])
    with col_input:
        ciudades_input = st.text_input("Enter cities separated by commas:", "Ingolstadt, Valladolid, El Cairo", key="ciudades_input_tab3")
    with col_dia:
        ahora_utc_tab5 = datetime.now(pytz.utc)
        dia_actual_t5 = ahora_utc_tab5.timetuple().tm_yday
        dia_del_ano_sel = st.slider("Day of the Year (Step: 10 days)", 1, 365, value=dia_actual_t5, step=10, key="tab5_dia_ano")
        
        # Convertir el día del año seleccionado a formato DD.MM.YYYY
        fecha_sel_dt = pd.to_datetime(f"{year}-01-01") + pd.Timedelta(days=dia_del_ano_sel - 1)
        fecha_sel_str = fecha_sel_dt.strftime("%d.%m.%Y")
        st.caption(f"📅 Selected Date: **{fecha_sel_str}** (Day {dia_del_ano_sel})")

    lista = [c.strip() for c in ciudades_input.split(",") if c.strip()]

    # 2. Generar datos para todas las ciudades y las 24 horas UTC
    analemas_tab5 = []
    nombres_con_offset = {}
    
    from timezonefinder import TimezoneFinder
    tf = TimezoneFinder()

    minuto_actual = ahora_utc_tab5.minute
    hora_actual_int = ahora_utc_tab5.hour

    for ciudad in lista:
        lat2, lon2 = obtener_coordenadas(ciudad)
        if lat2:
            tz_str = tf.timezone_at(lat=lat2, lng=lon2)
            if tz_str:
                tz = pytz.timezone(tz_str)
                dt_local = tz.localize(fecha_sel_dt.to_pydatetime())
                offset_total = int(dt_local.utcoffset().total_seconds() / 3600)
            else:
                offset_base = round(lon2 / 15.0)
                offset_total = offset_base + 1
                
            signo = "+" if offset_total >= 0 else ""
            nombre_etiqueta_leyenda = f"{ciudad} ({signo}{offset_total})"
                
            nombres_con_offset[ciudad] = {
                "curva": ciudad,
                "leyenda": nombre_etiqueta_leyenda
            }

            for h in range(0, 24):
                # Si es la hora actual, calculamos con la hora y los minutos reales exactos
                if h == hora_actual_int:
                    h_exacto = h + (minuto_actual / 60.0)
                    hora_str_val = f"{int(h):02d}:{minuto_actual:02d}"
                else:
                    h_exacto = float(h)
                    hora_str_val = f"{int(h):02d}:00"

                df_h = generar_analema(lat2, lon2, year, h_exacto).copy()
                df_h["hora"] = h
                df_h["hora_str"] = hora_str_val
                df_h["ciudad"] = ciudad
                df_h["ciudad_leyenda"] = nombre_etiqueta_leyenda
                df_h["ciudad_original"] = ciudad
                df_h["fecha"] = pd.to_datetime(f"{year}-01-01") + pd.to_timedelta(df_h.index, unit="D")
                df_h["fecha_str"] = df_h["fecha"].dt.strftime("%d.%m.%Y")
                df_h["dia_del_ano"] = df_h.index + 1
                analemas_tab5.append(df_h)
                    
    if analemas_tab5:
        df_all_t5 = pd.concat(analemas_tab5)
        lista_curvas = [nombres_con_offset[c]["curva"] for c in lista if c in nombres_con_offset]
        
        # 3. Crear figura base con animation_frame="hora" (slider de hora integrado)
        fig_tab5 = px.line(
            df_all_t5,
            x="azim",
            y="elev",
            color="ciudad",
            animation_frame="hora",
            range_x=[0, 360],
            range_y=[-10, 90],
            labels={"azim": "Azimuth (°)", "elev": "Elevation (°)", "hora": "UTC Time", "ciudad": "City"}
        )

        hora_utc_actual = ahora_utc_tab5.hour
        fig_tab5.layout.updatemenus[0].buttons[0].args[1]["frame"]["duration"] = 500
        fig_tab5.layout.sliders[0].active = hora_utc_actual

        # Reemplazar el icono de "stop" por "pause" en el botón de reproducción/pausa de Plotly
        if fig_tab5.layout.updatemenus and len(fig_tab5.layout.updatemenus) > 0:
            for btn in fig_tab5.layout.updatemenus[0].buttons:
                if "method" in btn and btn["method"] == "animate":
                    # Cambiar argumentos de pausa si existen de forma interna o forzar etiqueta visual si aplica
                    pass
            # Forzar la actualización del icono de pausa estándar de Plotly Animation Buttons
            fig_tab5.layout.updatemenus[0].pad = dict(t=0, r=0)
        
        # Corrección robusta para asegurar que los nombres en la leyenda muestren el offset y el icono de pausa en el botón
        for i, trace in enumerate(fig_tab5.data):
            if trace.name in nombres_con_offset:
                trace.name = nombres_con_offset[trace.name]["leyenda"]

        # Formato de hover unificado con nombre de la población incluido
        formato_hover_tab5 = (
            "<b>%{customdata[2]}</b><br>"
            "<b>UTC:</b> %{customdata[3]}<br>"
            "Date: %{customdata[1]}<br>"
            "Azimuth: %{x:.2f}°<br>"
            "Elevation: %{y:.2f}°<extra></extra>"
        )

        # Control para mostrar u ocultar las líneas de los arcos clave
        mostrar_arcos_clave = st.checkbox("Show Key Date Arcs (Daily Trajectories)", value=False, key="chk_arcos_tab5")

        fig_tab5.update_traces(
            line=dict(width=2),
            hovertemplate=formato_hover_tab5,
            customdata=df_all_t5[["hora", "fecha_str", "ciudad", "hora_str"]]
        )

        # Forzar la hora actual al inicio en las trazas principales asegurando el customdata completo
        df_actual_init_t5 = df_all_t5[df_all_t5["hora"] == hora_utc_actual]
        if not df_actual_init_t5.empty:
            for idx, et_ciudad in enumerate(lista_curvas):
                df_c = df_actual_init_t5[df_actual_init_t5["ciudad"] == et_ciudad]
                if not df_c.empty and idx < len(fig_tab5.data):
                    fig_tab5.data[idx].x = df_c["azim"].values
                    fig_tab5.data[idx].y = df_c["elev"].values
                    fig_tab5.data[idx].customdata = df_c[["hora", "fecha_str", "ciudad", "hora_str"]].values
                    
        # 4. Rombos para días clave (con leyenda agrupada)
        dias_clave = {
            80: ("Spring Equinox", "green"),
            172: ("Summer Solstice", "red"),
            266: ("Autumn Equinox", "orange"),
            355: ("Winter Solstice", "blue"),
            111: ("21 April - Aug", "purple"),
            52: ("21 Feb - Oct", "brown"),
            21: ("21 Jan - Nov", "pink"),
            141: ("21 May - Jul", "olive")
        }

        if mostrar_arcos_clave:
            for et_ciudad in lista_curvas:
                df_c_all = df_all_t5[df_all_t5["ciudad"] == et_ciudad]
                if not df_c_all.empty:
                    for dia_idx, (nombre, color) in dias_clave_lineas.items():
                        df_dia = df_c_all[df_c_all["dia_del_ano"] == dia_idx].sort_values("hora")
                        
                        if not df_dia.empty:
                            fig_tab5.add_trace(go.Scatter(
                                x=df_dia["azim"], 
                                y=df_dia["elev"], 
                                mode="lines",
                                line=dict(color=color, width=0.5, dash="dash"),
                                name=f"{nombre} ({et_ciudad})",
                                hovertemplate=(
                                    f"<b>{nombre} - {et_ciudad}</b><br>"
                                    "UTC: %{customdata[3]}<br>"
                                    "Date: %{customdata[1]}<br>"
                                    "Azimuth: %{x:.2f}°<br>"
                                    "Elevation: %{y:.2f}°<extra></extra>"
                                ),
                                customdata=df_dia[["hora", "fecha_str", "ciudad"]],
                                showlegend=False
                            ))
                
        for idx_c, et_ciudad in enumerate(lista_curvas):
            df_c_all = df_all_t5[df_all_t5["ciudad"] == et_ciudad]
            if not df_c_all.empty:
                df_c_hora = df_c_all[df_c_all["hora"] == hora_utc_actual].reset_index(drop=True)
                if not df_c_hora.empty:
                    for dia_idx, (nombre_hito, color_hito) in dias_clave.items():
                        if dia_idx < len(df_c_hora):
                            punto = df_c_hora.iloc[dia_idx]
                            show_legend_hito = (idx_c == 0)
                            fig_tab5.add_trace(go.Scatter(
                                x=[punto["azim"]], y=[punto["elev"]], mode="markers",
                                marker=dict(size=9, color=color_hito, line=dict(width=1, color="black"), symbol="diamond"),
                                name=nombre_hito, legendgroup="hitos", showlegend=show_legend_hito,
                                hovertemplate=f"<b>{nombre_hito} ({et_ciudad})</b><br>Date: {punto['fecha_str']}<br>Azimuth: %{{x:.2f}}°<br>Elevation: %{{y:.2f}}°<extra></extra>"
                            ))

        # 5. Añadir las flechas como una traza 'scatter' (visible en la animación)
        df_flechas = []
        for et_ciudad in lista_curvas:
            df_c_all = df_all_t5[df_all_t5["ciudad"] == et_ciudad]
            for h in range(24):
                df_c_h = df_c_all[df_c_all["hora"] == h].reset_index(drop=True)
                for d_frec in [80, 180, 280]:
                    if d_frec < len(df_c_h) and d_frec >= 5:
                        punto_ini = df_c_h.iloc[d_frec - 5]
                        punto_fin = df_c_h.iloc[d_frec]
                        df_flechas.append({
                            "azim": punto_fin["azim"], "elev": punto_fin["elev"],
                            "hora": h, "ciudad": et_ciudad, "tipo": "flecha_punta"
                        })
                        df_flechas.append({
                            "azim": punto_ini["azim"], "elev": punto_ini["elev"],
                            "hora": h, "ciudad": et_ciudad, "tipo": "flecha_base"
                        })

        # 6. Añadir el nombre de la ciudad al lado de cada analema (posicionado más arriba con shift de elevación)
        for et_ciudad in lista_curvas:
            df_c_all = df_all_t5[df_all_t5["ciudad"] == et_ciudad]
            if not df_c_all.empty:
                df_c_hora = df_c_all[df_c_all["hora"] == hora_utc_actual].reset_index(drop=True)
                if not df_c_hora.empty:
                    idx_etiqueta = 172 if 172 < len(df_c_hora) else len(df_c_hora) // 2
                    punto_etiq = df_c_hora.iloc[idx_etiqueta]
                    
                    fig_tab5.add_trace(go.Scatter(
                        x=[punto_etiq["azim"]],
                        y=[punto_etiq["elev"] + 2.5],  # Desplazado verticalmente hacia arriba
                        mode="text",
                        text=[f" {et_ciudad}"],
                        textposition="top center",
                        textfont=dict(size=12, color="darkslategray", family="sans-serif"),
                        showlegend=False,
                        hoverinfo="skip"
                    ))

        # 7. Añadir iconos de sol ☀️ para cada ciudad según el día del año seleccionado y la hora activa
        for et_ciudad in lista_curvas:
            df_c_sol = df_all_t5[(df_all_t5["ciudad"] == et_ciudad) & (df_all_t5["dia_del_ano"] == dia_del_ano_sel)]
            if not df_c_sol.empty:
                df_sol_punto = df_c_sol[df_c_sol["hora"] == hora_utc_actual]
                if not df_sol_punto.empty:
                    fig_tab5.add_trace(go.Scatter(
                        x=df_sol_punto["azim"],
                        y=df_sol_punto["elev"],
                        mode="markers+text",
                        marker=dict(size=14, color="gold", symbol="circle", line=dict(color="orange", width=2)),
                        text="☀️",
                        textposition="middle center",
                        name=f"Sol ({et_ciudad})",
                        showlegend=False,
                        hovertemplate=(
                                    f"<b>{et_ciudad}</b><br>"
                                    "<b>UTC:</b> %{customdata[3]}<br>"
                                    "Date: %{customdata[1]}<br>"
                                    "Azimuth: %{x:.2f}°<br>"
                                    "Elevation: %{y:.2f}°<extra></extra>"
                        ),
                        customdata=df_sol_punto[["hora", "fecha_str", "ciudad", "hora_str"]].values
                    ))

        # 8. Fondo gris para elevación negativa (< 0°)
        fig_tab5.add_shape(
            type="rect", xref="paper", yref="y",
            x0=0, x1=1, y0=-90, y1=0,
            fillcolor="rgba(128, 128, 128, 0.1)",
            line_width=0, layer="below"
        )

        # 9. Configuración de ejes con grid secundario y puntos cardinales en el eje X
        fig_tab5.update_layout(
            height=650,
            plot_bgcolor="#f7f7f7",
            paper_bgcolor="#f7f7f7",
            xaxis=dict(
                title="Azimuth (°)",
                range=[0, 360],
                tickvals=[0, 45, 90, 135, 180, 225, 270, 315, 360],
                ticktext=["0° (N)", "45° (NE)", "90° (E)", "135° (SE)", "180° (S)", "225° (SW)", "270° (W)", "315° (NW)", "360° (N)"],
                showgrid=True,
                gridwidth=1,
                gridcolor="rgba(200, 200, 200, 0.6)",
                zeroline=True,
                zerolinecolor="rgba(150, 150, 150, 0.8)"
            ),
            yaxis=dict(
                title="Elevation (°)",
                range=[-10, 90],
                tickvals=[-10, 0, 15, 30, 45, 60, 75, 90],
                showgrid=True,
                gridwidth=1,
                gridcolor="rgba(200, 200, 200, 0.6)",
                zeroline=True,
                zerolinecolor="rgba(150, 150, 150, 0.8)"
            ),
            margin=dict(l=40, r=80, t=40, b=40)
        )

        # Solución para problemas de renderizado de leyendas en dispositivos táctiles como iPad
        fig_tab5.update_layout(legend=dict(itemclick="toggleothers", itemdoubleclick="toggle"))

        # Alinear el botón de Play/Pause y el Slider a la misma altura manteniendo la función de animación
        fig_tab5.update_layout(
            updatemenus=[
                dict(
                    type="buttons",
                    buttons=[
                        dict(
                            label="▶",
                            method="animate",
                            args=[None, {"frame": {"duration": 500, "redraw": True}, "fromcurrent": True, "mode": "immediate"}]
                        ),
                        dict(
                            label="⏸",
                            method="animate",
                            args=[[None], {"frame": {"duration": 0, "redraw": False}, "mode": "immediate", "transition": {"duration": 0}}]
                        )
                    ],
                    direction="left",
                    pad={"r": 10, "t": 0},
                    showactive=False,
                    x=0.03,
                    xanchor="right",
                    y=-0.20,
                    yanchor="top"
                )
            ],
            sliders=[
                dict(
                    x=0.05,
                    y=-0.15,
                    xanchor="left",
                    yanchor="top",
                    pad=dict(t=0, b=0)
                )
            ]
        )

        st.plotly_chart(fig_tab5, use_container_width=True, config={"displayModeBar": True, "responsive": True})
    else:
        st.warning("Please, enter at least one valid city.")
        
# ---------------------------------------------------------
# TAB 6 – HORAS DE LUZ Y CALENDARIO (UTC / Local con DST)
# ---------------------------------------------------------
with tab6:
    st.markdown("<div class='card-minimal'><h2>Annual Sunlight Comparison</h2></div>", unsafe_allow_html=True)

    ahora_utc_tab5 = datetime.now(pytz.utc)
    
    # Calculamos las zonas dinámicamente según las coordenadas guardadas
    tz_local_1 = obtener_tz_dinamica(st.session_state.lat, st.session_state.lon)
    tz_local_2 = obtener_tz_dinamica(st.session_state.lat_comp, st.session_state.lon_comp)

    ahora_utc = datetime.now(pytz.utc) # Asegúrate de que esta variable esté definida
    ahora_local_1 = ahora_utc.astimezone(tz_local_1)
    ahora_local_2 = ahora_utc.astimezone(tz_local_2)
  
    col_info1, col_info2, col_vacia = st.columns([2, 2, 2])
    
    with col_info1:
        st.markdown(f"**📍 {st.session_state.poblacion}**")
        st.metric(label="Local Time", value=ahora_local_1.strftime('%H:%M:%S'))
        st.caption(f"UTC: {ahora_utc.strftime('%H:%M:%S')}")
        
    with col_info2:
        st.markdown(f"**⚖️ {st.session_state.poblacion_comp}**")
        st.metric(label="Local Time", value=ahora_local_2.strftime('%H:%M:%S'))
        st.caption(f"UTC: {ahora_utc.strftime('%H:%M:%S')}")
    st.markdown("---")

    col_op1, col_busq2 = st.columns([2, 3])
    with col_op1:
        mostrar_dst = st.checkbox("Include Daylight Saving Time (DST) change", value=True, key="dst_comp")
    with col_busq2:
        busqueda_comparativa = st.text_input("⚖️ Compare with another location:", placeholder="Ej: Barcelona, Roma, Tokio...", key="input_comp_tab5")
        if busqueda_comparativa:
            lat_c, lon_c = obtener_coordenadas(busqueda_comparativa)
            if lat_c and lon_c:
                if lat_c != st.session_state.lat_comp or lon_c != st.session_state.lon_comp:
                    st.session_state.lat_comp = lat_c
                    st.session_state.lon_comp = lon_c
                    st.session_state.poblacion_comp = obtener_nombre_por_coordenadas(lat_c, lon_c)
                    st.rerun()

    fechas_dt = [datetime(year, 1, 1) + pd.Timedelta(days=i) for i in range(365)]
    fechas_str = [f"{d.day:02d}.{d.month:02d}" for d in fechas_dt]

    dias, amanecer_1, atardecer_1 = calcular_curvas_solares(
        lat=st.session_state.lat, lon=st.session_state.lon, usar_dst=mostrar_dst
    )
    _, amanecer_2, atardecer_2 = calcular_curvas_solares(
        lat=st.session_state.lat_comp, lon=st.session_state.lon_comp, usar_dst=mostrar_dst
    )

    def decimal_a_hhmmss(h_decimal):
        h = int(h_decimal % 24)
        m_decimal = (h_decimal % 24 - h) * 60
        m = int(m_decimal)
        s = int(round((m_decimal - m) * 60))
        if s == 60:
            m += 1
            s = 0
        if m == 60:
            h = (h + 1) % 24
            m = 0
        return f"{h:02d}:{m:02d}:{s:02d}"

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
        
        porc_luz_max = (luz_max / 24.0) * 100
        porc_osc_max = (osc_max / 24.0) * 100
        porc_luz_min = (luz_min / 24.0) * 100
        porc_osc_min = (osc_min / 24.0) * 100
        
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

    # Precomputar los textos de hover de forma segura con bucles de Python estándar
    hover_am_1 = [f"Date: {x}<br>Sunrise: {decimal_a_hhmmss(val)}<extra></extra>" for x, val in zip(fechas_str, amanecer_1)]
    hover_at_1 = [f"Date: {x}<br>Sunset: {decimal_a_hhmmss(val)}<extra></extra>" for x, val in zip(fechas_str, atardecer_1)]
    hover_am_2 = [f"Date: {x}<br>Sunrise: {decimal_a_hhmmss(val)}<extra></extra>" for x, val in zip(fechas_str, amanecer_2)]
    hover_at_2 = [f"Date: {x}<br>Sunset: {decimal_a_hhmmss(val)}<extra></extra>" for x, val in zip(fechas_str, atardecer_2)]

    fig = go.Figure()

    # Usar fechas_dt directamente en el eje X para que Plotly reconozca la escala temporal
    fig.add_trace(go.Scatter(
        x=fechas_dt, y=amanecer_1, mode='lines', 
        name=f'Sunrise - {st.session_state.poblacion}', 
        line=dict(color='orange', width=2),
        text=hover_am_1, hovertemplate="%{text}"
    ))
    fig.add_trace(go.Scatter(
        x=fechas_dt, y=atardecer_1, mode='lines', 
        name=f'Sunset - {st.session_state.poblacion}', 
        line=dict(color='darkorange', width=2),
        text=hover_at_1, hovertemplate="%{text}"
    ))
    fig.add_trace(go.Scatter(
        x=fechas_dt, y=amanecer_2, mode='lines', 
        name=f'Sunrise - {st.session_state.poblacion_comp}', 
        line=dict(color='deepskyblue', width=2, dash='dash'),
        text=hover_am_2, hovertemplate="%{text}"
    ))
    fig.add_trace(go.Scatter(
        x=fechas_dt, y=atardecer_2, mode='lines', 
        name=f'Sunset - {st.session_state.poblacion_comp}', 
        line=dict(color='blue', width=2, dash='dash'),
        text=hover_at_2, hovertemplate="%{text}"
    ))

    # Definir fechas clave y añadirlas usando objetos datetime exactos
    dias_clave_lineas = {
        80: ("Spring Equinox", "green"), 172: ("Summer Solstice", "red"),
        266: ("Autumn Equinox", "orange"), 355: ("Winter Solstice", "blue")
    }

    for dia_idx, (label, color) in dias_clave_lineas.items():
        if 0 <= dia_idx < len(fechas_dt):
            fecha_exacta = fechas_dt[dia_idx]
            
            fig.add_vline(x=fecha_exacta, line_width=0.8, line_dash="dash", line_color=color)
            
            fig.add_annotation(
                x=fecha_exacta, y=24.5, text=label, showarrow=False,
                textangle=-90, font=dict(size=9, color=color), xanchor="left"
            )

    fig.update_layout(
        title=dict(text=f"Daylight comparison: {st.session_state.poblacion} vs {st.session_state.poblacion_comp}", font=dict(size=18)),
        xaxis_title="Date (Day.Month)",
        yaxis_title="Time of day",
        template="plotly_white",
        hovermode="x unified",
        yaxis=dict(range=[0, 26], dtick=2),
        xaxis=dict(
            type="date", 
            tickformat="%d.%m",
            nticks=12
        ),
        margin=dict(t=80)
    )

    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    col_info_A, col_info_B = st.columns(2)

    with col_info_A:
        st.markdown(f"### 📍 {st.session_state.poblacion}")
        st.markdown(f"☀️ **Longest day:** {stats_1['max_fecha']}")
        st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;   Hours of daylight: `{stats_1['max_luz']}` |   Darkness: `{stats_1['max_osc']}`")
        st.markdown(f"🌙 **Shortest day:** {stats_1['min_fecha']}")
        st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;   Hours of daylight: `{stats_1['min_luz']}` |   Darkness: `{stats_1['min_osc']}`")
        st.markdown("⏳ **Yearly totals:**")
        st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;   Day: `{stats_1['total_luz']}` |   Darkness: `{stats_1['total_osc']}`")

    with col_info_B:
        st.markdown(f"### ⚖️ {st.session_state.poblacion_comp}")
        st.markdown(f"☀️ **Longest day:** {stats_2['max_fecha']}")
        st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;   Hours of daylight: `{stats_2['max_luz']}` |   Darkness: `{stats_2['max_osc']}`")
        st.markdown(f"🌙 **Shortest day:** {stats_2['min_fecha']}")
        st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;   Hours of daylight: `{stats_2['min_luz']}` |   Darkness: `{stats_2['min_osc']}`")
        st.markdown("⏳ **Yearly totals:**")
        st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;   Day: `{stats_2['total_luz']}` |   Darkness: `{stats_2['total_osc']}`")


    ### Desktop Solar Calendar
    st.markdown("---")
    st.markdown("### 📅 Desktop Solar Calendar")

    # Control de año
    col_anio_centro, col_boton_hoy = st.columns([2, 2])
    with col_anio_centro:
        anio_sel = st.number_input("Year:", min_value=1000, max_value=2100, value=datetime.now().year, key="anio_solar_cal")
    
    # Rango: desde el 1 de diciembre del año anterior hasta el 31 de enero del año siguiente
    inicio_rango = datetime(anio_sel - 1, 12, 1)
    fin_rango = datetime(anio_sel + 1, 1, 31)
    fechas_rango = pd.date_range(start=inicio_rango, end=fin_rango)

    def obtener_datos_para_fechas(fechas, lat, lon, usar_dst):
        anios_necesarios = set(f.year for f in fechas)
        cache_curvas = {}
        
        year_original = globals().get('year', datetime.now().year)

        for a in anios_necesarios:
            globals()['year'] = a
            dias_y, am_y, at_y = calcular_curvas_solares(lat=lat, lon=lon, usar_dst=usar_dst)
            cache_curvas[a] = (am_y, at_y)

        globals()['year'] = year_original

        am_resultado = []
        at_resultado = []
        
        for f in fechas:
            y_f = f.year
            am_y, at_y = cache_curvas[y_f]
            dia_anual = (f - datetime(y_f, 1, 1)).days
            if 0 <= dia_anual < len(am_y):
                am_resultado.append(am_y[dia_anual])
                at_resultado.append(at_y[dia_anual])
            else:
                am_resultado.append(0.0)
                at_resultado.append(0.0)
                
        return am_resultado, at_resultado

    am_1_rango, at_1_rango = obtener_datos_para_fechas(fechas_rango, st.session_state.lat, st.session_state.lon, mostrar_dst)
    am_2_rango, at_2_rango = obtener_datos_para_fechas(fechas_rango, st.session_state.lat_comp, st.session_state.lon_comp, mostrar_dst)

    tabla_datos = []
    for i, fecha_iter in enumerate(fechas_rango):
        def get_day_data(am_arr, at_arr, idx):
            s_am = decimal_a_hhmmss(am_arr[idx])
            s_at = decimal_a_hhmmss(at_arr[idx])
            
            dur_luz = (at_arr[idx] - am_arr[idx]) if at_arr[idx] >= am_arr[idx] else ((24.0 - am_arr[idx]) + at_arr[idx])
            dur_osc = 24.0 - dur_luz
            
            porc_luz = (dur_luz / 24.0) * 100
            porc_osc = (dur_osc / 24.0) * 100
            
            s_luz = f"{int(dur_luz)}h {int(round((dur_luz%1)*60))}m ({porc_luz:.1f}%)"
            s_osc = f"{int(dur_osc)}h {int(round((dur_osc%1)*60))}m ({porc_osc:.1f}%)"
            
            return f"🌅 {s_am} | 🌇 {s_at} | ☀️ {s_luz} | 🌙 {s_osc}"

        tabla_datos.append({
            "Date": fecha_iter.strftime("%d.%m.%Y"),
            f"📍 {st.session_state.poblacion}": get_day_data(am_1_rango, at_1_rango, i),
            f"⚖️ {st.session_state.poblacion_comp}": get_day_data(am_2_rango, at_2_rango, i)
        })
        
    df = pd.DataFrame(tabla_datos)

    # Construir HTML interactivo con desplazamiento automático a la fecha de hoy
    import streamlit.components.v1 as components

    hoy_str = datetime.now().strftime("%d.%m.%Y")
    
    html_rows = []
    for _, row in df.iterrows():
        is_today = (row["Date"] == hoy_str)
        row_id = " id='row-today'" if is_today else ""
        row_class = " class='today-row'" if is_today else ""
        
        r_html = f"""
        <tr{row_id}{row_class}>
            <td>{row['Date']}</td>
            <td>{row[f"📍 {st.session_state.poblacion}"]}</td>
            <td>{row[f"⚖️ {st.session_state.poblacion_comp}"]}</td>
        </tr>
        """
        html_rows.append(r_html)

    full_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; margin: 0; padding: 0; }}
        .table-container {{ max-height: 480px; overflow-y: auto; border: 1px solid #e0e0e0; border-radius: 8px; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 14px; background: white; }}
        th, td {{ padding: 10px 14px; text-align: left; border-bottom: 1px solid #eee; color: #31333F; }}
        th {{ position: sticky; top: 0; background: #f8f9fa; z-index: 2; font-weight: 600; border-bottom: 2px solid #ddd; }}
        tr.today-row {{ background-color: #fff9db !important; font-weight: bold; border-left: 4px solid #fab005; }}
        tr:hover {{ background-color: #f8f9fa; }}
    </style>
    </head>
    <body>
        <div class="table-container" id="scroll-box">
            <table>
                <thead>
                    <tr>
                        <th>Date</th>
                        <th>📍 {st.session_state.poblacion}</th>
                        <th>⚖️ {st.session_state.poblacion_comp}</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(html_rows)}
                </tbody>
            </table>
        </div>
        <script>
            window.addEventListener('DOMContentLoaded', (event) => {{
                setTimeout(() => {{
                    const todayEl = document.getElementById('row-today');
                    if (todayEl) {{
                        todayEl.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                    }}
                }}, 150);
            }});
        </script>
    </body>
    </html>
    """

    components.html(full_html, height=500, scrolling=False)
    
# ---------------------------------------------------------
# TAB 7 – RESOURCES / INFO & MBSE mySISL MODEL
# ---------------------------------------------------------
with tab7:  
    # Sección "Acerca de la aplicación" siempre disponible
    st.markdown("""
    ### ℹ️ About Analema App
    * **Script created by:** dJoZeR - Ingolstadt, Agosto 2026
    * **Created with the help of:** Copilot y Gemini
    * **Built on the original idea by:** [SunEarthTools](https://www.sunearthtools.com/)
    """, unsafe_allow_html=True)

    st.markdown("---")
    
    # Checkbox para mostrar u ocultar el Modelo MBSE mySISL
    mostrar_mbse = st.checkbox("📐 Show MBSE mySISL", value=False, key="chk_mostrar_mbse")

    if mostrar_mbse:
        st.markdown("### 📐 MBSE mySISL (System Architecture)")
        st.markdown("Below is the formal representation of the application's components, functional blocks, and interfaces under the standard **MBSE mySISL**:")
        
        mbse_codigo = """SYSTEM AnalemaSolarApp {
    ACTOR User;
    
    BLOCK UI_Subsystem {
        INTERFACE main_tabs;
        INTERFACE sidebar_controls;
    }
    
    BLOCK Calculation_Engine {
        FUNCTION spa(fecha, lat, lon, hora_utc);
        FUNCTION calcular_curvas_solares(lat, lon, usar_dst);
        FUNCTION generar_analema(lat, lon, year, hora_utc);
        FUNCTION es_horario_verano(fecha, lon);
    }
    
    BLOCK External_Services {
        API open_meteo_geocoding;
        API nominatim_openstreetmap;
    }
    
    BLOCK Visualization_Engine {
        RENDER plotly_charts;
        RENDER folium_maps;
    }
    
    User --> UI_Subsystem : Configura ubicación, fecha y hora;
    UI_Subsystem --> Calculation_Engine : Envía parámetros geolocalización y temporales;
    Calculation_Engine --> External_Services : Consulta coordenadas de ciudad;
    Calculation_Engine --> Visualization_Engine : Proporciona matrices de Elevación y Azimuth;
    Visualization_Engine --> UI_Subsystem : Renderiza mapas y diagramas interactivos;
}"""
        st.code(mbse_codigo, language="text")
        st.info("This conceptual model describes the object-oriented and functional architecture of the solar analysis tool.")
