# -*- coding: utf-8 -*-
"""
Page Performance (ex Modules 13 à 15 du notebook) : KPI05 (Id6),
consommation carburant (Id7), émissions CO2 (Id8).

Étude portant sur les 10 vols identifiés dans le notebook comme ayant
survolé l'UTA Niamey le 10/04/2026 avec FPL et type d'aéronef compatible
OpenAP. Id7 dépend du calcul d'Id6, Id8 dépend du calcul d'Id7 : c'est la
chaîne de dépendance réelle du notebook, pas une contrainte artificielle.
"""

import pandas as pd
import streamlit as st
from streamlit_folium import st_folium
from openap import FuelFlow
from traffic.core import Traffic

from src import pipeline
from src import functions as fn
from src import maps
from src import config as cfg

st.set_page_config(page_title="Performance — PoC ATS Niamey", page_icon="📈", layout="wide")
st.title("📈 Indicateurs de performance ATS")

data = pipeline.load_pipeline()

LISTE_VOLS = ['THY3KA', 'THY215', 'TAP1527', 'RAM554', 'KLM589', 'THY15',
              'TAR399', 'UAE9652', 'ETH909', 'ETH906']

st.caption(
    "Étude portant sur 10 vols ayant survolé l'UTA Niamey le 10/04/2026, "
    "sélectionnés dans le notebook car disposant à la fois d'un plan de vol (FPL) "
    "et d'un type compatible avec la bibliothèque OpenAP : " + ", ".join(LISTE_VOLS)
)

# ═══════════════════════ Id6 / KPI05 — Allongement de trajectoire ══════════
st.header("KPI05 (Id6) — Allongement effectif de la trajectoire en route")

if st.button("Calculer KPI05 (Id6)", key="btn_id6"):
    with st.spinner("Reconstruction des routes FPL et calcul de l'allongement…"):
        df_uta_openap = fn.construire_df_uta_openap(data.df_tma_general2_net, data.contour_uta, data.FPL, data.BILLING)

        FPL = data.FPL.copy()
        FPL['Temps de Création'] = pd.to_datetime(FPL['Temps de Création'])
        fpl_10_april = FPL[FPL['Temps de Création'].dt.date == pd.to_datetime('2026-04-10').date()]
        FPL_10_avril = fpl_10_april['Texte']
        extracted_callsigns = FPL_10_avril.str.extract(r"-([^/-]+)(?:/[^-]*)?-", expand=False)
        fpl_filtered_by_callsign = FPL_10_avril[extracted_callsigns.isin(LISTE_VOLS)]

        traj_vols = (df_uta_openap[df_uta_openap["callsign"].isin(LISTE_VOLS)]
                     .sort_values(["callsign", "timestamp"]).reset_index(drop=True))

        vols = traj_vols[["callsign", "type"]].drop_duplicates()
        vols["Texte_fpl"] = vols.apply(
            lambda r: fn.trouver_fpl(r.callsign, r.type, fpl_filtered_by_callsign), axis=1)

        traj_vols_fpl = traj_vols.merge(vols, on=["callsign", "type"], how="left")

        routes_fpl = fn.construire_route_fpl(traj_vols_fpl, data.navaids_wps_uta)
        d_fpl = fn.calcul_dfpl(routes_fpl)
        d_real = fn.calcul_dreal(traj_vols)

        df_id6 = d_fpl.merge(d_real, on="callsign")
        df_id6["Id5 (%)"] = ((df_id6["D_REEL_nm"] - df_id6["D_FPL_nm"]) / df_id6["D_FPL_nm"] * 100)
        df_id6 = fn.ajouter_tolerance(df_id6, "Id6")

        Id6_global = (df_id6["D_REEL_nm"].sum() - df_id6["D_FPL_nm"].sum()) / df_id6["D_FPL_nm"].sum() * 100

        st.session_state["id6_df"] = df_id6
        st.session_state["id6_global"] = Id6_global
        st.session_state["routes_fpl"] = routes_fpl
        st.session_state["traj_vols"] = traj_vols

if "id6_df" in st.session_state:
    st.dataframe(st.session_state["id6_df"], use_container_width=True)
    fn.afficher_html(f"Id6 global = {st.session_state['id6_global']:.2f} %", style="sous_titre")

    st.markdown("**Trajectoires des 10 vols dans l'UTA**")
    carte_vols = maps.trac_trajectoires(Traffic(st.session_state["traj_vols"]), LISTE_VOLS, zoom=7)
    st_folium(carte_vols, width=None, height=500, key="carte_id6_vols", returned_objects=[])

    st.markdown("**Route FPL (orange) vs route réelle ADS-B (bleu) — exemple ETH909**")
    carte_route = maps.carte_route_fpl_vs_reel(
        st.session_state["routes_fpl"], st.session_state["traj_vols"], data.contour_uta, callsign="ETH909")
    st_folium(carte_route, width=None, height=500, key="carte_id6_route", returned_objects=[])

st.divider()

