# -*- coding: utf-8 -*-
"""
Fonctions du notebook PoC (Module 1.6, sections 1.6.1 a 1.6.18),
+ les fonctions definies plus loin dans le notebook (comparer_fr24_reel,
trouver_fpl) qui sont reutilisees telles quelles.

AUCUN ALGORITHME N'EST MODIFIE ICI.

Couche de compatibilite Streamlit (les 3 seules adaptations transverses) :

1. `display(...)` est redefini ci-dessous pour ecrire dans Streamlit au lieu
   d'IPython. Les fonctions du notebook appellent `display(df)` par son nom :
   comme ce fichier definit son propre `display` au niveau du module, ces
   appels sont automatiquement satisfaits sans toucher une seule ligne a
   l'interieur des fonctions.
2. `print(...)` est redefini de la meme maniere (sinon les messages
   partiraient dans les logs serveur et ne seraient jamais vus par le jury).
3. Trois fonctions se terminaient par un affichage direct propre a Jupyter
   (`fig.show()`, `plt.show()`, `display(DHTML(...))`) : `afficher_html`,
   `profil_vertical_temps`, `profil_horizontal_temps`, `plot_msaw_zones`,
   `sens_deux_routes`. Pour celles-ci uniquement, la derniere ligne d'affichage
   est remplacee par un `return` de l'objet (figure ou texte) : le calcul est
   strictement identique, seule la restitution change, et se fait ensuite
   depuis la page Streamlit via st.plotly_chart / st.pyplot / st.markdown.
"""

import math
import re
from datetime import datetime, timedelta
from pathlib import Path
from glob import glob
import os

import numpy as np
import pandas as pd
import streamlit as st

import matplotlib.pyplot as plt
from scipy.stats import norm

from pywmm import WMMv2
from geopy.distance import great_circle, geodesic
import nvector as nv

from traffic.core import Traffic, Flight

from shapely.geometry import Point, Polygon as SPolygon, LineString

import hvplot.pandas  # noqa: F401  (active l'accesseur .hvplot sur les DataFrame)
import plotly.graph_objects as go

from openap import prop

import meteostat as ms

from src.config import (
    NM_TO_M, FT_TO_M, GEOD, proj_niamey, ALT_TRANS, LARGEUR,
    RITAT, RN501, THR09R, VAR, BRG_TRUE, R_T, FACTEUR_CO2,
)

# ─────────────────────── Couche de compatibilite Streamlit ────────────────

def display(obj):
    """Remplace IPython.display.display : rend le resultat dans Streamlit."""
    if isinstance(obj, pd.DataFrame):
        st.dataframe(obj, use_container_width=True)
    elif isinstance(obj, pd.Series):
        st.dataframe(obj.to_frame(), use_container_width=True)
    else:
        st.write(obj)


def print(*args, **kwargs):  # noqa: A001 (redefinition volontaire, cf. docstring du module)
    """Remplace print() : affiche le message dans la page Streamlit."""
    st.write(" ".join(str(a) for a in args))


# global mutable, rempli par src/pipeline.py apres construction de l'UTA.
# Reproduit le fonctionnement du notebook ou `filtrer_d` et `creer_carte_base`
# lisent la variable globale `contour_uta` du notebook plutot qu'un parametre.
contour_uta = None


# ─────────────────────────── 1.6.1 Affichage ───────────────────────────────

def afficher_html(titre, style='titre'):
    styles = {
        'titre':      'color:#1F4E79;font-size:18px;font-weight:bold;border-bottom:2px solid #1F4E79;padding-bottom:4px;',
        'sous_titre': 'color:#2E5F8A;font-size:14px;font-weight:bold;margin-top:8px;',
        'succes':     'color:#1976D2;font-weight:bold;',
        'erreur':     'color:red;font-weight:bold;',
        'defaut':     'color:orange;font-weight:bold;',
    }
    st.markdown(f'<p style="{styles.get(style, "")}">{titre}</p>', unsafe_allow_html=True)


# ──────────────────── 1.6.2 Fonctions geometriques ─────────────────────────

def dms(d, m, s):
    return d + m / 60 + s / 3600


def centre_arc(p_start, p_end, rayon_nm, cote='gauche'):
    lat_avg = (p_start[0] + p_end[0]) / 2
    cos_lat = math.cos(math.radians(lat_avg))
    dx = (p_end[1] - p_start[1]) * 60 * cos_lat
    dy = (p_end[0] - p_start[0]) * 60
    chord = math.hypot(dx, dy)
    if chord > 2 * rayon_nm:
        raise ValueError("Corde trop longue")
    d_val = math.sqrt(rayon_nm ** 2 - (chord / 2) ** 2)
    ux, uy = dx / chord, dy / chord
    if cote == 'droite':
        px, py = uy, -ux
    else:
        px, py = -uy, ux
    cx = dx / 2 + d_val * px
    cy = dy / 2 + d_val * py
    lat_c = p_start[0] + cy / 60
    lon_c = p_start[1] + cx / (60 * cos_lat)
    return (lat_c, lon_c)


def arc_polyline(centre, p_start, p_end, rayon_nm=60, n=30, direction='ccw'):
    lat_c, lon_c = centre
    cos_lat = math.cos(math.radians(lat_c))

    def angle(p):
        dx = (p[1] - lon_c) * 60 * cos_lat
        dy = (p[0] - lat_c) * 60
        return math.atan2(dy, dx)

    a1 = angle(p_start)
    a2 = angle(p_end)
    if direction == 'ccw':
        while a2 < a1:
            a2 += 2 * math.pi
    else:
        while a2 > a1:
            a2 -= 2 * math.pi

    points = []
    for i in range(n + 1):
        t = i / n
        a = a1 + (a2 - a1) * t
        dx = rayon_nm * math.cos(a)
        dy = rayon_nm * math.sin(a)
        points.append((lat_c + dy / 60, lon_c + dx / (60 * cos_lat)))
    return points


def interpoler(p_a, p_b, n=10):
    return [(p_a[0] + (p_b[0] - p_a[0]) * (i / n),
             p_a[1] + (p_b[1] - p_a[1]) * (i / n)) for i in range(1, n)]


def construire_cercle(lat, lon, rayon_nm, n=120):
    R = 6371
    r = rayon_nm * 1.852
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        dlat = (r / R) * math.cos(a)
        dlon = (r / R) * math.sin(a) / math.cos(math.radians(lat))
        pts.append((lat + math.degrees(dlat), lon + math.degrees(dlon)))
    pts.append(pts[0])
    return pts


# ──────────────── 1.6.3 Construction des espaces aeriens ───────────────────

def construire_polygone_tma1():
    """TMA1 Niamey - cercle de 80 NM autour de DRRN (VOR/DME NY)."""
    NY = (dms(13, 29, 0), dms(2, 12, 23))
    coords = construire_cercle(NY[0], NY[1], 80)
    poly = SPolygon([(lon, lat) for lat, lon in coords])
    return coords, {"NY": NY}, {"NY": NY}, poly


