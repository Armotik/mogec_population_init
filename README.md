# MOGEC - Initialisation Spatio-Temporelle (t=0)

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![GeoPandas](https://img.shields.io/badge/GeoPandas-Active-green.svg)](https://geopandas.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Contexte du Projet
Ce module a été développé dans le cadre du projet **MOGEC** (Modélisation couplée de scénario de gestion de crise appliquée au risque de submersion marine). 

Les modèles d'évacuation multi-agents (comme ceux basés sur l'architecture BEN via GAMA) nécessitent une connaissance extrêmement précise de la position de la population à l'instant `t=0` (avant le déclenchement de l'alerte). En l'absence de capteurs temps réel exploitables (caméras), ce projet propose un **pipeline algorithmique déterministe de descente d'échelle (downscaling)** basé à 100% sur de l'Open Data.

## Fonctionnalités Principales
L'algorithme transforme des données statistiques agrégées (carreaux de 200m) en une distribution granulaire à l'échelle du bâtiment :

1. **Filtrage Géométrique :** Nettoyage des emprises non-habitables (< 9m²) via la BD TOPO et la BDNB.
2. **Dasymetric Mapping :** Distribution ciblée de la population (INSEE Filosofi) selon la capacité habitable et l'usage des bâtiments (Résidentiel, Commerce, Plage).
3. **Modulation Spatio-Temporelle :** Ajustement dynamique de la population générée en fonction de la saison (taux d'occupation des résidences secondaires) et de l'heure (rythmes circadiens de présence au domicile).
4. **Injection Sociodémographique :** Attribution stochastique de profils de ménages pour le paramétrage des comportements agents.

## Architecture des Données (100% Open Data)
Le pipeline nécessite le téléchargement préalable des bases de données suivantes pour la zone d'étude :
* **INSEE Filosofi :** Carroyage démographique 200m.
* **IGN BD TOPO :** Géométrie des bâtiments, usage (`USAGE1`), et nombre de logements (`NB_LOGTS`).
* **CSTB BDNB :** Emprise au sol et hauteur (pour estimation de la capacité de secours).
* **OpenStreetMap (OSM) :** Extraction dynamique via l'API (plages, campings, hôtels).

## Prérequis et Installation

Ce projet utilise des bibliothèques d'ingénierie spatiale avancées. Il est fortement recommandé d'utiliser un environnement virtuel.

```bash
# 1. Cloner le dépôt
git clone [https://github.com/ton-profil/mogec_population_init.git](https://github.com/ton-profil/mogec_population_init.git)
cd mogec_population_init

# 2. Créer un environnement virtuel (via venv ou conda)
python -m venv venv
source venv/bin/activate  # Sur Windows : venv\Scripts\activate

# 3. Installer les dépendances
pip install -r requirements.txt
```

## Utilisation

L'ensemble de la configuration (chemins d'accès aux bases de données, paramètres du scénario, zone d'étude) est externalisé pour garantir la reproductibilité. Aucune donnée n'est codée en dur.

1. Copiez le fichier de configuration par défaut :
    ```bash
    cp config_template.yaml config.yaml
    ```
2. Éditez config.yaml pour pointer vers vos données brutes locales et définir votre scénario (ex: scénario hivernal nocturne vs estival diurne).
3. Lancez le pipeline :
    ```bash
    python main.py --config config.yaml
    ```

### Format de Sortie

L'algorithme génère un fichier spatial (GeoPackage ou GeoJSON, configurable) contenant les centroïdes des bâtiments/zones avec leurs attributs de population respectifs, prêts à être instanciés par l'agent "Populateur" dans GAMA.

## Structure du Projet

```
mogec_population_init/
├── data/               # Données (brutes, intermédiaires, finales) - ignoré par git
├── src/                # Code source (extraction, géométrie, downscaling)
├── tests/              # Tests unitaires pour valider les formules mathématiques
├── config.yaml         # Fichier maître de configuration des scénarios
├── main.py             # Orchestrateur du pipeline
└── requirements.txt    # Dépendances Python
```

## Auteur
Anthony Mudet
Master 1 SMART Computing - Université de Nantes