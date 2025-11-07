import streamlit as st
import pandas as pd
import os
from dotenv import load_dotenv
from utils import (
    get_coordinates_from_address,
    get_id_cadastre_from_coordinates,
    get_dpe_exact_address,
    get_dpe_exact_coordinates,
    normalize_address,
    highlight_used_fields
)

# --- Charger la clé ADEME ---
load_dotenv()
ADEME_TOKEN = os.getenv("ADEME_TOKEN") or st.secrets.get("ADEME_TOKEN")

if not ADEME_TOKEN:
    st.error("⚠️ Clé ADEME introuvable. Ajoutez-la dans .env ou dans les secrets Streamlit.")
    st.stop()

# --- Titre de l'app ---
st.title("Enrichissement automatique fiches de bien")
st.write("Remarque: pour ce POC, seules les recherches dans le Finistère sont possibles.")

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
        df['adresse_complete'] == adresse_clean
    ]

    # 4. Sélectionner un DPE
    
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
            
    # 5. Sélectionner un DVF
    
    if len(df_dvf) > 1:
        st.write("Plusieurs transactions trouvées, veuillez affiner votre recherche :")

        # Étape 1 : choix de la surface
        choix_date_mutation = st.selectbox(
            "Date de la mutation :",
            options=sorted(df_dvf['date_mutation'].dropna().unique())
        )
        df_dvf = df_dvf[df_dvf['date_mutation'] == choix_date_mutation]

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
    for col in ['numero_dpe','adresse_ban','etiquette_dpe','date_etablissement_dpe','date_derniere_modification_dpe','etiquette_ges','conso_5 usages_par_m2_ef','conso_5_usages_par_m2_ep','emission_ges_5_usages par_m2','annee_construction','type_batiment','nombre_niveau_logement','complement_adresse_logement','surface_habitable_logement','type_installation_chauffage']:
        unique_vals = dpe_coordinates[col].dropna().unique()
        if len(unique_vals) == 1:
            final_data[col] = {"valeur": unique_vals[0], "source": "DPE"}
        elif len(unique_vals) > 1:
            final_data[col] = {"valeur": unique_vals.tolist(), "source": "DPE"}
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
        st.subheader("📄 Données DVF")
        if df_dvf.empty:
            st.warning("Aucune donnée DPE trouvée pour ces coordonnées.")
        else:
            # 1️⃣ Liste des champs utilisés dans df_final avec source DPE
            champs_utilises_dvf = df_final.loc[df_final["source de donnée"] == "DVF", "champ à remplir"].tolist()

            # 2️⃣ Transformer dpe_coordinates en format vertical
            df_dvf_display = df_dvf.transpose().reset_index()
            df_dvf_display.columns = ["champ à remplir", "valeur"]
            
             # 3️⃣ Trier pour mettre les champs utilisés en premier
            df_dvf_display["utilise"] = df_dvf_display["champ à remplir"].isin(champs_utilises_dvf)
            df_dvf_display = df_dvf_display.sort_values(by="utilise", ascending=False).drop(columns="utilise")

            # 4️⃣ Affichage avec style
            st.dataframe(
                df_dvf_display.style.apply(
                    lambda row: highlight_used_fields(row, champs_utilises_dvf),
                    axis=1
                )
            )

    with tab3:
        st.subheader("📄 Données DPE")
        if dpe_coordinates.empty:
            st.warning("Aucune donnée DPE trouvée pour ces coordonnées.")
        else:
            # 1️⃣ Liste des champs utilisés dans df_final avec source DPE
            champs_utilises_dpe = df_final.loc[df_final["source de donnée"] == "DPE", "champ à remplir"].tolist()

            # 2️⃣ Transformer dpe_coordinates en format vertical
            df_dpe_display = dpe_coordinates.transpose().reset_index()
            df_dpe_display.columns = ["champ à remplir", "valeur"]
            
            # 3️⃣ Trier pour mettre les champs utilisés en premier
            df_dpe_display["utilise"] = df_dpe_display["champ à remplir"].isin(champs_utilises_dpe)
            df_dpe_display = df_dpe_display.sort_values(by="utilise", ascending=False).drop(columns="utilise")

            # 4️⃣ Affichage avec style
            st.dataframe(
                df_dpe_display.style.apply(
                    lambda row: highlight_used_fields(row, champs_utilises_dpe),
                    axis=1
                )
            )