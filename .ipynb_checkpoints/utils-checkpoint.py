import requests
import json
import pandas as pd
import re
import unicodedata


def convert_to_int(df):
    df['adresse_numero'] = pd.to_numeric(df['adresse_numero'], errors='coerce').astype('Int64')
    df['code_postal'] = pd.to_numeric(df['code_postal'], errors='coerce').astype('Int64')
    df['code_type_local'] = pd.to_numeric(df['code_type_local'], errors='coerce').astype('Int64')
    df['surface_reelle_bati'] = pd.to_numeric(df['surface_reelle_bati'], errors='coerce').astype('Int64')
    df['nombre_pieces_principales'] = pd.to_numeric(df['nombre_pieces_principales'], errors='coerce').astype('Int64')
    df['surface_terrain'] = pd.to_numeric(df['surface_terrain'], errors='coerce').astype('Int64')
    return df

def normalize_address(adr):
    # Supprimer les accents
    nfkd_form = unicodedata.normalize('NFKD', adr)
    without_accents = "".join([c for c in nfkd_form if not unicodedata.combining(c)])
    # Supprimer les caractères spéciaux
    clean = re.sub(r'[^A-Za-z0-9\s]', '', without_accents)
    # Mettre en majuscules
    return clean.upper().strip()

def create_adresse_complete(df):
    # Nettoyage des NaN
    df[['adresse_suffixe', 'adresse_nom_voie', 'code_postal', 'nom_commune']] = \
        df[['adresse_suffixe', 'adresse_nom_voie', 'code_postal', 'nom_commune']].fillna('')

    # Création sans doubles espaces
    df['adresse_complete'] = df.apply(
        lambda row: " ".join(
            str(x) for x in [
                row['adresse_numero'],
                row['adresse_suffixe'],
                row['adresse_nom_voie'] + ",",
                str(row['code_postal']),
                row['nom_commune'].upper()
            ] if str(x).strip()
        ),
        axis=1
    )

    # Normalisation finale
    df["adresse_complete"] = df["adresse_complete"].apply(normalize_address)
    
    return df

def traitement_dvf(df):
    #je supprime les lignes où les valeurs sont égales au nom de la colonne
    mask = df.apply(lambda row: any(row[col] == col for col in df.columns), axis=1)
    df = df[~mask]
    #je ne garde que les appartements et les maisons
    df = df.loc[(df['code_type_local'] == 1) | (df['code_type_local'] == 2)]
    df = convert_to_int(df)
    df = create_adresse_complete(df)
    df.drop_duplicates(subset=['adresse_complete', 'id_parcelle', 'type_local', 'date_mutation', 'longitude', 'latitude'], inplace=True)
    return df

def get_coordinates_from_address(address: str, limit: int = 1):
    """
    Récupère les coordonnées GPS et infos à partir d'une adresse via l'API BAN.
    """
    base_url = "https://api-adresse.data.gouv.fr/search/"
    params = {
        "q": address,
        "limit": limit
    }

    try:
        response = requests.get(base_url, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()

        if not data.get("features"):
            return {"error": "Adresse introuvable"}

        feature = data["features"][0]
        longitude, latitude = feature["geometry"]["coordinates"]
        properties = feature["properties"]

        result = {
            "adresse_label": properties.get("label"),
            "latitude": latitude,
            "longitude": longitude,
            "code_insee": properties.get("citycode"),
            "code_postal": properties.get("postcode"),
            "coord_geo_x": properties.get("x"),
            "coord_geo_y": properties.get("y")
        }
        return result

    except requests.exceptions.RequestException as e:
        return {"error": str(e)}
    
def get_id_cadastre_from_coordinates(lon, lat, limit=3):
    """
    Récupère l'id d'une parcelle à partir des long/lat via l'API géoplateforme.
    """
    base_url = "https://data.geopf.fr/geocodage/reverse?"
    params = {
        "lon": lon,
        "lat": lat,
        "index": "parcel",
        "limit": limit,
        "returntruegeometry": "false"
    }

    try:
        response = requests.get(base_url, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()

        if not data.get("features"):
            return {"error": "Id parcelle introuvable"}

        # Boucle sur toutes les parcelles trouvées
        parcelles = []
        for feature in data["features"]:
            properties = feature.get("properties", {})
            parcelles.append(properties.get("id"))

        result = {
            "id_parcelles": parcelles
        }
        return result

    except requests.exceptions.RequestException as e:
        return {"error": str(e)}
    
    

def get_dpe_exact_address(normalized_address: str, token: str, size: int = 10):
    """
    Récupère les DPE correspondant exactement à l'adresse via l'API ADEME
    et retourne une chaîne JSON joliment formatée.
    """
    base_url = "https://data.ademe.fr/data-fair/api/v1/datasets/dpe03existant/lines"

    normalized_address = normalized_address.upper()

    headers = {
        "Authorization": f"Bearer {token}"
    }

    params = {
        "q": normalized_address,
        "select": "numero_dpe,adresse_ban,_geopoint,etiquette_dpe,date_etablissement_dpe,date_derniere_modification_dpe,etiquette_ges,conso_5_usages_par_m2_ef,conso_5_usages_par_m2_ep,emission_ges_5_usages_par_m2,annee_construction,type_batiment,nombre_niveau_logement,complement_adresse_logement,surface_habitable_logement,type_installation_chauffage",
        "sort": "date_derniere_modification_dpe",
        "q_fields": "adresse_ban",
        "size": size
    }


    try:
        r = requests.get(base_url, headers=headers, params=params, timeout=10)
        r.raise_for_status()
        data = r.json().get("results", [])

        # Retourner en JSON joli
        return json.dumps(data, indent=4, ensure_ascii=False)

    except requests.exceptions.RequestException as e:
        # Erreur en JSON joli
        return json.dumps({"error": str(e)}, indent=4, ensure_ascii=False)

from io import StringIO

def get_dpe_exact_coordinates(x, y, token: str, size: int = 10):
    """
    Récupère les DPE correspondant exactement à l'adresse via l'API ADEME
    et retourne un DataFrame pandas directement depuis le CSV.
    """
    base_url = "https://data.ademe.fr/data-fair/api/v1/datasets/dpe03existant/lines"

    headers = {
        "Authorization": f"Bearer {token}"
    }

    params = {
        "sort": "date_derniere_modification_dpe",
        "coordonnee_cartographique_x_ban_eq": x,
        "coordonnee_cartographique_y_ban_eq": y,
        "size": size,
        "format": "csv"  # ✅ Demande le CSV directement
    }

    try:
        r = requests.get(base_url, headers=headers, params=params, timeout=10)
        r.raise_for_status()

        # Charger directement le CSV dans un DataFrame
        df = pd.read_csv(StringIO(r.text))
        return df

    except requests.exceptions.RequestException as e:
        return pd.DataFrame([{"error": str(e)}])
    
# 3️⃣ Fonction de surbrillance : mauve si le champ est dans champs_utilises_dpe
def highlight_used_fields(row, champs_utilises):
    return ['background-color: #e2d8f3' if row["champ à remplir"] in champs_utilises else '' for _ in row]