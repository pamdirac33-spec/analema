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
        
        cos_ha = (np.cos(np.radians(90.833)) / (np.cos(lat_rad) * np.cos(decl))) - (np.tan(lat_rad) * np.tan(decl))
        cos_ha = np.clip(cos_ha, -1.0, 1.0)
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

coords = streamlit_js_eval(
    js_expressions="JSON.stringify(window.streamlitReceivedMessage)",
    key="coords_eval"
)

if coords:
    try:
        data = eval(coords)
        if data and "lat" in data and "lon" in data:
            if data["lat"] != st.session_state.lat or data["lon"] != st.session_state.lon:
                st.session_state.lat = data["lat"]
                st.session_state.lon = data["lon"]
                st.session_state.poblacion = obtener_nombre_por_coordenadas(
                    st.session_state.lat,
                    st.session_state.lon
                )
                st.rerun()
    except Exception:
        pass

if "lat_comp" not in st.session_state:
    st.session_state.lat_comp = 41.6333
    st.session_state.lon_comp = -4.7167
    st.session_state.poblacion_comp = "Valladolid (España)"

# ---------------------------------------------------------
# BARRA LATERAL FIJA
# ---------------------------------------------------------
st.sidebar.success("📍 Ubicación seleccionada")
    
ahora_utc_sidebar = datetime.now(pytz.utc)
es_dst_sidebar = es_horario_verano(datetime.now(), st.session_state.lon)
huso_sidebar = int(round(st.session_state.lon / 15.0))
offset_sidebar = huso_sidebar + (1 if es_dst_sidebar else 0)
ahora_local_sidebar = ahora_utc_sidebar + timedelta(hours=offset_sidebar)

st.sidebar.markdown(
    f"""
**Ciudad:** {st.session_state.poblacion}  
**Lat:** {st.session_state.lat:.5f}  
**Lon:** {st.session_state.lon:.5f}  
**Hora Local:** {ahora_local_sidebar.strftime('%H:%M:%S')}  
**Hora UTC:** {ahora_utc_sidebar.strftime('%H:%M:%S')}
"""
)

year = st.sidebar.number_input("Año", value=datetime.now().year, step=1)

# Inicializar la hora global en st.session_state usando la hora local actual de la ubicación si no existe
if "hora" not in st.session_state:
    st.session_state.hora = ahora_local_sidebar.hour

# Slider de la hora enlazado directamente a st.session_state.hora
st.session_state.hora = st.sidebar.slider("Hora del día", 0, 23, st.session_state.hora, key="slider_hora_global")
hora = st.session_state.hora

usar_dst_analema = st.sidebar.checkbox("Aplicar Horario de Verano (DST)", value=False, key="chk_dst_analema")


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

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["Mapa", "Analema animada", "Comparación", "Funciones avanzadas", "Horas de sol", "Resources/Info"])

# ---------------------------------------------------------
# TAB 1 – MAPA INTERACTIVO
# ---------------------------------------------------------
with tab1:
    st.markdown("<div class='card-minimal'><h2>Selección de ubicación</h2></div>", unsafe_allow_html=True)

    if "busqueda_query" not in st.session_state:
        st.session_state.busqueda_query = ""

    if "map_tile_active" not in st.session_state:
        st.session_state.map_tile_active = "Satélite"

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

    satelite_checked = (st.session_state.map_tile_active == "Satélite")
    street_checked = (st.session_state.map_tile_active == "Street")

    mapa_tab1 = folium.Map(
        location=[st.session_state.lat, st.session_state.lon],
        zoom_start=st.session_state.zoom,
        tiles=None
    )

    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri World Imagery",
        name="Satélite",
        control=True,
        show=satelite_checked,
        overlay=False
    ).add_to(mapa_tab1)

    folium.TileLayer(
        tiles="https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
        attr="Esri Boundaries and Places",
        name="Satélite",
        control=False,
        show=satelite_checked,
        overlay=True
    ).add_to(mapa_tab1)

    folium.TileLayer(
        tiles="openstreetmap",
        name="Street",
        control=True,
        show=street_checked,
        overlay=False
    ).add_to(mapa_tab1)

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
        if output_mapa.get("zoom") and output_mapa["zoom"] != st.session_state.zoom:
            st.session_state.zoom = output_mapa["zoom"]

        all_layers = output_mapa.get("all_layers")
        if all_layers:
            for layer_name, layer_info in all_layers.items():
                if layer_info.get("active") is True:
                    if layer_name == "Satélite" and st.session_state.map_tile_active != "Satélite":
                        st.session_state.map_tile_active = "Satélite"
                    elif layer_name == "Street" and st.session_state.map_tile_active != "Street":
                        st.session_state.map_tile_active = "Street"

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
    st.markdown("<div class='card-minimal'><h2>Evolución analema por horas UTC</h2></div>", unsafe_allow_html=True)

    mostrar_todas_analemas = st.checkbox("Mostrar todas las analemas horarias UTC a la vez", value=False, key="chk_todas_analemas")

    analemas = []
    meses_es = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
    
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
            "elev": "Elevación (°)",
            "hora": "Hora UTC"
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
        355: ("Winter Solstice", "blue")
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
                x=df_dia_df["azim"], y=df_dia_df["elev"], mode="lines",
                line=dict(color=color_hito, width=1, dash="dash"),
                name=nombre_hito_en,
                hovertemplate=f"<b>{nombre_hito_en}</b><br>Azimuth: %{{x:.2f}}°<br>Elevation: %{{y:.2f}}°<extra></extra>"
            ))

    fig.update_layout(
        height=600,
        plot_bgcolor="#f7f7f7",
        paper_bgcolor="#f7f7f7",
        font=dict(size=13, color="#333"),
        title=dict(
            text="Evolución analema por horas UTC con Solsticios y Equinoccios",
            x=0, xanchor="left", font=dict(size=18, family="sans-serif")
        ),
        showlegend=True
    )

    st.plotly_chart(fig, width="stretch")

