# Référence de configuration MOGEC

## Vue d'ensemble

La configuration du projet est organisée en trois niveaux :

- [config/base.yaml](/home/armotik/Documents/Université/M1/S2/TER/config/base.yaml) : base commune du modèle.
- [config/validation/proxies.yaml](/home/armotik/Documents/Université/M1/S2/TER/config/validation/proxies.yaml) : validation temporelle par proxys.
- [config/scenarios/](/home/armotik/Documents/Université/M1/S2/TER/config/scenarios) : scénarios concrets.

Les fichiers [config.yaml](/home/armotik/Documents/Université/M1/S2/TER/config.yaml), [config_weekday_school_day.yaml](/home/armotik/Documents/Université/M1/S2/TER/config_weekday_school_day.yaml) et [config_summer_day.yaml](/home/armotik/Documents/Université/M1/S2/TER/config_summer_day.yaml) restent disponibles comme points d'entrée compatibles avec les scripts existants.

## Logique d'héritage

- `config/base.yaml` définit le socle commun.
- `config/validation/proxies.yaml` ajoute les scénarios de comparaison et les proxys.
- chaque fichier de `config/scenarios/` surcharge ensuite le bloc `scenario` et, si besoin, certaines composantes non résidentielles.

## Sections de la base

### `project`

- Rôle : identité du projet, CRS de référence et reproductibilité.
- Unités : `crs_epsg` en code EPSG, `random_seed` entier.
- Source : choix de modélisation interne.
- Effet sur le modèle : fixe le référentiel spatial et les tirages aléatoires.
- Valeurs typiques : `crs_epsg = 2154`, `random_seed` stable par dépôt.
- Risques si mal réglé : erreurs de projection, résultats non reproductibles, identifiants bâtiment instables.

### `study_area`

- Rôle : définir le territoire d'étude et la frontière de clip.
- Unités : `buffer_m` en mètres.
- Paramètre clé : `allow_network_fallback` (booléen, `false` recommandé pour la reproductibilité).
- Source : référentiel administratif local.
- Effet sur le modèle : contrôle les bâtiments retenus, la population incluse et le clip final.
- Valeurs typiques : `buffer_m = 200`.
- Risques si mal réglé : perte de bâtiments de bordure, double comptage ou omission de population.

### `data_paths`

- Rôle : référencer les sources d'entrée et les sorties principales.
- Unités : chemins relatifs au fichier YAML qui les déclare.
- Source : arborescence locale du projet.
- Effet sur le modèle : conditionne le chargement effectif des données spatiales et tabulaires.
- Valeurs typiques : chemins sous `../data/01_raw`, `../data/02_interim`, `../data/03_processed`.
- Risques si mal réglé : échec de chargement, export au mauvais endroit, confusion entre jeux préparés et jeux bruts.

### `external_preparation`

- Rôle : piloter les scripts de préparation des données externes.
- Unités : mètres, ratios, capacités par unité.
- Source : hypothèses de matching et calibration externe.
- Effet sur le modèle : influence la qualité des tables intermédiaires utilisées ensuite.
- Valeurs typiques : distance de matching `120 m`, ratios d'hébergement calibrés localement.
- Risques si mal réglé : appariement peu fiable des offres touristiques ou plages mal transformées.

### `visualization`

- Rôle : paramétrer les sorties graphiques Python.
- Unités : tailles de figure, seuils de flux, largeurs relatives.
- Source : choix de présentation.
- Effet sur le modèle : aucun effet scientifique direct sur la simulation.
- Valeurs typiques : `figure_size = [22, 14]`.
- Risques si mal réglé : graphiques peu lisibles, sans impact sur la population simulée.

### `filtering`

- Rôle : filtrer les bâtiments trop petits et gérer les cas sans nombre de logements.
- Unités : mètres carrés.
- Source : hypothèse de nettoyage spatial.
- Effet sur le modèle : modifie le support bâti disponible pour la ventilation résidentielle.
- Valeurs typiques : `min_building_area_m2 = 9`, `fallback_sqm_per_dwelling = 80`.
- Risques si mal réglé : micro-polygones parasites ou sous/surestimation du nombre de logements.

### `demographics`

- Rôle : fixer les cibles démographiques et la structure des foyers.
- Unités : parts `[0,1]`, effectifs entiers.
- Source : Insee 2022 et hypothèses de reconstruction des ménages.
- Effet sur le modèle : contrôle la pyramide des âges, les rôles attribués et la composition des foyers.
- Valeurs typiques : pyramide d'âge sommant à `1.0`, structure des ménages calibrée localement.
- Risques si mal réglé : profils de population incohérents, déséquilibre entre scolaires, actifs et seniors.

### `destination_model`

- Rôle : définir les pools de destinations internes selon le rôle.
- Unités : mètres, coefficients de décroissance, surfaces par personne.
- Source : hypothèses métier sur l'attractivité du bâti.
- Effet sur le modèle : oriente les destinations scolaires et d'activité locale.
- Valeurs typiques : distances de `3000` à `4500 m`, `distance_decay` entre `1.2` et `1.5`.
- Risques si mal réglé : affectations irréalistes ou surconcentration sur quelques bâtiments.

### `temporal_model`