def construire_polygone_tma2():
    """TMA2 Niamey - polygone defini par l'AIP ASECNA."""
    sommets = {
        'P1': (dms(15, 14, 12),    dms(0, 3, 0)),
        'P2': (dms(16, 14, 16.29), -dms(0, 1, 35.40)),
        'P3': (dms(16, 15, 18),    dms(1, 0, 48)),
        'P4': (dms(16, 15, 0),     dms(4, 35, 0)),
        'P5': (dms(13, 43, 39.24), dms(4, 35, 0.41)),
        'P6': (dms(11, 0, 38.28),  dms(3, 45, 6.37)),
        'P7': (dms(11, 0, 0),      -dms(0, 29, 0)),
        'P8': (dms(12, 21, 0),     -dms(0, 29, 0)),
    }
    BAKAB = centre_arc(sommets['P1'], sommets['P2'], 60, 'gauche')
    OG = (dms(12, 20, 46.6), -dms(1, 30, 46.2))
    arc1 = arc_polyline(BAKAB, sommets['P1'], sommets['P2'])
    arc2 = arc_polyline(OG, sommets['P8'], sommets['P1'])
    frontiere = interpoler(sommets['P5'], sommets['P6'])
    contour = (arc1
               + [sommets['P3'], sommets['P4'], sommets['P5']]
               + frontiere
               + [sommets['P6'], sommets['P7'], sommets['P8']]
               + arc2
               + [sommets['P1']])
    poly = SPolygon([(lon, lat) for lat, lon in contour])
    return contour, sommets, {"BAKAB": BAKAB, "OG": OG}, poly


def construire_polygone_uta():
    """UTA Niamey - meme contour que TMA2 (FL245-FL460)."""
    return construire_polygone_tma2()


ESPACES = {
    "TMA1": (construire_polygone_tma1, "blue"),
    "TMA2": (construire_polygone_tma2, "green"),
    "UTA":  (construire_polygone_uta, "red"),
}


def couleur_vol(groupe):
    dest = groupe['dest_icao'].iloc[0]
    orig = groupe['orig_icao'].iloc[0]
    if dest == 'DRRN':
        return 'yellow'   # arrivee
    elif orig == 'DRRN':
        return 'orange'   # depart
    else:
        return 'blue'     # survol


# NOTE : les fonctions de cartographie interactive (creer_carte, afficher_zone,
# afficher_toutes_zones, creer_carte_base, ajouter_trajectoires_sur_carte,
# trac_trajectoires) etaient ecrites avec ipyleaflet, qui ne peut pas se
# rendre dans Streamlit. Elles sont reprises a l'identique (mêmes coordonnees,
# mêmes couleurs, meme logique) mais avec la bibliotheque folium, dans
# src/maps.py.


# ──────────────────── 1.6.5 Chargement des donnees ─────────────────────────

def charger_fpl(fpl_dir):
    """Charge l'ensemble des fichiers FPL (.tsv) d'un dossier."""
    fpl_files = sorted(glob(os.path.join(fpl_dir, "*.tsv")))
    if not fpl_files:
        raise FileNotFoundError(f"Aucun fichier .tsv trouve dans {fpl_dir}")
    header = pd.read_csv(fpl_files[0], sep="\t", skiprows=3,
                          nrows=0, encoding="latin1").columns.tolist()
    liste_df = []
    for fichier in fpl_files:
        df = pd.read_csv(fichier, sep="\t", skiprows=4, header=None,
                          names=header, encoding="latin1", low_memory=False)
        df["Fichier"] = os.path.basename(fichier)
        liste_df.append(df)
    return pd.concat(liste_df, ignore_index=True)


FIELDS_BILLING = [
    ('Callsign',       0,   9),
    ('REG',            9,  20),
    ('Type',          20,  25),
    ('Origine',       25,  30),
    ('Destination',   30,  35),
    ('Règle de vol',  35,  37),
    ('Statut',        37,  39),
    ('Operation_Type', 39, 43),
    ('Billing_Type',  43,  57),
    ('Date',          57,  65),
    ('Number_Count',  65,  71),
    ('Position1',     71,  83),
    ('Time1',         83,  88),
    ('Position2',     88, 100),
    ('Time2',        100, 104),
]


def lire_fichiers_billing(billing_dir):
    """Lit et concatene les fichiers Billing (.bill) d'un dossier."""
    fichiers = sorted(glob(billing_dir + "*.bill"))
    lignes = []
    for fichier in fichiers:
        with open(fichier, "r", encoding="utf-8", errors="ignore") as f:
            for ligne in f:
                if ligne.strip():
                    lignes.append({nom: ligne[debut:fin].strip()
                                   for nom, debut, fin in FIELDS_BILLING})
    return pd.DataFrame(lignes)


def charger_donnees(path):
    """Charge un fichier CSV, Excel, JSON ou Parquet et retourne un DataFrame"""
    if not os.path.exists(path):
        print(f"NOTFOUND  {os.path.basename(path)}  (fichier introuvable)")
        return None

    try:
        if path.endswith(".csv"):
            df = pd.read_csv(path)
        elif path.endswith((".xlsx", ".xls")):
            df = pd.read_excel(path)
        elif path.endswith(".json"):
            df = pd.read_json(path)
        elif path.endswith(".parquet"):
            df = pd.read_parquet(path)
        else:
            print(f"ECHEC  {os.path.basename(path)}  (format non pris en charge)")
            return None
    except Exception as e:
        print(f"ECHEC  {os.path.basename(path)}  ({type(e).__name__})")
        return None

    for col in df.columns:
        if 'timestamp' in col.lower() or 'date' in col.lower():
            df[col] = pd.to_datetime(df[col], utc=True, errors='coerce')

    return df


def charger_dossier_concatener(chemin, parse_dates=None, tri_naturel=True, verbose=True):
    """
    Charge et concatene tous les fichiers CSV d'un dossier.
    Tri naturel actif par defaut (tranche1 < tranche2 < ... < tranche8).
    """
    fichiers = glob(os.path.join(chemin, '*.csv'))

    if not fichiers:
        raise FileNotFoundError(f'Aucun fichier CSV trouve dans : {chemin}')

    if tri_naturel:
        def _cle(p):
            return [int(t) if t.isdigit() else t.lower()
                    for t in re.split(r'(\d+)', os.path.basename(p))]
        fichiers = sorted(fichiers, key=_cle)
    else:
        fichiers = sorted(fichiers)

    dfs = []
    for f in fichiers:
        try:
            df = pd.read_csv(f, parse_dates=parse_dates or False, low_memory=False)
            df['_source'] = os.path.basename(f)
            dfs.append(df)
        except Exception as e:
            print(f'[AVERT] {os.path.basename(f)} ignore : {e}')

    df_out = pd.concat(dfs, ignore_index=True)

    return df_out


# ─────────────── 1.6.6 Nettoyage et preparation ADS-B ──────────────────────

