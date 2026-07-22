# -*- coding: utf-8 -*-
"""
Page d'accueil du PoC Streamlit.

Presentation, objectifs, carte de la zone d'etude et statistiques generales.
Le chargement/nettoyage des donnees (Modules 1 a 7 du notebook) est
declenche ici, une seule fois grace au cache (voir src/pipeline.py) : le
"journal" de nettoyage qui s'affiche plus bas la premiere fois que l'app
demarre correspond exactement aux tableaux produits par nettoyer_identifiants()
dans le notebook.
"""

import streamlit as st
from streamlit_folium import st_folium

from src import pipeline
from src import functions as fn
from src import maps

st.set_page_config(page_title="PoC ATS Niamey", page_icon="✈️", layout="wide")

st.title("PoC — Sécurité et performance ATS, espace aérien du Niger (Niamey)")

st.markdown(
    """
Cette application est la démonstration opérationnelle du Proof of Concept (PoC) réalisé dans le cadre du
mémoire d'ingénieur *« Analyse des données de surveillance du trafic aérien à des fins de sécurité et
performance ATS : démonstration de la valeur opérationnelle d'un dataset de trajectoires aériennes pour
l'ASECNA — cas de l'espace aérien du Niger »*.

Elle réutilise **telles quelles** les fonctions Python développées et validées dans le notebook du PoC ;
seule la couche d'affichage est adaptée à Streamlit.
"""
)

st.subheader("Objectifs")
st.markdown(
    """
- Calculer des indicateurs de **sécurité ATS** (Id1 à Id5) à partir des données ADS-B FlightRadar24,
  croisées avec les plans de vol (FPL), le Billing, les filets STCA/MSAW et le référentiel d'obstacles de DRRN.
- Calculer des indicateurs de **performance ATS** (Id6/KPI05, Id7/KPI16, Id8) : allongement de trajectoire,
  surconsommation de carburant et émissions de CO₂ liées au guidage radar.
- Démontrer que ces traitements, validés dans le notebook, sont exploitables au travers d'une interface
  opérationnelle simple.
"""
)

st.subheader("Zone d'étude")
st.caption("UTA Niamey (FL245–FL460, rouge), TMA2 (FL145–FL245, vert) et TMA1 (FL145–Sol, bleu), AIP ASECNA.")

carte = maps.afficher_toutes_zones()
st_folium(carte, width=None, height=500, returned_objects=[])

st.divider()
st.subheader("Chargement des données du PoC")
st.caption(
    "Chargement, nettoyage et construction des espaces aériens (Modules 1 à 7 du notebook). "
    "Mis en cache : ne s'exécute qu'une seule fois."
)

with st.spinner("Chargement…"):
    data = pipeline.load_pipeline()

st.divider()
st.subheader("Statistiques générales")

synthese = fn.synthese_fr24(data.DATASET, aerodromes_locaux=["DRRN"])
col1, col2 = st.columns([1, 1])
with col1:
    st.dataframe(synthese, use_container_width=True, hide_index=True)
with col2:
    st.metric("Nombre de vols (dataset combiné)", int(data.DATASET["icao24"].nunique()))
    st.metric("Plans de vol FPL chargés", len(data.FPL))
    st.metric("Alertes STCA (avril 2026)", len(data.df_STCA))
    st.metric("Alertes MSAW (avril 2026)", len(data.df_MSAW))

st.info("Utilisez le menu à gauche pour accéder aux pages Exploration, Sécurité, Performance et Démonstration.")
