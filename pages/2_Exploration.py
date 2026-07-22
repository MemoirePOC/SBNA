# -*- coding: utf-8 -*-
"""
Page Exploration (ex Module 6.2 du notebook : analyse exploratoire).

Choix du dataset, nombre de vols, répartition ARR/DEP/Survol, graphiques
déjà produits dans le notebook (taux d'équipement, vols par heure).
"""

import pandas as pd
import streamlit as st
import holoviews as hv
from streamlit_bokeh import streamlit_bokeh

from src import pipeline
from src import functions as fn

st.set_page_config(page_title="Exploration — PoC ATS Niamey", page_icon="🔎", layout="wide")
st.title("🔎 Exploration des données")

data = pipeline.load_pipeline()

# ── Choix du dataset ─────────────────────────────────────────────────────
DATASETS = {
    "Dataset 1 — TMA_GENERALE": data.df_tma_general_net,
    "Dataset 2 — TMA_GENERALE (2)": data.df_tma_general2_net,
    "Dataset 3 — TMA_GENERALE 07-08/04/2026": data.df_tma_general3_net,
    "Dataset 4 — TMA_GENERALE 08-09/04/2026": data.df_tma_general4_net,
    "Tous les datasets combinés": data.DATASET,
}

choix = st.selectbox("Choisir le dataset à explorer", list(DATASETS.keys()), index=4)
df_choisi = DATASETS[choix]

st.subheader("Synthèse du dataset — " + choix)
synthese = fn.synthese_fr24(df_choisi, aerodromes_locaux=["DRRN"])
st.dataframe(synthese, use_container_width=True, hide_index=True)

st.subheader("Répartition ARR / DEP / Survol")
repartition = synthese[synthese["Indicateur"].isin(["ARRIVEES", "DEPARTS", "SURVOLS"])]
st.bar_chart(repartition.set_index("Indicateur"))

st.subheader("Sources de surveillance (ADS-B, MLAT, ...)")
st.dataframe(fn.tableau_sources(df_choisi), use_container_width=True)

st.divider()
st.subheader("Nombre de vols par heure de la journée")

df_plot = df_choisi.copy()
df_plot["timestamp"] = pd.to_datetime(df_plot["timestamp"], utc=True)
vols_par_heure = (df_plot.groupby(df_plot["timestamp"].dt.hour)["icao24"]
                  .nunique().rename("Nb_vols").sort_index())
df_plot_h = vols_par_heure.reset_index()
df_plot_h["timestamp"] = df_plot_h["timestamp"].astype(str)

diagramme_heures = df_plot_h.hvplot.bar(
    x="timestamp", y="Nb_vols", height=450, rot=0,
    xlabel="Heure UTC", ylabel="Nombre de vols",
    title="Nombre de vols par heure de la journée",
    color="Nb_vols", cmap="Blues",
)
streamlit_bokeh(hv.render(diagramme_heures, backend="bokeh"), use_container_width=True, key="chart_vols_heure")

st.divider()
st.subheader("Taux d'emport par équipement de surveillance (case 10b des FPL)")

STATUT_EQ = (fn.analyse_ssr_adsb(data.FPL) * 100).round(1)
chart_statut = STATUT_EQ.hvplot.bar(
    y="TAUX", height=500, rot=70, color="TAUX", cmap="Set3",
    legend="top_left", title="Taux d'emport par équipement de surveillance",
)
streamlit_bokeh(hv.render(chart_statut, backend="bokeh"), use_container_width=True, key="chart_statut_eq")
STATUT_EQ.columns = ["TAUX_%"]
st.dataframe(STATUT_EQ, use_container_width=True)

st.subheader("Synthèse SSR / ADS-B / les deux / aucun")
EQ = (fn.taux_equipement(data.FPL) * 100).round(1)
chart_eq = EQ.hvplot.bar(
    y="TAUX", height=500, rot=70, color="TAUX", cmap="Set3",
    legend="top_left", title="Taux d'emport de transpondeurs SSR et ADS-B",
)
streamlit_bokeh(hv.render(chart_eq, backend="bokeh"), use_container_width=True, key="chart_eq_taux")
EQ.columns = ["TAUX_%"]
st.dataframe(EQ, use_container_width=True)

st.divider()
st.subheader("Comparaison FR24 vs données réelles (Billing) — 08/04/2026")
comparaison = fn.comparer_fr24_reel(data.df_tma_general3_net, data.vols_uta)
st.dataframe(comparaison, use_container_width=True, hide_index=True)
