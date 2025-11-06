import streamlit as st
import pandas as pd
import os
from dotenv import load_dotenv
from utils import (
    get_coordinates_from_address,
    get_id_cadastre_from_coordinates,
    get_dpe_exact_address,
    get_dpe_exact_coordinates,
    normalize_address
)

# --- Charger la clé ADEME ---
load_dotenv()
ADEME_TOKEN = os.getenv("ADEME_TOKEN") or st.secrets.get("ADEME_TOKEN")

if not ADEME_TOKEN:
    st.error("⚠️ Clé ADEME introuvable. Ajoutez-la dans .env ou dans les secrets Streamlit.")
    st.stop()

# --- Titre de l'app ---
st.title("Enrichissement automatique fiches de bien")

# --- Saisie de l'adresse ---
adresse_input = st.text_input("Entrez une adresse :", "12 RUE DE POUL AR BACHET 29200")

if adresse_input:
    # 1. Géocodage via BAN
    coords = get_coordinates_from_address(adresse_input)
    if "error" in coords:
        st.error(f"Erreur géocodage : {coords['error']}")
        st.stop()

    st.write("**Adresse normalisée :**", coords["adresse_label"])
    st.write("**Coordonnées :**", coords["latitude"], coords["longitude"])

    # 2. DPE par coordonnées
    dpe_coordinates = get_dpe_exact_coordinates(coords["coord_geo_x"], coords["coord_geo_y"], ADEME_TOKEN)

    if dpe_coordinates.empty:
        st.warning("Aucun DPE trouvé pour ces coordonnées.")
        st.stop()

    # 3. DVF
    df = pd.read_csv("dvf_ok.csv")
    adresse_clean = normalize_address(coords["adresse_label"])
    df_dvf = df.loc[
        df['adresse_complete'] == adresse_clean,
        ['surface_reelle_bati', 'nombre_pieces_principales', 'surface_terrain']
    ]

    # 4. Fusion DVF + DPE
    for col in ['surface_reelle_bati', 'nombre_pieces_principales', 'surface_terrain']:
        unique_vals = df_dvf[col].dropna().unique()
        if len(unique_vals) == 1:
            dpe_coordinates[col] = unique_vals[0]
        elif len(unique_vals) > 1:
            dpe_coordinates[col] = [unique_vals.tolist()] * len(dpe_coordinates)
        else:
            dpe_coordinates[col] = None

    # 5. Sélection interactive si plusieurs DPE
    if len(dpe_coordinates) > 1:
        st.write("Plusieurs DPE trouvés :")
        st.dataframe(dpe_coordinates[['numero_dpe', 'surface_habitable_logement', 'etiquette_dpe']])

        choix_surface = st.selectbox(
            "Sélectionnez la surface habitable pour filtrer :",
            options=sorted(dpe_coordinates['surface_habitable_logement'].unique())
        )
        dpe_coordinates = dpe_coordinates[dpe_coordinates['surface_habitable_logement'] == choix_surface]

    # 6. Résultats finaux
    st.subheader("Résultats filtrés")
    st.dataframe(dpe_coordinates)