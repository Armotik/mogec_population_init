# Guide de fonctionnement et de réutilisation du modèle

Ce document s'adresse à des personnes qui veulent réutiliser le projet MOGEC, le porter vers un autre territoire ou l'intégrer dans une chaîne de travail scientifique. L'objectif est de rassembler, dans un seul document, les éléments nécessaires pour comprendre le rôle de chaque brique, les données attendues, les hypothèses principales, les sorties produites et les points à adapter.

## 1. Finalité du projet

Le projet produit une population synthétique spatialisée à l'échelle du bâtiment, avec une dynamique horaire sur 24 heures.

La question traitée est la suivante :

> pour un scénario donné, combien de personnes sont présentes dans chaque bâtiment de la zone d'étude à l'heure initiale, puis à chaque heure de la journée ?

Le modèle est actuellement configuré pour Batz-sur-Mer, mais sa structure est réutilisable à condition de disposer d'un bâti, d'une population de référence, d'un jeu minimal de données locales et d'une configuration cohérente.

## 2. Ce que produit le modèle

La sortie principale est un GeoPackage bâtimentaire contenant notamment :

- `pop_t0` : population présente à l'heure de référence du scénario ;
- `pop_h0` à `pop_h23` : population présente pour chaque heure ;
- des comptes par profil (`n_scolaire`, `n_senior`, `n_actif_local`, `n_actif_navetteur`, `n_inactif`) ;
- des indicateurs de population non résidentielle ;
- des attributs utiles pour GAMA et pour l'audit scientifique.

La maille finale de lecture est donc le bâtiment. Les foyers, les profils et les trajectoires individuelles existent dans le calcul, mais servent principalement à reconstruire la dynamique horaire avant agrégation finale.

## 3. Architecture générale du projet

Le point d'entrée principal est [main.py](/home/armotik/Documents/Université/M1/S2/TER/main.py). Il charge un fichier YAML puis délègue le traitement à [src/pipeline.py](/home/armotik/Documents/Université/M1/S2/TER/src/pipeline.py).

Le pipeline suit l'ordre logique suivant :

1. charger la zone d'étude ;
2. charger et préparer les bâtiments (écoles + culte) ;
3. joindre les bâtiments à la grille de population ;
4. répartir la population résidentielle ;
5. ajouter la population non résidentielle ;
6. reconstruire les foyers et les profils ;
7. affecter les destinations ;
8. générer la matrice horaire ;
9. exporter le résultat final.

Les grands blocs du dépôt sont les suivants :

- `src/core/` : logique métier du modèle ;
- `src/io/` : chargement, validation de configuration, préparation externe, export ;
- `src/visualization/` : lecture, contrôle et validation ;
- `scripts/` : commandes prêtes à l'emploi pour préparer les données et générer les sorties.

## 4. Enchaînement détaillé des traitements

### 4.1. Chargement de la configuration

La configuration est chargée par `load_config` dans [src/pipeline.py](/home/armotik/Documents/Université/M1/S2/TER/src/pipeline.py). Elle supporte l'héritage via `extends`, ce qui permet de définir :

- une base commune ;
- des blocs de validation ;
- des scénarios dérivés.

La validation de structure est assurée par [src/io/config_validation.py](/home/armotik/Documents/Université/M1/S2/TER/src/io/config_validation.py). Cette validation contrôle en particulier :

- la présence des sections obligatoires ;
- les types ;
- les bornes de probabilité ;
- la cohérence de certaines distributions ;
- la structure minimale des blocs `evidence`.

### 4.2. Définition du territoire

Le modèle charge la frontière d'étude avec et sans buffer. Le buffer sert à travailler proprement en bordure, alors que le clip strict sert à limiter la sortie finale au territoire retenu.

Les paramètres concernés se trouvent dans le bloc `study_area`.

### 4.3. Préparation du bâti

Le modèle charge ensuite le bâti depuis la BD TOPO ou un jeu équivalent. Il effectue plusieurs opérations :

