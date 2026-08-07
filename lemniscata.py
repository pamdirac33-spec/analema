import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import requests
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import math
import folium
from streamlit_folium import st_folium
import time
import streamlit.components.v1 as components
from streamlit_js_eval import streamlit_js_eval
import pytz

# ---------------------------------------------------------
# CONFIGURACIÓN GENERAL
# ---------------------------------------------------------
st.set_page_config(
    page_title="Analema Solar",
    page_icon="☀️",
    layout="wide",
)

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

def calcular_curvas_solares(lat, lon, usar_dst=True):
    # Asegurar que lat y lon son numéricos
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        lat, lon = 48.77568, 11.48840

    dias = np.arange(1, 366)
    amanecer_horas = []
    atardecer_horas = []
    lat_rad = np.radians(lat)
    huso_base = int(round(lon / 15.0))

    for dia in dias:
        fecha_actual = datetime(2026, 1, 1) + timedelta(days=int(dia) - 1)
        es_dst_activo = es_horario_verano(fecha_actual, lon) if usar_dst else False

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
        
        offset_total = huso_base + (1 if es_dst_activo else 0)
        h_amanecer = (amanecer_utc_min / 60.0) + offset_total
        h_atardecer = (atardecer_utc_min / 60.0) + offset_total
            
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
# ---------------------------------------------------------
# BARRA LATERAL FIJA
# ---------------------------------------------------------
st.sidebar.success("📍 Selected Location")
    
ahora_utc_sidebar = datetime.now(pytz.utc)
es_dst_sidebar = es_horario_verano(datetime.now(), st.session_state.lon)
huso_sidebar = int(round(st.session_state.lon / 15.0))
offset_sidebar = huso_sidebar + (1 if es_dst_sidebar else 0)
ahora_local_sidebar = ahora_utc_sidebar + timedelta(hours=offset_sidebar)

st.sidebar.markdown(
    f"""
**City:** {st.session_state.poblacion}  
**Lat:** {st.session_state.lat:.5f}  
**Lon:** {st.session_state.lon:.5f}  
**Local Time:** {ahora_local_sidebar.strftime('%H:%M:%S')}  
**UTC:** {ahora_utc_sidebar.strftime('%H:%M:%S')}
"""
)

year = st.sidebar.number_input("Año", value=datetime.now().year, step=1)

# Inicializar estados de mes y día en session_state si no existen
if "mes" not in st.session_state:
    st.session_state.mes = ahora_local_sidebar.month
if "dia" not in st.session_state:
    st.session_state.dia = ahora_local_sidebar.day
if "hora" not in st.session_state:
    st.session_state.hora = ahora_local_sidebar.hour

st.sidebar.markdown("#### Control Temporal")

# Sliders integrados en la barra lateral con las variables originales
st.session_state.mes = st.sidebar.slider("Month", 1, 12, st.session_state.mes, step=1)

import calendar
max_dias_mes = calendar.monthrange(year, st.session_state.mes)[1]
if st.session_state.dia > max_dias_mes:
    st.session_state.dia = max_dias_mes

st.session_state.dia = st.sidebar.slider("Day", 1, max_dias_mes, st.session_state.dia, step=1)

st.session_state.hora = st.sidebar.slider("Time of Day", 0, 23, st.session_state.hora, key="slider_hora_global", step=1)
hora = st.session_state.hora

usar_dst_analema = st.sidebar.checkbox("Apply Daylight Saving Time(DST)", value=False, key="chk_dst_analema")

# Construir la fecha global unificada para el resto de pestañas a partir de los valores de la sidebar
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

tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(["Map", "Animated Analema", "Cities Comparison", "Advanced Features", "Polar/Cartesian", "Daylight Hours", "Resources/Info"])

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

    st.markdown("<div class='card-minimal'><h2>Selección de ubicación</h2></div>", unsafe_allow_html=True)

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
            key="input_busq_tab1_text"
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
    mostrar_todas_analemas = st.checkbox("Show all Analemas - UTC", value=False, key="chk_todas_analemas")

    analemas = []
    meses_es = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    
    for h in range(4, 23):
        df_h = generar_analema(st.session_state.lat, st.session_state.lon, year, h).copy()
        df_h["hora"] = h
        df_h["fecha"] = pd.to_datetime(f"{year}-01-01") + pd.to_timedelta(df_h.index, unit="D")
        df_h["mes_nombre"] = df_h["fecha"].dt.month.apply(lambda m: meses_es[m-1])
        df_h["dia_del_ano"] = df_h.index
        analemas.append(df_h)

    df_all = pd.concat(analemas)

    fig = px.line(
        df_all,
        x="azim",
        y="elev",
        animation_frame="hora",
        labels={
            "azim": "Azimuth (°)",
            "elev": "Elevation (°)",
            "hora": "UTC Time"
        }
    )

    fig.update_traces(
        line=dict(color="#1f77b4", width=2),
        hovertemplate=
        "<b>Hora UTC %{customdata[0]}:00</b><br>" +
        "Día del año: %{customdata[1]}<br>" +
        "Mes: %{customdata[2]}<br>" +
        "Azimuth: %{x:.2f}°<br>" +
        "Elevación: %{y:.2f}°<extra></extra>",
        customdata=df_all[["hora", "dia_del_ano", "mes_nombre"]]
    )

    # Dos flechas por analema (días 100 y 280 del año)
    dias_flechas = [100, 280]

    # Si se muestran todas las analemas a la vez, añadimos flechas estáticas para cada hora
    if mostrar_todas_analemas:
        for h in range(4, 23):
            df_h = df_all[df_all["hora"] == h].reset_index(drop=True)
            for d_frec in dias_flechas:
                if d_frec < len(df_h) and d_frec >= 5:
                    x_arrow = df_h.loc[d_frec, "azim"]
                    y_arrow = df_h.loc[d_frec, "elev"]
                    x_prev = df_h.loc[d_frec - 5, "azim"]
                    y_prev = df_h.loc[d_frec - 5, "elev"]
                    
                    fig.add_annotation(
                        x=x_arrow, y=y_arrow, ax=x_prev, ay=y_prev,
                        xref="x", yref="y", axref="x", ayref="y",
                        showarrow=True, arrowhead=2, arrowsize=1.1,
                        arrowwidth=1.2, arrowcolor="#ff7f0e",
                        visible=True
                    )
            
            fig.add_trace(go.Scatter(
                x=df_h["azim"], y=df_h["elev"], mode="lines",
                line=dict(color="rgba(150, 150, 150, 0.35)", width=1),
                name=f"Analema {h}:00 UTC", showlegend=False, hoverinfo="skip"
            ))

    dias_clave_lineas = {
        80: ("Spring Equinox", "green"),
        172: ("Summer Solstice", "red"),
        266: ("Autumn Equinox", "orange"),
        355: ("Winter Solstice", "blue"),
        111: ("21 April - Aug", "purple"),
        52: ("21 Feb - Oct", "brown"),
        21: ("21 Jan - Nov", "pink"),
        141: ("21 May - Jul", "olive")
    }

    for dia_idx, (nombre_hito_en, color_hito) in dias_clave_lineas.items():
        df_dia_completo = []
        for h in range(4, 23):
            df_h = df_all[df_all["hora"] == h].reset_index()
            if dia_idx < len(df_h):
                df_dia_completo.append(df_h.iloc[dia_idx])
        
        if df_dia_completo:
            df_dia_df = pd.DataFrame(df_dia_completo)
            fig.add_trace(go.Scatter(
                x=df_dia_df["azim"],
                y=df_dia_df["elev"],
                mode="lines",
                line=dict(color=color_hito, width=0.5, dash="dash"),
                name=nombre_hito_en,
                hovertemplate=f"<b>{nombre_hito_en}</b><br>Azimuth: %{{x:.2f}}°<br>Elevation: %{{y:.2f}}°<extra></extra>"
            ))

    ## Grey zone when elevatgion < 0° 
    fig.add_shape(
        type="rect",
        xref="paper", yref="y",
        x0=0, x1=1,          # Cubre todo el ancho del gráfico
        y0=-90, y1=0,        # Desde -90° hasta 0°
        fillcolor="rgba(128, 128, 128, 0.2)", # Color gris con transparencia
        line_width=0,
        layer="below"        # Asegura que esté detrás de las líneas del analema
    )

    # Mapeo de azimut a etiquetas
    marcas_azimut = {
        0: "N", 45: "NE", 90: "E", 135: "SE", 
        180: "S", 225: "SW", 270: "W", 315: "NW"
    }

    # Añadir líneas verticales más oscuras
    for grado, etiqueta in marcas_azimut.items():
        # Línea vertical
        fig.add_shape(
            type="line",
            x0=grado, x1=grado,
            y0=-10, y1=90, # Extensión vertical del gráfico
            line=dict(color="gray", width=1.5), # Más oscuro que el grid normal
            layer="below"
        )
        
        # Etiqueta sin fondo
        fig.add_annotation(
            x=grado,
            y=92, # Colocamos la etiqueta justo encima del área de datos
            text=etiqueta,
            showarrow=False,
            font=dict(size=12, color="black"),
            bgcolor=None # Asegura que no tenga fondo
        )
    
        fig.update_layout(
        height=550,
        plot_bgcolor="#f7f7f7",
        paper_bgcolor="#f7f7f7",
        font=dict(size=13, color="#333"),
        
        # Eje X: Grid normal cada 10° + tus nuevas líneas maestras
        xaxis=dict(
            title="Azimuth (°)",
            tickmode='linear',
            dtick=10,
            gridcolor='rgba(200, 200, 200, 0.3)',
            range=[0, 360]
        ),
        
        # Eje Y: Grid cada 5°
        yaxis=dict(
            title="Elevation (°)",
            tickmode='linear',
            dtick=5,
            gridcolor='rgba(200, 200, 200, 0.5)',
            range=[-10, 90]
        ),
        
        showlegend=True,
        legend=dict(
            orientation="v",       # Leyenda horizontal
            yanchor="top",         # Anclaje superior
            y=0.99,                # Posición vertical (cerca del techo)
            xanchor="right",        # Anclaje izquierdo
            x=0.99,                # Posición horizontal (cerca del margen izquierdo)
            bgcolor="rgba(255, 255, 255, 0.6)", # Fondo ligeramente transparente para que no moleste
            bordercolor="lightgray",
            borderwidth=1
        ),
        margin=dict(l=40, r=40, t=80, b=40) # Ajusta el margen superior 't' si el título choca
    )
    st.plotly_chart(fig, width="stretch")

