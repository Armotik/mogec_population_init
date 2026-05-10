# Validation scientifique et portée des résultats

Ce document distingue trois niveaux qu'il faut garder séparés dans le mémoire :

1. la cohérence technique de l'export ;
2. la cohérence interne du scénario ;
3. la confrontation du modèle à des références externes.

Le projet peut démontrer solidement les deux premiers points. Le troisième demande une comparaison avec des données ou des connaissances extérieures au modèle.

## 1. Ce que le projet peut vérifier directement

### Structure de l'export

Questions à poser :

- le GeoPackage final est-il complet ;
- les identifiants sont-ils stables et sans doublon ;
- les colonnes `pop_h0` à `pop_h23` sont-elles toutes présentes ;
- existe-t-il des valeurs négatives ou incohérentes.

Sorties concernées :

- `src/visualization/validation.py::structural_quality_report`
- `scientific_methodology_checklist`

Interprétation :

- si ces contrôles échouent, il faut corriger le modèle avant toute discussion scientifique ;
- ce sont des préconditions de validité.

### Cohérence démographique

Questions à poser :

- la somme des rôles reconstruits retombe-t-elle sur `pop_t0` ;
- les rôles réalisés restent-ils proches des cibles du scénario.

Sorties concernées :

- `role_targets_vs_realized`
- `scientific_methodology_checklist`

Interprétation :

- un faible écart renforce la solidité du scénario ;
- un écart important signale un paramétrage fragile ou une logique de génération à revoir.

### Cohérence temporelle

Questions à poser :

- le cycle journalier varie-t-il réellement ;
- les heures de pic et de creux sont-elles compatibles avec le scénario choisi ;
- l'amplitude journalière reste-t-elle plausible pour le territoire étudié.

Sorties concernées :

- `hourly_population_profile`
- `plot_scientific_validation_dashboard`
- `src/visualization/temporal_visu.py`

Interprétation :

- une série quasi plate doit alerter ;
- une dynamique très forte doit être justifiée par le scénario, par exemple navettes, tourisme ou saison.

### Traçabilité des hypothèses sensibles

Questions à poser :

- chaque brique non résidentielle active renvoie-t-elle à une source identifiable ;
- la formule utilisée est-elle explicitée ;
- la date de vérification est-elle indiquée ;
- le niveau de confiance est-il déclaré.

Sorties concernées :

- `src/io/config_validation.py`
- `evidence_traceability_report`

Interprétation :

- sans bloc `evidence`, une hypothèse peut être utile mais reste fragile scientifiquement ;
- un bloc `evidence` complet ne prouve pas l'hypothèse, mais rend la méthode plus vérifiable.

## 2. Ce que la cohérence interne ne démontre pas

Une exportation propre, des rôles bien calibrés et des courbes lisibles ne suffisent pas à affirmer :

- que les personnes sont dans les bons bâtiments réels ;
- que les heures de départ et de retour sont exactes ;
- que les populations non résidentielles sont simulées au bon niveau ;
- que la journée reconstruite reproduit fidèlement une journée observée.

En pratique :

- la cohérence interne répond à la question « le modèle fait-il ce qu'il annonce ? » ;
- la confrontation externe répond à la question « le modèle ressemble-t-il suffisamment au territoire réel ? ».

## 3. Démarche de confrontation externe

La validation la plus solide est progressive.

### Niveau 1. Ordres de grandeur institutionnels

Comparer le modèle à des références indépendantes :

- population communale INSEE ;
- structure par âge ;
- part d'actifs travaillant dans la commune ;
- capacités scolaires ;
- capacités touristiques ;
- capacités d'hébergement déclarées.

Objectif : vérifier que le scénario reste dans une enveloppe plausible.

### Niveau 2. Validation par composante

Examiner séparément chaque bloc :

- résidentiel : population totale, bâtiments habités, densités aberrantes ;
- scolaire : nombre d'élèves affectés, cohérence avec les bâtiments d'enseignement ;
- actifs locaux : destinations internes plausibles ;
- navetteurs : baisse diurne compatible avec la structure d'emploi ;
- hébergement : ordre de grandeur compatible avec l'offre touristique ;
- plages : fréquentation cohérente avec la saison et la météo.

Objectif : éviter qu'un résultat global correct masque une composante erronée.

### Niveau 3. Validation spatiale

Vérifier notamment :

- si les principaux pôles d'arrivée sont crédibles ;
- si certaines zones restent anormalement vides ;
- si les plus fortes densités apparaissent dans des secteurs attendus.

Objectif : repérer des erreurs invisibles dans les seuls tableaux agrégés.

### Niveau 4. Validation temporelle

Vérifier notamment :

- la logique du pic nocturne ;
- la plausibilité du creux diurne ;
- la forme de la reprise en fin de journée.

Objectif : confronter le rythme simulé au rythme attendu du territoire.

### Niveau 5. Appui terrain ou expertise locale

Quand c'est possible, confronter le modèle à :

- des comptages ponctuels ;
- des observations communales ;
- une expertise locale ;
- des retours d'acteurs du territoire ;
- la documentation d'événements réels.

Objectif : sortir d'une validation purement interne au modèle.

## 4. Sorties disponibles dans le dépôt

Le script suivant génère un dossier de validation complet :

```bash
./.venv/bin/python scripts/generate_scientific_validation.py --config config.yaml
```

Sorties produites par défaut dans `data/04_visualization/validation/` :

- `validation_dashboard.png`
- `structural_quality.csv`
- `export_metrics.csv`
- `hourly_profile.csv`
- `role_targets_vs_realized.csv`
- `non_residential_validation.csv`
- `occupied_buildings_by_usage.csv`
- `evidence_traceability.csv`
- `scientific_methodology_checklist.csv`
- `external_proxy_validation.csv`

`external_proxy_validation.csv` sert à confronter le modèle à plusieurs proxys publics déjà mobilisés dans le projet :

- emplois locaux de la commune ;
- capacités scolaires locales ;
- capacité touristique retenue.

Pour un scénario marqué `is_school_holiday: true`, le proxy scolaire devient surtout indicatif. Dans ce cas, un statut `info` peut être plus pertinent qu'un `pass`.

Deux outils complètent cette lecture :

```bash
./.venv/bin/python scripts/generate_profile_activity_explorer.py --config config.yaml
./.venv/bin/python scripts/run_proxy_validation.py --config config.yaml
./.venv/bin/python scripts/run_realtime_profile_explorer.py --config config.yaml
```

Le premier produit une page HTML utile pour lire qualitativement les profils et les activités simulées. Le deuxième compare des courbes simulées à des courbes de référence documentées. Le troisième fournit une interface web locale pour suivre un foyer, une personne et les statuts scolaires sur carte.

## 5. Formulations utiles pour le mémoire

Formulation robuste :

> Le modèle ne prétend pas observer directement la réalité. Il produit une reconstruction spatio-temporelle cohérente, paramétrée et traçable, dont la validité est appréciée à partir de contrôles internes et d'une confrontation progressive à des références externes.

Formulation à éviter :

> Le modèle montre la population réelle de Batz-sur-Mer heure par heure.

La seconde formulation est trop forte scientifiquement.
