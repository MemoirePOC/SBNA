# PoC ATS Niamey — Application Streamlit

Interface Streamlit du Proof of Concept du mémoire *Sécurité et performance ATS,
espace aérien du Niger*. Réutilise telles quelles les fonctions du notebook ;
seule la couche d'affichage (IPython/ipyleaflet/hvplot → Streamlit/folium/bokeh)
est adaptée. Voir les commentaires en tête de `src/functions.py` et `src/maps.py`
pour le détail des adaptations.

## Arborescence

```
SBNA/
├── app.py                  # page Accueil (point d'entrée Streamlit)
├── requirements.txt
├── packages.txt             # dépendances système (proj/geos, pour pyproj/shapely/traffic)
├── pages/
│   ├── 2_Exploration.py
│   ├── 3_Securite.py
│   ├── 4_Performance.py
│   └── 5_Demonstration.py
├── src/
│   ├── config.py             # constantes, chemins, cas de démonstration
│   ├── functions.py           # les 65 fonctions du notebook
│   ├── maps.py               # cartes folium (adaptées d'ipyleaflet)
│   └── pipeline.py            # chargement + nettoyage (Modules 1 à 7), mis en cache
└── data/
    └── DATASET_POC/            # <-- à ajouter : ton dossier de données (voir ci-dessous)
```

## 1. Ajouter le dataset

Place ton dossier `DATASET_POC` (celui téléchargé depuis Google Drive, dézippé)
directement dans `SBNA/data/`, de façon à obtenir :

```
SBNA/data/DATASET_POC/FR24API/1_TMA_GENERALE/...
SBNA/data/DATASET_POC/FPL/...
SBNA/data/DATASET_POC/Billing_Avril_2026/...
SBNA/data/DATASET_POC/STCA_AVRIL_2026.xlsx
SBNA/data/DATASET_POC/MSAW_AVRIL_2026.xlsx
SBNA/data/DATASET_POC/obstacles_drrn.csv
...
```

C'est exactement l'arborescence que le notebook attendait sous
`drive/MyDrive/DATASET_POC/` — seul le point de départ change (`src/config.py`,
variable `PATH`).

## 2. Mettre le tout sur GitHub (interface web, sans ligne de commande)

1. Va sur [github.com](https://github.com) → **New repository** (nom libre, ex. `poc-ats-niamey`), coche *Public* ou *Private* selon ton besoin, puis **Create repository**.
2. Sur la page du repo vide, clique **uploading an existing file** (ou *Add file → Upload files*).
3. Ouvre le dossier `SBNA` sur ton ordinateur et **glisse-dépose tout son contenu** (fichiers ET sous-dossiers `pages/`, `src/`, `data/`) dans la zone d'upload de GitHub — le navigateur préserve l'arborescence des sous-dossiers.
   - Comme `DATASET_POC` ne fait que 21 Mo, aucune limite GitHub n'est en jeu (limite individuelle : 100 Mo/fichier).
   - Si l'upload web refuse un très grand nombre de fichiers d'un coup, fais-le en deux fois : d'abord `app.py`, `requirements.txt`, `packages.txt`, `pages/`, `src/` ; puis reviens sur *Add file → Upload files* pour `data/DATASET_POC/`.
4. Écris un message de commit (ex. "Ajout app Streamlit + dataset PoC") → **Commit changes**.
5. Vérifie sur GitHub que l'arborescence est identique à celle listée plus haut (notamment que `data/DATASET_POC/` n'est pas devenu `data/DATASET_POC/DATASET_POC/` par erreur de glisser-déposer).

## 3. Déployer sur Streamlit Community Cloud

1. Va sur [share.streamlit.io](https://share.streamlit.io) et connecte-toi avec ton compte GitHub.
2. **New app** → choisis ton dépôt, la branche `main`, et renseigne **Main file path : `app.py`**.
3. Clique **Deploy**. Streamlit installera automatiquement `requirements.txt` et `packages.txt`.
4. Le tout premier chargement sera plus long que les suivants : installation des bibliothèques (`traffic`, `openap` sont volumineuses), puis, à la première visite de la page Accueil, exécution unique du nettoyage des données (tu verras défiler les tableaux de nettoyage — c'est normal, c'est mis en cache et ne se reproduira plus ensuite pour les visiteurs suivants).

## Points de vigilance

- **`traffic`** a des dépendances système (proj, geos) : `packages.txt` les installe. Si le build échoue sur Streamlit Cloud malgré tout, regarde les logs de build (bouton *Manage app*) — c'est le point le plus probable de blocage et il faudra alors ajuster les versions dans `requirements.txt`.
- **Meteostat** (correction QNH, Id2) fait un appel réseau. En cas d'échec (pas de réseau, service indisponible), la fonction `ajouter_qnh` retombe automatiquement sur la pression standard 1013,25 hPa (comportement déjà prévu dans le notebook, pas une modification).
- **`traffic.data.navaids`** télécharge sa base de données de points de navigation au premier usage — inclus dans le même chargement mis en cache que le reste.
