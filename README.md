# MOGEC - Initialisation spatio-temporelle de la population

Projet de préparation d'une population synthétique spatialisée pour Batz-sur-Mer, réalisé dans le cadre du TER de Master 1 SMART Computing.

Le code Python produit un état initial exploitable dans GAMA :
- une population répartie par bâtiment à `T0` ;
- une matrice horaire `pop_h0` à `pop_h23` ;
- des attributs d'audit pour expliciter les hypothèses et les corrections appliquées.

## Objectif du projet

La question traitée est la suivante :

> à une heure donnée, dans un scénario donné, combien de personnes sont présentes dans chaque bâtiment ou zone utile de la commune ?

Le cas d'usage principal est un scénario de submersion marine de type Xynthia, mais la structure du projet reste paramétrable pour d'autres contextes.

## Chaîne de traitement

Le traitement suit les étapes suivantes :

1. charger la frontière d'étude et le bâti ;
2. filtrer les petites emprises non plausibles ;
3. attribuer un `building_id` stable, puis marquer écoles/culte ;
4. joindre les bâtiments avec le carroyage Filosofi ;
5. répartir la population résidentielle ;
6. ajouter, si besoin, les composantes non résidentielles ;
7. reconstruire les foyers et les rôles ;
8. affecter les destinations principales ;
9. intégrer restaurants (les lieux de culte sont identifiés en amont) ;
10. générer la matrice horaire sur 24 heures ;
11. exporter le résultat au format GeoPackage.

## Structure du dépôt

```text
mogec_population_init/
├── config.yaml                         # Scénario principal
├── config_summer_day.yaml              # Variante de scénario
├── main.py                             # Point d'entrée
├── notebooks/                          # Lecture exploratoire et validation
├── scripts/                            # Préparation, exécution, visualisations
├── src/
│   ├── core/                           # Logique métier
│   ├── io/                             # Chargement, export, validation
│   └── visualization/                  # Sorties graphiques et interfaces locales
├── tests/                              # Tests unitaires et d'intégration
└── data/                               # Données brutes, intermédiaires et finales
```

## Modules principaux

### `src/core/`

- `downscaling.py` : répartition de la population résidentielle dans les bâtiments.
- `agendas.py` : construction des foyers, attribution des rôles et des destinations.
- `destinations.py` : tirage gravitaire des destinations internes.
- `temporal.py` : génération de `pop_h0` à `pop_h23`.
- `non_residential.py` : hébergements, activités, plages et audit du double comptage.
- `restaurants.py` : rattachement des restaurants au bâti et gestion des horaires.
- `cultes.py` : repérage des bâtiments de culte.
- `identifiers.py` : création d'identifiants stables.

### `src/io/`

- `loaders.py` : chargement des couches spatiales.
- `exporters.py` : export final GeoPackage.
- `external_data_preparation.py` : préparation locale des données touristiques et des plages.
- `config_validation.py` : validation des blocs sensibles de configuration.

### `src/visualization/`

- `exploration.py` : tables prêtes à l'emploi pour notebook.
- `validation.py` : sorties de validation scientifique.
- `heatmap.py`, `temporal_heatmap.py` : visualisations statiques complémentaires.
- `profile_activity.py`, `realtime_explorer.py` : lecture des profils et des trajectoires simulées.

## Configuration

Toute la logique de scénario est portée par `config.yaml`.

Le fichier règle notamment :
- la zone d'étude ;
- la politique de fallback réseau sur la frontière (`study_area.allow_network_fallback`) ;
- les chemins des données ;
- les paramètres démographiques ;
- les règles de destination ;
- les profils temporels ;
- l'heure réelle correspondant à `T0` via `scenario.reference_hour` ;
- les composantes non résidentielles ;
- les sources et niveaux de confiance associés aux hypothèses.

Le scénario `config_summer_day.yaml` montre comment dériver une configuration avec `extends: config.yaml` sans dupliquer toute la base.

## Préparer les données

### 1. Installer l'environnement

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

Pour un environnement figé, le snapshot des dépendances installées est disponible dans `requirements-lock.txt`.

### 2. Télécharger les données ouvertes

```bash
bash scripts/download_open_data.sh
```

Le script vérifie l'intégrité SHA256 de chaque fichier avant usage, avec le manifeste versionné dans [docs/open_data_checksums.sha256](/home/armotik/Documents/Université/M1/S2/TER/docs/open_data_checksums.sha256).

### 3. Préparer les sources externes

Cette étape harmonise les offres touristiques, prépare les restaurants, construit les tables de capacité et les zones de plage.

```bash
./.venv/bin/python main.py prepare --config config.yaml
```

## Exécuter le modèle

### Scénario principal

```bash
./.venv/bin/python main.py run --config config.yaml
```

### Variante de scénario

```bash
./.venv/bin/python main.py run --config config_summer_day.yaml
```

### Validation dry-run (sans pipeline lourd)

```bash
./.venv/bin/python main.py validate --config config.yaml
```

## Sorties principales

