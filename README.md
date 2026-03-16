# MOGEC - Initialisation Spatio-Temporelle de la Population

Projet d'initialisation spatiale et temporelle de la population pour la commune de Batz-sur-Mer, dans le cadre du TER de Master 1 SMART Computing.

Le pipeline Python produit un environnement initial exploitable dans GAMA :
- une répartition bâtimentaire de la population à `T0` ;
- une matrice horaire `pop_h0` à `pop_h23` ;
- des attributs d'audit pour documenter les hypothèses, les profils et les corrections appliquées.

## Objectif scientifique

Le modèle cherche à répondre à une question simple :

> à une heure donnée, dans un scénario donné, combien de personnes sont présentes dans chaque bâtiment ou zone pertinente de la commune ?

Le cas d'usage principal est la simulation d'un événement de submersion marine de type Xynthia, mais l'architecture est paramétrable pour d'autres territoires et d'autres contextes.

## Ce que fait le pipeline

Le pipeline assemble plusieurs briques.

1. Chargement de la frontière d'étude et des bâtiments.
2. Filtrage géométrique des petites emprises non plausibles.
3. Attribution d'un `building_id` stable.
4. Jointure des bâtiments avec le carroyage Filosofi.
5. Ventilation de la population résidentielle vers les bâtiments.
6. Ajout optionnel des composantes non résidentielles :
   - hébergements touristiques ;
   - activités et équipements ;
   - plages exogènes.
7. Génération des foyers et des rôles :
   - scolaires ;
   - actifs locaux ;
   - actifs navetteurs ;
   - seniors.
8. Affectation des destinations principales.
9. Intégration des restaurants et des lieux de culte.
10. Génération de la matrice horaire 24h.
11. Export en GeoPackage pour GAMA.

## Structure du dépôt

```text
mogec_population_init/
├── config.yaml                         # Scénario principal
├── config_summer_day.yaml              # Exemple de scénario contrasté
├── main.py                             # Point d'entrée du pipeline
├── notebooks/                          # Exploration et validation scientifique
├── scripts/                            # Téléchargement, préparation, visualisations
├── src/
│   ├── core/                           # Logique métier
│   ├── io/                             # Chargement, export, validation config
│   └── visualization/                  # Fonctions d'appui pour cartes et notebooks
├── tests/                              # Tests unitaires et d'intégration
└── data/                               # Données brutes, intermédiaires, finales
```

## Modules principaux

### `src/core/`

- `downscaling.py` : ventilation de la population résidentielle vers les bâtiments.
- `agendas.py` : construction des foyers, attribution des rôles et des destinations.
- `destinations.py` : tirage gravitaire des bâtiments destination.
- `temporal.py` : génération de `pop_h0` à `pop_h23`.
- `non_residential.py` : hébergements, activités, plages, audit du double comptage.
- `restaurants.py` : rattachement des restaurants aux bâtiments et gestion des horaires.
- `cultes.py` : repérage des bâtiments de culte.
- `identifiers.py` : création des identifiants stables.

### `src/io/`

- `loaders.py` : chargement des couches spatiales.
- `exporters.py` : export final GeoPackage.
- `external_data_preparation.py` : préparation locale des données touristiques et des plages.
- `config_validation.py` : contrôle minimal des blocs `evidence`.

### `src/visualization/`

- `exploration.py` : tableaux prêts à l'emploi pour notebook exploratoire.
- `validation.py` : tableaux de validation scientifique.
- `heatmap.py`, `temporal_heatmap.py` : visualisations statiques complémentaires.

## Configuration

Toute la logique de scénario est externalisée dans `config.yaml`.

Le fichier contrôle notamment :
- la zone d'étude ;
- les chemins de données ;
- les paramètres démographiques ;
- les règles de destination ;
- les profils temporels ;
- les composantes non résidentielles ;
- les preuves et niveaux de confiance associés.

Le scénario dérivé `config_summer_day.yaml` montre comment utiliser `extends: config.yaml` pour créer un scénario contrasté sans dupliquer toute la configuration.

## Préparation des données

### 1. Installer l'environnement

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Télécharger les données ouvertes

Le projet contient un script rejouable :

```bash
bash scripts/download_open_data.sh
```

### 3. Préparer les sources externes

Cette étape harmonise les offres touristiques, prépare les restaurants, construit les tables de capacité et les zones de plage.

```bash
./.venv/bin/python scripts/prepare_external_sources.py --config config.yaml
```

## Exécuter le pipeline

### Scénario principal

```bash
./.venv/bin/python main.py --config config.yaml
```

### Scénario contrasté

```bash
./.venv/bin/python main.py --config config_summer_day.yaml
```

## Sorties principales

### Export final

Le fichier principal est :

`data/03_processed/population_batz_t0.gpkg`

Il contient notamment :
- `building_id` : identifiant stable ;
- `usage_1` : type d'usage du bâtiment ;
- `pop_t0` : population présente à l'état initial ;
- `pop_h0` à `pop_h23` : population présente par heure ;
- `n_scolaire`, `n_senior`, `n_actif_local`, `n_actif_navetteur` ;
- `pop_nonres_accommodation`, `pop_nonres_activity` ;
- colonnes d'audit du double comptage ;
- attributs POI `is_restaurant`, `is_culte`.

### Tables intermédiaires utiles

Dans `data/02_interim/external/` :
- `batz_restaurants_prepared.csv`
- `batz_accommodation_capacity.csv`
- `batz_accommodation_calibration.csv`
- `batz_accommodation_overlap_audit.csv`
- `batz_beaches.gpkg`

## Notebooks

Deux notebooks servent à la lecture scientifique du modèle.

- `notebooks/visualisation_exploratoire.ipynb`
  Vue exploratoire simple : cartes de `T0`, courbes horaires, types de destination.

- `notebooks/validation_scientifique_modele.ipynb`
  Validation interne : structure du GeoPackage, métriques globales, rôle cible vs rôle réalisé, non résidentiel, bâtiments les plus variables.

## Tests

Lancer l'ensemble de la suite :

```bash
./.venv/bin/pytest -q
```

Quelques blocs utiles à tester isolément :

```bash
./.venv/bin/pytest -q tests/test_agendas.py
./.venv/bin/pytest -q tests/test_temporal.py
./.venv/bin/pytest -q tests/test_non_residential.py
./.venv/bin/pytest -q tests/test_validation_helpers.py
```

## État scientifique du modèle

Le projet fournit aujourd'hui :
- une cohérence structurelle forte de l'export ;
- une reproductibilité stricte par seed ;
- des scénarios paramétrables ;
- une documentation des hypothèses non résidentielles via les blocs `evidence`.

Le modèle reste un modèle simulé calibré par données, pas une observation directe du terrain. Les points à discuter dans le mémoire sont donc :
- la qualité des hypothèses horaires ;
- la calibration des composantes d'activité ;
- la représentativité des données touristiques ;
- l'écart entre cohérence interne et validation externe.

## Auteur

Anthony Mudet  
Master 1 SMART Computing - Université de Nantes
