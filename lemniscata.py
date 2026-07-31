import streamlit as st
import pandas as pd
import requests
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import math
import folium
from streamlit_folium import st_folium

# ---------------------------------------------------------
# CONFIGURACIÓN GENERAL
# ---------------------------------------------------------
st.set_page_config(
    page_title="Analema Solar",
    layout="wide",
)

st.markdown("""
<style>
body { font-size: 20px; }
button, input, select, textarea { font-size: 22px !important; }
.block-container { padding-top: 1rem; }
.card {
    background: #f8f9fa;
    padding: 1.5rem;
    border-radius: 15px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.1);
    margin-bottom: 2rem;
}
h1, h2, h3 { text-align: center; }
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

# ---------------------------------------------------------
# BARRA LATERAL FIJA
# ---------------------------------------------------------
st.sidebar.title("📍 Ubicación")

poblacion = st.sidebar.text_input("Ciudad", "Ingolstadt")
lat, lon = obtener_coordenadas(poblacion)

if lat is None:
    st.sidebar.error("No se encontraron coordenadas para esa población.")
    st.stop()

st.sidebar.success(f"{poblacion}\nLat: {lat}\nLon: {lon}")

year = st.sidebar.number_input("Año", value=datetime.now().year, step=1)
hora = st.sidebar.slider("Hora del día", 0, 23, 12)

# ---------------------------------------------------------
# TÍTULO PRINCIPAL
# ---------------------------------------------------------
st.markdown("<div class='card'><h1>🌞 Analema Solar Interactiva</h1></div>", unsafe_allow_html=True)

# ---------------------------------------------------------
# PESTAÑAS
# ---------------------------------------------------------
tab1, tab2, tab3 = st.tabs(["Mapa", "Analema animada", "Comparación"])

# ---------------------------------------------------------
# TAB 1 – MAPA INTERACTIVO
# ---------------------------------------------------------
with tab1:
    st.markdown("<div class='card'><h2>🗺️ Selección de ubicación en el mapa</h2></div>", unsafe_allow_html=True)

    mapa = folium.Map(location=[lat, lon], zoom_start=10)
    folium.Marker([lat, lon], popup=poblacion).add_to(mapa)

    resultado = st_folium(mapa, width=600, height=400)

    if resultado and resultado.get("last_clicked"):
        lat = resultado["last_clicked"]["lat"]
        lon = resultado["last_clicked"]["lng"]
        st.sidebar.success(f"📍 Nueva ubicación\nLat: {lat}\nLon: {lon}")

# ---------------------------------------------------------
# TAB 2 – ANALEMA ANIMADA POR HORAS
# ---------------------------------------------------------
with tab2:
    st.markdown("<div class='card'><h2>🌞 Analema por hora</h2></div>", unsafe_allow_html=True)

    df = generar_analema(lat, lon, year, hora)

    plt.style.use("seaborn-v0_8-darkgrid")
    fig, ax = plt.subplots(figsize=(6, 6))

    ax.plot(df["azim"], df["elev"], linewidth=1.0, color="orange")
    ax.set_xlabel("Azimuth (°)", fontsize=14)
    ax.set_ylabel("Elevación (°)", fontsize=14)
    ax.set_title(f"Analema – {hora}:00 h – {year}", fontsize=18)

    st.pyplot(fig)

# ---------------------------------------------------------
# TAB 3 – COMPARACIÓN ENTRE CIUDADES
# ---------------------------------------------------------
with tab3:
    st.markdown("<div class='card'><h2>📊 Comparación de analemas por ciudades</h2></div>", unsafe_allow_html=True)

    ciudades = st.text_area("Introduce ciudades separadas por comas:", "Ingolstadt, Valladolid, El Cairo")
    lista = [c.strip() for c in ciudades.split(",") if c.strip()]

    plt.style.use("seaborn-v0_8-darkgrid")
    fig, ax = plt.subplots(figsize=(6, 6))

    colores = ["red", "blue", "green", "purple", "orange", "cyan"]

    for i, ciudad in enumerate(lista):
        lat2, lon2 = obtener_coordenadas(ciudad)
        if lat2:
            df2 = generar_analema(lat2, lon2, year, hora)
            ax.plot(df2["azim"], df2["elev"], linewidth=1.0,
                    color=colores[i % len(colores)], label=ciudad)

    ax.set_xlabel("Azimuth (°)", fontsize=14)
    ax.set_ylabel("Elevación (°)", fontsize=14)
    ax.set_title(f"Comparación – {hora}:00 h – {year}", fontsize=18)
    ax.legend()

    st.pyplot(fig)
