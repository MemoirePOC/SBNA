# -*- coding: utf-8 -*-
"""
Variables globales du PoC (ex Module 1.5 du notebook).
Valeurs et noms strictement identiques au notebook. Seule PATH change :
dans Colab c'etait 'drive/MyDrive/DATASET_POC/', ici c'est un chemin
relatif au depot GitHub, puisque le dataset est versionne dans data/.
"""

from pathlib import Path
import pandas as pd
from pyproj import Proj, Geod

# ─── Constantes physiques et projection ──────────────────────────────────
NM_TO_M = 1852.0
FT_TO_M = 0.3048
GEOD = Geod(ellps="WGS84")

# Projection stereographique TopSky - SYSTEM_CENTRE Niamey
proj_niamey = Proj(proj='stere', lat_0=16.25, lon_0=3.495833,
                    k_0=1.0, x_0=0, y_0=0, ellps='WGS84')

# ─── Donnees de DRRN ──────────────────────────────────────────────────────
ALT_TRANS = 3800
LARGEUR = 45
RITAT = (13.47378, 2.00136)      # IAF/IF
RN501 = (13.47731, 2.07697)      # FAF/FAP
THR09R = (13.48161, 2.16941)     # seuil 09R
VAR = -1.0                       # declinaison Niamey 1 W (AIP DRRN)
BRG_TRUE = 88.0 + VAR
R_T = 6371000.0

# --- Referentiel pour le franchissement des obstacles DRRN
df_obstacles = pd.DataFrame([
    {"Seuil": "09R", "nom": "NDB NY", "lat": 13.480972, "lon": 2.156528, "alt_ft": 715,
     "dist_der_m": 2784, "MFO_DEP_ft": 0.008 * 2784 / 0.3048, "MFO_ARR_ft": 75 / 0.3048, "D_seuil_m": 3084},

    {"Seuil": "27L", "nom": "VOR/DME", "lat": 13.481500, "lon": 2.198500, "alt_ft": 722,
     "dist_der_m": 190, "MFO_DEP_ft": 0.008 * 190 / 0.3048, "MFO_ARR_ft": 75 / 0.3048, "D_seuil_m": 390}])

# ─── Chemins des fichiers de donnees ─────────────────────────────────────
# Repertoire racine du depot (ce fichier est dans src/, on remonte d'un cran)
BASE_DIR = Path(__file__).resolve().parent.parent
PATH = str(BASE_DIR / "data" / "DATASET_POC") + "/"

FICHIER_STCA = PATH + 'STCA_AVRIL_2026.xlsx'
FICHIER_MSAW = PATH + 'MSAW_AVRIL_2026.xlsx'
FPL_DIR = PATH + 'FPL/'
BILLING_DIR = PATH + 'Billing_Avril_2026/'

PATH_FR24 = PATH + 'FR24API/'
TMA_GENERAL_DIR = PATH_FR24 + '1_TMA_GENERALE/'
APPROCHE_DIR = PATH_FR24 + '2_APPROCHE_FINALE/'
RMG_DIR = PATH_FR24 + '3_REMISE_DE_GAZ/'
AIRPROX_DIR = PATH_FR24 + '4_AIRPROX/'
STCA1_DIR = PATH_FR24 + '5_STCA/STCA1/'
STCA2_DIR = PATH_FR24 + '5_STCA/STCA2/'
STCA3_DIR = PATH_FR24 + '5_STCA/STCA3/'
DEP_DIR = PATH_FR24 + '6_DEPART/'
AIRPROX_120s_DIR = PATH_FR24 + '7_AIRPROX_120s/'
TMA_GENERAL_DIR2 = PATH_FR24 + '8_TMA_GENERALE/'
TMA_GENERAL_DIR3 = PATH_FR24 + 'TMA_GENERALE0804/'
TMA_GENERAL_DIR4 = PATH_FR24 + 'TMA_GENERALE0904/'
STCA_SSR_DIR = PATH_FR24 + 'STCA_SSR/'

# ─── Obstacles d'aerodrome DRRN ───────────────────────────────────────────
Obstacles = PATH + 'obstacles_drrn.csv'

# ─── Parametres carte ─────────────────────────────────────────────────────
col_id = 'icao24'
col_type = 'type'

# ─── CO2 ───────────────────────────────────────────────────────────────────
FACTEUR_CO2 = 3.16   # Jet A1 : Annexe 16 Volume IV, CORSIA, OACI

# ─── Cas illustratifs fixes pour la page Demonstration ────────────────────
# Ce sont les couples/vols deja etudies et commentes dans le memoire.
CAS_DEMONSTRATION = {
    "STCA CFG289 / VIR478 (16/04/2026 22:42) - airprox croisement vertical": {
        "type": "stca_pair",
        "callsigns": ("CFG289", "VIR478"),
        "altitude_range": (36000, 40000),
        "label": "STCA du 2026-04-16 22:42:15 a 22:44:15",
        "traffic_source": "stca_ssr",
    },
    "STCA RAM545Y / AFR149 (19/04/2026 00:36) - STCA pertinent": {
        "type": "stca_pair",
        "callsigns": ("RAM545Y", "AFR149"),
        "altitude_range": (27000, 41000),
        "label": "STCA du 2026-04-19 00:36:38 a 00:37:12",
        "traffic_source": "adsb_stca",
    },
    "Airprox reconstruit SKK047 / THY538": {
        "type": "airprox_pair",
        "callsigns": ("SKK047", "THY538"),
        "altitude_range": None,
        "label": "Presomption d'airprox reconstruite (Id3/Id4)",
        "traffic_source": "apx",
    },
    "Allongement de trajectoire ETH909 (KPI05, 10/04/2026)": {
        "type": "route_fpl",
        "callsigns": ("ETH909",),
        "altitude_range": None,
        "label": "Route FPL vs route reelle - ETH909",
        "traffic_source": "uta_openap",
    },
}
