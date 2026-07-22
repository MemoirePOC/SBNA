 # -*- coding: utf-8 -*-
"""
Pipeline de chargement (ex Modules 2, 3, 4, 6 du notebook).

Toute la logique (quelles fonctions appeler, dans quel ordre, sur quels
fichiers) est copiee telle quelle depuis le notebook. Le seul changement :
c'est regroupe dans une fonction unique, mise en cache par Streamlit
(@st.cache_resource), pour n'etre executee qu'une seule fois par session
au lieu d'etre relancee a chaque interaction utilisateur - un notebook
Jupyter ne s'execute qu'une fois "a la main", Streamlit relance le script
a chaque clic, d'ou la necessite du cache.
"""

from dataclasses import dataclass, field
from typing import Any

import pandas as pd
import streamlit as st

from traffic.core import Traffic
from traffic.data import navaids
from shapely.geometry import Point, Polygon as SPolygon

from src import config as cfg
from src import functions as fn


@dataclass
class PoCData:
    """Conteneur simple pour toutes les donnees chargees/nettoyees."""
    # Espaces aeriens
    contour_tma1: Any = None
    contour_tma2: Any = None
    contour_uta: Any = None
    poly_uta: Any = None
    sommets_tma2: Any = None
    centres_tma2: Any = None

    # Datasets bruts / nettoyes
    df_tma_general_net: Any = None
    df_tma_general2_net: Any = None
    df_tma_general3_net: Any = None
    df_tma_general4_net: Any = None
    df_airprox_net: Any = None
    df_stca1_net: Any = None
    df_stca2_net: Any = None
    df_stca3_net: Any = None
    df_stca_ssr_net: Any = None
    df_rmg1_net: Any = None
    df_rmg2_net: Any = None
    df_depart_net: Any = None
    df_approach_net: Any = None

    df_STCA: Any = None
    df_MSAW: Any = None
    FPL: Any = None
    BILLING: Any = None
    OBSTACLES: Any = None
    df_obstacles: Any = None

    # Objets Traffic
    Vols: Any = None
    APX: Any = None
    STCA1: Any = None
    STCA2: Any = None
    STCA3: Any = None
    RMG_2025: Any = None
    RMG_2024: Any = None
    SSR: Any = None

    # Derives (Modules 6-7)
    DATASET: Any = None
    df_uta: Any = None
    poly_uta_shapely: Any = None
    navaids_wps_uta: Any = None
    vols_uta: Any = None

    # STCA candidats a l'airprox (Module 10.1-10.3)
    df_adsb_stca: Any = None
    df_STCA_cand: Any = None


def _construire_df_stca_candidats(df_STCA, df_stca_ssr_net):
    """Reprend exactement les cellules du Module 10.1 a 10.3 du notebook :
    identification des alertes STCA (par callsign, ou par correspondance
    SSR->callsign via la projection stereographique Topsky)."""

    df_STCA_filtre = df_STCA[df_STCA['Aircraft'].notna() & df_STCA['Compared Aircraft'].notna()].copy()

    df_STCA_nan = df_STCA.drop(df_STCA_filtre.index)
    df_STCA_ssr_valid = df_STCA_nan[
        (df_STCA_nan['Aircraft SSR-Code'] != 0) &
        (df_STCA_nan['Compared Aircraft SSR-COde'] != 0) &
        (df_STCA_nan['Aircraft SSR-Code'] != df_STCA_nan['Compared Aircraft SSR-COde'])
    ]

    scale = 1852.0
    longitudes_ac, latitudes_ac = cfg.proj_niamey(
        df_STCA_ssr_valid['Aircraft Pos X'].values * scale,
        df_STCA_ssr_valid['Aircraft Pos Y'].values * scale, inverse=True)

    longitudes_comp, latitudes_comp = cfg.proj_niamey(
        df_STCA_ssr_valid['Compared Aircraft Pos X'].values * scale,
        df_STCA_ssr_valid['Compared Aircraft Pos Y'].values * scale, inverse=True)

    df_STCA_ssr_valid = df_STCA_ssr_valid.assign(
        Aircraft_Lat=latitudes_ac, Aircraft_Lon=longitudes_ac,
        Compared_Lat=latitudes_comp, Compared_Lon=longitudes_comp)

    squawk_to_callsign = (df_stca_ssr_net.dropna(subset=["callsign"]).drop_duplicates(subset=["squawk"])
                          .set_index("squawk")["callsign"])

    df_STCA_identifie = df_STCA_ssr_valid.copy()
    mask_aircraft = df_STCA_identifie["Aircraft"].isna()
    df_STCA_identifie.loc[mask_aircraft, "Aircraft"] = (
        df_STCA_identifie.loc[mask_aircraft, "Aircraft SSR-Code"].map(squawk_to_callsign))

    mask_compared = df_STCA_identifie["Compared Aircraft"].isna()
    df_STCA_identifie.loc[mask_compared, "Compared Aircraft"] = (
        df_STCA_identifie.loc[mask_compared, "Compared Aircraft SSR-COde"].map(squawk_to_callsign))

    df_STCA_identifie = df_STCA_identifie[df_STCA_filtre.columns]
    df_STCA_cand = pd.concat([df_STCA_filtre, df_STCA_identifie], ignore_index=True)
    return df_STCA_cand