# ---------------------------------------------------------
# TAB 3 – COMPARACIÓN ENTRE CIUDADES (UTC)
# ---------------------------------------------------------
with tab3:
    st.markdown("<div class='card-minimal'><h2>Analemas Comparison by Cities (UTC)</h2></div>", unsafe_allow_html=True)
    
    col_input, col_btn, col_espacio = st.columns([2.5, 0.8, 3.7])
    with col_input:
        ciudades_input = st.text_input("Introduce ciudades separadas por comas:", "Ingolstadt, Valladolid, El Cairo", key="ciudades_input_tab3")
    with col_btn:
        buscar_cl_btn = st.button("Buscar", key="btn_buscar_tab3")

    lista = [c.strip() for c in ciudades_input.split(",") if c.strip()]
    fig_tab3 = go.Figure()
    colores_ciudades = px.colors.qualitative.Bold
    
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

    # Dos flechas por analema (días 100 y 280 del año)
    dias_flechas = [100, 280]
    
    # 1. Primero pintamos las curvas y flechas de todas las ciudades para que aparezcan juntas en la leyenda
    datos_ciudades = []
    for idx, ciudad in enumerate(lista):
        lat2, lon2 = obtener_coordenadas(ciudad)
        if lat2:
            color_ciudad = colores_ciudades[idx % len(colores_ciudades)]
            df2 = generar_analema(lat2, lon2, year, hora).copy()
            df2["fecha"] = pd.to_datetime(f"{year}-01-01") + pd.to_timedelta(df2.index, unit="D")
            df2["mes_nombre"] = df2["fecha"].dt.month.apply(lambda m: meses_es[m-1])
            df2["dia_del_ano"] = df2.index
            
            fig_tab3.add_trace(go.Scatter(
                x=df2["azim"], y=df2["elev"], mode="lines",
                line=dict(color=color_ciudad, width=0.5),
                name=ciudad, legendgroup=ciudad,
                hovertemplate=f"<b>{ciudad}</b><br>Azimuth: %{{x:.2f}}°<br>Elevación: %{{y:.2f}}°"
            ))

            df2_reset = df2.reset_index(drop=True)
            for d_frec in dias_flechas:
                if d_frec < len(df2_reset) and d_frec >= 5:
                    x_arrow = df2_reset.loc[d_frec, "azim"]
                    y_arrow = df2_reset.loc[d_frec, "elev"]
                    x_prev = df2_reset.loc[d_frec - 5, "azim"]
                    y_prev = df2_reset.loc[d_frec - 5, "elev"]
                    
                    fig_tab3.add_annotation(
                        x=x_arrow, y=y_arrow, ax=x_prev, ay=y_prev,
                        xref="x", yref="y", axref="x", ayref="y",
                        showarrow=True, arrowhead=2, arrowsize=1.1,
                        arrowwidth=1.2, arrowcolor=color_ciudad
                    )
            
            datos_ciudades.append((df2, ciudad))

    # 2. Después añadimos los hitos estacionales para que se agrupen al final de la leyenda
    for dia, (nombre_hito, color_hito) in dias_clave.items():
        for idx, (df2, ciudad) in enumerate(datos_ciudades):
            if dia < len(df2):
                punto = df2.iloc[dia]
                show_legend_hito = (idx == 0)
                fig_tab3.add_trace(go.Scatter(
                    x=[punto["azim"]], y=[punto["elev"]], mode="markers",
                    marker=dict(size=10, color=color_hito, line=dict(width=1, color="black"), symbol="diamond"),
                    name=nombre_hito, legendgroup="hitos", showlegend=show_legend_hito,
                    hovertemplate=f"<b>{nombre_hito} ({ciudad})</b><br>Azimuth: %{{x:.2f}}°<br>Elevación: %{{y:.2f}}°<extra></extra>"
                ))

    fig_tab3.update_layout(
        height=650,
        plot_bgcolor="#f7f7f7",
        paper_bgcolor="#f7f7f7",
        title=dict(text=f"Comparativa de Analemas UTC – Hora UTC: {hora}:00 – Año: {year}", x=0),
        xaxis_title="Azimuth (°)",
        yaxis_title="Elevación (°)"
    )
    st.plotly_chart(fig_tab3, width="stretch")
    