- Rôle : définir les rythmes horaires par rôle et les sensibilités au contexte.
- Unités : heures, écarts-types horaires, probabilités `[0,1]`, sensibilités `[0,1]`.
- Source : hypothèses comportementales calibrées et validation par proxys.
- Effet sur le modèle : produit les trajectoires individuelles puis la matrice `pop_h0` à `pop_h23`.
- Valeurs typiques : départs scolaires vers `8h30`, retours vers `16h30-17h`, pause méridienne explicite.
- Risques si mal réglé : courbes horaires peu crédibles, proxys en échec, dynamique diurne déformée.
- Point de calibration : `temporal_model.household_dynamics.escort_scoring` permet d'ajuster les poids de sélection des accompagnateurs scolaires (rôle, proximité, pickup, alignement horaire).

### `poi_matching`

- Rôle : rattacher les POI restaurants au bâti.
- Unités : mètres, listes d'usages autorisés.
- Source : audit local OSM + BD TOPO.
- Effet sur le modèle : permet d'utiliser les restaurants dans les agendas.
- Valeurs typiques : `max_distance_m = 80`.
- Risques si mal réglé : restaurants non appariés ou rattachés au mauvais bâtiment.

### `non_residential_model`

- Rôle : ajouter des populations exogènes non résidentielles.
- Sous-blocs :
  - `accommodation` : hébergements touristiques.
  - `activities` : fréquentation diurne des commerces et équipements.
  - `beaches` : fréquentation des plages, à n'activer que si une source externe traçable permet de la documenter.
- Unités : personnes, parts, coefficients horaires, mètres carrés par personne.
- Source : données touristiques, hypothèses surfaciques, calibration locale.
- Effet sur le modèle : enrichit `pop_t0` et la dynamique journalière au-delà des seuls résidents.
- Valeurs typiques : `tau_occupation` faible en hiver, plus élevé en été ; plages désactivées hors scénarios estivaux.
- Risques si mal réglé : double comptage, surreprésentation touristique, pics artificiels.
- Recommandation actuelle du dépôt : conserver `beaches` dans la config avec `enabled: false` tant qu'aucun comptage, proxy externe ou source locale défendable n'est retenu.

### `infrastructures`

- Rôle : documenter les écoles locales, leur matching et les horaires exportés vers GAMA.
- Unités : capacités en personnes, coordonnées géographiques, mètres.
- Source : CSV écoles, géolocalisation locale, réglages GAMA.
- Effet sur le modèle : sécurise le pool scolaire interne et la cohérence d'export.
- Valeurs typiques : deux écoles locales, `match_max_distance_m = 120`.
- Risques si mal réglé : pool scolaire vide, bâtiments d'enseignement mal identifiés.

## Sections de validation

### `proxy_validation.scenario_sets`

- Rôle : définir des ensembles de scénarios comparables pour les scripts de validation.
- Unités : chemins de fichiers YAML et labels.
- Source : organisation interne du projet.
- Effet sur le modèle : aucun effet sur la simulation ; effet direct sur les comparaisons multi-scénarios.
- Risques si mal réglé : scripts pointant vers de mauvais scénarios.

### `proxy_validation.temporal_proxies`

- Rôle : comparer des courbes simulées à des courbes de référence publiques.
- Unités : séries horaires sur 24 heures, seuils de corrélation, RMSE et décalage de pic.
- Source : Insee, GTFS, horaires publics d'écoles, inférences documentées.
- Effet sur le modèle : aucun effet sur la simulation ; effet direct sur l'évaluation scientifique.
- Valeurs typiques : `correlation_pass_min` entre `0.80` et `0.85`.
- Risques si mal réglé : validation trompeuse, seuils trop permissifs ou trop stricts.

## Sections de scénario

### `scenario`

- Rôle : instancier un cas de simulation concret.
- Sous-blocs :
  - `residences` : occupation résidentielle à `T0`.
  - `commerce` : intensité commerciale du scénario.
  - `tourisme` : météo et occupation touristique.
  - `temporal_context` : saison, météo, alerte, jour religieux.
- Unités : parts `[0,1]`, heure entière `0-23`, coefficients contextuels.
- Source : hypothèses de scénario.
- Effet sur le modèle : modifie directement l'état initial et certains comportements horaires.
- Valeurs typiques :
  - hiver nocturne : `reference_hour = 2`, `alpha_domicile` élevé ;
  - jour ouvré : `reference_hour = 14`, `alert_level = 0.0` ;
  - été : `tau_saison` et `tau_occupation_lits` élevés.
- Risques si mal réglé : incohérence entre heure de référence, saison, météo et composantes activées.

## Validation technique

Le chargement principal passe par [src/pipeline.py](/home/armotik/Documents/Université/M1/S2/TER/src/pipeline.py#L83) et la validation structurée par [src/io/config_validation.py](/home/armotik/Documents/Université/M1/S2/TER/src/io/config_validation.py#L1).

La validation vérifie notamment :

- la présence des sections attendues sur une configuration complète ;
- les types des champs sensibles ;
- les bornes `[0,1]` des probabilités ;
- la cohérence des distributions démographiques ;
- la structure minimale des proxys ;
- la complétude des blocs `evidence` lorsqu'une brique sensible est activée.