- filtrage des emprises trop petites ;
- calcul de centroïdes ;
- attribution d'un identifiant stable `building_id` ;
- intégration des écoles connues dans le bâti ;
- repérage des bâtiments de culte avant la ventilation résidentielle.

Le bâtiment est l'objet spatial central du projet. Toutes les populations finissent par être attribuées à cette maille.

### 4.4. Jointure à la population de référence

Le bâti est joint à une grille de population, ici Filosofi. Cette étape fournit la population agrégée qui sera redistribuée sur les bâtiments résidentiels.

Le modèle suppose donc qu'une population de référence existe déjà à une maille plus grossière que le bâtiment.

### 4.5. Ventilation résidentielle

La ventilation résidentielle est implémentée dans [src/core/downscaling.py](/home/armotik/Documents/Université/M1/S2/TER/src/core/downscaling.py).

Principe :

- seuls les bâtiments résidentiels reçoivent la population résidentielle ;
- un poids de capacité est calculé pour chaque bâtiment ;
- ce poids repose d'abord sur le nombre de logements s'il existe ;
- sinon, il est estimé à partir de la surface et de la hauteur ;
- la population du carreau est répartie entre les bâtiments du carreau selon ces poids ;
- les arrondis sont corrigés par la méthode du plus fort reste.

Le résultat est une première valeur `pop_t0` résidentielle.

Cette étape dépend fortement des paramètres :

- `scenario.residences.r_rp`
- `scenario.residences.r_rs`
- `scenario.residences.tau_saison`
- `scenario.residences.alpha_domicile`
- `filtering.fallback_sqm_per_dwelling`

### 4.6. Intégration des populations non résidentielles

Le modèle peut ajouter trois grandes familles de présence non résidentielle :

- hébergements touristiques ;
- activités et équipements ;
- plages.

Ces briques sont pilotées par `non_residential_model`.

L'idée est de ne pas limiter la présence humaine à la seule population résidente. Cette étape peut modifier `pop_t0` et la dynamique horaire.

Les hébergements touristiques s'appuient sur une table de capacité préparée en amont. Les activités reposent sur des règles surfaciques et des profils horaires. Le bloc plage reste prévu dans la configuration, mais il peut être maintenu désactivé tant qu'aucune source externe suffisamment traçable n'est retenue pour le calibrer.

### 4.7. Reconstruction des foyers et des profils

Cette étape est portée par [src/core/agendas.py](/home/armotik/Documents/Université/M1/S2/TER/src/core/agendas.py).

Le modèle reconstruit des foyers synthétiques à l'intérieur de chaque bâtiment habité, puis attribue à chaque membre un profil. Les profils utilisés dans la configuration actuelle sont :

- `scolaire`
- `senior`
- `actif_local`
- `actif_navetteur`
- `inactif`

Cette étape joue un rôle central, car elle conditionne :

- les effectifs par profil ;
- les destinations principales ;
- la structure familiale ;
- les mécanismes d'accompagnement scolaire ;
- la dynamique horaire finale.

Les paramètres concernés se trouvent surtout dans `demographics`, `destination_model`, `temporal_model` et `infrastructures`.

### 4.8. Affectation des destinations

Les destinations sont affectées selon le profil :

- écoles pour les scolaires ;
- bâtiments internes attractifs pour une partie des actifs locaux ;
- extérieur de la commune pour les navetteurs ;
- domicile ou sorties ponctuelles selon les autres profils.

L'affectation combine principalement :

- l'usage des bâtiments ;
- une capacité estimée ;
- une distance maximale ;
- un coefficient de décroissance avec la distance.

Cette logique est définie dans `destination_model`.

### 4.9. Génération de la matrice horaire

La matrice horaire est construite dans [src/core/temporal.py](/home/armotik/Documents/Université/M1/S2/TER/src/core/temporal.py).

Le modèle reconstruit, pour chaque membre synthétique, une présence heure par heure. Ensuite, ces présences sont réagrégées au niveau bâtimentaire pour produire `pop_h0` à `pop_h23`.

Les colonnes horaires résultent donc :