def nettoyer_identifiants(df: pd.DataFrame, label: str = 'Dataset') -> pd.DataFrame:

    def est_vide(serie):
        return serie.isna() | (serie.astype(str).str.strip() == '')

    def tableau_etape(etape, description, avant, apres):
        display(pd.DataFrame({
            'Étape': [etape],
            'Opération': [description],
            'Lignes avant': [f'{avant:,}'],
            'Lignes supprimées': [f'{avant - apres:,}'],
            'Lignes restantes': [f'{apres:,}'],
        }))

    afficher_html(f'Nettoyage des identifiants — {label}', style='titre')

    # Etape 1 : doublons exacts
    afficher_html('Étape 1 — Suppression des doublons exacts', style='sous_titre')
    avant = len(df)
    df = df.drop_duplicates()
    tableau_etape(1, 'Lignes entièrement identiques supprimées', avant, len(df))

    # Etape 2 : lignes sans callsign ET sans flight
    afficher_html('Étape 2 — Lignes sans callsign ET sans flight', style='sous_titre')
    avant = len(df)
    masque_incomplet = est_vide(df['callsign']) & est_vide(df['flight'])

    df_ok = df[~masque_incomplet].copy()
    df_incomplet = df[masque_incomplet].copy()

    ref = (
        df_ok
        .groupby('fr24_id', as_index=False)
        .agg(callsign_ref=('callsign', 'first'),
             flight_ref=('flight', 'first'))
    )

    df_incomplet = df_incomplet.merge(ref, on='fr24_id', how='left')
    recuperables = df_incomplet['callsign_ref'].notna() | df_incomplet['flight_ref'].notna()

    df_recupere = df_incomplet[recuperables].copy()
    df_recupere['callsign'] = df_recupere['callsign_ref'].fillna(df_recupere['callsign'])
    df_recupere['flight'] = df_recupere['flight_ref'].fillna(df_recupere['flight'])
    df_recupere = df_recupere.drop(columns=['callsign_ref', 'flight_ref'])

    n_recuperees = recuperables.sum()
    n_supprimees = (~recuperables).sum()

    display(pd.DataFrame({
        'Catégorie': ['Sans callsign & flight', 'fr24_id récupérable', 'fr24_id orphelin'],
        'Lignes': [f'{masque_incomplet.sum():,}',
                   f'{n_recuperees:,}',
                   f'{n_supprimees:,}'],
        'Action': ['détectées', 'callsign/flight récupéré', 'supprimées'],
    }))

    df_final = pd.concat([df_ok, df_recupere], ignore_index=True)

    afficher_html('Bilan global', style='sous_titre')
    display(pd.DataFrame({
        'Indicateur': ['Lignes initiales', 'Doublons exacts', 'Orphelins supprimés', 'Lignes finales'],
        'Valeur': [f'{avant:,}',
                   f'{avant - len(df_ok) - masque_incomplet.sum():,}',
                   f'{n_supprimees:,}',
                   f'{len(df_final):,}'],
    }))

    return df_final.rename(columns={'lat': 'latitude', 'fr24_id': 'icao24', 'lon': 'longitude', 'alt': 'altitude'})


def nettoyer_positions_altitudes(df, alt_min=0, alt_max=65000):
    """Supprime les positions geographiques invalides et les altitudes aberrantes."""
    n0 = len(df)
    df = df[df['latitude'].between(-90, 90) & df['longitude'].between(-180, 180)].copy()
    n1 = len(df)
    df = df[df['altitude'].between(alt_min, alt_max)].copy()
    n2 = len(df)
    print(f"Positions invalides : {n0 - n1}")
    print(f"Altitudes aberrantes : {n1 - n2}")
    print(f"Points conserves : {n2:,} ({n2 / n0 * 100:.1f} %)")
    return df


def filtrer_d(df_clean, contour):
    """Filtre les points ADS-B dans la bounding box puis dans le polygone UTA."""
    lats = [p[0] for p in contour]
    lons = [p[1] for p in contour]
    bbox = df_clean[
        df_clean['latitude'].between(min(lats), max(lats)) &
        df_clean['longitude'].between(min(lons), max(lons))
    ].copy()
    print(f"Filtre bbox    : {len(df_clean) - len(bbox)} points écartés")
    # contour_uta (global) prime sur le parametre `contour`, comme dans le notebook.
    # Si le global n'a pas encore ete renseigne par le pipeline (page ouverte trop
    # tot), on retombe sur le parametre deja recu : meme contour UTA, pas de crash.
    poly = SPolygon([(lon, lat) for lat, lon in (contour_uta or contour)])
    mask = bbox.apply(lambda r: poly.contains(Point(r['longitude'], r['latitude'])), axis=1)
    df_uta = bbox[mask].copy()
    print(f"Filtre polygone : {(~mask).sum()} points écartés")
    print(f"Points dans UTA : {len(df_uta)}")
    return df_uta, poly


# ───────────────────── 1.6.7 Fonctions MSAW ────────────────────────────────

def plot_msaw_zones(df):
    """Graphique de repartition des callsigns selon le niveau d'alertes MSAW."""
    df = df.sort_values("Nombre_alertes", ascending=True)
    callsigns = df["Aircraft Callsign"]
    values = df["Nombre_alertes"]
    fig = plt.figure(figsize=(10, 8))
    plt.axvspan(0, 5, color="green", alpha=0.2)
    plt.axvspan(5, 10, color="orange", alpha=0.2)
    plt.axvspan(10, max(values.max(), 10), color="red", alpha=0.2)
    plt.scatter(values, callsigns)
    plt.xlabel("Nombre d'alertes MSAW")
    plt.ylabel("Aircraft Callsign")
    plt.title("Répartition des 15 premiers Callsign selon le niveau de risque MSAW")
    plt.grid(True, linestyle="--", alpha=0.4)
    return fig


# ─────────────────── 1.6.8 Equipements de surveillance ─────────────────────

def analyse_ssr_adsb(FPL):
    """
    I1 / I2 — Taux d'emport SSR et ADS-B OUT depuis la case 10b des FPL OACI.
    La case 10b est extraite entre le 2e '/' et le '-' qui suit.
    """
    equip10b = (FPL["Texte"]
                .str.extract(r'^(?:[^/]+/){2}([^-]+)-', expand=False)
                .fillna(""))
    n = len(FPL)
    statut = pd.DataFrame({
        "SSR_MODE_A":    equip10b.str.contains("A", regex=False).sum() / n,
        "SSR_MODE_C":    equip10b.str.contains("C", regex=False).sum() / n,
        "SSR_S_CODE_S":  equip10b.str.contains("S", regex=False).sum() / n,
        "SSR_S_CODE_E":  equip10b.str.contains("E", regex=False).sum() / n,
        "SSR_S_CODE_H":  equip10b.str.contains("H", regex=False).sum() / n,
        "SSR_S_CODE_I":  equip10b.str.contains("I", regex=False).sum() / n,
        "SSR_S_CODE_L":  equip10b.str.contains("L", regex=False).sum() / n,
        "SSR_S_CODE_P":  equip10b.str.contains("P", regex=False).sum() / n,
        "SSR_S_CODE_X":  equip10b.str.contains("X", regex=False).sum() / n,
        "ADSB_CODE_B1":  equip10b.str.contains("B1", regex=False).sum() / n,
        "ADSB_CODE_B2":  equip10b.str.contains("B2", regex=False).sum() / n,
        "ADSB_CODE_U1":  equip10b.str.contains("U1", regex=False).sum() / n,
        "ADSB_CODE_U2":  equip10b.str.contains("U2", regex=False).sum() / n,
        "ADSB_CODE_V1":  equip10b.str.contains("V1", regex=False).sum() / n,
        "ADSB_CODE_V2":  equip10b.str.contains("V2", regex=False).sum() / n,
    }, index=["TAUX"]).T
    return statut.sort_values("TAUX", ascending=False)


