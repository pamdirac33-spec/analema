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

# Estilos CSS Profesionales y Modernos
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
            <span class='sun-animated'>☀️</span> Analema Solar Interactiva (UTC)
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

    mostrar_todas_analemas = st.checkbox("Show all Analemas - UTC", value=False, key="chk_todas_analemas")

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

    # 3. Crear figura base con animación (genera la curva de la hora activa)
    fig = px.line(
        df_all, x="azim", y="elev", animation_frame="hora",
        range_x=[0, 360], range_y=[-10, 90],
        labels={"azim": "Azimuth (°)", "elev": "Elevation (°)", "hora": "UTC Time"}
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
            fig.add_trace(go.Scatter(
                x=df_h["azim"], y=df_h["elev"], mode="lines",
                line=dict(color="rgba(150, 150, 150, 0.3)", width=1),
                showlegend=False, hoverinfo="skip"
            ))

    # Icono sol actual
    df_sol_actual = df_all[(df_all["dia_del_ano"] == dia_del_ano_actual - 1) & (df_all["hora"] == hora_utc_actual)]
    if not df_sol_actual.empty:
        fig.add_trace(go.Scatter(
            x=[df_sol_actual.iloc[0]["azim"]], y=[df_sol_actual.iloc[0]["elev"]],
            mode="markers+text", marker=dict(size=18, color="gold", symbol="circle", line=dict(color="orange", width=2)),
            text="☀️", textposition="middle center", showlegend=False, hoverinfo="skip"
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
    
    # 6. Etiquetas de hora UTC (Situadas arriba del todo, en el pico de cada curva)
    for h in range(0, 24):
        df_h = df_all[df_all["hora"] == h].reset_index(drop=True)
        idx_max = df_h["elev"].idxmax()
        
        # Etiqueta de la hora en el medio de la curva (siempre visible)
        fig.add_annotation(
            x=df_h.iloc[idx_max]["azim"], 
            y=df_h.iloc[idx_max]["elev"],
            text=f"{h}:00", 
            showarrow=False, 
            yshift=10, 
            font=dict(size=9, color="rgba(80, 80, 80, 0.9)"),
            visible=True
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
            
            df_visible_hoy = df_dia_actual[df_dia_actual["elev"] > 0]
            punto_etiqueta_hoy = df_visible_hoy.iloc[-1] if not df_visible_hoy.empty else df_dia_actual.iloc[len(df_dia_actual)//2]
            fig.add_annotation(
                x=punto_etiqueta_hoy["azim"], y=punto_etiqueta_hoy["elev"],
                text=f" Today ({fecha_hoy_str})", showarrow=False, font=dict(color="magenta", size=10, weight="bold"),
                xanchor="left", xshift=5
            )
            
    # 7. Fondo gris para elevación negativa (< 0°)
    fig.add_shape(
        type="rect", xref="paper", yref="y",
        x0=0, x1=1, y0=-90, y1=0,
        fillcolor="rgba(128, 128, 128, 0.1)",
        line_width=0, layer="below"
    )

    # 8. Configuración de ejes con grid secundario y puntos cardinales (Mismo estilo que tab3)
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
    
    st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------
# TAB 3 – DIAGRAMA POLAR Y CARTESIANO CON CONTROLES TEMPORALES Y ANIMACIÓN
# ---------------------------------------------------------
with tab3:
    # 1. Controles superiores (Slider del Día del Año)
    ahora_utc_tab3 = datetime.now(pytz.utc)
    dia_actual_t3 = ahora_utc_tab3.timetuple().tm_yday
    hora_utc_actual = ahora_utc_tab3.hour

    dia_del_ano_tab3 = st.slider("Day of the Year (Step: 10 days)", 1, 365, value=dia_actual_t3, step=10, key="tab3_dia_ano")
    fecha_sel_dt = pd.to_datetime(f"{year}-01-01") + pd.Timedelta(days=dia_del_ano_tab3 - 1)
    date_val_tab3 = fecha_sel_dt.strftime("%d.%m.%Y")
    fecha_sel_str = fecha_sel_dt.strftime("%d.%m.%Y")
    st.caption(f"📅 Selected Date: **{fecha_sel_str}** (Day {dia_del_ano_tab3}) — *Usa los controles de reproducción o el deslizador inferior para cambiar la hora UTC.*")

    fecha_tab3 = fecha_sel_dt.to_pydatetime()
    
    # Obtener el offset base y ajustar por horario de verano (DST)
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
        df_h["date"] = date_val_tab3  
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
    
    h_local_ini = (hora_utc_actual + offset_total) % 24
    hl_i = int(h_local_ini)
    ml_i = int(round((h_local_ini - hl_i) * 60))
    if ml_i == 60:
        hl_i = (hl_i + 1) % 24
        ml_i = 0
    local_time_inicial = f"{hl_i:02d}:{ml_i:02d}"
    utc_time_inicial = f"{hora_utc_actual:02d}:00"

    info_text_comun = (
        f"Date: {date_val_tab3}<br>"
        f"Lat: {lat_val_c}<br>"
        f"Lon: {lon_val_c}<br>"
        f"Local Time: {local_time_inicial}<br>"
        f"UTC: {utc_time_inicial}"
    )
    
    # =========================================================
    # 3. DIAGRAMA SOLAR POLAR
    # =========================================================
    st.markdown("### 🌐 UTC Polar Solar Diagram (Trajectories and Analemmas)")

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

    fig_polar.update_traces(
        line=dict(width=1.5, color="darkviolet"),
        hovertemplate="<b>Analemma Point</b><br>"
                      "Date: %{customdata[0]}<br>"
                      "UTC: %{customdata[1]:02d}:00<br>"
                      "Az: %{theta:.1f}°<br>"
                      "El: %{customdata[2]:.1f}°<extra></extra>"
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
        azimuths_t, radios_t = [], []
        for h in np.linspace(0, 24, 100):
            el, az = spa(fecha_obj, st.session_state.lat, st.session_state.lon, h)
            if el >= 0:
                azimuths_t.append(az)
                radios_t.append(90 - el)
        if azimuths_t:
            fig_polar.add_trace(go.Scatterpolar(
                r=radios_t, theta=azimuths_t, mode='lines',
                name=nombre_hito, line=dict(width=0.4, color=color_hito, dash="dash"),
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
    az_hoy_t, r_hoy_t = [], []
    for h in np.linspace(0, 24, 100):
        el, az = spa(fecha_tab3, st.session_state.lat, st.session_state.lon, h)
        if el >= 0:
            az_hoy_t.append(az)
            r_hoy_t.append(90 - el)

    if az_hoy_t:
        fig_polar.add_trace(go.Scatterpolar(
            r=r_hoy_t, theta=az_hoy_t, mode='lines',
            name=f" ({date_val_tab3})",
            line=dict(width=0.4, color="magenta", dash="dash"),
            showlegend=False
        ))
        fig_polar.add_trace(go.Scatterpolar(
            r=[r_hoy_t[0]], theta=[az_hoy_t[0]], mode='text',
            text=[f"  ({date_val_tab3})"],
            textposition="middle right",
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
    if el_sun_ini >= 0:
        fig_polar.add_trace(go.Scatterpolar(
            r=[90 - el_sun_ini], theta=[az_sun_ini], mode='markers',
            name="Sun Now",
            marker=dict(size=14, color="gold", symbol="circle", line=dict(color="orange", width=2)),
            text="☀️", 
            textposition="middle center", 
            showlegend=False,
            hovertemplate=f"<b>Sun Now</b><br>UTC: {hora_utc_actual:02d}:00<br>Azimuth: %{{theta:.1f}}°<br>Elevation: {el_sun_ini:.1f}°<extra></extra>"
        ))

    # Creación de Frames para la animación del slider de horas
    frames = []
    for h in range(0, 24):
        df_h = df_all_tab3[df_all_tab3["hora"] == h]
        custom_data_h = np.stack((
            df_h["date"],
            df_h["hora_str"],
            df_h["elev"]
        ), axis=-1)
        
        frame_traces = [
            go.Scatterpolar(
                r=df_h["r"],
                theta=df_h["azim"],
                mode="lines",
                customdata=custom_data_h,
                line=dict(width=1.5, color="darkviolet"),
                hovertemplate="<b>Analemma Point</b><br>"
                              "Date: %{customdata[0]}<br>"
                              "UTC: %{customdata[1]:02d}:00<br>"
                              "Az: %{theta:.1f}°<br>"
                              "El: %{customdata[2]:.1f}°<extra></extra>"
            )
        ]
        
        # Añadir el sol correspondiente al frame
        el_sun, az_sun = spa(fecha_tab3, st.session_state.lat, st.session_state.lon, float(h))
        if el_sun >= 0:
            frame_traces.append(go.Scatterpolar(
                r=[90 - el_sun], theta=[az_sun], mode='markers',
                marker=dict(size=14, color="gold", symbol="circle", line=dict(color="orange", width=2)),
                text="☀️", textposition="middle center", showlegend=False,
                hovertemplate=f"<b>Sun Now</b><br>UTC: {h:02d}:00<br>Azimuth: %{{theta:.1f}}°<br>Elevation: {el_sun:.1f}°<extra></extra>"
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
        x=0.0, y=-0.14, xanchor="left", yanchor="top", direction="left",
        buttons=[
            dict(label="▶", method="animate", args=[None, {"frame": {"duration": 500, "redraw": True}, "fromcurrent": True}]),
            dict(label="⏸", method="animate", args=[[None], {"frame": {"duration": 0, "redraw": False}, "mode": "immediate"}])
        ]
    )]

    fig_polar.update_layout(
        polar=dict(
            angularaxis=dict(direction="clockwise", period=360, rotation=90, dtick=10, tickvals=[0, 45, 90, 135, 180, 225, 270, 315], ticktext=["N", "NE", "E", "SE", "S", "SW", "W", "NW"]),
            radialaxis=dict(visible=True, range=[0, 90], dtick=10, angle=90, side="counterclockwise"),
            bgcolor="#f7f7f7"
        ),
        height=750, paper_bgcolor="#f7f7f7",
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
    st.markdown("### 📈 UTC Cartesian Solar Diagram (Elevation vs Azimuth)")

    fig_cartesiano = go.Figure()

    # Añadir trazas iniciales para la hora UTC actual (Frame por defecto)
    df_init_cart = df_all_tab3[df_all_tab3["hora"] == hora_utc_actual]
    if not df_init_cart.empty:
        custom_data_cart_init = np.stack((
            df_init_cart["date"],
            df_init_cart["hora_str"],
            df_init_cart["azim"],
            df_init_cart["elev"]
        ), axis=-1)
        
        fig_cartesiano.add_trace(go.Scatter(
            x=df_init_cart["azim"],
            y=df_init_cart["elev"],
            mode="lines",
            name="Analemma",
            showlegend=False,  # <-- Oculta la leyenda del Analemma
            customdata=custom_data_cart_init,
            line=dict(width=1.5, color="darkviolet"),
            hovertemplate="<b>Analemma Point</b><br>"
                          "Date: %{customdata[0]}<br>"
                          "UTC: %{customdata[1]}:00<br>"
                          "Az: %{customdata[2]:.1f}°<br>"
                          "El: %{customdata[3]:.1f}°<extra></extra>"
        ))

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
        el_et_hoy, az_et_hoy = spa(fecha_tab3, st.session_state.lat, st.session_state.lon, 15.0)
        if el_et_hoy < 0:
            az_et_hoy, el_et_hoy = az_hoy_c[-1], el_hoy_c[-1]

        fig_cartesiano.add_trace(go.Scatter(
            x=[az_et_hoy], y=[el_et_hoy], mode='text',
            text=[f" ({date_val_tab3})"],
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
        custom_data_cart_h = np.stack((
            df_h["date"],
            df_h["hora_str"],
            df_h["azim"],
            df_h["elev"]
        ), axis=-1)
        
        frame_traces = [
            go.Scatter(
                x=df_h["azim"],
                y=df_h["elev"],
                mode="lines",
                customdata=custom_data_cart_h,
                line=dict(width=1.5, color="darkviolet"),
                hovertemplate="<b>Analemma Point</b><br>"
                              "Date: %{customdata[0]}<br>"
                              "UTC: %{customdata[1]}:00<br>"
                              "Az: %{customdata[2]:.1f}°<br>"
                              "El: %{customdata[3]:.1f}°<extra></extra>"
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

    # Configuración de Slider y Botones de Reproducción Cartesianos
    sliders_cart = [dict(
        active=hora_utc_actual,
        currentvalue={"prefix": "UTC Time="},
        pad={"t": 10, "b": 0},
        x=0.15, len=0.83, xanchor="left", y=-0.14, yanchor="top",
        steps=[dict(args=[[str(k)], {"frame": {"duration": 500, "redraw": True}, "mode": "immediate"}],
                    label=f"{k}:00", method="animate") for k in range(24)]
    )]

    updatemenus_cart = [dict(
        type="buttons",
        showactive=False,
        x=0.0, y=-0.14, xanchor="left", yanchor="top", direction="left",
        buttons=[
            dict(label="▶", method="animate", args=[None, {"frame": {"duration": 500, "redraw": True}, "fromcurrent": True}]),
            dict(label="⏸", method="animate", args=[[None], {"frame": {"duration": 0, "redraw": False}, "mode": "immediate"}])
        ]
    )]

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
    # 1. Inicialización segura de estados para los controles superiores de la Tab 4
    if "tab4_mes" not in st.session_state:
        st.session_state.tab4_mes = meses_es[datetime.now().month - 1]
    if "tab4_dia" not in st.session_state:
        st.session_state.tab4_dia = datetime.now().day
    if "tab4_hora" not in st.session_state:
        st.session_state.tab4_hora = datetime.now(pytz.utc).hour

    # 2. Controles temporales comunes en la parte superior de la pestaña
    col_t1, col_t2, col_t3, col_t4 = st.columns([2, 2, 1, 1])
    
    with col_t1:
        mes_sel = st.selectbox("Month", meses_es, key="tab4_mes")
        mes_idx = meses_es.index(mes_sel) + 1
        
    with col_t2:
        max_dias = calendar.monthrange(year, mes_idx)[1]
        if st.session_state.tab4_dia > max_dias:
            st.session_state.tab4_dia = max_dias
        dia_sel = st.slider("Day", 1, max_dias, key="tab4_dia")
        
    with col_t3:
        hora_sel = st.number_input("Hour (UTC)", 0, 23, key="tab4_hora")
        
    with col_t4:
        st.write("###")
        if st.button("🔄 Update local time", key="btn_update_tab4"):
            st.rerun()

    st.divider()

    # Variables de tiempo unificadas para toda la Tab 4 basadas en los controles superiores
    fecha_tab4 = datetime(year, mes_idx, dia_sel)
    date_val_tab4 = fecha_tab4.strftime('%Y-%m-%d')
    hora_utc_calculada = float(hora_sel)

    # Cálculo dinámico de la hora local para la Tab 4
    h_local_tab4 = (hora_sel + offset_sidebar) % 24
    hl_tab4 = int(h_local_tab4)
    ml_tab4 = int(round((h_local_tab4 - hl_tab4) * 60))
    if ml_tab4 == 60:
        hl_tab4 = (hl_tab4 + 1) % 24
        ml_tab4 = 0
    
    local_time_calculada = f"{hl_tab4:02d}:{ml_tab4:02d}:00"
    utc_time_calculada = f"{hora_sel:02d}:00:00"

    # ---------------------------------------------------------
    # PRIMER MAPA DE LA TAB 4 (Posición del Sol y Orientación E/W)
    # ---------------------------------------------------------
    st.markdown("### Sun Position & Orientation")
    
    elev_sol, azim_sol = spa(fecha_tab4, st.session_state.lat, st.session_state.lon, hora_utc_calculada)

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

    lat_val = f"{st.session_state.lat:.3f}°"
    lon_val = f"{st.session_state.lon:.3f}°"

    info_box_html = f"""
        <div style="position: absolute; top: 10px; left: 10px; z-index: 1000; background: rgba(255, 255, 255, 0.85); padding: 8px 12px; border-radius: 6px; border: 1px solid #ccc; font-family: sans-serif; font-size: 11px; line-height: 1.4; color: #222;">
            <b>Date:</b> {date_val_tab4}<br>
            <b>Lat:</b> {lat_val}<br>
            <b>Lon:</b> {lon_val}<br>
            <b>Local Time:</b> {local_time_calculada}<br>
            <b>UTC:</b> {utc_time_calculada}
        </div>
        """
    
    mapa4 = folium.Map(
        location=[st.session_state.lat, st.session_state.lon],
        zoom_start=10,
        tiles="CartoDB positron"
    )

    mapa4.get_root().html.add_child(folium.Element(info_box_html))

    if 0 <= azim_sol <= 90:
        az_ew = 90 - azim_sol
        ref_ew = "Norte del Este"
    elif 90 < azim_sol <= 180:
        az_ew = azim_sol - 90
        ref_ew = "Sur del Este"
    elif 180 < azim_sol <= 270:
        az_ew = 270 - azim_sol
        ref_ew = "Sur del Oeste"
    else:
        az_ew = azim_sol - 270
        ref_ew = "Norte del Oeste"

    html_reticula_gigante = """
    <div style="position: relative; width: 0px; height: 0px; overflow: visible; z-index: 100;">
        <div style="position: absolute; width: 400px; height: 400px; left: -200px; top: -200px;
                    background-color: rgba(255, 255, 255, 0.08);
                    border-radius: 50%; border: 1.5px dashed rgba(150,150,150,0.5);
                    display: flex; align-items: center; justify-content: center; pointer-events: none;">
            <div style="position: absolute; width: 100%; height: 1px; background: rgba(150,150,150,0.35);"></div>
            <div style="position: absolute; width: 1px; height: 100%; background: rgba(150,150,150,0.35);"></div>
            <div style="position: absolute; width: 100%; height: 1px; background: rgba(150,150,150,0.2); transform: rotate(45deg);"></div>
            <div style="position: absolute; width: 1px; height: 100%; background: rgba(150,150,150,0.2); transform: rotate(135deg);"></div>
            <span style="position: absolute; top: 4px; left: 50%; transform: translateX(-50%); color: #d32f2f; font-weight: bold; font-family: sans-serif; font-size: 13px; background: rgba(255,255,255,0.8); padding: 0 3px; border-radius: 3px;">N</span>
            <span style="position: absolute; bottom: 4px; left: 50%; transform: translateX(-50%); color: #d32f2f; font-weight: bold; font-family: sans-serif; font-size: 13px; background: rgba(255,255,255,0.8); padding: 0 3px; border-radius: 3px;">S</span>
            <span style="position: absolute; top: 50%; right: 6px; transform: translateY(-50%); color: #d32f2f; font-weight: bold; font-family: sans-serif; font-size: 13px; background: rgba(255,255,255,0.8); padding: 0 3px; border-radius: 3px;">E</span>
            <span style="position: absolute; top: 50%; left: 6px; transform: translateY(-50%); color: #d32f2f; font-weight: bold; font-family: sans-serif; font-size: 13px; background: rgba(255,255,255,0.8); padding: 0 3px; border-radius: 3px;">W</span>
        </div>
    </div>
    """

    folium.Marker(
        [st.session_state.lat, st.session_state.lon],
        popup=st.session_state.poblacion,
        icon=folium.DivIcon(html=html_reticula_gigante, icon_size=(1, 1), icon_anchor=(0, 0))
    ).add_to(mapa4)

    def calcular_punto_proyectado(lat_orig, lon_orig, azim_deg, distancia_km):
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
                math.sin(rad_az) * math.sin(distancia_km / R_earth) * math.cos(lat_rad),
                math.cos(distancia_km / R_earth) - math.sin(rad_lat) * math.sin(math.radians(lat_dest))
            )
        )
        return [lat_dest, lon_dest]

    puntos_tray = []
    for h_loop in np.linspace(0, 24, 120):
        elev_h, azim_h = spa(fecha_tab4, st.session_state.lat, st.session_state.lon, float(h_loop))
        if elev_h >= 0:
            dist_h = 18.0
            pt = calcular_punto_proyectado(st.session_state.lat, st.session_state.lon, azim_h, dist_h)
            puntos_tray.append(pt)

    lat_sol_p, lon_sol_p = calcular_punto_proyectado(st.session_state.lat, st.session_state.lon, azim_sol, 18.0)
    
    html_sol_custom = f"""
    <div style="position: relative; width: 30px; height: 30px; background-color: rgba(255, 165, 0, 0.95);
                border-radius: 50%; border: 2px solid #222; box-shadow: 0 2px 6px rgba(0,0,0,0.4);
                display: flex; align-items: center; justify-content: center; font-size: 14px; cursor: pointer; z-index: 1000;">
        ☀️
        <div style="position: absolute; bottom: -18px; left: 50%; transform: translateX(-50%);
                    background: rgba(0,0,0,0.8); color: white; padding: 1px 6px; border-radius: 3px;
                    font-size: 10px; white-space: nowrap; font-weight: bold;">
            {azim_sol:.1f}°
        </div>
    </div>
    """

    folium.Marker(
        [lat_sol_p, lon_sol_p],
        popup=folium.Popup(f"""
        <div style="font-size: 12px; font-family: sans-serif; line-height: 1.4;">
            <b>UTC:</b> {utc_time_calculada}<br>
            <b>Az:</b> {azim_sol:.1f}°<br>
            <b>El:</b> {elev_sol:.1f}°<br>
            <b>Angle E/W:</b> {az_ew:.1f}° {ref_ew}
        </div>
        """, max_width=300),
        icon=folium.DivIcon(
            html=html_sol_custom, 
            icon_size=(30, 30), 
            icon_anchor=(15, 15)
        )
    ).add_to(mapa4)
    
    folium.PolyLine(
        locations=[[st.session_state.lat, st.session_state.lon], [lat_sol_p, lon_sol_p]],
        color="orange",
        weight=2,
        dash_array="4, 4",
        tooltip="Línea de orientación hacia el Sol"
    ).add_to(mapa4)

    if elev_sol > 0:
        sombra_m = 1 / math.tan(math.radians(elev_sol))
    else:
        sombra_m = 0
    dist_sombra = sombra_m / 1000
    if dist_sombra > 0:
        lat_sombra, lon_sombra = calcular_punto_proyectado(st.session_state.lat, st.session_state.lon, azim_sol, dist_sombra)
        folium.PolyLine(
            locations=[[st.session_state.lat, st.session_state.lon], [lat_sombra, lon_sombra]],
            color="black",
            weight=3,
            tooltip="Sombra proyectada"
        ).add_to(mapa4)

    if puntos_tray:
        folium.PolyLine(
            locations=puntos_tray,
            color="orange",
            weight=2.5,
            tooltip="Trayectoria solar del día seleccionado"
        ).add_to(mapa4)

    st_folium(mapa4, width="100%", height=700, key="mapa_avanzado_tab4", returned_objects=[])


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
            value=int(hora_sel),
            step=1,
            key="slider_utc_animacion_tab4"
        )

        mapa_animado = folium.Map(
            location=[st.session_state.lat, st.session_state.lon],
            zoom_start=10,
            tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            attr="Esri World Imagery"
        )

        info_box_anim = f"""
        <div style="position: absolute; top: 10px; left: 10px; z-index: 1000; background: rgba(255, 255, 255, 0.85); padding: 8px 12px; border-radius: 6px; border: 1px solid #ccc; font-family: sans-serif; font-size: 11px; line-height: 1.4; color: #222;">
            <b>Date:</b> {date_val_tab4}<br>
            <b>Lat:</b> {lat_val}<br>
            <b>Lon:</b> {lon_val}<br>
            <b>Local Time:</b> {local_time_calculada}<br>
            <b>UTC:</b> {utc_time_calculada}
        </div>
        """
        mapa_animado.get_root().html.add_child(folium.Element(info_box_anim))

        puntos_24h_completa = []
        for h in range(24):
            elev_h, azim_h = spa(fecha_tab4, st.session_state.lat, st.session_state.lon, float(h))
            az_rad_h = math.radians(azim_h)
            lat_h = math.degrees(math.asin(math.sin(lat_rad)*math.cos(dist_km/R) + math.cos(lat_rad)*math.sin(dist_km/R)*math.cos(az_rad_h)))
            lon_h = math.degrees(lon_rad + math.atan2(math.sin(az_rad_h)*math.sin(dist_km/R)*math.cos(lat_rad), math.cos(dist_km/R) - math.sin(lat_rad)*math.sin(math.radians(lat_h))))
            puntos_24h_completa.append([lat_h, lon_h])

            if h > 0:
                folium.PolyLine(
                    locations=[puntos_24h_completa[h-1], puntos_24h_completa[h]],
                    color="orange" if elev_h > 0 else "#888888",
                    weight=2,
                    dash_array="4, 4"
                ).add_to(mapa_animado)

        for h in range(hora_slider_utc + 1):
            elev_h, azim_h = spa(fecha_tab4, st.session_state.lat, st.session_state.lon, float(h))
            az_rad_h = math.radians(azim_h)
            lat_h = math.degrees(math.asin(math.sin(lat_rad)*math.cos(dist_km/R) + math.cos(lat_rad)*math.sin(dist_km/R)*math.cos(az_rad_h)))
            lon_h = math.degrees(lon_rad + math.atan2(math.sin(az_rad_h)*math.sin(dist_km/R)*math.cos(lat_rad), math.cos(dist_km/R) - math.sin(lat_rad)*math.sin(math.radians(lat_h))))

            color_icono = "orange" if elev_h > 0 else "#888888"
            estado_txt = "Day (Sun visible)" if elev_h >= 0 else "Night"
            icono_emoji = "☀️" if elev_h >= 0 else "🌙"

            h_local_loop = (h + offset_sidebar) % 24
            hl_h = int(h_local_loop)
            ml_h = int(round((h_local_loop - hl_h) * 60))
            if ml_h == 60:
                hl_h = (hl_h + 1) % 24
                ml_h = 0
            
            hora_local_loop_str = f"{hl_h:02d}:{ml_h:02d}:00"
            utc_loop_str = f"{h:02d}:00:00"
            utc_hm_label = f"{h:02d}:00"

            es_hora_actual = (h == hora_slider_utc)
            tam_icono = 32 if es_hora_actual else 22
            borde_icono = "3px solid red" if es_hora_actual else "2px solid #222"
            z_index_val = 1005 if es_hora_actual else 1000

            html_sol_anim = f"""
            <div style="position: relative; width: {tam_icono}px; height: {tam_icono}px; left: -{tam_icono/2}px; top: -{tam_icono/2}px; z-index: {z_index_val};">
                <div style="position: absolute; width: {tam_icono-4}px; height: {tam_icono-4}px; background-color: {color_icono};
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
                popup=folium.Popup(f"""
                <div style="font-size: 12px; font-family: sans-serif; line-height: 1.4;">
                    <b>UTC:</b> {utc_loop_str}<br>
                    <b>Local:</b> {hora_local_loop_str}<br>
                    <b>Az:</b> {azim_h:.1f}°<br>
                    <b>El:</b> {elev_h:.1f}°<br>
                    <b>Day status:</b> {estado_txt}<br>
                </div>
                """, max_width=300),
                icon=folium.DivIcon(
                    html=html_sol_anim, 
                    icon_size=(tam_icono, tam_icono), 
                    icon_anchor=(0, 0)
                )
            ).add_to(mapa_animado)

        folium.Marker(
            [st.session_state.lat, st.session_state.lon],
            popup=st.session_state.poblacion,
            icon=folium.Icon(color="red", icon="info-sign")
        ).add_to(mapa_animado)

        st_folium(mapa_animado, width="100%", height=700, key="mapa_animado_integrado_tab4", returned_objects=[])

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
            value=int(hora_sel),
            step=1,
            key="slider_utc_animacion_dome_tab4"
        )

        mapa_domo = folium.Map(
            location=[st.session_state.lat, st.session_state.lon],
            zoom_start=11,
            tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            attr="Esri World Imagery"
        )

        info_box_dome = f"""
        <div style="position: absolute; top: 10px; left: 10px; z-index: 1000; background: rgba(255, 255, 255, 0.85); padding: 8px 12px; border-radius: 6px; border: 1px solid #ccc; font-family: sans-serif; font-size: 11px; line-height: 1.4; color: #222;">
            <b>Date:</b> {date_val_tab4}<br>
            <b>Lat:</b> {lat_val}<br>
            <b>Lon:</b> {lon_val}<br>
            <b>Local Time:</b> {local_time_calculada}<br>
            <b>UTC:</b> {utc_time_calculada}
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
                    math.sin(rad_az) * math.sin(distancia_km / R_earth) * math.cos(lat_rad),
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
                tooltip="Trayectoria solar en domo polar"
            ).add_to(mapa_domo)

        for h in range(hora_slider_utc_dome + 1):
            elev_h, azim_h = spa(fecha_tab4, st.session_state.lat, st.session_state.lon, float(h))
            
            if elev_h >= 0:
                pt_h = calcular_punto_polar_domo(st.session_state.lat, st.session_state.lon, azim_h, elev_h, radio_max_km=15.0)

                color_icono = "orange" if elev_h > 0 else "#888888"
                estado_txt = "Day (Sun visible)" if elev_h >= 0 else "Night"
                icono_emoji = "☀️" if elev_h >= 0 else "🌙"

                h_local_loop = (h + offset_sidebar) % 24
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
                        <b>UTC:</b> {utc_loop_str}<br>
                        <b>Local:</b> {hora_local_loop_str}<br>
                        <b>Azimuth:</b> {azim_h:.1f}°<br>
                        <b>Elevation:</b> {elev_h:.1f}°<br>
                        <b>Day status:</b> {estado_txt}<br>
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
    for ciudad in lista:
        lat2, lon2 = obtener_coordenadas(ciudad)
        if lat2:
            for h in range(0, 24):
                df_h = generar_analema(lat2, lon2, year, float(h)).copy()
                df_h["hora"] = h
                df_h["ciudad"] = ciudad
                df_h["fecha"] = pd.to_datetime(f"{year}-01-01") + pd.to_timedelta(df_h.index, unit="D")
                df_h["fecha_str"] = df_h["fecha"].dt.strftime("%d.%m.%Y")
                df_h["dia_del_ano"] = df_h.index + 1
                analemas_tab5.append(df_h)

    if analemas_tab5:
        df_all_t5 = pd.concat(analemas_tab5)
        
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

        # Formato de hover unificado con nombre de la población incluido
        formato_hover_tab5 = (
            "<b>%{customdata[2]} - ☀️ UTC %{customdata[0]}:00</b><br>"
            "Date: %{customdata[1]}<br>"
            "Azimuth: %{x:.2f}°<br>"
            "Elevation: %{y:.2f}°<extra></extra>"
        )

        # Control para mostrar u ocultar las líneas de los arcos clave
        mostrar_arcos_clave = st.checkbox("Show Key Date Arcs (Daily Trajectories)", value=False, key="chk_arcos_tab5")

        fig_tab5.update_traces(
            line=dict(width=2),
            hovertemplate=formato_hover_tab5,
            customdata=df_all_t5[["hora", "fecha_str", "ciudad"]]
        )

        # Forzar la hora actual al inicio en las trazas principales
        df_actual_init_t5 = df_all_t5[df_all_t5["hora"] == hora_utc_actual]
        if not df_actual_init_t5.empty:
            for idx, ciudad in enumerate(lista):
                df_c = df_actual_init_t5[df_actual_init_t5["ciudad"] == ciudad]
                if not df_c.empty and idx < len(fig_tab5.data):
                    fig_tab5.data[idx].x = df_c["azim"].values
                    fig_tab5.data[idx].y = df_c["elev"].values
                    fig_tab5.data[idx].customdata = df_c[["hora", "fecha_str", "ciudad"]].values

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
            for ciudad in lista:
                df_c_all = df_all_t5[df_all_t5["ciudad"] == ciudad]
                if not df_c_all.empty:
                    for dia_idx, (nombre, color) in dias_clave_lineas.items():
                        # Filtramos los datos para ese día del año específico y los ordenamos por hora (0 a 23)
                        df_dia = df_c_all[df_c_all["dia_del_ano"] == dia_idx].sort_values("hora")
                        
                        if not df_dia.empty:
                            fig_tab5.add_trace(go.Scatter(
                                x=df_dia["azim"], 
                                y=df_dia["elev"], 
                                mode="lines",
                                line=dict(color=color, width=0.5, dash="dash"), # Línea fina de grosor 0.5
                                name=f"{nombre} ({ciudad})",
                                hovertemplate=(
                                    f"<b>{nombre} - {ciudad}</b><br>"
                                    "UTC Time: %{customdata[0]}:00<br>"
                                    "Date: %{customdata[1]}<br>"
                                    "Azimuth: %{x:.2f}°<br>"
                                    "Elevation: %{y:.2f}°<extra></extra>"
                                ),
                                customdata=df_dia[["hora", "fecha_str", "ciudad"]],
                                showlegend=False
                            ))
                
        for idx_c, ciudad in enumerate(lista):
            df_c_all = df_all_t5[df_all_t5["ciudad"] == ciudad]
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
                                hovertemplate=f"<b>{nombre_hito} ({ciudad})</b><br>Date: {punto['fecha_str']}<br>Azimuth: %{{x:.2f}}°<br>Elevation: %{{y:.2f}}°<extra></extra>"
                            ))

        # 5. Añadir las flechas como una traza 'scatter' (visible en la animación)
        # Creamos un dataframe que contenga las coordenadas de inicio y fin de las flechas para cada hora
        df_flechas = []
        for ciudad in lista:
            df_c_all = df_all_t5[df_all_t5["ciudad"] == ciudad]
            for h in range(24):
                df_c_h = df_c_all[df_c_all["hora"] == h].reset_index(drop=True)
                for d_frec in [80, 180, 280]:
                    if d_frec < len(df_c_h) and d_frec >= 5:
                        # Creamos puntos intermedios para dibujar la flecha
                        punto_ini = df_c_h.iloc[d_frec - 5]
                        punto_fin = df_c_h.iloc[d_frec]
                        df_flechas.append({
                            "azim": punto_fin["azim"], "elev": punto_fin["elev"],
                            "hora": h, "ciudad": ciudad, "tipo": "flecha_punta"
                        })
                        df_flechas.append({
                            "azim": punto_ini["azim"], "elev": punto_ini["elev"],
                            "hora": h, "ciudad": ciudad, "tipo": "flecha_base"
                        })

        # 6. Añadir el nombre de la ciudad al lado de cada analema (Corregido color a 'darkslategray')
        for ciudad in lista:
            df_c_all = df_all_t5[df_all_t5["ciudad"] == ciudad]
            if not df_c_all.empty:
                df_c_hora = df_c_all[df_c_all["hora"] == hora_utc_actual].reset_index(drop=True)
                if not df_c_hora.empty:
                    idx_etiqueta = 172 if 172 < len(df_c_hora) else len(df_c_hora) // 2
                    punto_etiq = df_c_hora.iloc[idx_etiqueta]
                    
                    fig_tab5.add_trace(go.Scatter(
                        x=[punto_etiq["azim"]],
                        y=[punto_etiq["elev"]],
                        mode="text",
                        text=[f"  {ciudad}"],
                        textposition="top right",
                        textfont=dict(size=12, color="darkslategray", family="sans-serif"),
                        showlegend=False,
                        hoverinfo="skip"
                    ))

        # 7. Añadir iconos de sol ☀️ para cada ciudad según el día del año seleccionado y la hora activa
        for ciudad in lista:
            df_c_sol = df_all_t5[(df_all_t5["ciudad"] == ciudad) & (df_all_t5["dia_del_ano"] == dia_del_ano_sel)]
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
                        name=f"Sol ({ciudad})",
                        showlegend=False,
                        hovertemplate=f"<b>{ciudad} - Sol ({fecha_sel_str})</b><br>Date: {fecha_sel_str}<br>Azimuth: %{{x:.2f}}°<br>Elevation: %{{y:.2f}}°<extra></extra>"
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

        st.plotly_chart(fig_tab5, use_container_width=True)
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
        st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;• Hours of daylight: `{stats_1['max_luz']}` | Darkness: `{stats_1['max_osc']}`")
        st.markdown(f"🌙 **Shortest day:** {stats_1['min_fecha']}")
        st.markdown("⏳ **Yearly totals:**")
        st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;• Day: `{stats_1['total_luz']}` | Darkness: `{stats_1['total_osc']}`")

    with col_info_B:
        st.markdown(f"### ⚖️ {st.session_state.poblacion_comp}")
        st.markdown(f"☀️ **Longest day:** {stats_2['max_fecha']}")
        st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;• Hours of daylight: `{stats_2['max_luz']}` | Darkness: `{stats_2['max_osc']}`")
        st.markdown(f"🌙 **Shortest day:** {stats_2['min_fecha']}")
        st.markdown("⏳ **Yearly totals:**")
        st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;• Day: `{stats_2['total_luz']}` | Darkness: `{stats_2['total_osc']}`")


    ### Desktop Solar Calendar
    st.markdown("---")
    st.markdown("### 📅 Desktop Solar Calendar")

    # Controles para seleccionar Fecha (Mes y Año)
    col_mes, col_anio = st.columns([3, 1])
    with col_mes:
        mes_map = {1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun", 
                   7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"}
        mes_sel_nombre = st.select_slider("Select Month:", options=list(mes_map.values()), value=mes_map[datetime.now().month])
        mes_idx = [k for k, v in mes_map.items() if v == mes_sel_nombre][0]
    
    with col_anio:
        anio_sel = st.number_input("Year:", min_value=2000, max_value=2100, value=datetime.now().year)

    # Calcular los datos del mes seleccionado
    # Ajustamos el rango de días para el mes seleccionado
    import calendar
    _, ultimo_dia = calendar.monthrange(anio_sel, mes_idx)
    
    # Preparar datos para la tabla
    tabla_datos = []
    for dia in range(1, ultimo_dia + 1):
        fecha_iter = datetime(anio_sel, mes_idx, dia)
        idx_anual = (fecha_iter - datetime(anio_sel, 1, 1)).days
        
        # Obtener datos de las curvas (debes asegurarte de que calcular_curvas_solares 
        # devuelva arrays de 365 días)
        def get_day_data(am, at, idx):
            s_am = decimal_a_hhmmss(am[idx])
            s_at = decimal_a_hhmmss(at[idx])
            dur = (at[idx] - am[idx]) if at[idx] >= am[idx] else ((24.0 - am[idx]) + at[idx])
            s_dur = f"{int(dur)}h {int(round((dur%1)*60))}m"
            
            # Simplemente usa el emoji. En casi todos los navegadores modernos, ☀️ se verá amarillo.
            return f"🌅 {s_am} | 🌇 {s_at} | ☀️ {s_dur}"

        tabla_datos.append({
            "Date": fecha_iter.strftime("%d.%m.%Y"),
            f"📍 {st.session_state.poblacion}": get_day_data(amanecer_1, atardecer_1, idx_anual),
            f"⚖️ {st.session_state.poblacion_comp}": get_day_data(amanecer_2, atardecer_2, idx_anual)
        })

    # Mostrar tabla
    import pandas as pd
    df = pd.DataFrame(tabla_datos)
    # st.dataframe permite ocultar el índice de forma nativa
    st.dataframe(df, hide_index=True, use_container_width=True)

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
