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
adresse_input = st.text_input("Entrez une adresse :")

if adresse_input:
    # 1. Géocodage via BAN
    coords = get_coordinates_from_address(adresse_input)
    if "error" in coords:
        st.error(f"Erreur géocodage : {coords['error']}")
        st.stop()

    # 2. DPE par coordonnées
    dpe_coordinates = get_dpe_exact_coordinates(coords["coord_geo_x"], coords["coord_geo_y"], ADEME_TOKEN)

    if dpe_coordinates.empty:
        st.warning("Aucun DPE trouvé pour ces coordonnées.")

    # 3. DVF
    df = pd.read_csv("dvf_ok.csv")
    adresse_clean = normalize_address(coords["adresse_label"])
    df_dvf = df.loc[
        df['adresse_complete'] == adresse_clean,
        ['surface_reelle_bati', 'nombre_pieces_principales', 'surface_terrain']
    ]

    # 5. Sélectionner un DPE
    
    if len(dpe_coordinates) > 1:
        st.write("Plusieurs DPE trouvés, veuillez affiner votre recherche :")

        # Étape 1 : choix de la surface
        choix_surface = st.selectbox(
            "Sélectionnez la surface habitable logement :",
            options=sorted(dpe_coordinates['surface_habitable_logement'].dropna().unique())
        )
        dpe_coordinates = dpe_coordinates[dpe_coordinates['surface_habitable_logement'] == choix_surface]

        # Étape 2 : choix du numéro de DPE si plusieurs avec la même surface
        if len(dpe_coordinates) > 1:
            choix_dpe = st.selectbox(
                "Plusieurs DPE ont la même surface. Sélectionnez le numéro de DPE :",
                options=dpe_coordinates['numero_dpe'].dropna().unique()
            )
            dpe_coordinates = dpe_coordinates[dpe_coordinates['numero_dpe'] == choix_dpe]

    # 6. Construire final_data avec DVF + DPE
    final_data = {}

    # Champs DVF
    for col in ['surface_reelle_bati', 'nombre_pieces_principales', 'surface_terrain']:
        unique_vals = df_dvf[col].dropna().unique()
        if len(unique_vals) == 1:
            final_data[col] = {"valeur": unique_vals[0], "source": "DVF"}
        elif len(unique_vals) > 1:
            final_data[col] = {"valeur": unique_vals.tolist(), "source": "DVF"}
        else:
            final_data[col] = {"valeur": None, "source": "DVF"}

    # Champs DPE
    for col in dpe_coordinates.columns:
        # Convertir toutes les valeurs en tuples si ce sont des listes
        vals = [
            tuple(v) if isinstance(v, list) else v
            for v in dpe_coordinates[col].dropna()
        ]

        # Maintenant .unique() peut fonctionner car tout est hashable
        unique_vals = pd.Series(vals).unique()

        if len(unique_vals) == 1:
            # Si c'est un tuple, reconvertir en liste pour l'affichage utilisateur
            val = list(unique_vals[0]) if isinstance(unique_vals[0], tuple) else unique_vals[0]
            final_data[col] = {"valeur": val, "source": "DPE"}
        elif len(unique_vals) > 1:
            # Reconvertir tous les tuples en listes pour affichage
            val_list = [list(v) if isinstance(v, tuple) else v for v in unique_vals]
            final_data[col] = {"valeur": val_list, "source": "DPE"}
        else:
            final_data[col] = {"valeur": None, "source": "DPE"}

    # 7. Transformer en DataFrame vertical
    df_final = pd.DataFrame([
        {"champ à remplir": champ, "valeur": data["valeur"], "source de donnée": data["source"]}
        for champ, data in final_data.items()
    ])

    # 8. Affichage interactif
    st.subheader("🎯 Résultats à compléter")
    for idx, row in df_final.iterrows():
        champ = row["champ à remplir"]
        valeur = row["valeur"]
        source = row["source de donnée"]

        if isinstance(valeur, list):
            choix = st.selectbox(f"{champ} ({source})", options=valeur)
            df_final.at[idx, "valeur"] = choix
        else:
            st.write(f"**{champ} ({source})** : {valeur}")

    # 9. Afficher le tableau final
    tab1, tab2, tab3 = st.tabs(["✅ Données finales", "📊 Données DVF", "📄 Données DPE"])

    with tab1:
        st.subheader("✅ Données finales")
        st.dataframe(df_final)

    with tab2:
        st.subheader("📊 Données DVF")
        if df_dvf.empty:
            st.warning("Aucune donnée DVF trouvée pour cette adresse.")
        else:
            st.dataframe(df_final.loc[df_final['source de donnée'] == 'DVF'])

    with tab3:
        st.subheader("📄 Données DPE")
        if dpe_coordinates.empty:
            st.warning("Aucune donnée DPE trouvée pour ces coordonnées.")
        else:
            st.dataframe(df_final.loc[df_final['source de donnée'] == 'DPE'])