def taux_equipement(FPL):
    """
    Taux de vols equipes SSR, ADS-B, les deux, ou aucun des deux,
    a partir de la case 10b des FPL OACI.
    """
    equip10b = (FPL["Texte"]
                .str.extract(r'^(?:[^/]+/){2}([^-]+)-', expand=False)
                .fillna(""))

    codes_ssr = ["A", "C", "S", "E", "H", "I", "L", "P", "X"]
    codes_adsb = ["B1", "B2", "U1", "U2", "V1", "V2"]

    ssr_ok = pd.concat([equip10b.str.contains(c, regex=False) for c in codes_ssr], axis=1).any(axis=1)
    adsb_ok = pd.concat([equip10b.str.contains(c, regex=False) for c in codes_adsb], axis=1).any(axis=1)

    n = len(FPL)
    taux = pd.Series({
        "SSR_SEUL":       (ssr_ok & ~adsb_ok).sum() / n,
        "ADSB_SEUL":      (adsb_ok & ~ssr_ok).sum() / n,
        "SSR_ET_ADSB":    (ssr_ok & adsb_ok).sum() / n,
        "AUCUN_DES_DEUX": (~ssr_ok & ~adsb_ok).sum() / n,
        "SSR_TOTAL":      ssr_ok.sum() / n,
        "ADSB_TOTAL":     adsb_ok.sum() / n,
    }, name="TAUX")

    return taux.to_frame()


# ──────────────── 1.6.9 Profils vertical et horizontal ─────────────────────

def profil_vertical_temps(traffic_obj, id_avion_1, id_avion_2, label='', altitude_range=None):
    """Trace les profils d'altitude de deux aeronefs."""
    if hasattr(id_avion_1, 'callsign'):
        id_avion_1 = id_avion_1.callsign
    if hasattr(id_avion_2, 'callsign'):
        id_avion_2 = id_avion_2.callsign

    afficher_html(f'Evolution verticale dans le temps - {id_avion_1} vs {id_avion_2}  |  {label}', style='titre')

    df = traffic_obj.data.copy()
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True, errors='coerce')

    vol1 = df[df['callsign'] == id_avion_1].sort_values('timestamp')
    vol2 = df[df['callsign'] == id_avion_2].sort_values('timestamp')

    if vol1.empty or vol2.empty:
        afficher_html('Un des deux identifiants est introuvable dans le dataset.', style='erreur')
        return None

    hover = ('<b>%{fullData.name}</b><br>'
             'Heure : %{x|%H:%M:%S} UTC<br>'
             'Altitude : %{y:,.0f} ft'
             '<extra></extra>')

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=vol1['timestamp'], y=vol1['altitude'],
                              mode='lines+markers', name=id_avion_1, line=dict(width=2), marker=dict(size=4),
                              hovertemplate=hover))
    fig.add_trace(go.Scatter(
        x=vol2['timestamp'], y=vol2['altitude'], mode='lines+markers', name=id_avion_2,
        line=dict(width=2), marker=dict(size=4), hovertemplate=hover))

    fig.update_layout(
        title=f"{id_avion_1} vs {id_avion_2} - Profils d'altitude",
        xaxis_title='Temps (UTC)', yaxis_title='Altitude (ft)',
        hovermode='closest', height=450,
        legend=dict(orientation='h', y=1.08))

    if altitude_range is not None:
        fig.update_yaxes(range=altitude_range)

    return fig


def profil_vertical_distance(df, callsigns, label="callsign"):
    if isinstance(callsigns, str):
        callsigns = [callsigns]
    p = None
    for cs in callsigns:
        g = df[df.callsign.eq(cs)].sort_values("timestamp")
        c = g.hvplot.line(x="cumdist", y="altitude",
                           hover_cols=["timestamp", "latitude", "longitude", "flight"]) \
            .relabel(g[label].iat[0])
        p = c if p is None else p * c

    return p.opts(title="Évolution verticale par rapport à la distance", xlabel="Distance", ylabel="Altitude (ft)")


def profil_horizontal_temps(traffic_obj, id_avion_1, id_avion_2, label=''):
    """Evolution de la distance horizontale entre deux aeronefs."""
    if hasattr(id_avion_1, 'callsign'):
        id_avion_1 = id_avion_1.callsign
    if hasattr(id_avion_2, 'callsign'):
        id_avion_2 = id_avion_2.callsign

    afficher_html(f"Evolution du rapprochement horizontal - {id_avion_1} vs {id_avion_2} | {label}",
                  style="titre")
    df = traffic_obj.data.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

    vol1 = (df[df.callsign == id_avion_1].sort_values("timestamp").set_index("timestamp"))
    vol2 = (df[df.callsign == id_avion_2].sort_values("timestamp").set_index("timestamp"))

    if vol1.empty or vol2.empty:
        afficher_html("Un des deux vols est introuvable.", style="erreur")
        return None

    commun = vol1.join(vol2, how="inner", lsuffix="_1", rsuffix="_2")

    if commun.empty:
        afficher_html("Aucun instant commun.", style="erreur")
        return None

    _, _, distance = GEOD.inv(commun["longitude_1"].values,
                               commun["latitude_1"].values, commun["longitude_2"].values,
                               commun["latitude_2"].values)

    commun["distance_nm"] = distance / 1852
    hover = (
        "<b>%{x|%H:%M:%S}</b><br>"
        "Distance horizontale : %{y:.2f} NM"
        "<extra></extra>"
    )

    fig = go.Figure()

    fig.add_trace(go.Scatter(x=commun.index,
                              y=commun["distance_nm"], mode="lines+markers",
                              name="Ecart horizontal", hovertemplate=hover))

    fig.add_hline(y=5, line_dash="dash", annotation_text="5 NM")

    fig.update_layout(title=f"{id_avion_1} vs {id_avion_2} - Ecart horizontal",
                       xaxis_title="Temps (UTC)", yaxis_title="Ecart horizontal (NM)",
                       hovermode="closest", height=450)
    return fig


def sens_deux_routes(traffic_obj):
    """Determiner si les avions sont sur la meme route, des routes convergentes
    ou en sens inverses. Utile pour le controle aux procedures."""
    vols = list(traffic_obj)
    f1, f2 = vols[0], vols[1]
    t1 = f1.data['track'].median()
    t2 = f2.data['track'].median()

    diff = abs(t1 - t2) % 360

    if diff < 45 or diff > 315:
        type_route = "Même route"
    elif 45 <= diff <= 135 or 225 <= diff <= 315:
        type_route = "Routes convergentes"
    else:
        type_route = "Routes en sens inverse"

    return (f"{f1.callsign} → {t1:.1f}°  |  {f2.callsign} → {t2:.1f}°\n"
            f"Angle : {diff:.1f}°  →  {type_route}")


# ─────── 1.6.10 Id1 - Minimum des taux de rapprochement des aeronefs ───────

def serie_Tr(df, sh_nm=10.0, sv_ft=1000.0, alt_min_ft=1000.0):
    """Serie des Tr(i,j) pour chaque couple d'aeronefs."""
    sync = Traffic(df.query('altitude >= @alt_min_ft'))

    tab = (sync.closest_point_of_approach(lateral_separation=20 * 1852,
                                          vertical_separation=2000).data)
    tab = (tab[tab['icao24_x'] < tab['icao24_y']]
           .rename(columns={
               'icao24_x': 'icao24_i',
               'callsign_x': 'aeronef_i',
               'icao24_y': 'icao24_j',
               'callsign_y': 'aeronef_j'
           }))

    tab["Trh"] = tab["lateral"] / sh_nm
    tab["Trv"] = tab["vertical"] / sv_ft
    tab["Tr"] = tab[["Trh", "Trv"]].max(axis=1)

    cols = ['timestamp', 'icao24_i', 'aeronef_i',
            'icao24_j', 'aeronef_j',
            'lateral', 'vertical',
            'Trh', 'Trv', 'Tr']

    return tab[cols].sort_values(
        ['icao24_i', 'icao24_j', 'timestamp']
    ).reset_index(drop=True)