def _load_pipeline_impl() -> PoCData:
    d = PoCData()

    # ── Module 3 : espaces aeriens ─────────────────────────────────────────
    d.contour_tma1, _, _, _ = fn.construire_polygone_tma1()
    d.contour_tma2, d.sommets_tma2, d.centres_tma2, _ = fn.construire_polygone_tma2()
    d.contour_uta, _, _, d.poly_uta = fn.construire_polygone_uta()

    # Rend contour_uta disponible aux fonctions qui le lisent en global
    # (filtrer_d, creer_carte_base), exactement comme dans le notebook.
    fn.contour_uta = d.contour_uta

    # ── Module 2 : chargement des fichiers ──────────────────────────────────
    df_tma_general = fn.charger_dossier_concatener(cfg.TMA_GENERAL_DIR, parse_dates=['timestamp', 'query_timestamp_utc'])
    df_tma_general2 = fn.charger_dossier_concatener(cfg.TMA_GENERAL_DIR2, parse_dates=['timestamp', 'query_timestamp_utc'])
    df_tma_general3 = fn.charger_dossier_concatener(cfg.TMA_GENERAL_DIR3, parse_dates=['timestamp', 'query_timestamp_utc'])
    df_tma_general4 = fn.charger_dossier_concatener(cfg.TMA_GENERAL_DIR4, parse_dates=['timestamp', 'query_timestamp_utc'])

    d.df_STCA = fn.charger_donnees(cfg.FICHIER_STCA)
    df_stca1 = fn.charger_dossier_concatener(cfg.STCA1_DIR, parse_dates=['timestamp'])
    df_stca2 = fn.charger_dossier_concatener(cfg.STCA2_DIR, parse_dates=['timestamp'])
    df_stca3 = fn.charger_dossier_concatener(cfg.STCA3_DIR, parse_dates=['timestamp'])
    df_stca_ssr = fn.charger_dossier_concatener(cfg.STCA_SSR_DIR, parse_dates=['timestamp'])

    df_FPL = fn.charger_fpl(cfg.FPL_DIR)
    d.df_MSAW = fn.charger_donnees(cfg.FICHIER_MSAW)
    df_billing = fn.lire_fichiers_billing(cfg.BILLING_DIR)

    df_airprox = fn.charger_dossier_concatener(cfg.AIRPROX_DIR, parse_dates=['timestamp'])
    df_approach = fn.charger_dossier_concatener(cfg.APPROCHE_DIR, parse_dates=['timestamp'])
    df_rmg1 = fn.charger_donnees(cfg.RMG_DIR + 'RMG1_2025-04-24.csv')
    df_rmg2 = fn.charger_donnees(cfg.RMG_DIR + 'RMG3_2024-09-15.csv')
    df_depart = fn.charger_dossier_concatener(cfg.DEP_DIR, parse_dates=['timestamp'])

    d.OBSTACLES = fn.charger_donnees(cfg.Obstacles)

    # ── Module 4 : nettoyage des identifiants + objets Traffic ─────────────
    d.df_tma_general_net = fn.nettoyer_identifiants(df_tma_general, 'TMA_GENERAL')
    d.df_tma_general2_net = fn.nettoyer_identifiants(df_tma_general2, 'TMA_GENERAL')
    d.df_tma_general3_net = fn.nettoyer_identifiants(df_tma_general3, 'TMA_GENERAL')
    d.df_tma_general4_net = fn.nettoyer_identifiants(df_tma_general4, 'TMA_GENERAL')
    d.df_airprox_net = fn.nettoyer_identifiants(df_airprox, 'AIRPROX')
    d.df_stca1_net = fn.nettoyer_identifiants(df_stca1, 'STCA1')
    d.df_stca2_net = fn.nettoyer_identifiants(df_stca2, 'STCA2')
    d.df_stca3_net = fn.nettoyer_identifiants(df_stca3, 'STCA3')
    d.df_rmg1_net = fn.nettoyer_identifiants(df_rmg1, 'RMG_2025')
    d.df_rmg2_net = fn.nettoyer_identifiants(df_rmg2, 'RMG_2024')
    d.df_depart_net = fn.nettoyer_identifiants(df_depart, 'DEPARTS')
    d.df_approach_net = fn.nettoyer_identifiants(df_approach, 'APP')
    d.df_stca_ssr_net = fn.nettoyer_identifiants(df_stca_ssr, 'STCA_SSR')

    d.Vols = Traffic(d.df_tma_general_net)
    d.APX = Traffic(d.df_airprox_net)
    d.STCA1 = Traffic(d.df_stca1_net)
    d.STCA2 = Traffic(d.df_stca2_net)
    d.STCA3 = Traffic(d.df_stca3_net)
    d.RMG_2025 = Traffic(d.df_rmg1_net)
    d.RMG_2024 = Traffic(d.df_rmg2_net)
    d.SSR = Traffic(d.df_stca_ssr_net)

    df_FPL.columns = df_FPL.columns.str.lstrip()
    FPL = df_FPL[df_FPL['Texte'].fillna("").str.strip().ne("")].iloc[:, :-1]
    d.FPL = FPL.drop_duplicates(subset=['Texte'], keep="first")

    d.BILLING = df_billing.drop_duplicates().reset_index(drop=True).copy()
    d.BILLING.columns = d.BILLING.columns.str.lstrip()
    d.BILLING['Date'] = pd.to_datetime(d.BILLING['Date'])

    # ── Module 6 : nettoyage positions/altitudes + filtrage geographique ───
    df_clean = fn.nettoyer_positions_altitudes(d.df_tma_general2_net, alt_min=0, alt_max=65000)
    d.df_uta, d.poly_uta_shapely = fn.filtrer_d(df_clean, d.contour_uta)

    d.DATASET = pd.concat([d.df_tma_general_net, d.df_tma_general2_net, d.df_tma_general3_net, d.df_tma_general4_net])

    d.vols_uta = fn.vols_uta_billing(d.BILLING, navaids, d.poly_uta_shapely, "2026-04-08")

    # Waypoints/navaids situes dans le contour de l'UTA (utilise au Module 13)
    poly = SPolygon([(lon, lat) for lat, lon in d.contour_uta])
    wps = navaids.data
    d.navaids_wps_uta = wps[wps.apply(lambda r: poly.intersects(Point(r.longitude, r.latitude)), axis=1)]

    # ── Referentiel obstacles (Module 9) avec D_protection_m ────────────────
    d.df_obstacles = cfg.df_obstacles.copy()
    d.df_obstacles["D_protection_m"] = d.df_obstacles["D_seuil_m"].apply(fn.d_protection_pans_ops)

    # ── STCA candidats a l'airprox + dataset ADS-B combine (Modules 10-11) ──
    d.df_adsb_stca = pd.concat(
        [d.df_stca1_net, d.df_stca2_net, d.df_stca3_net, d.df_stca_ssr_net], ignore_index=True)
    d.df_STCA_cand = _construire_df_stca_candidats(d.df_STCA, d.df_stca_ssr_net)

    return d


@st.cache_resource(show_spinner="Chargement et nettoyage des données PoC (Modules 1 à 7)…")
def load_pipeline() -> PoCData:
    """Version mise en cache de _load_pipeline_impl().

    Rend `display()`/`print()` silencieux le temps du chargement : ce sont
    de simples journaux de nettoyage (nettoyer_identifiants, etc.), pas des
    resultats a montrer. Sans ca, Streamlit rejoue ce journal sur CHAQUE
    page qui appelle load_pipeline() pour la premiere fois (comportement du
    cache), au lieu de l'afficher une seule fois. Aucune fonction n'est
    modifiee : on echange juste temporairement ce que `display`/`print`
    pointent, le temps de l'appel.
    """
    original_display, original_print = fn.display, fn.print
    fn.display = lambda *args, **kwargs: None
    fn.print = lambda *args, **kwargs: None
    try:
        return _load_pipeline_impl()
    finally:
        fn.display = original_display
        fn.print = original_print