- des profils ;
- des foyers ;
- des destinations ;
- des paramètres temporels du scénario ;
- de l'ajout éventuel de populations d'activité ou de plage.

### 4.10. Export final

L'export final est produit par [src/io/exporters.py](/home/armotik/Documents/Université/M1/S2/TER/src/io/exporters.py). Il sélectionne les colonnes utiles à la simulation et à la lecture scientifique, puis écrit un GeoPackage unique.

Le fichier final contient également :

- `scenario_name`
- `day_of_week`
- `reference_hour`
- `random_seed`

## 5. Données d'entrée nécessaires

### 5.1. Données obligatoires

Pour exécuter le pipeline complet, il faut au minimum :

- une frontière d'étude ;
- un bâti polygonal avec usages ;
- une grille de population de référence ;
- un fichier décrivant les écoles ;
- les chemins de sortie ;
- une configuration complète.

### 5.2. Données optionnelles mais structurantes

Selon les briques activées, il faut aussi :

- des jeux tourismes pour restaurants et hébergements ;
- une source de capacité touristique ;
- des zones de plage ;
- un audit local pour les restaurants ;
- des proxys de validation si l'on veut évaluer la cohérence temporelle du modèle.

### 5.3. Préparation externe

La préparation des données externes est faite par [scripts/prepare_external_sources.py](/home/armotik/Documents/Université/M1/S2/TER/scripts/prepare_external_sources.py), qui appelle [src/io/external_data_preparation.py](/home/armotik/Documents/Université/M1/S2/TER/src/io/external_data_preparation.py).

Cette étape produit des tables intermédiaires stables pour :

- les restaurants ;
- les capacités d'hébergement ;
- les plages.

Sans cette étape, certaines briques non résidentielles ne peuvent pas fonctionner correctement.

## 6. Structure de la configuration

La configuration est le centre de pilotage du projet. Le détail des blocs est donné dans [docs/config_reference.md](/home/armotik/Documents/Université/M1/S2/TER/docs/config_reference.md). Pour la réutilisation, les sections les plus importantes sont les suivantes :

- `project` : CRS, graine aléatoire, stratégie d'identifiant ;
- `study_area` : territoire d'étude ;
- `data_paths` : sources d'entrée et sorties ;
- `filtering` : nettoyage du bâti ;
- `demographics` : cibles démographiques et structure des foyers ;
- `destination_model` : logique de destination ;
- `temporal_model` : profils horaires ;
- `poi_matching` : rattachement des restaurants ;
- `non_residential_model` : composantes non résidentielles ;
- `infrastructures` : écoles locales ;
- `scenario` : contexte d'exécution concret.

Pour réutiliser le projet sur un autre terrain, il faut au minimum reprendre soigneusement ces blocs. Changer seulement les chemins de données ne suffit pas.

## 7. Comment exécuter le projet

### 7.1. Préparer les sources externes

```bash
./.venv/bin/python main.py prepare --config config.yaml
```

### 7.2. Exécuter le pipeline complet

```bash
./.venv/bin/python main.py run --config config.yaml
```

### 7.3. Valider la configuration en dry-run

```bash
./.venv/bin/python main.py validate --config config.yaml
```

### 7.4. Générer les sorties de contrôle

```bash
./.venv/bin/python scripts/generate_scientific_validation.py --config config.yaml
./.venv/bin/python main.py proxy-validate --config config.yaml
./.venv/bin/python main.py explore --mode html --config config.yaml
./.venv/bin/python main.py explore --mode web --config config.yaml
```

Les scripts historiques dans `scripts/` restent disponibles comme wrappers de compatibilité.

## 8. Procédure de réutilisation sur un autre territoire

Une procédure réaliste de portage est la suivante :

1. définir le nouveau territoire et son CRS de travail ;
2. préparer un bâti polygonal avec usages exploitables ;
3. identifier une source de population de référence compatible avec une redistribution au bâtiment ;
4. renseigner ou recalibrer les écoles et les capacités locales ;
5. préparer les sources externes si les briques touristiques ou d'activité sont conservées ;
6. adapter `config/base.yaml` ou créer une nouvelle base ;
7. créer un scénario minimal ;
8. exécuter le pipeline sans composantes optionnelles ;
9. vérifier l'export, puis réactiver progressivement les briques non résidentielles ;
10. documenter les hypothèses dans les blocs `evidence`.