def tab_Tr(df, **kwargs):
    """Une ligne par couple correspondant au minimum de Tr."""
    serie = serie_Tr(df, **kwargs)

    return (serie.sort_values("Tr")
            .drop_duplicates(subset=["icao24_i", "icao24_j"], keep="first")
            .reset_index(drop=True))


def conclusion_id1(Id1, tab_paires, sh_nm=10.0, sv_ft=1000.0):
    afficher_html(f"Minima de séparation appliquables pour l'étude : Horizontal = {sh_nm:g} NM, Vertical = {sv_ft:g} ft (MANEX)", style='sous_titre')

    if Id1 < 1:
        afficher_html(f"Id1 = {Id1:.3f} < 1 : au moins une perte de séparation détectée sur la periode considérée : analyse requise.", style='erreur')
        paires_infrac = tab_paires[tab_paires['Tr'] < 1]
        display(paires_infrac)
    else:
        afficher_html(f"Id1 = {Id1:.3f} ≥ 1 : minima de séparation respectés sur la période considérée", style='succes')
        display(tab_paires.head(5))


# ────────────────── 1.6.11 Id2 - Franchissement d'obstacles ────────────────

def detecter_dep_arr(df, alt_transition=ALT_TRANS, cle="icao24"):
    dep = df[(df.orig_icao == "DRRN") & (df.altitude <= alt_transition)].sort_values([cle, "timestamp"])
    arr = df[(df.dest_icao == "DRRN") & (df.altitude <= alt_transition)].sort_values([cle, "timestamp"])

    dep0 = dep[dep.altitude == 0].groupby(cle).tail(1)
    dep = pd.concat([dep[dep.altitude > 0], dep0]).sort_values([cle, "timestamp"])

    arr0 = arr[arr.altitude == 0].groupby(cle).head(1)
    arr = pd.concat([arr[arr.altitude > 0], arr0]).sort_values([cle, "timestamp"])

    dep["phase"] = "DEP"
    arr["phase"] = "ARR"

    return pd.concat([dep, arr], ignore_index=True)


THR = {"09R": (13.481611, 2.169414), "27L": (13.483233, 2.204500)}
QFU = {"09R": 87, "27L": 267}


def ecart_cap(a, b):
    return abs((a - b + 180) % 360 - 180)


def detecter_piste(df, cle="icao24", tol=30):
    out = []

    for _, g in df.groupby(cle):
        g = g.sort_values("timestamp").copy()
        p = g.iloc[0] if g.phase.iat[0] == "DEP" else g.iloc[-1]

        piste = None
        for r, (lat, lon) in THR.items():
            if ecart_cap(p.track, QFU[r]) <= tol:
                piste = r
                break

        g["piste"] = piste
        out.append(g)

    return pd.concat(out, ignore_index=True)


def ajouter_qnh(df, station="61052", coeff_ft_par_hpa=28.0):
    df = df.copy()

    df = df.drop(columns=["QNH", "QNH_estime", "altitude_qnh"], errors="ignore")

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

    debut = df["timestamp"].min().floor("h").tz_convert(None)
    fin = df["timestamp"].max().ceil("h").tz_convert(None)

    brutes = ms.hourly(station, debut, fin).fetch()

    if brutes.empty or "pres" not in brutes.columns:
        df["QNH"] = 1013.25
        df["QNH_estime"] = True
        df["altitude_qnh"] = df["altitude"] + (df["QNH"] - 1013.25) * coeff_ft_par_hpa
        return df

    qnh = (brutes.reset_index()[["time", "pres"]].rename(columns={"time": "timestamp", "pres": "QNH"}))
    qnh["timestamp"] = pd.to_datetime(qnh["timestamp"]).dt.tz_localize("UTC")

    df = pd.merge_asof(df.sort_values("timestamp"), qnh.sort_values("timestamp"),
                        on="timestamp", direction="nearest")

    df["QNH_estime"] = df["QNH"].isna()
    df["QNH"] = df["QNH"].fillna(1013.25)

    df["altitude_qnh"] = df["altitude"] + (df["QNH"] - 1013.25) * coeff_ft_par_hpa

    return df


def d_protection_pans_ops(D):
    D = min(max(D, 60), 12660)
    return 300 + 2 * (D - 60) * math.tan(math.radians(15))


def calcul_id2(df, df_obstacles):
    doublons = df_obstacles["Seuil"][df_obstacles["Seuil"].duplicated()].unique()
    if len(doublons) > 0:
        raise ValueError(f"Seuils en double dans df_obstacles : {list(doublons)}")

    obs = {r.Seuil: r for _, r in df_obstacles.iterrows()}
    pistes_valides = {"09R", "27L"}

    def obstacle(l):
        if l.piste not in pistes_valides:
            raise ValueError(f"Piste inattendue : {l.piste!r} (attendu 09R ou 27L)")
        if l.phase == "DEP":
            return obs["27L"] if l.piste == "09R" else obs["09R"]
        else:
            return obs["09R"] if l.piste == "09R" else obs["27L"]

    df = df.copy()
    df["date_vol"] = pd.to_datetime(df["timestamp"]).dt.date
    df["heure_vol"] = pd.to_datetime(df["timestamp"]).dt.time

    lignes = []

    for _, l in df.iterrows():
        o = obstacle(l)

        dh = GEOD.inv(l.longitude, l.latitude, o.lon, o.lat)[2]
        dv = l.altitude_qnh - o.alt_ft
        mfo = o.MFO_DEP_ft if l.phase == "DEP" else o.MFO_ARR_ft

        lignes.append([
            l.date_vol, l.heure_vol, l.icao24, l.callsign, l.phase, l.piste,
            o.nom, dh, dv, mfo, o.D_protection_m
        ])

    pts = pd.DataFrame(lignes, columns=[
        "date_vol", "heure_vol", "icao24", "callsign", "phase", "piste",
        "obstacle", "dh_m", "dv_ft", "mfo_ft", "d_protection_m"
    ])

    res = (pts.sort_values("dh_m")
           .groupby(["icao24", "date_vol"], as_index=False)
           .first())

    res["Txv"] = res["dv_ft"] / res["mfo_ft"]
    res["Txh"] = res["dh_m"] / res["d_protection_m"]
    res["Tx"] = res[["Txv", "Txh"]].max(axis=1)

    return res[[
        "date_vol", "heure_vol", "icao24", "callsign", "phase", "piste",
        "obstacle", "dh_m", "dv_ft", "Txh", "Txv", "Tx"
    ]]


# ──────────────────── 1.6.12 Id3 - Pertinence des STCA ─────────────────────