# ═══════════════════════ Id7 — Consommation additionnelle de carburant ════
st.header("Id7 (KPI16 GANP) — Consommation additionnelle de carburant")
st.caption("Nécessite d'avoir calculé KPI05 (Id6) au préalable : Id7 traduit en carburant l'écart de distance mesuré à l'Id6.")

if "id6_df" not in st.session_state:
    st.warning("Calculez d'abord KPI05 (Id6) ci-dessus.")
elif st.button("Calculer la consommation de carburant (Id7)", key="btn_id7"):
    with st.spinner("Intégration du débit carburant (OpenAP FuelFlow) sur chaque trajectoire…"):
        traj_vols = st.session_state["traj_vols"]
        df_id6 = st.session_state["id6_df"]

        Mtows = fn.construire_df_mtow(traj_vols)
        df_calc = traj_vols.merge(Mtows[["callsign", "MTOW_kg"]], on="callsign", how="left").rename(columns={
            "gspeed": "groundspeed", "vspeed": "vertical_rate", "Type": "typecode"})

        resultats = []
        for callsign, vol in df_calc.groupby("callsign"):
            vol = vol.sort_values("timestamp").copy()
            vol["timestamp"] = pd.to_datetime(vol["timestamp"])
            vol["dt"] = vol["timestamp"].diff().dt.total_seconds().fillna(0)
            masse = 0.85 * vol["MTOW_kg"].iloc[0]

            ff_model = FuelFlow(vol["typecode"].iloc[0], use_synonym=True)

            fuel_total = 0.0
            for _, row in vol.iterrows():
                ff = float(ff_model.enroute(mass=masse, tas=row["groundspeed"],
                                             alt=row["altitude"], vs=row["vertical_rate"]))
                fuel = ff * row["dt"]
                fuel_total += fuel
                masse -= fuel
            resultats.append({"callsign": callsign, "typecode": vol["typecode"].iloc[0], "fuel_kg": round(fuel_total, 1)})
        df_fuel = pd.DataFrame(resultats)

        df_id7 = (df_id6[["callsign", "D_FPL_nm", "D_REEL_nm", "Id5 (%)"]]
                  .merge(df_fuel[["callsign", "typecode", "fuel_kg"]], on="callsign"))

        df_id7["FF_nm"] = df_id7["fuel_kg"] / df_id7["D_REEL_nm"]
        df_id7["Id6_kg"] = df_id7["FF_nm"] * (df_id7["D_REEL_nm"] - df_id7["D_FPL_nm"])
        df_id7 = fn.ajouter_tolerance(df_id7, "Id7")
        df_id7 = df_id7[["callsign", "typecode", "fuel_kg", "FF_nm", "Id6_kg", "Tol_kg"]].round(2)

        st.session_state["id7_df"] = df_id7
        st.session_state["id7_global"] = df_id7["Id6_kg"].sum()

if "id7_df" in st.session_state:
    fn.afficher_html("Consommation additionnelle de carburant (KPI 16 GANP)", style="sous_titre")
    st.dataframe(st.session_state["id7_df"], use_container_width=True)
    fn.afficher_html(f"Id7 global = {st.session_state['id7_global']:.2f} kg", style="sous_titre")

st.divider()

# ═══════════════════════ Id8 — Émissions de CO2 ═══════════════════════════
st.header("Id8 — Émissions de CO₂ sous guidage radar vs sans guidage radar")
st.caption("Nécessite d'avoir calculé la consommation de carburant (Id7) ci-dessus. Facteur CORSIA : 1 kg de Jet A-1 → 3,16 kg de CO₂.")

if "id7_df" not in st.session_state:
    st.warning("Calculez d'abord la consommation de carburant (Id7) ci-dessus.")
elif st.button("Calculer les émissions de CO₂ (Id8)", key="btn_id8"):
    df_id8 = st.session_state["id7_df"].copy()
    df_id8["Id7_kgCO2"] = df_id8["Id6_kg"] * cfg.FACTEUR_CO2
    df_id8["CO2_guidage_radar(kg)"] = df_id8["fuel_kg"] * cfg.FACTEUR_CO2
    df_id8["CO2_sans_guidage_radar(kg)"] = (df_id8["fuel_kg"] - df_id8["Id6_kg"]) * cfg.FACTEUR_CO2
    df_id8 = fn.ajouter_tolerance(df_id8, "Id8")
    df_id8 = df_id8[["callsign", "typecode", "CO2_sans_guidage_radar(kg)",
                      "CO2_guidage_radar(kg)", "Id7_kgCO2", "Tol_kgCO2"]].round(2)

    st.session_state["id8_df"] = df_id8
    st.session_state["id8_global"] = df_id8["Id7_kgCO2"].sum()

if "id8_df" in st.session_state:
    st.dataframe(st.session_state["id8_df"], use_container_width=True)
    fn.afficher_html(f"Id8 global = {st.session_state['id8_global']:.2f} kg de CO₂", style="sous_titre")
