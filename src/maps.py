# -*- coding: utf-8 -*-
"""
Adaptation des fonctions de cartographie du notebook (ipyleaflet -> folium).

ipyleaflet est un widget Jupyter : il ne peut pas se rendre dans une page
Streamlit. La bibliotheque equivalente supportee par Streamlit est `folium`
(via le composant `streamlit_folium`). Les fonctions ci-dessous reproduisent
exactement les memes cartes que le notebook (memes coordonnees, memes
couleurs, meme contenu) : seule l'API de dessin change (Polygon/Marker/
Polyline d'ipyleaflet -> equivalents folium). Aucune coordonnee, aucun calcul
geometrique n'est modifie : toutes les geometries proviennent des fonctions
inchangees de src/functions.py (construire_polygone_tma1, etc.).
"""

import folium
from folium import DivIcon

from src import functions as fn

PALETTE = [
    '#e74c3c', '#2980b9', '#27ae60', '#f39c12', '#8e44ad',
    '#e6194B', '#3cb44b', '#ffe119', '#4363d8', '#f58231',
    '#911eb4', '#42d4f4', '#f032e6', '#bfef45', '#fabebe',
    '#469990', '#e6beff', '#9A6324', '#fffac8', '#800000']


def creer_carte(contour, couleur="red", nom="Zone", zoom=7):
    """Equivalent folium de creer_carte() (ipyleaflet)."""
    centre_lat = sum(p[0] for p in contour) / len(contour)
    centre_lon = sum(p[1] for p in contour) / len(contour)
    m = folium.Map(location=[centre_lat, centre_lon], zoom_start=zoom, tiles="cartodbpositron")
    layer = folium.Polygon(
        locations=contour, color=couleur, weight=2,
        fill=True, fill_color=couleur, fill_opacity=0.3, tooltip=nom,
    )
    layer.add_to(m)
    return m, layer


def afficher_zone(nom):
    """Equivalent folium de afficher_zone() (ipyleaflet)."""
    nom = nom.upper()
    if nom not in fn.ESPACES:
        raise ValueError(f"Zone inconnue : {list(fn.ESPACES.keys())}")
    func, couleur = fn.ESPACES[nom]
    contour, sommets, centres, poly = func()
    carte, _ = creer_carte(contour, couleur, nom)
    return carte, contour, poly, sommets, centres


def afficher_toutes_zones():
    """Equivalent folium de afficher_toutes_zones() : TMA1 (bleu), TMA2 (vert), UTA (rouge)."""
    carte = folium.Map(location=[14.5, 0], zoom_start=7, tiles="cartodbpositron")
    for nom, (func, couleur) in fn.ESPACES.items():
        contour, _, _, _ = func()
        folium.Polygon(
            locations=contour, color=couleur, weight=2,
            fill=True, fill_color=couleur, fill_opacity=0.25, tooltip=nom,
        ).add_to(carte)
    folium.LayerControl().add_to(carte)
    return carte


def creer_carte_base(zoom=7):
    """Equivalent folium de creer_carte_base() : utilise fn.contour_uta,
    exactement comme le notebook utilisait la variable globale contour_uta."""
    contour_uta = fn.contour_uta
    centre = (sum(p[0] for p in contour_uta) / len(contour_uta),
              sum(p[1] for p in contour_uta) / len(contour_uta))
    m = folium.Map(location=list(centre), zoom_start=zoom, tiles="cartodbpositron")
    folium.Polygon(
        locations=contour_uta, color="royalblue", weight=2,
        fill=False, tooltip="UTA",
    ).add_to(m)
    return m


def ajouter_trajectoires_sur_carte(existing_map, df, col_id='callsign'):
    """Equivalent folium de ajouter_trajectoires_sur_carte() :
    Bleu = survols, Jaune = arrivees, Orange = departs (fn.couleur_vol)."""
    for cs, groupe in df.groupby(col_id):
        groupe = groupe.sort_values('timestamp')
        coords = list(zip(groupe['latitude'], groupe['longitude']))
        couleur = fn.couleur_vol(groupe)
        folium.PolyLine(locations=coords, color=couleur, weight=2, fill=False, tooltip=str(cs)).add_to(existing_map)
    return existing_map


def trac_trajectoires(traffic_obj, callsigns, zoom=8):
    """Equivalent folium de trac_trajectoires() : une couleur par vol (PALETTE),
    avec l'indicatif affiche au bout de la trajectoire."""
    m = creer_carte_base(zoom)

    for cs, color in zip(callsigns, PALETTE):
        df = traffic_obj.data.query("callsign == @cs").sort_values("timestamp")
        if df.empty:
            continue
        coords = list(zip(df['latitude'], df['longitude']))
        folium.PolyLine(locations=coords, color=color, weight=3, opacity=0.9, tooltip=cs).add_to(m)
        folium.map.Marker(
            coords[-1],
            icon=DivIcon(
                icon_size=(80, 22), icon_anchor=(0, 11),
                html=f'<div style="color:{color};font-weight:bold;background:white;'
                     f'padding:1px 5px;border-left:3px solid {color};font-size:12px">{cs}</div>',
            ),
        ).add_to(m)

    return m


# ─────────────────── Cartes ad hoc (cellules du notebook) ──────────────────

def carte_obstacles(OBSTACLES):
    """Module 9 : carte des obstacles d'aerodrome DRRN (cliquables)."""
    m = folium.Map(location=[13.481547, 2.183614], zoom_start=14, tiles="cartodbpositron")  # ARP DRRN
    for _, obs in OBSTACLES.iterrows():
        popup_html = (f"<b>{obs.nom}</b><br>{obs.type}<br>{obs.altitude_ft} ft<br>{obs.balisage}")
        folium.Marker(
            location=[obs.lat, obs.lon],
            popup=folium.Popup(popup_html, max_width=250),
        ).add_to(m)
    return m


def carte_segment_piste(df_app, callsign="SKK046"):
    """Module 12 : trajectoire d'un vol en approche finale, zoomee sur le seuil 09R."""
    vol = df_app[df_app["callsign"] == callsign].sort_values("timestamp")
    m = folium.Map(location=list(fn.THR09R), zoom_start=15, tiles="cartodbpositron")
    if not vol.empty:
        folium.PolyLine(
            locations=list(zip(vol["latitude"], vol["longitude"])), weight=2, color="blue"
        ).add_to(m)
    return m


def carte_route_fpl_vs_reel(routes_fpl, traj_vols, contour_uta, callsign="ETH909"):
    """Module 13 : comparaison route FPL (orange, waypoints en rouge) vs route reelle ADS-B (bleu)."""
    mFPL = routes_fpl.query('callsign==@callsign').sort_values("ordre")
    mADSB = traj_vols.query('callsign==@callsign').sort_values("timestamp")

    m = folium.Map(location=[mADSB.latitude.mean(), mADSB.longitude.mean()], zoom_start=7, tiles="cartodbpositron")

    folium.PolyLine(locations=list(zip(mADSB.latitude, mADSB.longitude)), color="blue", weight=2, tooltip="Route réelle (ADS-B)").add_to(m)
    folium.PolyLine(locations=list(zip(mFPL.latitude, mFPL.longitude)), color="orange", weight=2, tooltip="Route FPL").add_to(m)

    for _, r in mFPL.iterrows():
        folium.CircleMarker(
            location=[r.latitude, r.longitude], radius=5, color="red", fill=True, fill_color="red",
            popup=folium.Popup(str(r.point), max_width=150),
        ).add_to(m)

    folium.PolyLine(locations=contour_uta, color="green", weight=5, tooltip="UTA").add_to(m)

    return m