def extrapoler_points(traj, t0, tolerance='10s', horizon='120s', freq='10s'):
    traj = traj.sort_values('timestamp').drop_duplicates('timestamp')
    e = traj.loc[(traj['timestamp'] - t0).abs().idxmin()]
    if abs(e['timestamp'] - t0) > pd.Timedelta(tolerance):
        return None

    dt0 = (t0 - e['timestamp']).total_seconds()
    p0 = great_circle(nautical=e['gspeed'] * dt0 / 3600).destination((e['latitude'], e['longitude']), e['track'])
    h0 = e['altitude'] + e['vspeed'] * dt0 / 60

    t = pd.date_range(t0, t0 + pd.Timedelta(horizon), freq=freq)
    dt = (t - t0).total_seconds()
    pts = [great_circle(nautical=e['gspeed'] * s / 3600).destination((p0.latitude, p0.longitude), e['track']) for s in dt]

    return pd.DataFrame({
        'timestamp': t,
        'latitude': [p.latitude for p in pts],
        'longitude': [p.longitude for p in pts],
        'altitude': h0 + e['vspeed'] * dt / 60
    })


def trajectoires_predites_stca(df_stca_filtre, df_adsb, **kwargs):
    tables = {}
    for _, al in df_stca_filtre.iterrows():
        t0 = pd.Timestamp(al['Conflict From'])
        t0 = t0.tz_localize('UTC') if t0.tz is None else t0
        couple = f"{al['Aircraft']} / {al['Compared Aircraft']}"
        for cs in (al['Aircraft'], al['Compared Aircraft']):
            pts = extrapoler_points(df_adsb[df_adsb['callsign'] == cs], t0, **kwargs)
            if pts is not None:
                tables[(couple, cs)] = pts
    return tables


def Tr_couple(pts_i, pts_j, sh_nm=10.0, sv_ft=1000.0):
    p = pts_i.merge(pts_j, on='timestamp', suffixes=('_i', '_j'))
    d = [great_circle((a, b), (c, e)).nm for a, b, c, e in
         zip(p.latitude_i, p.longitude_i, p.latitude_j, p.longitude_j)]
    p["Trh"] = np.array(d) / sh_nm
    p["Trv"] = (p.altitude_i - p.altitude_j).abs() / sv_ft
    p["Tr"] = p[["Trh", "Trv"]].max(axis=1)
    return p


# ─── 1.6.13 Id4 - Ecart temporel STCA <-> premiere manoeuvre de resolution ──

def _etat_interp(g, t):
    """Position reelle interpolee de l'aeronef a l'instant t."""
    g = g.sort_values('timestamp')
    ts = g['timestamp'].astype('int64').to_numpy()
    tt = pd.Timestamp(t).value
    if len(ts) == 0 or tt < ts[0] or tt > ts[-1]:
        return None
    return (np.interp(tt, ts, g['latitude'].to_numpy()),
            np.interp(tt, ts, g['longitude'].to_numpy()),
            np.interp(tt, ts, g['altitude'].to_numpy()))


def tr_reel(df_adsb, id_i, id_j, t, cle='icao24', sh_nm=10.0, sv_ft=1000.0):
    ei = _etat_interp(df_adsb[df_adsb[cle] == id_i], t)
    ej = _etat_interp(df_adsb[df_adsb[cle] == id_j], t)
    if ei is None or ej is None:
        return None
    d_nm = GEOD.inv(ei[1], ei[0], ej[1], ej[0])[2] / 1852.0
    dalt = abs(ei[2] - ej[2])
    return max(d_nm / sh_nm, dalt / sv_ft)


def indicateur_id4(al_df, dfa, cle='icao24', horizon='120s', sh_nm=10., sv_ft=1000.):
    """Id4 : ecart entre conflict_from et l'instant ou la separation cesse de retrecir
    et recommence a augmenter (CPA reel). Cas Tr_extrapol < 1 uniquement."""
    out = []
    for _, a in al_df[al_df['Tr_extrapol'] < 1].iterrows():
        t0 = pd.Timestamp(a['conflict_from'])
        t0 = t0.tz_localize('UTC') if t0.tz is None else t0
        i, j = a[f'{cle}_i'], a[f'{cle}_j']

        ts = pd.Index(sorted(set(dfa.loc[dfa[cle] == i, 'timestamp']) |
                              set(dfa.loc[dfa[cle] == j, 'timestamp'])))

        ts = ts[(ts >= t0) & (ts <= t0 + pd.Timedelta(horizon))]

        s = pd.Series({t: v for t in ts
                       if (v := tr_reel(dfa, i, j, t, cle, sh_nm, sv_ft)) is not None})

        r = dict(icao24_i=a['icao24_i'], icao24_j=a['icao24_j'], callsign_i=a['callsign_i'],
                 callsign_j=a['callsign_j'], conflict_from=t0, Resolution_time=pd.NaT,
                 Id4=np.nan, Tr=np.nan)
        if not s.empty:
            k = int(np.argmin(s.values))
            r.update(Resolution_time=s.index[k], Id4=(s.index[k] - t0).total_seconds(),
                     Tr=float(s.values[k]), cpa_hors_fenetre=(k == len(s) - 1))
        out.append(r)
    return pd.DataFrame(out)


# ──────────────── 1.6.14 Id5 - Alignement axe de piste ─────────────────────

def _nm(lat, lon, ref):
    return GEOD.inv(lon, lat, ref[1], ref[0])[2] / 1852.0


def _diff_ang(a, b):
    return (a - b + 180) % 360 - 180


def construire_df_app(df, cle='icao24', r_iaf=5.0, r_thr=2.0, brg=BRG_TRUE, tol=5.0):
    """Arrivees 09R : segment RITAT -> premier toucher (eviter les virages pour degager la piste).
       Tolerance de tol deg sur les cap entre IAF/IF RITAT et le FAF/FAP RN501 (retrait des virages)"""
    df = df[df["source"] == "ADSB"].copy()
    segs = []
    for vid, g in df.groupby(cle):
        g = g.sort_values('timestamp').reset_index(drop=True)
        sol = g.index[g['altitude'] == 0]
        if len(sol) == 0:
            continue
        i_td = sol[0]
        if _nm(g.loc[i_td, 'latitude'], g.loc[i_td, 'longitude'], THR09R) > r_thr:
            continue
        avant = g.loc[:i_td]
        d_iaf = avant.apply(lambda r: _nm(r.latitude, r.longitude, RITAT), axis=1)
        if d_iaf.min() > r_iaf:
            continue
        seg = g.loc[d_iaf.idxmin():i_td].copy()
        if seg['altitude'].iloc[0] <= 0:
            continue
        i_faf = seg.apply(lambda r: _nm(r.latitude, r.longitude, RN501), axis=1).idxmin()
        pos = seg.index.get_loc(i_faf)
        avant_faf = seg.iloc[:pos]
        avant_faf = avant_faf[_diff_ang(avant_faf['track'], brg).abs() <= tol]
        apres_faf = seg.iloc[pos:]
        seg = pd.concat([avant_faf, apres_faf])
        if seg.empty:
            continue
        segs.append(seg)
    return pd.concat(segs, ignore_index=True) if segs else pd.DataFrame()


