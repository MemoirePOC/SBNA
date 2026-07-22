# -*- coding: utf-8 -*-
"""
Page Sécurité (ex Modules 8 à 11 du notebook) : Id1, Id2, Id3, Id4.

Un bouton par indicateur. Le calcul ne se lance qu'au clic (résultats
gardés en session_state pour rester affichés quand un autre bouton est
utilisé). Le contenu de chaque bloc reprend, sans changement, les cellules
correspondantes du notebook.
"""

import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from src import pipeline
from src import functions as fn
from src import maps

st.set_page_config(page_title="Sécurité — PoC ATS Niamey", page_icon="🛡️", layout="wide")
st.title("🛡️ Indicateurs de sécurité ATS")

data = pipeline.load_pipeline()

# ═══════════════════════ Id1 — Minimum du taux de rapprochement ═══════════
st.header("Id1 — Minimum des taux de rapprochement des aéronefs")
st.caption("Module 8 du notebook — closest_point_of_approach sur le dataset TMA_GENERALE (4).")

if st.button("Calculer Id1", key="btn_id1"):
    with st.spinner("Calcul d'Id1…"):
        paires = fn.tab_Tr(data.df_tma_general4_net)
        Id1 = paires["Tr"].min()
        paires = fn.ajouter_tolerance(paires, "Id1")
        st.session_state["id1_value"] = Id1
        st.session_state["id1_paires"] = paires

if "id1_value" in st.session_state:
    fn.conclusion_id1(st.session_state["id1_value"], tab_paires=st.session_state["id1_paires"])

st.divider()

# ═══════════════════════ Id2 — Franchissement d'obstacles ═════════════════
st.header("Id2 — Taux de conformité au franchissement des obstacles")
st.caption("Module 9 du notebook — obstacles critiques DRRN (NDB NY, VOR/DME), correction QNH via Meteostat.")

st.markdown("**Carte des obstacles d'aérodrome DRRN** (cliquer sur un marqueur pour le détail)")
st_folium(maps.carte_obstacles(data.OBSTACLES), width=None, height=450, returned_objects=[])

if st.button("Calculer Id2", key="btn_id2"):
    with st.spinner("Calcul d'Id2 (correction QNH via Meteostat, peut prendre quelques secondes)…"):
        df_dep_arr = fn.detecter_dep_arr(data.df_tma_general_net)
        df_rwy = fn.detecter_piste(df_dep_arr)
        df_rwy = fn.ajouter_qnh(df_rwy)
        df_rwy_filtre = df_rwy.dropna(subset=["piste"])
        df_id2 = fn.calcul_id2(df_rwy_filtre, data.df_obstacles)
        Id2 = df_id2.Tx.min()
        st.session_state["id2_value"] = Id2
        st.session_state["id2_df"] = df_id2

if "id2_value" in st.session_state:
    Id2 = st.session_state["id2_value"]
    df_id2 = st.session_state["id2_df"]
    if Id2 < 1:
        fn.afficher_html(f"Id2 = {Id2:.3f} < 1", style="erreur")
        fn.afficher_html("Attention : les marges de franchissement d'obstacles n'ont pas été respectées pour les vols suivants :", style="sous_titre")
        st.dataframe(df_id2[df_id2.Tx < 1].sort_values("Tx"), use_container_width=True)
    else:
        fn.afficher_html(f"Id2 = {Id2:.3f} ≥ 1", style="succes")
        fn.afficher_html("Les marges de franchissement d'obstacles ont été respectées sur l'ensemble de la période.", style="sous_titre")
        st.dataframe(df_id2.sort_values("Tx").head(5), use_container_width=True)

st.divider()

# ═══════════════════════ Id3 — Pertinence des alertes STCA ════════════════
st.header("Id3 — Taux de pertinence des alertes STCA")
st.caption("Module 10 du notebook — extrapolation à 10s des trajectoires sur l'horizon de look-ahead (2 min).")

if st.button("Calculer Id3", key="btn_id3"):
    with st.spinner("Extrapolation des trajectoires STCA…"):
        predites = fn.trajectoires_predites_stca(data.df_STCA_cand, data.df_adsb_stca)

        tr_min = []
        for _, al in data.df_STCA_cand.iterrows():
            couple = f"{al['Aircraft']} / {al['Compared Aircraft']}"
            a, b = (couple, al['Aircraft']), (couple, al['Compared Aircraft'])
            if a in predites and b in predites:
                pred = fn.Tr_couple(predites[a], predites[b])
                tr_min.append(pred["Tr"].min())

        pertinentes = sum(tr < 1 for tr in tr_min)
        non_pertinentes = sum(tr >= 1 for tr in tr_min)
        fausses = len(data.df_STCA) - pertinentes - non_pertinentes

        st.session_state["id3_pertinentes"] = pertinentes
        st.session_state["id3_non_pertinentes"] = non_pertinentes
        st.session_state["id3_fausses"] = fausses
        st.session_state["id3_cand"] = data.df_STCA_cand