En pratique, les points les plus sensibles d'un portage sont :

- la qualité des usages du bâti ;
- la disponibilité d'une population de référence à maille fine ;
- la capacité à identifier les écoles et les pôles d'activité ;
- la calibration des composantes non résidentielles ;
- la cohérence des horaires avec le nouveau terrain.

## 9. Questions auxquelles le document doit permettre de répondre

### Quelle est l'unité spatiale du résultat ?

Le bâtiment.

### À quel moment `pop_t0` est-elle calculée ?

Après la ventilation résidentielle, puis après l'ajout éventuel des composantes non résidentielles actives pour le scénario.

### Les `pop_h*` sont-elles indépendantes de `pop_t0` ?

Non. Elles prolongent le même modèle, mais avec une reconstruction horaire fondée sur les profils, les foyers, les destinations et les composantes dynamiques.

### Le modèle travaille-t-il à l'échelle individuelle ?

Pendant le calcul, oui, sous forme synthétique, via des membres de foyers. Mais la sortie standard reste agrégée à l'échelle bâtimentaire.

### Où sont codées les hypothèses fortes ?

Principalement dans la configuration :

- structure des foyers ;
- parts démographiques ;
- règles de destination ;
- profils horaires ;
- coefficients non résidentiels ;
- paramètres de scénario.

### Qu'est-ce qui est spécifique à Batz-sur-Mer ?

La configuration fournie, les données locales, les écoles, les proxys et une partie des calibrations. La structure du pipeline, elle, est plus générale.

### Qu'est-ce qui doit être repris avec prudence sur un autre terrain ?

- les coefficients de capacité par surface ;
- les distances maximales de destination ;
- les profils horaires ;
- les règles de fréquentation d'activité ;
- les hypothèses touristiques ;
- les statuts scolaires et les capacités locales.

### Comment savoir si le portage est cohérent ?

Il faut au minimum contrôler :

- la structure du GeoPackage ;
- les effectifs globaux ;
- les comptes par profil ;
- les courbes horaires ;
- les bâtiments recevant les plus fortes densités ;
- les sorties de validation externe quand des proxys existent.

## 10. Limites à garder en tête

Le projet ne fournit pas une observation directe du terrain. Il produit une reconstruction paramétrée. La qualité du résultat dépend donc fortement :

- de la qualité du bâti et de ses usages ;
- de la source démographique de référence ;
- de la calibration des paramètres ;
- de la documentation des hypothèses ;
- de la capacité à confronter le résultat à des ordres de grandeur ou à des observations externes.

Autrement dit, la réutilisation du projet demande autant une adaptation méthodologique qu'une adaptation technique.

## 11. Lecture conseillée des autres documents

Pour compléter ce guide :

- [docs/config_reference.md](/home/armotik/Documents/Université/M1/S2/TER/docs/config_reference.md) pour le détail des blocs YAML ;
- [docs/validation_scientifique.md](/home/armotik/Documents/Université/M1/S2/TER/docs/validation_scientifique.md) pour le cadre de validation ;
- [docs/proxy_validation.md](/home/armotik/Documents/Université/M1/S2/TER/docs/proxy_validation.md) pour la validation temporelle par proxys ;
- [docs/exploration_profils.md](/home/armotik/Documents/Université/M1/S2/TER/docs/exploration_profils.md) pour lire les interfaces de contrôle.

## 12. Résumé opérationnel

Pour réutiliser le projet, il faut comprendre quatre choses :

1. le bâtiment est la maille de sortie ;
2. la configuration porte l'essentiel des hypothèses ;
3. la dynamique horaire passe par des foyers et des profils synthétiques ;
4. un portage sérieux exige de recalibrer les données, les coefficients et les scénarios, pas seulement de remplacer des fichiers.