def construire_df_final(df, cle='icao24', r_faf=2.0, r_thr=2.0):
    """Final 09R : segment FAF/FAP RN501 -> premier toucher
        (eviter les virages pour degager la piste)"""
    df = df[df["source"] == "ADSB"].copy()
    segs = []
    for vid, g in df.groupby(cle):
        g = g.sort_values('timestamp').reset_index(drop=True)
        sol = g.index[g['altitude'] == 0]
        if len(sol) == 0:
            continue
        i_td = sol[0]
        if _nm(g.loc[i_td, 'latitude'], g.loc[i_td, 'longitude'], THR09R) > r_thr:
            continue
        avant = g.loc[:i_td]
        d_faf = avant.apply(lambda r: _nm(r.latitude, r.longitude, RN501), axis=1)
        if d_faf.min() > r_faf:
            continue
        seg = g.loc[d_faf.idxmin():i_td].copy()
        if seg['altitude'].iloc[0] <= 0:
            continue
        segs.append(seg)
    return pd.concat(segs, ignore_index=True) if segs else pd.DataFrame()


frame = nv.FrameE(name="WGS84")
p_faf = frame.GeoPoint(latitude=RN501[0], longitude=RN501[1], degrees=True)
p_thr = frame.GeoPoint(latitude=THR09R[0], longitude=THR09R[1], degrees=True)
axe_final = nv.GeoPath(p_faf, p_thr)  # La droite FAF - THR09R


def ecart_lateral_m(lat, lon):
    point = frame.GeoPoint(latitude=lat, longitude=lon, degrees=True)
    return abs(axe_final.cross_track_distance(point, method="greatcircle"))


def interpretation_ecart(val):
    if pd.isna(val):
        return np.nan
    if val <= 5:
        return "Très bien aligné "
    elif val <= 10:
        return "Bien aligné "
    elif val <= 20:
        return "Alignement acceptable "
    elif val <= 50:
        return "Décalé "
    elif val <= 100:
        return "Fortement décalé"
    else:
        return "Hors bord de piste "


def interpretation_instabilite(val):
    if pd.isna(val):
        return np.nan
    if val <= 10:
        return "Stable"
    elif val <= 20:
        return "Assez stable"
    elif val <= 40:
        return "Instable"
    else:
        return "Très instable"


def id5_alignement(df_app, cle="icao24"):
    demi_largeur = LARGEUR / 2
    lignes = []

    for _, g in df_app.groupby(cle):
        g = g.sort_values("timestamp")
        d = g.apply(lambda r: ecart_lateral_m(r.latitude, r.longitude), axis=1)

        dmoy = np.abs(d).mean()
        sigma = d.std()
        id5_ecart = 100 * dmoy / demi_largeur
        id5_instab = 100 * sigma / demi_largeur

        lignes.append({
            "Date": g["timestamp"].iloc[-1].date(),
            "Heure_arrivee": g["timestamp"].iloc[-1].strftime("%H:%M:%S"),
            "icao24": g["icao24"].iloc[0],
            "Callsign": g["callsign"].iloc[0],
            "Ecart_moy_m": round(dmoy, 1),
            "Id5_ecart (%)": round(id5_ecart, 1),
            "Interpretation_ecart": interpretation_ecart(id5_ecart),
            "Sigma_m": round(sigma, 1),
            "Id5_instabilite (%)": round(id5_instab, 1),
            "Interpretation_instabilite": interpretation_instabilite(id5_instab)
        })

    return pd.DataFrame(lignes).sort_values(["Date", "Heure_arrivee"])


# ────────────── 1.6.15 Id6 - Allongement effectif (KPI05 GANP) ─────────────

def construire_route_fpl(df_calc_fpl, navaids_wps_uta):
    routes = []
    wp_set = set(navaids_wps_uta["name"].astype(str).str.upper())
    for cs, g in df_calc_fpl.groupby("callsign"):
        g = g.sort_values("timestamp")
        texte = g["Texte_fpl"].dropna().iloc[0]
        mots = re.findall(r"\b[A-Z0-9]{2,10}\b", texte.upper())
        wp_ordonnes = []
        deja_vus = set()

        for m in mots:
            if m in wp_set and m not in deja_vus:
                wp_ordonnes.append(m)
                deja_vus.add(m)

        route = [{"ordre": 0, "point": "ENTREE_UTA", "latitude": g.iloc[0]["latitude"],
                  "longitude": g.iloc[0]["longitude"]}]

        for k, wp in enumerate(wp_ordonnes, start=1):
            r = navaids_wps_uta.loc[navaids_wps_uta["name"].str.upper() == wp].iloc[0]
            route.append({"ordre": k, "point": wp, "latitude": r["latitude"],
                          "longitude": r["longitude"]})

        route.append({"ordre": len(route), "point": "SORTIE_UTA", "latitude": g.iloc[-1]["latitude"],
                      "longitude": g.iloc[-1]["longitude"]})

        df_route = pd.DataFrame(route)
        df_route["callsign"] = cs
        routes.append(df_route)

    return pd.concat(routes, ignore_index=True)


def calcul_dfpl(route_fpl):
    res = []
    for cs, g in route_fpl.groupby("callsign"):
        g = g.sort_values("ordre")
        d_fpl = 0
        for i in range(len(g) - 1):
            lat1, lon1 = g.iloc[i][["latitude", "longitude"]]
            lat2, lon2 = g.iloc[i + 1][["latitude", "longitude"]]
            d_fpl += GEOD.inv(lon1, lat1, lon2, lat2)[2]
        res.append({"callsign": cs, "D_FPL_nm": d_fpl / 1852})
    return pd.DataFrame(res)


def calcul_dreal(df_adsb):
    res = []
    for cs, g in df_adsb.groupby("callsign"):
        g = g.sort_values("timestamp")
        d_real = 0
        for i in range(len(g) - 1):
            lat1, lon1 = g.iloc[i][["latitude", "longitude"]]
            lat2, lon2 = g.iloc[i + 1][["latitude", "longitude"]]
            d_real += GEOD.inv(lon1, lat1, lon2, lat2)[2]
        res.append({"callsign": cs, "D_REEL_nm": d_real / 1852})
    return pd.DataFrame(res)


# ─────────────── 1.6.16 Id8 - Emissions de CO2 (via OpenAP) ────────────────

def construire_df_uta_openap(df, contour_uta_arg, FPL, BILLING):
    """Cette fonction collecte les survols dans l'UTA disposant d'un plan de vol (FPL)
     et dont le type d'aeronef est compatible avec OpenAP"""
    df = nettoyer_positions_altitudes(df, alt_min=0, alt_max=65000)
    df_uta, _ = filtrer_d(df, contour_uta_arg)

    callsigns = FPL["Texte"].str.extract(r"-([^/-]+)(?:/[^-]*)?-", expand=False)

    vols = BILLING.loc[(BILLING["Operation_Type"] == "OVF") &
                        (BILLING["Date"] == pd.Timestamp("2026-04-10")) &
                        (BILLING["Callsign"].isin(callsigns)), ["Callsign", "Type"]
                        ]
    types_openap = {a.upper() for a in prop.available_aircraft()}
    return (df_uta.merge(vols, left_on="callsign", right_on="Callsign")
            .loc[lambda d: d["Type"].str.upper().isin(types_openap)].copy())


def construire_df_mtow(df):
    vols = df[["callsign", "Type"]].drop_duplicates().copy()
    vols["MTOW_kg"] = vols["Type"].apply(lambda t: prop.aircraft(t.upper())["mtow"])
    return vols.sort_values("callsign").reset_index(drop=True)


# ─────────────────── 1.6.17 Tolerance sur les calculs ──────────────────────