if "id3_pertinentes" in st.session_state:
    n_stca = len(data.df_STCA)
    fn.afficher_html(f"Id3_p = {100 * st.session_state['id3_pertinentes'] / n_stca:.2f} % : des alertes d'avril 2026 sont pertinentes", style="erreur")
    fn.afficher_html(f"Id3_non_p = {100 * st.session_state['id3_non_pertinentes'] / n_stca:.2f} % : des alertes d'avril 2026 sont non pertinentes", style="succes")
    fn.afficher_html(f"Id3_fa = {100 * st.session_state['id3_fausses'] / n_stca:.2f} % : des alertes d'avril 2026 sont des fausses alertes", style="defaut")
    with st.expander("Détail des alertes STCA candidates à l'airprox (Aircraft / Compared Aircraft identifiés)"):
        st.dataframe(st.session_state["id3_cand"], use_container_width=True)

st.divider()

# ═══════════════════════ Id4 — Écart temporel STCA / résolution ═══════════
st.header("Id4 — Écart temporel entre le déclenchement du STCA et la première manœuvre de résolution")
st.caption("Module 11 du notebook — combine les STCA reconstruits automatiquement (Id1) et les STCA pertinents identifiés en Id3.")

if st.button("Calculer Id4", key="btn_id4"):
    with st.spinner("Calcul d'Id4…"):
        # --- 11.1 Détection automatique des alertes STCA pertinentes sur les trajectoires ---
        donnees_adsb = pd.concat([data.df_tma_general_net, data.df_tma_general2_net], ignore_index=True)
        serie = fn.serie_Tr(donnees_adsb)
        serie = fn.ajouter_tolerance(serie, "Id1")
        rap = serie[(serie["Tr"] < 5)]
        rap = fn.ajouter_tolerance(rap, "Id1")

        instants_stca = []
        for _, r in rap.iterrows():
            i, j, t0 = r.icao24_i, r.icao24_j, r.timestamp
            couple = tuple(sorted([i, j]))
            pts_i = fn.extrapoler_points(donnees_adsb[donnees_adsb.icao24 == i], t0)
            pts_j = fn.extrapoler_points(donnees_adsb[donnees_adsb.icao24 == j], t0)
            if pts_i is None or pts_j is None:
                continue
            pred = fn.Tr_couple(pts_i, pts_j)
            if pred.Tr.min() >= 1:
                continue
            instants_stca.append({
                "couple": couple, "timestamp": t0, "icao24_i": i, "icao24_j": j,
                "callsign_i": r.aeronef_i, "callsign_j": r.aeronef_j,
                "Tr_init": r.Tr, "Tr_min_extrapol": pred.Tr.min(),
            })
        df_tmp = pd.DataFrame(instants_stca).sort_values("timestamp")
        df_stca_reconstruit = (df_tmp.sort_values(["couple", "timestamp"])
                                .assign(dt=lambda d: d.groupby("couple")["timestamp"].diff()))
        df_stca_reconstruit = df_stca_reconstruit[
            df_stca_reconstruit["dt"].isna() | (df_stca_reconstruit["dt"] > pd.Timedelta("5min"))
        ].drop(columns="dt").reset_index(drop=True)

        df_stca_recons_pertinents = df_stca_reconstruit.rename(
            columns={"Tr_init": "Tr", "timestamp": "conflict_from", "Tr_min_extrapol": "Tr_extrapol"}
        )[["conflict_from", "icao24_i", "icao24_j", "callsign_i", "callsign_j", "Tr", "Tr_extrapol"]]

        # --- 11.2 Calcul d'Id4 ---
        predites = fn.trajectoires_predites_stca(data.df_STCA_cand, data.df_adsb_stca)
        rows = []
        for _, al in data.df_STCA_cand.iterrows():
            couple = f"{al['Aircraft']} / {al['Compared Aircraft']}"
            i, j = al["Aircraft"], al["Compared Aircraft"]
            t0 = pd.Timestamp(al["Conflict From"])
            a, b = (couple, i), (couple, j)
            if a not in predites or b not in predites:
                continue
            pred = fn.Tr_couple(predites[a], predites[b])
            ip = pred.Tr.idxmin()
            tr = pred.at[ip, "Tr"]
            if tr >= 1:
                continue
            rows.append({
                "conflict_from": t0, "icao24_i": i, "icao24_j": j,
                "callsign_i": al["Aircraft"], "callsign_j": al["Compared Aircraft"],
                "Tr_extrapol": tr,
            })
        df_stca_pertinents = pd.DataFrame(rows)

        id4_stca = fn.indicateur_id4(df_stca_pertinents, data.df_adsb_stca, cle="callsign", horizon="160s")
        id4_recons = fn.indicateur_id4(df_stca_recons_pertinents, data.df_tma_general_net, cle="icao24", horizon="160s")
        id4 = pd.concat([id4_stca, id4_recons], ignore_index=True)

        st.session_state["id4_df"] = id4

if "id4_df" in st.session_state:
    st.caption("NaT / NaN indiquent que les avions sont sortis de l'espace de couverture des données sans avoir eu à régler le conflit.")
    st.dataframe(st.session_state["id4_df"], use_container_width=True)