### Export final

Le fichier principal est :

`data/03_processed/population_batz_t0.gpkg`

On y retrouve notamment :
- `building_id` : identifiant stable ;
- `usage_1` : type d'usage du bâtiment ;
- `pop_t0` : population présente à l'état initial du scénario ;
- `pop_h0` à `pop_h23` : population présente à chaque heure ;
- `reference_hour` : heure réelle associée à `T0` ;
- `n_scolaire`, `n_senior`, `n_actif_local`, `n_actif_navetteur` ;
- `pop_nonres_accommodation`, `pop_nonres_activity` ;
- les colonnes d'audit du double comptage ;
- les indicateurs POI `is_restaurant`, `is_culte`.

### Tables intermédiaires utiles

Dans `data/02_interim/external/` :
- `batz_restaurants_prepared.csv`
- `batz_accommodation_capacity.csv`
- `batz_accommodation_calibration.csv`
- `batz_accommodation_overlap_audit.csv`
- `batz_beaches.gpkg`

## Lecture et validation

### Notebooks

- `notebooks/visualisation_exploratoire.ipynb`
  Lecture simple de `T0`, des courbes horaires et des types de destination.

- `notebooks/validation_scientifique_modele.ipynb`
  Vérification de la structure du GeoPackage, des métriques globales, des rôles réalisés et des composantes non résidentielles.

### Scripts de lecture

Générer un dossier de validation hors notebook :

```bash
./.venv/bin/python scripts/generate_scientific_validation.py --config config.yaml
```

Comparer un ou plusieurs scénarios à des courbes de référence publiques :

```bash
./.venv/bin/python main.py proxy-validate --config config.yaml
```

Générer une page HTML autonome pour lire les profils et les activités simulées :

```bash
./.venv/bin/python main.py explore --mode html --config config.yaml
```

Lancer une interface web locale avec lecture horaire, filtre par foyer et carte :

```bash
./.venv/bin/python main.py explore --mode web --config config.yaml
```

L'interface locale permet de charger l'un des scénarios `config*.yaml` présents à la racine du dépôt, puis d'examiner en direct les profils, les trajectoires et la validation par proxy associée au scénario actif.

### Documentation associée

- `docs/validation_scientifique.md`
  Cadre méthodologique pour distinguer cohérence interne, traçabilité des hypothèses et confrontation externe.

- `docs/proxy_validation.md`
  Validation temporelle par proxys, sur un ou plusieurs scénarios.

- `docs/exploration_profils.md`
  Guide de lecture des vues HTML et web locales pour inspecter les profils, les foyers et les trajectoires simulées.

- `docs/config_reference.md`
  Référence synthétique des blocs de configuration et de leurs effets sur le modèle.

- `docs/fonctionnement_modele.md`
  Guide de fonctionnement et de réutilisation du modèle pour un lecteur voulant reprendre le projet sur un autre terrain.

Le dossier de validation contient aussi `external_proxy_validation.csv`, qui confronte le modèle à quelques proxys publics mobilisés dans la configuration. La page HTML autonome est écrite par défaut dans `data/04_visualization/profile_activity_explorer.html` et le serveur local est exposé par défaut sur `http://127.0.0.1:8765`.

## CLI unifiée

La CLI unique est portée par `main.py` avec sous-commandes :

```bash
./.venv/bin/python main.py run --config config.yaml
./.venv/bin/python main.py prepare --config config.yaml
./.venv/bin/python main.py validate --config config.yaml
./.venv/bin/python main.py explore --mode web --config config.yaml
./.venv/bin/python main.py proxy-validate --config config.yaml
```

Les scripts historiques de `scripts/` restent utilisables comme wrappers de compatibilité.

Niveaux de verbosité CLI :

```bash
./.venv/bin/python main.py -v validate --config config.yaml
./.venv/bin/python main.py -vv proxy-validate --config config.yaml
```

## Tests

Lancer toute la suite :

```bash
./.venv/bin/pytest -q
```

Découpage par marqueurs :

```bash
./.venv/bin/pytest -q -m "unit"
./.venv/bin/pytest -q -m "integration and not slow"
./.venv/bin/pytest -q -m "slow"
```

Couverture locale :

```bash
./.venv/bin/pytest -q -m "unit" --cov=src --cov-report=term-missing --cov-report=xml --cov-config=.coveragerc
```

## État actuel du modèle

Le projet fournit aujourd'hui :
- une structure d'export cohérente ;
- une reproductibilité contrôlée par graine ;
- des scénarios paramétrables ;
- une documentation des hypothèses non résidentielles via les blocs `evidence`.

Le modèle reste une reconstruction simulée à partir de données et d'hypothèses. Les points à discuter dans le mémoire portent donc surtout sur :
- la qualité des hypothèses horaires ;
- la calibration des composantes d'activité ;
- la représentativité des données touristiques ;
- l'écart entre cohérence interne et validation externe.

## Auteur

Anthony Mudet  
Master 1 SMART Computing - Université de Nantes