# ---------------------------------------------------------
# TAB 3 – COMPARACIÓN ENTRE CIUDADES (UTC)
# ---------------------------------------------------------
with tab3:
    st.markdown("<div class='card-minimal'><h2>Comparación de analemas por ciudades (UTC)</h2></div>", unsafe_allow_html=True)
    
    col_input, col_btn, col_espacio = st.columns([2.5, 0.8, 3.7])
    with col_input:
        ciudades_input = st.text_input("Introduce ciudades separadas por comas:", "Ingolstadt, Valladolid, El Cairo", key="ciudades_input_tab3")
    with col_btn:
        buscar_cl_btn = st.button("Buscar", key="btn_buscar_tab3")

    lista = [c.strip() for c in ciudades_input.split(",") if c.strip()]
    fig_tab3 = go.Figure()
    colores_ciudades = px.colors.qualitative.Bold
    
    dias_clave = {
        80: ("Equinoccio de Primavera", "green"),
        172: ("Solsticio de Verano", "red"),
        266: ("Equinoccio de Otoño", "orange"),
        355: ("Solsticio de Invierno", "blue")
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
                line=dict(color=color_ciudad, width=2),
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
    st.markdown("<div class='card-minimal'><h2>Funciones avanzadas y seguimiento solar (UTC)</h2></div>", unsafe_allow_html=True)
   
    ahora_utc_real = datetime.now(pytz.utc)
    hora_decimal_utc = float(hora) # Usamos la hora de la barra lateral izquierda
    elev_sol, azim_sol = spa(ahora_utc_real, st.session_state.lat, st.session_state.lon, hora_decimal_utc)

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

    zona_local = pytz.timezone("Europe/Berlin")
    ahora_local_real = ahora_utc_real.astimezone(zona_local)
    
    if "aplicar_dst_sidebar" in st.session_state and not st.session_state.aplicar_dst_sidebar:
        ahora_local_real = ahora_local_real - timedelta(hours=1)

    lat_val = f"{st.session_state.lat:.3f}°"
    lon_val = f"{st.session_state.lon:.3f}°"
    date_val = f"{ahora_local_real.strftime('%Y-%m-%d')}"
    local_time_val = f"{ahora_local_real.strftime('%H:%M:%S')}"
    utc_val = f"{ahora_utc_real.strftime('%H:%M:%S')} UTC"

    info_box_html = f"""
    <div style="position: absolute; top: 10px; left: 10px; z-index: 1000; background: rgba(255, 255, 255, 0.85); padding: 8px 12px; border-radius: 6px; border: 1px solid #ccc; font-family: sans-serif; font-size: 11px; line-height: 1.4; color: #222;">
        <b>lat:</b> {lat_val}<br>
        <b>lon:</b> {lon_val}<br>
        <b>date:</b> {date_val}<br>
        <b>local time:</b> {local_time_val}<br>
        <b>UTC:</b> {utc_val}
    </div>
    """

    st.markdown("### Posición actual del Sol y Orientación E/W (UTC)")
    
    mapa4 = folium.Map(
        location=[st.session_state.lat, st.session_state.lon],
        zoom_start=10,
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri World Imagery"
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
        R = 6371.0

        lat_dest = math.degrees(
            math.asin(
                math.sin(rad_lat) * math.cos(distancia_km / R) +
                math.cos(rad_lat) * math.sin(distancia_km / R) * math.cos(rad_az)
            )
        )
        lon_dest = math.degrees(
            rad_lon + math.atan2(
                math.sin(rad_az) * math.sin(distancia_km / R) * math.cos(lat_rad),
                math.cos(distancia_km / R) - math.sin(rad_lat) * math.sin(math.radians(lat_dest))
            )
        )
        return [lat_dest, lon_dest]

    puntos_tray = []
    lat_sol, lon_sol = None, None

    for h in np.linspace(0, 24, 120):
        elev_h, azim_h = spa(ahora_utc_real, st.session_state.lat, st.session_state.lon, float(h))
        if elev_h >= 0:
            dist_h = 18.0
            pt = calcular_punto_proyectado(st.session_state.lat, st.session_state.lon, azim_h, dist_h)
            puntos_tray.append(pt)
            
            if abs(h - hora_decimal_utc) < 0.1:
                lat_sol, lon_sol = pt

    if lat_sol is None or lon_sol is None:
        lat_sol, lon_sol = calcular_punto_proyectado(st.session_state.lat, st.session_state.lon, azim_sol, 18.0)

    html_sol_custom = f"""
    <div style="position: relative; width: 40px; height: 40px; left: -20px; top: -20px; z-index: 1000;">
        <div style="position: absolute; width: 30px; height: 30px; background-color: rgba(255, 165, 0, 0.95);
                    border-radius: 50%; border: 2px solid #222; box-shadow: 0 2px 6px rgba(0,0,0,0.4);
                    display: flex; align-items: center; justify-content: center; font-size: 14px; cursor: pointer;">
            ☀️
        </div>
        <div style="position: absolute; bottom: -14px; left: 50%; transform: translateX(-50%);
                    background: rgba(0,0,0,0.8); color: white; padding: 1px 6px; border-radius: 3px;
                    font-size: 10px; white-space: nowrap; font-weight: bold;">
            {azim_sol:.1f}°
        </div>
    </div>
    """

    folium.Marker(
        [lat_sol, lon_sol],
        popup=folium.Popup(f"""
        <div style="font-size: 12px; font-family: sans-serif; line-height: 1.4;">
            <b>Hora UTC real:</b> {ahora_utc_real.strftime('%H:%M:%S')}<br>
            <b>Azimuth estándar:</b> {azim_sol:.1f}°<br>
            <b>Elevación:</b> {elev_sol:.1f}°<br>
            <b>Ángulo E/W:</b> {az_ew:.1f}° {ref_ew}
        </div>
        """, max_width=300),
        icon=folium.DivIcon(html=html_sol_custom, icon_size=(40, 40), icon_anchor=(20, 20))
    ).add_to(mapa4)

    folium.PolyLine(
        locations=[[st.session_state.lat, st.session_state.lon], [lat_sol, lon_sol]],
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
            color="yellow",
            weight=2.5,
            tooltip="Trayectoria solar del día"
        ).add_to(mapa4)

    st_folium(mapa4, width=None, height=500, key="mapa_avanzado_tab4", returned_objects=[])
    
    st.markdown("---")
    st.markdown("### Animación de Trayectoria Solar 24H UTC (Línea de tiempo interactiva)")

    from folium.plugins import TimestampedGeoJson

    mapa_animado = folium.Map(
        location=[st.session_state.lat, st.session_state.lon],
        zoom_start=10,
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri World Imagery"
    )

    mapa_animado.get_root().html.add_child(folium.Element(info_box_html))

    puntos_24h_completa = []
    for h in range(24):
        elev_h, azim_h = spa(ahora_utc_real, st.session_state.lat, st.session_state.lon, float(h))
        az_rad_h = math.radians(azim_h)
        lat_h = math.degrees(math.asin(math.sin(lat_rad)*math.cos(dist_km/R) + math.cos(lat_rad)*math.sin(dist_km/R)*math.cos(az_rad_h)))
        lon_h = math.degrees(lon_rad + math.atan2(math.sin(az_rad_h)*math.sin(dist_km/R)*math.cos(lat_rad), math.cos(dist_km/R) - math.sin(lat_rad)*math.sin(math.radians(lat_h))))
        puntos_24h_completa.append([lat_h, lon_h])

    folium.PolyLine(
        locations=puntos_24h_completa + [puntos_24h_completa[0]],
        color="orange",
        weight=2,
        dash_array="4, 4",
        tooltip="Trayectoria completa de 24h UTC"
    ).add_to(mapa_animado)

    features = []
    fecha_base = ahora_utc_real.strftime('%Y-%m-%d')
    
    for h in range(24):
        elev_h, azim_h = spa(ahora_utc_real, st.session_state.lat, st.session_state.lon, float(h))
        az_rad_h = math.radians(azim_h)
        lat_h = math.degrees(math.asin(math.sin(lat_rad)*math.cos(dist_km/R) + math.cos(lat_rad)*math.sin(dist_km/R)*math.cos(az_rad_h)))
        lon_h = math.degrees(lon_rad + math.atan2(math.sin(az_rad_h)*math.sin(dist_km/R)*math.cos(lat_rad), math.cos(dist_km/R) - math.sin(lat_rad)*math.sin(math.radians(lat_h))))

        color_icono = "orange" if elev_h >= 0 else "#333333"
        estado_txt = "Día (Sol Visible)" if elev_h >= 0 else "Noche (Bajo el horizonte)"

        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [lon_h, lat_h],
            },
            "properties": {
                "time": f"{fecha_base}T{h:02d}:00:00",
                "style": {"color": color_icono},
                "icon": "circle",
                "iconstyle": {
                    "fillColor": color_icono,
                    "fillOpacity": 0.9,
                    "stroke": "true",
                    "color": "#000000",
                    "weight": 1,
                    "radius": 8
                },
                "popup": f"<b>Hora UTC:</b> {h:02d}:00<br><b>Estado:</b> {estado_txt}<br><b>Elevación:</b> {elev_h:.1f}°<br><b>Azimuth:</b> {azim_h:.1f}°"
            },
        }
        features.append(feature)

    TimestampedGeoJson(
        {
            "type": "FeatureCollection",
            "features": features,
        },
        period="PT1H",
        add_last_point=False,
        auto_play=False,
        loop=True,
        max_speed=1,
        time_slider_drag_update=True,
        transition_time=200
    ).add_to(mapa_animado)

    folium.Marker(
        [st.session_state.lat, st.session_state.lon],
        popup=st.session_state.poblacion,
        icon=folium.Icon(color="red", icon="info-sign")
    ).add_to(mapa_animado)

    st_folium(mapa_animado, width=None, height=500, key="mapa_animado_integrado_tab4", returned_objects=[])
    
    st.markdown("---")
    st.markdown("### 🌐 Diagrama Solar Polar UTC (Trayectorias y Analemas)")
    st.markdown("Representación estereográfica/polar de la posición solar en UTC: el centro es el cenit (90° de elevación) y el borde exterior representa el horizonte (0°).")

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

    year = ahora_utc_real.year

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

        az_horas, r_horas, el_horas, text_horas = [], [], [], []
        for h in range(0, 25):
            el_h, az_h = spa(fecha_obj, st.session_state.lat, st.session_state.lon, float(h))
            if el_h >= 0:
                az_horas.append(az_h)
                r_horas.append(90 - el_h)
                el_horas.append(el_h)
                text_horas.append(f"{h:02d}:00 UTC")

        fig_polar.add_trace(go.Scatterpolar(
            r=r_horas,
            theta=az_horas,
            mode='markers+text',
            name=f"{nombre_hito} (Hours UTC)",
            showlegend=False,
            marker=dict(size=4, color=color_hito),
            text=text_horas,
            textposition="top center",
            textfont=dict(size=9, color="#555"),
            hovertemplate=f"<b>{nombre_hito}</b><br>Hour UTC: %{{text}}<br>Azimuth: %{{theta:.1f}}°<br>Elevation: %{{customdata:.1f}}°<extra></extra>",
            customdata=el_horas
        ))

    az_hoy_t, el_hoy_t, r_hoy_t = [], [], []
    for h in np.linspace(0, 24, 100):
        el, az = spa(ahora_utc_real, st.session_state.lat, st.session_state.lon, h)
        if el >= 0:
            az_hoy_t.append(az)
            el_hoy_t.append(el)
            r_hoy_t.append(90 - el)

    fig_polar.add_trace(go.Scatterpolar(
        r=r_hoy_t,
        theta=az_hoy_t,
        mode='lines',
        name=f"Current Day ({ahora_utc_real.strftime('%d %b')})",
        line=dict(width=2.5, color="magenta", dash="dash"),
        hovertemplate="<b>Current Day</b><br>Azimuth: %{theta:.1f}°<br>Elevation: %{customdata:.1f}°<extra></extra>",
        customdata=el_hoy_t
    ))

    df_analema_hoy = generar_analema(st.session_state.lat, st.session_state.lon, year, hora_decimal_utc)
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
        name=f"Analemma ({ahora_utc_real.strftime('%H:%M:%S')} UTC)",
        line=dict(width=1.5, color="darkviolet"),
        hovertemplate="<b>Current Analemma</b><br>Azimuth: %{theta:.1f}°<br>Elevation: %{customdata:.1f}°<extra></extra>",
        customdata=el_an_hoy
    ))
    
    if elev_sol >= 0:
        fig_polar.add_trace(go.Scatterpolar(
            r=[90 - elev_sol],
            theta=[azim_sol],
            mode='markers',
            name=f"Sun Now ({ahora_utc_real.strftime('%H:%M')}h UTC)",
            marker=dict(size=16, color="orange", line=dict(width=2, color="black")),
            hovertemplate=f"<b>Sun Now ({ahora_utc_real.strftime('%H:%M')}h UTC)</b><br>Azimuth: %{{theta:.1f}}°<br>Elevation: {elev_sol:.1f}°<extra></extra>"
        ))

    info_text = f"<b>lat:</b> {lat_val}<br><b>lon:</b> {lon_val}<br><b>date:</b> {date_val}<br><b>local time:</b> {local_time_val}<br><b>UTC:</b> {utc_val}"

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
                text=info_text,
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

    st.markdown("---")
    st.markdown("### 📈 Diagrama Solar Cartesiano UTC (Elevación vs Azimuth)")
    st.markdown(f"Representación cartesiana basada estrictamente en la hora UTC ({ahora_utc_real.strftime('%H:%M:%S')}): el eje horizontal muestra el Azimuth (0° a 360°) y el eje vertical la Elevación (0° a 90°).")

    fig_cartesiano = go.Figure()

    for az_grid in range(0, 361, 10):
        es_principal = (az_grid % 30 == 0)
        fig_cartesiano.add_trace(go.Scatter(
            x=[az_grid, az_grid],
            y=[0, 90],
            mode='lines',
            line=dict(
                color="rgba(200, 200, 200, 0.5)" if es_principal else "rgba(220, 220, 220, 0.25)",
                width=1.0 if es_principal else 0.5,
                dash="solid" if es_principal else "dot"
            ),
            showlegend=False,
            hoverinfo='skip'
        ))

    for el_grid in range(0, 91, 10):
        es_principal = (el_grid % 30 == 0)
        fig_cartesiano.add_trace(go.Scatter(
            x=[0, 360],
            y=[el_grid, el_grid],
            mode='lines',
            line=dict(
                color="rgba(200, 200, 200, 0.5)" if es_principal else "rgba(220, 220, 220, 0.25)",
                width=1.0 if es_principal else 0.5,
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
                text_horas.append(f"{h:02d}:00 UTC")

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
        el, az = spa(ahora_utc_real, st.session_state.lat, st.session_state.lon, h)
        if el >= 0:
            az_hoy_t.append(az)
            el_hoy_t.append(el)

    fig_cartesiano.add_trace(go.Scatter(
        x=az_hoy_t,
        y=el_hoy_t,
        mode='lines',
        name=f"Current Day ({ahora_utc_real.strftime('%d %b')})",
        line=dict(width=2.5, color="magenta", dash="dash"),
        hovertemplate="<b>Current Day</b><br>Azimuth: %{x:.1f}°<br>Elevation: %{y:.1f}°<extra></extra>"
    ))

    df_analema_hoy = generar_analema(st.session_state.lat, st.session_state.lon, year, hora_decimal_utc)
    az_an_hoy, el_an_hoy = [], []
    for _, row in df_analema_hoy.iterrows():
        if row["elev"] >= 0:
            az_an_hoy.append(row["azim"])
            el_an_hoy.append(row["elev"])

    fig_cartesiano.add_trace(go.Scatter(
        x=az_an_hoy,
        y=el_an_hoy,
        mode='lines',
        name=f"Analemma ({ahora_utc_real.strftime('%H:%M:%S')} UTC)",
        line=dict(width=1.5, color="darkviolet"),
        hovertemplate=f"<b>Analemma ({ahora_utc_real.strftime('%H:%M:%S')} UTC)</b><br>Azimuth: %{{x:.1f}}°<br>Elevation: %{{y:.1f}}°<extra></extra>"
    ))
    
    if elev_sol >= 0:
        fig_cartesiano.add_trace(go.Scatter(
            x=[azim_sol],
            y=[elev_sol],
            mode='markers',
            name=f"Sun Now ({ahora_utc_real.strftime('%H:%M:%S')} UTC)",
            marker=dict(size=14, color="orange", line=dict(width=2, color="black")),
            hovertemplate=f"<b>Sun Now ({ahora_utc_real.strftime('%H:%M:%S')} UTC)</b><br>Azimuth: %{{x:.1f}}°<br>Elevation: %{{y:.1f}}°<extra></extra>"
        ))

    info_text_cartesiano = f"lat: {lat_val}<br>lon: {lon_val}<br>date: {date_val}<br>local time: {local_time_val}<br>UTC: {utc_val}"

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
# TAB 5 – HORAS DE LUZ Y CALENDARIO (UTC / Local con DST)
# ---------------------------------------------------------
with tab5:
    st.markdown("<div class='card-minimal'><h2>Comparativa Anual de Luz Solar</h2></div>", unsafe_allow_html=True)

    col_info1, col_info2, col_vacia = st.columns([2, 2, 2])
    with col_info1:
        st.markdown(f"**📍 {st.session_state.poblacion}**")
        st.metric(label="Hora Actual UTC", value=f"{ahora_utc_sidebar.strftime('%H:%M:%S')} UTC")
    with col_info2:
        st.markdown(f"**⚖️ {st.session_state.poblacion_comp}**")
        st.metric(label="Hora Actual UTC", value=f"{ahora_utc_sidebar.strftime('%H:%M:%S')} UTC")

    st.markdown("---")

    col_op1, col_busq2 = st.columns([2, 3])
    with col_op1:
        mostrar_dst = st.checkbox("Incluir cambio de horario de verano (DST)", value=True, key="dst_comp")
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

    dias, amanecer_1, atardecer_1 = calcular_curvas_solares(lat=st.session_state.lat, lon=st.session_state.lon, usar_dst=mostrar_dst)
    _, amanecer_2, atardecer_2 = calcular_curvas_solares(lat=st.session_state.lat_comp, lon=st.session_state.lon_comp, usar_dst=mostrar_dst)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=fechas_str, y=amanecer_1, mode='lines', name=f'Amanecer - {st.session_state.poblacion}', line=dict(color='orange', width=2)))
    fig.add_trace(go.Scatter(x=fechas_str, y=atardecer_1, mode='lines', name=f'Atardecer - {st.session_state.poblacion}', line=dict(color='darkorange', width=2)))
    fig.add_trace(go.Scatter(x=fechas_str, y=amanecer_2, mode='lines', name=f'Amanecer - {st.session_state.poblacion_comp}', line=dict(color='deepskyblue', width=2, dash='dash')))
    fig.add_trace(go.Scatter(x=fechas_str, y=atardecer_2, mode='lines', name=f'Atardecer - {st.session_state.poblacion_comp}', line=dict(color='blue', width=2, dash='dash')))

    fig.update_layout(
        title=dict(text=f"Comparativa de luz solar: {st.session_state.poblacion} vs {st.session_state.poblacion_comp}", font=dict(size=18)),
        xaxis_title="Fecha (Día.Mes)", yaxis_title="Hora UTC / Local (con DST)", template="plotly_white", yaxis=dict(range=[0, 24], dtick=2)
    )
    st.plotly_chart(fig, width="stretch")

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
        mostrar_calendario = st.checkbox("Mostrar calendario completo (estilo escritorio)", key="chk_modo_calendario")

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

# ---------------------------------------------------------
# TAB 6 – RESOURCES / INFO
# ---------------------------------------------------------
with tab6:
    st.markdown("<div class='card-minimal'><h2>Info</h2></div>", unsafe_allow_html=True)
    st.markdown("""
    ### ℹ️ Acerca de la aplicación
    * **Script realizado por:** dJoZeR - Ingolstadt, Agosto 2026
    * **Realizado con la ayuda de:** Copilot y Gemini
    * **Construido sobre la idea original de:** [SunEarthTools](https://www.sunearthtools.com/)
    """, unsafe_allow_html=True)