# ---------------------------------------------------------
# TAB 4 – ANIMACIÓN DE TRAYECTORIA SOLAR CON LÍNEA DE TIEMPO (TIMESTAMPEDGEOJSON)
# ---------------------------------------------------------
with tab4:

    # ---------------------------------------------------------
    # PRIMER MAPA DE LA TAB 4 (Posición del Sol y Orientación E/W)
    # ---------------------------------------------------------
    st.markdown("### Sun Position & Orientation")
    
    # Cálculo preciso de la hora UTC matemática a partir de la hora local de la barra lateral
    hora_utc_calculada = (st.session_state.hora - offset_sidebar) % 24
    
    # Cálculo SPA utilizando la fecha de la barra lateral y la hora UTC exacta
    elev_sol, azim_sol = spa(fecha_global, st.session_state.lat, st.session_state.lon, float(hora_utc_calculada))

    # Obtención de la hora local y UTC sincronizadas en formato HH:MM:SS para cuadros contextuales
    local_time_calculada = ahora_local_sidebar.strftime('%H:%M:%S')

    if 'ahora_utc_sidebar' in locals() and hasattr(ahora_utc_sidebar, 'strftime'):
        utc_time_calculada = ahora_utc_sidebar.strftime('%H:%M:%S')
    else:
        # Convertimos el número decimal de horas a un timedelta
        tiempo_delta = timedelta(hours=float(hora_utc_calculada))
        
        # Un timedelta no tiene formato directo HH:MM:SS fácil, pero podemos sacarlo así:
        total_segundos = int(tiempo_delta.total_seconds()) % 86400  # Asegura rango de 24 horas
        h = total_segundos // 3600
        m = (total_segundos % 3600) // 60
        s = total_segundos % 60
        
        utc_time_calculada = f"{h:02d}:{m:02d}:{s:02d}"

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
        <b>Lat:</b> {lat_val}<br>
        <b>Lon:</b> {lon_val}<br>
        <b>Date:</b> {date_val_global}<br>
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

    # Bucle para dibujar la trayectoria solar de fondo
    puntos_tray = []
    for h_loop in np.linspace(0, 24, 120):
        elev_h, azim_h = spa(fecha_global, st.session_state.lat, st.session_state.lon, float(h_loop))
        if elev_h >= 0:
            dist_h = 18.0
            pt = calcular_punto_proyectado(st.session_state.lat, st.session_state.lon, azim_h, dist_h)
            puntos_tray.append(pt)

    # --- CORRECCIÓN CLAVE ---
    # Calculamos la posición exacta del sol actual usando su propio azimut y la misma distancia (18.0 km)
    # Garantiza que el icono se dibuje exactamente sobre la trayectoria.
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
            icon_anchor=(15, 15)  # Ancla exactamente en la mitad (15px de 30px)
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

    st_folium(mapa4, width="100%", height=1000, key="mapa_avanzado_tab4", returned_objects=[])


    # ---------------------------------------------------------
    # SEGUNDO MAPA DE LA TAB 4 (Trayectoria Acumulada sin Recargar la Página)
    # ---------------------------------------------------------
    st.markdown("---")
    st.markdown("### Sun Trajectory Animation - UTC")

    @st.fragment
    def render_mapa_animado_acumulado():
        from datetime import datetime, timezone

        # Obtención de la hora UTC real actual del sistema para la inicialización por defecto
        ahora_utc_real = datetime.now(timezone.utc)
        hora_utc_real_int = ahora_utc_real.hour

        # Widget de control deslizante dentro del fragmento (solo recarga este bloque al moverlo)
        hora_slider_utc = st.slider(
            "Select an UTC Time:",
            min_value=0,
            max_value=23,
            value=hora_utc_real_int,
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
            <b>Lat:</b> {lat_val}<br>
            <b>Lon:</b> {lon_val}<br>
            <b>Date:</b> {date_val_global}<br>
            <b>Local Time:</b> {local_time_calculada}<br>
            <b>UTC:</b> {utc_time_calculada}
        </div>
        """
        mapa_animado.get_root().html.add_child(folium.Element(info_box_anim))

        puntos_24h_completa = []
        fecha_base = fecha_global.strftime('%Y-%m-%d')

        # Bucle para calcular y dibujar la línea de trayectoria completa de fondo
        for h in range(24):
            elev_h, azim_h = spa(fecha_global, st.session_state.lat, st.session_state.lon, float(h))
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

        # Bucle para pintar los soles/lunas acumulados desde las 00:00 hasta la hora seleccionada
        for h in range(hora_slider_utc + 1):
            elev_h, azim_h = spa(fecha_global, st.session_state.lat, st.session_state.lon, float(h))
            az_rad_h = math.radians(azim_h)
            lat_h = math.degrees(math.asin(math.sin(lat_rad)*math.cos(dist_km/R) + math.cos(lat_rad)*math.sin(dist_km/R)*math.cos(az_rad_h)))
            lon_h = math.degrees(lon_rad + math.atan2(math.sin(az_rad_h)*math.sin(dist_km/R)*math.cos(lat_rad), math.cos(dist_km/R) - math.sin(lat_rad)*math.sin(math.radians(lat_h))))

            # --- CORRECCIÓN DE COLOR E ICONO ---
            color_icono = "orange" if elev_h > 0 else "#888888"
            estado_txt = "Day (Sun visible)" if elev_h >= 0 else "Night"
            icono_emoji = "☀️" if elev_h >= 0 else "🌙"

            # --- CÁLCULO DE HORAS EN FORMATO HH:MM:SS Y H:M PARA LA ETIQUETA ---
            h_local_loop = (h + offset_sidebar) % 24
            hl_h = int(h_local_loop)
            ml_h = int(round((h_local_loop - hl_h) * 60))
            if ml_h == 60:
                hl_h = (hl_h + 1) % 24
                ml_h = 0
            
            hora_local_loop_str = f"{hl_h:02d}:{ml_h:02d}:00"
            utc_loop_str = f"{h:02d}:00:00"
            utc_hm_label = f"{h:02d}:00"  # Formato H:M solicitado

            # Destacar con un tamaño mayor y borde rojo el sol/luna de la hora exacta seleccionada
            es_hora_actual = (h == hora_slider_utc)
            tam_icono = 32 if es_hora_actual else 22
            borde_icono = "3px solid red" if es_hora_actual else "2px solid #222"
            z_index_val = 1005 if es_hora_actual else 1000

            # HTML limpio sin fondo ni borde en la etiqueta de texto
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

    # Ejecución del fragmento aislado
    render_mapa_animado_acumulado()

    # ---------------------------------------------------------
    # TERCER MAPA DE LA TAB 4 (Esfera / Cúpula Polar 3D de Elevación y Azimut)
    # ---------------------------------------------------------
    st.markdown("---")
    st.markdown("### Solar Chart Polar Dome - Azimuth & Elevation Grid")

    @st.fragment
    def render_mapa_domo_polar():
        from datetime import datetime, timezone

        ahora_utc_real = datetime.now(timezone.utc)
        hora_utc_real_int = ahora_utc_real.hour

        hora_slider_utc_dome = st.slider(
            "Select an UTC Time (Solar Chart Dome):",
            min_value=0,
            max_value=23,
            value=hora_utc_real_int,
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
            <b>Lat:</b> {lat_val}<br>
            <b>Lon:</b> {lon_val}<br>
            <b>Date:</b> {date_val_global}<br>
            <b>Local Time:</b> {local_time_calculada}<br>
            <b>UTC:</b> {utc_time_calculada}
        </div>
        """
        mapa_domo.get_root().html.add_child(folium.Element(info_box_dome))

        def calcular_punto_polar_domo(lat_orig, lon_orig, azim_deg, elev_deg, radio_max_km=15.0):
            if elev_deg < 0:
                elev_efectiva = max(0.0, elev_deg)
            else:
                elev_efectiva = elev_deg
            
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

        # 1. Círculos concéntricos de elevación cada 10° (con rejilla más clara y menos transparente)
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

            # Etiqueta de grados en el eje vertical norte (Azimut 0°)
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

        # 2. Líneas radiales de azimut cada 30° con mayor opacidad y oscuridad
        for az_linea in range(0, 360, 30):
            puntos_radial = []
            for el in range(0, 91, 5):
                puntos_radial.append(calcular_punto_polar_domo(st.session_state.lat, st.session_state.lon, float(az_linea), float(el), radio_max_km=15.0))
            
            folium.PolyLine(
                locations=puntos_radial,
                color="rgba(255, 255, 224, 0.8)",
                weight=1.3,
                dash_array="2, 2"
            ).add_to(mapa_domo)

        # 2. Líneas radiales de azimut cada 30° con mayor opacidad y claridad
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

        # Puntos cardinales SIN fondo blanco y con los grados al lado del texto
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

        # 3. Dibujar la trayectoria solar completa de 24 horas proyectada en el domo
        puntos_tray_dome = []
        for h_loop in np.linspace(0, 24, 120):
            elev_h, azim_h = spa(fecha_global, st.session_state.lat, st.session_state.lon, float(h_loop))
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

        # 4. Bucle para pintar las marcas horarias acumuladas (Solo hora UTC limpia al lado del icono)
        for h in range(hora_slider_utc_dome + 1):
            elev_h, azim_h = spa(fecha_global, st.session_state.lat, st.session_state.lon, float(h))
            
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

        # Marcador central de la ubicación de referencia (Zenit / Centro)
        folium.Marker(
            [st.session_state.lat, st.session_state.lon],
            popup=st.session_state.poblacion,
            icon=folium.Icon(color="red", icon="info-sign")
        ).add_to(mapa_domo)

        st_folium(mapa_domo, width="100%", height=700, key="mapa_domo_polar_tab4", returned_objects=[])

    render_mapa_domo_polar()
    
# ---------------------------------------------------------
# TAB 5 – DIAGRAMA POLAR Y CARTESIANO
# ---------------------------------------------------------
with tab5:
    # ---------------------------------------------------------
    # DIAGRAMA SOLAR POLAR UTC (Trayectorias y Analemas)
    # ---------------------------------------------------------
    st.markdown("---")
    st.markdown("### 🌐 UTC Polar Solar Diagram (Trajectories and Analemmas)")
    st.markdown(f"Polar representation synchronized with the sidebar (Date: **{date_val_global}**, Local Time: **{local_time_calculada}**, UTC Time: **{utc_time_calculada}**)")
    
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

    fig_polar = go.Figure()

    for angulo in range(0, 360, 10):
        fig_polar.add_trace(go.Scatterpolar(
            r=[0, 90],
            theta=[angulo, angulo],
            mode='lines',
            line=dict(color="rgba(200, 200, 200, 0.4)", width=0.5 if angulo % 90 != 0 else 1.2),
            showlegend=False,
            hoverinfo='skip'
        ))

    for d_idx, (nombre_hito, color_hito) in dias_polar_dict.items():
        fecha_obj = datetime(year, 1, 1) + timedelta(days=d_idx-1)
        azimuths_t = []
        elevaciones_t = []
        radios_t = []
        
        for h in np.linspace(0, 24, 100):
            el, az = spa(fecha_obj, st.session_state.lat, st.session_state.lon, h)
            if el >= 0:
                azimuths_t.append(az)
                elevaciones_t.append(el)
                radios_t.append(90 - el)

        fig_polar.add_trace(go.Scatterpolar(
            r=radios_t,
            theta=azimuths_t,
            mode='lines',
            name=nombre_hito,
            line=dict(width=1, color=color_hito),
            hovertemplate=f"<b>{nombre_hito}</b><br>Azimuth: %{{theta:.1f}}°<br>Elevation: %{{customdata:.1f}}°<extra></extra>",
            customdata=elevaciones_t
        ))

        az_horas_p, r_horas_p, text_horas_p, el_horas_p = [], [], [], []
        for h in range(0, 25):
            h_val = float(h if h < 24 else 23.99)
            el_h, az_h = spa(fecha_obj, st.session_state.lat, st.session_state.lon, h_val)
            if el_h >= 0:
                az_horas_p.append(az_h)
                r_horas_p.append(90 - el_h)
                text_horas_p.append(f"{h:02d}")
                el_horas_p.append(el_h)

        if az_horas_p:
            fig_polar.add_trace(go.Scatterpolar(
                r=r_horas_p,
                theta=az_horas_p,
                mode='markers+text',
                name=f"{nombre_hito} (Hours UTC)",
                showlegend=False,
                marker=dict(size=4, color=color_hito),
                text=text_horas_p,
                textposition="top center",
                textfont=dict(size=9, color="#555"),
                hovertemplate=f"<b>{nombre_hito}</b><br>Hour UTC: %{{text}}<br>Azimuth: %{{theta:.1f}}°<br>Elevation: %{{customdata:.1f}}°<extra></extra>",
                customdata=el_horas_p
            ))

    az_hoy_t, el_hoy_t, r_hoy_t = [], [], []
    for h in np.linspace(0, 24, 100):
        el, az = spa(fecha_global, st.session_state.lat, st.session_state.lon, h)
        if el >= 0:
            az_hoy_t.append(az)
            el_hoy_t.append(el)
            r_hoy_t.append(90 - el)

    fig_polar.add_trace(go.Scatterpolar(
        r=r_hoy_t,
        theta=az_hoy_t,
        mode='lines',
        name=f"Current Day ({date_val_global})",
        line=dict(width=2.5, color="magenta", dash="dash"),
        hovertemplate="<b>Current Day</b><br>Azimuth: %{theta:.1f}°<br>Elevation: %{customdata:.1f}°<extra></extra>",
        customdata=el_hoy_t
    ))

    df_analema_hoy = generar_analema(st.session_state.lat, st.session_state.lon, year, float(hora_utc_calculada))
    az_an_hoy, r_an_hoy, el_an_hoy = [], [], []
    for _, row in df_analema_hoy.iterrows():
        if row["elev"] >= 0:
            az_an_hoy.append(row["azim"])
            r_an_hoy.append(90 - row["elev"])
            el_an_hoy.append(row["elev"])

    fig_polar.add_trace(go.Scatterpolar(
        r=r_an_hoy,
        theta=az_an_hoy,
        mode='lines',
        name=f"Analemma (UTC {utc_time_calculada})",
        line=dict(width=1.5, color="darkviolet"),
        hovertemplate="<b>Current Analemma</b><br>Azimuth: %{theta:.1f}°<br>Elevation: %{customdata:.1f}°<extra></extra>",
        customdata=el_an_hoy
    ))
    
    if elev_sol >= 0:
        fig_polar.add_trace(go.Scatterpolar(
            r=[90 - elev_sol],
            theta=[azim_sol],
            mode='markers',
            name=f"Sun Now ({date_val_global} Local: {local_time_calculada})",
            marker=dict(size=16, color="orange", line=dict(width=2, color="black")),
            hovertemplate=(
                "<b>Sun Now</b><br>"
                f"<b>Fecha:</b> {date_val_global}<br>"
                f"<b>Hora Local:</b> {local_time_calculada}<br>"
                f"<b>Hora UTC:</b> {utc_time_calculada}<br>"
                "<b>Azimuth:</b> %{theta:.1f}°<br>"
                f"<b>Elevación:</b> {elev_sol:.1f}°<extra></extra>"
            )
        ))

    lat_val_c = f"{st.session_state.lat:.3f}°"
    lon_val_c = f"{st.session_state.lon:.3f}°"
    info_text_polar = f"lat: {lat_val_c}<br>lon: {lon_val_c}<br>date: {date_val_global}<br>Local: {local_time_calculada}<br>UTC: {utc_time_calculada}"

    fig_polar.update_layout(
        polar=dict(
            angularaxis=dict(
                direction="clockwise",
                period=360,
                rotation=90,
                dtick=10,
                tickvals=[0, 45, 90, 135, 180, 225, 270, 315],
                ticktext=["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
            ),
            radialaxis=dict(
                visible=True,
                range=[0, 90],
                dtick=10,
                tickvals=[0, 10, 20, 30, 40, 50, 60, 70, 80, 90],
                ticktext=["90° (Zenith)", "80°", "70°", "60°", "50°", "40°", "30°", "20°", "10°", "0° (Horizon)"],
                angle=90,
                side="counterclockwise"
            ),
            bgcolor="#f7f7f7"
        ),
        autosize=True,
        height=680,
        paper_bgcolor="#f7f7f7",
        font=dict(size=12, color="#333"),
        title=dict(text=""),
        dragmode="zoom",
        annotations=[
            dict(
                text=info_text_polar,
                x=0.0,
                y=1.0,
                xref="paper",
                yref="paper",
                align="left",
                showarrow=False,
                bgcolor="rgba(255,255,255,0.85)",
                bordercolor="#ccc",
                borderwidth=1,
                borderpad=6,
                font=dict(size=11, color="#222")
            )
        ],
        showlegend=True,
        legend=dict(
            x=1.0,
            y=1,
            xanchor="left",
            yanchor="top",
            bgcolor="rgba(255,255,255,0.85)",
            bordercolor="#e5e5e5",
            borderwidth=1,
            font=dict(size=11)
        ),
        margin=dict(l=20, r=150, t=20, b=20)
    )

    st.plotly_chart(
        fig_polar, 
        width="stretch", 
        config={
            "scrollZoom": True, 
            "displayModeBar": True,
            "modeBarButtonsToAdd": ["zoomPolar", "panPolar", "resetScalePolar"]
        }
    )

    # ---------------------------------------------------------
    # DIAGRAMA SOLAR CARTESIANO UTC (Elevación vs Azimuth)
    # ---------------------------------------------------------
    st.markdown("---")
    st.markdown("### 📈 UTC Cartesian Solar Diagram (Elevation vs Azimuth)")
    st.markdown(f"Cartesian representation based on the date **{date_val_global}** (Local Time: **{local_time_calculada}**, UTC Time: **{utc_time_calculada}**)")

    fig_cartesiano = go.Figure()

    for az_grid in range(0, 361, 5):
        es_principal = (az_grid % 30 == 0)
        es_secundaria = (az_grid % 10 == 0)
        
        fig_cartesiano.add_trace(go.Scatter(
            x=[az_grid, az_grid],
            y=[0, 90],
            mode='lines',
            line=dict(
                color="rgba(200, 200, 200, 0.5)" if es_principal else ("rgba(210, 210, 210, 0.35)" if es_secundaria else "rgba(220, 220, 220, 0.2)"),
                width=1.0 if es_principal else (0.75 if es_secundaria else 0.4),
                dash="solid" if es_principal else "dot"
            ),
            showlegend=False,
            hoverinfo='skip'
        ))

    for el_grid in range(0, 91, 5):
        es_principal = (el_grid % 30 == 0)
        es_secundaria = (el_grid % 10 == 0)
        
        fig_cartesiano.add_trace(go.Scatter(
            x=[0, 360],
            y=[el_grid, el_grid],
            mode='lines',
            line=dict(
                color="rgba(200, 200, 200, 0.5)" if es_principal else ("rgba(210, 210, 210, 0.35)" if es_secundaria else "rgba(220, 220, 220, 0.3)"),
                width=1.0 if es_principal else (0.85 if es_secundaria else 0.6),
                dash="solid" if es_principal else "dot"
            ),
            showlegend=False,
            hoverinfo='skip'
        ))

    for d_idx, (nombre_hito, color_hito) in dias_polar_dict.items():
        fecha_base_hito = datetime(year, 1, 1) + timedelta(days=d_idx-1)
        azimuths_t = []
        elevaciones_t = []
        
        for h in np.linspace(0, 24, 100):
            el, az = spa(fecha_base_hito, st.session_state.lat, st.session_state.lon, h)
            if el >= 0:
                azimuths_t.append(az)
                elevaciones_t.append(el)

        if azimuths_t:
            fig_cartesiano.add_trace(go.Scatter(
                x=azimuths_t,
                y=elevaciones_t,
                mode='lines',
                name=nombre_hito,
                line=dict(width=1, color=color_hito),
                hovertemplate=f"<b>{nombre_hito}</b><br>Azimuth: %{{x:.1f}}°<br>Elevation: %{{y:.1f}}°<extra></extra>"
            ))

        az_horas, el_horas, text_horas = [], [], []
        for h in range(0, 25):
            h_val = float(h if h < 24 else 23.99)
            el_h, az_h = spa(fecha_base_hito, st.session_state.lat, st.session_state.lon, h_val)
            if el_h >= 0:
                az_horas.append(az_h)
                el_horas.append(el_h)
                text_horas.append(f"{h:02d}")

        if az_horas:
            fig_cartesiano.add_trace(go.Scatter(
                x=az_horas,
                y=el_horas,
                mode='markers+text',
                name=f"{nombre_hito} (Hours UTC)",
                showlegend=False,
                marker=dict(size=4, color=color_hito),
                text=text_horas,
                textposition="top center",
                textfont=dict(size=9, color="#555"),
                hovertemplate=f"<b>{nombre_hito}</b><br>Hour UTC: %{{text}}<br>Azimuth: %{{x:.1f}}°<br>Elevation: %{{y:.1f}}°<extra></extra>"
            ))

    az_hoy_t, el_hoy_t = [], []
    for h in np.linspace(0, 24, 100):
        el, az = spa(fecha_global, st.session_state.lat, st.session_state.lon, h)
        if el >= 0:
            az_hoy_t.append(az)
            el_hoy_t.append(el)

    fig_cartesiano.add_trace(go.Scatter(
        x=az_hoy_t,
        y=el_hoy_t,
        mode='lines',
        name=f"Current Day ({date_val_global})",
        line=dict(width=2.5, color="magenta", dash="dash"),
        hovertemplate="<b>Current Day</b><br>Azimuth: %{x:.1f}°<br>Elevation: %{y:.1f}°<extra></extra>"
    ))

    df_analema_hoy = generar_analema(st.session_state.lat, st.session_state.lon, year, float(hora_utc_calculada))
    az_an_hoy, el_an_hoy = [], []
    for _, row in df_analema_hoy.iterrows():
        if row["elev"] >= 0:
            az_an_hoy.append(row["azim"])
            el_an_hoy.append(row["elev"])

    fig_cartesiano.add_trace(go.Scatter(
        x=az_an_hoy,
        y=el_an_hoy,
        mode='lines',
        name=f"Analemma (UTC {utc_time_calculada})",
        line=dict(width=1.5, color="darkviolet"),
        hovertemplate=f"<b>Analemma</b><br>Azimuth: %{{x:.1f}}°<br>Elevation: %{{y:.1f}}°<extra></extra>"
    ))
    
    if elev_sol >= 0:
        fig_cartesiano.add_trace(go.Scatter(
            x=[azim_sol],
            y=[elev_sol],
            mode='markers',
            name=f"Sun Now ({date_val_global} Local: {local_time_calculada})",
            marker=dict(size=14, color="orange", line=dict(width=2, color="black")),
            hovertemplate=(
                "<b>Sun Now</b><br>"
                f"<b>Fecha:</b> {date_val_global}<br>"
                f"<b>Hora Local:</b> {local_time_calculada}<br>"
                f"<b>Hora UTC:</b> {utc_time_calculada}<br>"
                "<b>Azimuth:</b> %{x:.1f}°<br>"
                f"<b>Elevación:</b> {elev_sol:.1f}°<extra></extra>"
            )
        ))

    lat_val_c = f"{st.session_state.lat:.3f}°"
    lon_val_c = f"{st.session_state.lon:.3f}°"
    info_text_cartesiano = f"lat: {lat_val_c}<br>lon: {lon_val_c}<br>date: {date_val_global}<br>Local: {local_time_calculada}<br>UTC: {utc_time_calculada}"

    fig_cartesiano.update_layout(
        xaxis=dict(
            title="Azimuth (°)",
            range=[0, 360],
            dtick=10,
            showgrid=False,
            zeroline=False
        ),
        yaxis=dict(
            title="Elevation (°)",
            range=[0, 90],
            dtick=10,
            showgrid=False,
            zeroline=False
        ),
        autosize=True,
        height=550,
        paper_bgcolor="#f7f7f7",
        plot_bgcolor="#f7f7f7",
        font=dict(size=12, color="#333"),
        showlegend=True,
        legend=dict(
            x=1.02,
            y=1,
            xanchor="left",
            yanchor="top",
            bgcolor="rgba(255,255,255,0.85)",
            bordercolor="#e5e5e5",
            borderwidth=1,
            font=dict(size=11)
        ),
        annotations=[
            dict(
                text=info_text_cartesiano,
                x=0.01,
                y=0.99,
                xref="paper",
                yref="paper",
                align="left",
                showarrow=False,
                bgcolor="rgba(255,255,255,0.85)",
                bordercolor="#ccc",
                borderwidth=1,
                borderpad=6,
                font=dict(size=11, color="#222")
            )
        ],
        margin=dict(l=40, r=150, t=30, b=40)
    )

    st.plotly_chart(
        fig_cartesiano, 
        width="stretch", 
        config={
            "scrollZoom": True, 
            "displayModeBar": True
        }
    )

# ---------------------------------------------------------
# TAB 6 – HORAS DE LUZ Y CALENDARIO (UTC / Local con DST)
# ---------------------------------------------------------
with tab6:
    st.markdown("<div class='card-minimal'><h2>Annual Sunlight Comparison</h2></div>", unsafe_allow_html=True)

    ahora_utc_tab5 = datetime.now(pytz.utc)
    
    # Obtener zonas horarias aproximadas o utilizar las locales de las ubicaciones si están disponibles
    # (Por defecto, usamos tz_local basadas en la longitud o pytz según corresponda)
    tz_local_1 = pytz.timezone('Europe/Berlin')  # O ajustado a la ubicación principal si se calcula dinámicamente
    tz_local_2 = pytz.timezone('Europe/Madrid')  # O ajustado a la ubicación de comparación
    
    ahora_local_1 = ahora_utc_tab5.astimezone(tz_local_1)
    ahora_local_2 = ahora_utc_tab5.astimezone(tz_local_2)

    col_info1, col_info2, col_vacia = st.columns([2, 2, 2])
    
    with col_info1:
        st.markdown(f"**📍 {st.session_state.poblacion}**")
        st.metric(label="Hora Local", value=ahora_local_1.strftime('%H:%M:%S'))
        st.caption(f"UTC: {ahora_utc_tab5.strftime('%H:%M:%S')}")
        
    with col_info2:
        st.markdown(f"**⚖️ {st.session_state.poblacion_comp}**")
        st.metric(label="Hora Local", value=ahora_local_2.strftime('%H:%M:%S'))
        st.caption(f"UTC: {ahora_utc_tab5.strftime('%H:%M:%S')}")
    st.markdown("---")

    col_op1, col_busq2 = st.columns([2, 3])
    with col_op1:
        mostrar_dst = st.checkbox("Include Daylight Saving Time (DST) change", value=True, key="dst_comp")
    with col_busq2:
        busqueda_comparativa = st.text_input("⚖️ Comparar con otra ciudad:", placeholder="Ej: Barcelona, Roma, Tokio...", key="input_comp_tab5")
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
    hover_am_1 = [f"Fecha: {x}<br>Amanecer: {decimal_a_hhmmss(val)}<extra></extra>" for x, val in zip(fechas_str, amanecer_1)]
    hover_at_1 = [f"Fecha: {x}<br>Atardecer: {decimal_a_hhmmss(val)}<extra></extra>" for x, val in zip(fechas_str, atardecer_1)]
    hover_am_2 = [f"Fecha: {x}<br>Amanecer: {decimal_a_hhmmss(val)}<extra></extra>" for x, val in zip(fechas_str, amanecer_2)]
    hover_at_2 = [f"Fecha: {x}<br>Atardecer: {decimal_a_hhmmss(val)}<extra></extra>" for x, val in zip(fechas_str, atardecer_2)]

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=fechas_str, y=amanecer_1, mode='lines', 
        name=f'Amanecer - {st.session_state.poblacion}', 
        line=dict(color='orange', width=2),
        text=hover_am_1,
        hovertemplate="%{text}"
    ))
    fig.add_trace(go.Scatter(
        x=fechas_str, y=atardecer_1, mode='lines', 
        name=f'Atardecer - {st.session_state.poblacion}', 
        line=dict(color='darkorange', width=2),
        text=hover_at_1,
        hovertemplate="%{text}"
    ))
    fig.add_trace(go.Scatter(
        x=fechas_str, y=amanecer_2, mode='lines', 
        name=f'Amanecer - {st.session_state.poblacion_comp}', 
        line=dict(color='deepskyblue', width=2, dash='dash'),
        text=hover_am_2,
        hovertemplate="%{text}"
    ))
    fig.add_trace(go.Scatter(
        x=fechas_str, y=atardecer_2, mode='lines', 
        name=f'Atardecer - {st.session_state.poblacion_comp}', 
        line=dict(color='blue', width=2, dash='dash'),
        text=hover_at_2,
        hovertemplate="%{text}"
    ))

    fig.update_layout(
        title=dict(text=f"Comparativa de luz solar: {st.session_state.poblacion} vs {st.session_state.poblacion_comp}", font=dict(size=18)),
        xaxis_title="Fecha (Día.Mes)",
        yaxis_title="Hora del día",
        template="plotly_white",
        hovermode="x unified",
        yaxis=dict(range=[0, 24], dtick=2),
        xaxis=dict(nticks=12)
    )

    st.plotly_chart(fig, width="stretch")

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

    st.markdown("---")
    st.markdown("### 📅 Calendario Solar Estilo Escritorio")

    if "cal_fecha_seleccionada" not in st.session_state:
        st.session_state.cal_fecha_seleccionada = datetime(year, datetime.now().month, datetime.now().day).date()
    if "chk_modo_calendario" not in st.session_state:
        st.session_state.chk_modo_calendario = False

    col_chk_cal, col_btn_today = st.columns([3, 1])
    
    with col_btn_today:
        if st.button("📍 Ir a Hoy", key="btn_ir_hoy"):
            st.session_state.chk_modo_calendario = True
            st.session_state.cal_fecha_seleccionada = datetime.now().date()
            st.rerun()

    with col_chk_cal:
        mostrar_calendario = st.checkbox(
            "Mostrar calendario completo (estilo escritorio)", 
            key="chk_modo_calendario"
        )

    if mostrar_calendario:
        import calendar
        
        nombres_meses_es = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
        
        col_m1, col_m2 = st.columns([2, 2])
        with col_m1:
            mes_actual_idx = st.session_state.cal_fecha_seleccionada.month - 1
            mes_elegido_nombre = st.selectbox("Seleccionar Mes:", nombres_meses_es, index=mes_actual_idx, key="sel_mes_cal")
            mes_idx = nombres_meses_es.index(mes_elegido_nombre) + 1

        cal = calendar.Calendar(firstweekday=0)
        dias_mes = cal.monthdayscalendar(year, mes_idx)

        st.markdown(f"#### 🗓️ {mes_elegido_nombre} {year}")
        
        dias_semana = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
        cols_cabecera = st.columns(7)
        for idx, d_sem in enumerate(dias_semana):
            cols_cabecera[idx].markdown(f"<div style='text-align: center; font-weight: bold; color: #555;'>{d_sem}</div>", unsafe_allow_html=True)

        fecha_seleccionada_obj = st.session_state.cal_fecha_seleccionada

        for semana in dias_mes:
            cols_semana = st.columns(7)
            for i, dia_num in enumerate(semana):
                with cols_semana[i]:
                    if dia_num == 0:
                        st.markdown("<div style='padding: 10px;'></div>", unsafe_allow_html=True)
                    else:
                        fecha_iter = datetime(year, mes_idx, dia_num).date()
                        es_hoy = (fecha_iter == datetime.now().date())
                        es_seleccionado = (fecha_iter == fecha_seleccionada_obj)

                        label_btn = f"⭐ {dia_num}" if es_hoy else f"{dia_num}"
                        tipo_boton = "primary" if es_seleccionado else "secondary"
                        
                        if st.button(label_btn, key=f"dia_{mes_idx}_{dia_num}", type=tipo_boton, use_container_width=True):
                            st.session_state.cal_fecha_seleccionada = fecha_iter
                            st.rerun()

        st.markdown("---")
        idx_dia_anual = (fecha_seleccionada_obj - datetime(year, 1, 1).date()).days
        
        if 0 <= idx_dia_anual < len(fechas_dt):
            am_1 = decimal_a_hhmmss(amanecer_1[idx_dia_anual])
            at_1 = decimal_a_hhmmss(atardecer_1[idx_dia_anual])
            dur_1 = (atardecer_1[idx_dia_anual] - amanecer_1[idx_dia_anual]) if atardecer_1[idx_dia_anual] >= amanecer_1[idx_dia_anual] else ((24.0 - amanecer_1[idx_dia_anual]) + atardecer_1[idx_dia_anual])
            dur_1_str = f"{int(dur_1)}h {int(round((dur_1%1)*60))}m"

            am_2 = decimal_a_hhmmss(amanecer_2[idx_dia_anual])
            at_2 = decimal_a_hhmmss(atardecer_2[idx_dia_anual])
            dur_2 = (atardecer_2[idx_dia_anual] - amanecer_2[idx_dia_anual]) if atardecer_2[idx_dia_anual] >= amanecer_2[idx_dia_anual] else ((24.0 - amanecer_2[idx_dia_anual]) + atardecer_2[idx_dia_anual])
            dur_2_str = f"{int(dur_2)}h {int(round((dur_2%1)*60))}m"

            st.markdown(f"### 📌 Detalles solares para el día: **{fecha_seleccionada_obj.strftime('%d de %B de %Y')}**")
            
            col_det1, col_det2 = st.columns(2)
            with col_det1:
                st.markdown(f"#### 📍 {st.session_state.poblacion}")
                st.markdown(f"🌅 **Amanecer:** `{am_1}`")
                st.markdown(f"🌇 **Anochecer:** `{at_1}`")
                st.markdown(f"⏳ **Duración del día:** `{dur_1_str}`")

            with col_det2:
                st.markdown(f"#### ⚖️ {st.session_state.poblacion_comp}")
                st.markdown(f"🌅 **Amanecer:** `{am_2}`")
                st.markdown(f"🌇 **Anochecer:** `{at_2}`")
                st.markdown(f"⏳ **Duración del día:** `{dur_2_str}`")

# ---------------------------------------------------------
# TAB 7 – RESOURCES / INFO
# ---------------------------------------------------------
with tab7:
    st.markdown("<div class='card-minimal'><h2>Info</h2></div>", unsafe_allow_html=True)
    st.markdown("""
    ### ℹ️ Acerca de la aplicación
    * **Script realizado por:** dJoZeR - Ingolstadt, Agosto 2026
    * **Realizado con la ayuda de:** Copilot y Gemini
    * **Construido sobre la idea original de:** [SunEarthTools](https://www.sunearthtools.com/)
    """, unsafe_allow_html=True)