def ajouter_tolerance(df, ind, pr_h=10, pr_v=25):
    df = df.copy()
    dd = pr_h / 2.448 * np.sqrt(2) * norm.ppf(0.95)
    dnm = dd / 1852

    if ind == "Id1":
        df["Tol_Tr"] = np.maximum(dd / (df.lateral * 1852), pr_v / df.vertical)

    elif ind == "Id2":
        df["Tol_marge"] = dnm

    elif ind == "Id5":
        t = 100 * dd / (LARGEUR / 2)
        df["Tol_ecart (%)"] = df["Tol_instabilite (%)"] = t

    elif ind == "Id6":
        df["Tol_Id6 (%)"] = 100 * dnm / df.D_FPL_nm

    elif ind == "Id7":
        dff = df.FF_nm * dnm / df.D_REEL_nm
        df["Tol_kg"] = np.sqrt(((df.D_REEL_nm - df.D_FPL_nm) * dff) ** 2 + (df.FF_nm * dnm) ** 2)

    elif ind == "Id8":
        df["Tol_kg"] = pd.to_numeric(df["Tol_kg"])
        df["Tol_kgCO2"] = 3.16 * df["Tol_kg"]

    tol = [c for c in df.columns if c.startswith("Tol_")]
    df[tol] = df[tol].apply(lambda s: s.map(lambda x: f"{x:.5f}" if pd.notna(x) else ""))

    return df


# ────────────────────── 1.6.18 Analyse exploratoire ────────────────────────

def formater_plages_dates(dates):
    """Regroupe des dates en plages continues, separees par ' | ' si non consecutives."""
    dates = sorted(pd.to_datetime(pd.Series(dates)).dt.date.unique())
    plages = []
    debut = dates[0]
    prec = dates[0]
    for d in dates[1:]:
        if (d - prec).days > 1:
            plages.append((debut, prec))
            debut = d
        prec = d
    plages.append((debut, prec))

    texte = []
    for deb, fin in plages:
        if deb == fin:
            texte.append(deb.strftime("%d/%m/%Y"))
        else:
            texte.append(f"{deb.strftime('%d/%m/%Y')} au {fin.strftime('%d/%m/%Y')}")
    return " | ".join(texte)


def synthese_fr24(df_fr24, aerodromes_locaux=None):
    df = df_fr24.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

    n_lignes = len(df)
    n_vols = df["icao24"].nunique()

    dates_uniques = df["timestamp"].dt.tz_convert(None).dt.date.unique()
    jours_couverts = formater_plages_dates(dates_uniques)

    resultats = {
        "Nombre de lignes": n_lignes,
        "Nombre de vol": n_vols,
        "Jours couverts": jours_couverts,
    }

    if aerodromes_locaux:
        vols_info = df.groupby("icao24").agg(
            orig_icao=("orig_icao", "first"),
            dest_icao=("dest_icao", "first"),
        )
        is_dep = vols_info["orig_icao"].isin(aerodromes_locaux)
        is_arr = vols_info["dest_icao"].isin(aerodromes_locaux)

        resultats["ARRIVEES"] = int((is_arr & ~is_dep).sum())
        resultats["DEPARTS"] = int((is_dep & ~is_arr).sum())
        resultats["SURVOLS"] = int((~is_dep & ~is_arr).sum())

    return pd.DataFrame(resultats.items(), columns=["Indicateur", "Valeur"])


def tableau_sources(df_fr24, col_source="source", col_callsign="callsign"):
    """
    Nombre de vols distincts ayant eu au moins une position recue
    par chaque source (ADS-B, MLAT, etc.).
    """
    tableau = (
        df_fr24.groupby(col_source)[col_callsign]
        .nunique()
        .rename("Nb_vols")
        .sort_values(ascending=False)
        .to_frame()
    )
    tableau["Part (%)"] = (100 * tableau["Nb_vols"] / df_fr24[col_callsign].nunique()).round(1)
    return tableau


def vols_uta_billing(BILLING, navaids, poly_uta, jour):
    """Vols du Billing d'une journee traversant l'UTA.
       ARR et DEP retenus d'office, OVF retenus si la route directe entree-sortie coupe l'UTA."""
    df = BILLING[BILLING["Date"] == pd.Timestamp(jour)].copy()

    ref = (navaids.data[["name", "latitude", "longitude"]]
           .drop_duplicates("name").set_index("name"))

    def coords(nom):
        if nom in ref.index:
            p = ref.loc[nom]
            p = p.iloc[0] if isinstance(p, pd.DataFrame) else p
            return p["latitude"], p["longitude"]
        return None, None

    def dans_uta(row):
        if row["Operation_Type"] in ("ARR", "DEP"):
            return True
        lat_e, lon_e = coords(row["Position1"])
        lat_s, lon_s = coords(row["Position2"])
        if None in (lat_e, lon_e, lat_s, lon_s):
            return False
        return LineString([(lon_e, lat_e), (lon_s, lat_s)]).intersects(poly_uta)

    df["Dans_UTA"] = df.apply(dans_uta, axis=1)
    return df[df["Dans_UTA"]].copy()


def comparer_fr24_reel(df_fr24, df_billing, aerodrome="DRRN"):
    def cat(orig, dest):
        if dest == aerodrome:
            return "ARRIVEES"
        if orig == aerodrome:
            return "DEPARTS"
        return "SURVOLS"
    f = df_fr24.drop_duplicates("icao24")
    n_fr24 = f.apply(lambda r: cat(r["orig_icao"], r["dest_icao"]), axis=1).value_counts()

    map_ope = {"ARR": "ARRIVEES", "DEP": "DEPARTS", "OVF": "SURVOLS"}
    n_reel = df_billing["Operation_Type"].map(map_ope).value_counts()

    j_fr24 = f"{df_fr24['timestamp'].min():%d/%m/%Y} au {df_fr24['timestamp'].max():%d/%m/%Y}"
    j_reel = f"{df_billing['Date'].min():%d/%m/%Y} au {df_billing['Date'].max():%d/%m/%Y}"

    lignes = [{"Indicateur": "Jours couverts", "Valeur_FR24": j_fr24, "Valeur_Reel": j_reel}]
    for c in ["ARRIVEES", "DEPARTS", "SURVOLS"]:
        lignes.append({"Indicateur": c,
                       "Valeur_FR24": int(n_fr24.get(c, 0)),
                       "Valeur_Reel": int(n_reel.get(c, 0))})
    tab = pd.DataFrame(lignes)
    tab["% FR24/Reel"] = tab.apply(
        lambda r: round(100 * r["Valeur_FR24"] / r["Valeur_Reel"], 1)
        if isinstance(r["Valeur_FR24"], int) and r["Valeur_Reel"] else "", axis=1)
    return tab


def trouver_fpl(callsign, type, fpl_filtered_by_callsign):
    """NB : le notebook original referencait `fpl_filtered_by_callsign` en
    variable globale de cellule. Ici le dataframe est passe explicitement en
    parametre (seul changement : signature, la logique interne est identique)
    car il n'existe pas de cellule Jupyter equivalente dans Streamlit."""
    fpls = fpl_filtered_by_callsign[fpl_filtered_by_callsign
                                     .str.contains(rf"-{callsign}", case=False, na=False)]
    fpls = fpls[fpls.str.contains(str(type), case=False, na=False)]
    return fpls.iloc[0] if len(fpls) else None
