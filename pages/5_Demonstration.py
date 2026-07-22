# -*- coding: utf-8 -*-
"""
Page Démonstration : sélection d'un conflit parmi les cas illustratifs déjà
étudiés et commentés dans le notebook (Modules 10, 11 et 13), affichage de
la trajectoire, de la carte et des résultats calculés.

Cas fixes (validés avec l'auteur du mémoire) plutôt qu'une sélection
dynamique parmi toutes les paires détectées : on reste fidèle aux exemples
déjà analysés dans le mémoire.
"""

import streamlit as st
from streamlit_folium import st_folium
from traffic.core import Traffic

from src import pipeline
from src import functions as fn
from src import maps
from src.config import CAS_DEMONSTRATION

st.set_page_config(page_title="Démonstration — PoC ATS Niamey", page_icon="🎯", layout="wide")
st.title("🎯 Démonstration — cas de conflit illustratifs")

data = pipeline.load_pipeline()

nom_cas = st.selectbox("Choisir un cas à démontrer", list(CAS_DEMONSTRATION.keys()))
cas = CAS_DEMONSTRATION[nom_cas]

st.subheader(cas["label"])

if cas["type"] in ("stca_pair", "airprox_pair"):
    cs1, cs2 = cas["callsigns"]

    # Traffic source correspondant au cas (mêmes objets que le notebook)
    source_map = {
        "stca_ssr": data.SSR,
        "adsb_stca": Traffic(data.df_adsb_stca),
        "apx": data.APX,
    }
    traffic_obj = source_map[cas["traffic_source"]]

    col_map, col_res = st.columns([2, 1])

    with col_map:
        st.markdown("**Trajectoires**")
        carte = maps.trac_trajectoires(traffic_obj, [cs1, cs2], zoom=6)
        st_folium(carte, width=None, height=450, key=f"carte_{nom_cas}", returned_objects=[])

    with col_res:
        st.markdown("**Résultats calculés (Id1 — Tr au point de rapprochement le plus proche)**")
        sous_traffic = traffic_obj.query(f'callsign == "{cs1}" or callsign == "{cs2}"')
        if sous_traffic is not None and len(list(sous_traffic)) >= 2:
            resultat = fn.tab_Tr(sous_traffic.data)
            resultat = fn.ajouter_tolerance(resultat, "Id1")
            st.dataframe(resultat, use_container_width=True)
            try:
                st.text(fn.sens_deux_routes(sous_traffic))
            except Exception:
                pass
        else:
            st.warning("Trajectoires insuffisantes dans ce dataset pour recalculer Tr sur ce couple.")

    st.markdown("**Profil vertical**")
    fig_v = fn.profil_vertical_temps(traffic_obj, cs1, cs2, label=cas["label"], altitude_range=cas["altitude_range"])
    if fig_v is not None:
        st.plotly_chart(fig_v, use_container_width=True)

    st.markdown("**Profil horizontal (écart entre les deux aéronefs)**")
    fig_h = fn.profil_horizontal_temps(traffic_obj, cs1, cs2, label=cas["label"])
    if fig_h is not None:
        st.plotly_chart(fig_h, use_container_width=True)

    if cas["traffic_source"] == "stca_ssr":
        st.caption(
            "Ce STCA du 16/04/2026 conduit à un airprox reconstruit entre 22:43:18 et 22:43:57 "
            "(croisement en sens inverse, cf. sens des routes ci-dessus)."
        )

elif cas["type"] == "route_fpl":
    (cs,) = cas["callsigns"]
    if "routes_fpl" not in st.session_state or "traj_vols" not in st.session_state:
        st.warning(
            "Ce cas réutilise les résultats du KPI05 (Id6). "
            "Allez d'abord sur la page **Performance** et cliquez sur « Calculer KPI05 (Id6) », "
            "puis revenez ici."
        )
    else:
        routes_fpl = st.session_state["routes_fpl"]
        traj_vols = st.session_state["traj_vols"]

        col_map, col_res = st.columns([2, 1])
        with col_map:
            st.markdown("**Route FPL (orange) vs route réelle ADS-B (bleu)**")
            carte = maps.carte_route_fpl_vs_reel(routes_fpl, traj_vols, data.contour_uta, callsign=cs)
            st_folium(carte, width=None, height=500, key="carte_eth909", returned_objects=[])

        with col_res:
            st.markdown("**Résultats calculés (Id6)**")
            if "id6_df" in st.session_state:
                ligne = st.session_state["id6_df"][st.session_state["id6_df"]["callsign"] == cs]
                st.dataframe(ligne, use_container_width=True)
            else:
                st.info("Détail Id6 non disponible (recalculez KPI05 sur la page Performance).")

st.divider()

# ═══════════════════ Id5 — Trajectoire SKK046 zoomée sur le seuil 09R ═════
st.subheader("Trajectoire de SKK046 en approche finale (zoom seuil 09R)")

if "df_final_id5" not in st.session_state:
    st.warning(
        "Ce cas réutilise le segment d'approche finale calculé pour l'Id5. "
        "Allez d'abord sur la page **Sécurité** et cliquez sur « Calculer Id5 », puis revenez ici."
    )
else:
    carte_skk046 = maps.carte_segment_piste(st.session_state["df_final_id5"], callsign="SKK046")
    st_folium(carte_skk046, width=None, height=500, key="carte_skk046", returned_objects=[])
