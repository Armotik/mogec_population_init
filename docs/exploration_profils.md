# Lecture des profils et des activités individuelles

Ce document explique comment utiliser les deux interfaces de lecture des profils MOGEC et comment interpréter ce qu'elles montrent.

## 1. Finalité

Ces interfaces servent à répondre à trois questions simples :

- quels profils existent dans le scénario ;
- comment ces profils se répartissent entre domicile, destinations internes et extérieur de la commune selon l'heure ;
- à quoi ressemble, heure par heure, la journée simulée d'une personne synthétique.

Il ne s'agit pas d'une observation individuelle du terrain. Les parcours affichés sont reconstruits à partir des règles du scénario et des données mobilisées dans le modèle.

## 2. Deux modes d'utilisation

### Page HTML autonome

Depuis la racine du projet :

```bash
./.venv/bin/python main.py explore --mode html --config config.yaml
```

Sortie par défaut :

`data/04_visualization/profile_activity_explorer.html`

Cette page est autonome et peut être ouverte localement dans un navigateur.

### Interface web locale

Depuis la racine du projet :

```bash
./.venv/bin/python main.py explore --mode web --config config.yaml
```

URL par défaut :

`http://127.0.0.1:8765`

Cette interface est plus adaptée si l'on veut :

- faire varier l'heure en continu ;
- basculer entre fond plan et fond satellite ;
- suivre un foyer entier ;
- sélectionner une personne sans régénérer un fichier HTML ;
- changer de scénario parmi les fichiers `config*.yaml` présents à la racine du dépôt ;
- relancer le calcul du scénario courant ;
- consulter la validation par proxy et ses métadonnées de traçabilité.
- comparer un même proxy entre plusieurs scénarios déclarés dans `proxy_validation.scenario_sets`.

Le fond satellite dépend de tuiles web externes. Sans connexion côté navigateur, l'interface reste utilisable avec son fond de secours.

## 3. Organisation des vues

Les interfaces sont construites autour de plusieurs lectures complémentaires :

- un résumé des effectifs par profil ;
- un filtre de profil ;
- un sélecteur de foyer et de personne ;
- une lecture horaire combinant synthèse du profil, chronologie individuelle et repérage spatial.
- pour l'interface web locale, un sélecteur de scénario ;
- pour l'interface web locale, un panneau de validation par proxy.

Profils actuellement distingués :

- `scolaire`
- `senior`
- `actif_local`
- `actif_navetteur`
- `inactif`

## 4. Comment lire les résultats

### Résumé par profil

Les cartes du haut donnent l'effectif total de chaque profil. Elles permettent de vérifier rapidement qu'un profil n'a pas disparu, n'est pas surreprésenté ou n'a pas été produit en quantité incohérente.

### Répartition horaire

Pour le profil sélectionné, l'interface indique heure par heure le nombre de personnes :

- au domicile ;
- dans une destination interne à la commune ;
- à l'extérieur de la commune.

Cette lecture sert à vérifier la logique temporelle du scénario. Par exemple :

- les `actif_navetteur` doivent davantage sortir de la commune en journée ;
- les `actif_local` doivent rester plus présents sur des destinations internes ;
- les `scolaire` ne doivent pas dépasser artificiellement la capacité scolaire disponible ;
- les `inactif` doivent conserver une présence plus forte au domicile.

### Chronologie individuelle

Le panneau individuel affiche, pour la personne sélectionnée :

- son bâtiment de domicile ;
- sa destination principale éventuelle ;
- son état heure par heure ;
- le lieu associé à chaque heure.

Cette lecture aide à repérer des cas peu plausibles, par exemple :

- un navetteur qui ne quitte jamais son domicile ;
- un scolaire envoyé hors commune alors qu'une capacité locale reste disponible ;
- un profil local absent toute la journée ;
- une succession de lieux qui ne correspond pas à la logique attendue du scénario.

### Lecture du foyer

Dans l'interface web locale, le panneau foyer permet de contrôler :

- la taille du foyer ;
- la présence d'enfant ;
- le nombre d'enfants accompagnés ;
- l'activité courante de chaque membre à l'heure choisie.

Cette vue est utile pour vérifier la cohérence familiale, notamment autour des déplacements scolaires.

### Validation par proxy

Dans l'interface web locale, un panneau dédié permet aussi de lire les proxys temporels actifs du scénario.

On y trouve :

- le statut du proxy (`pass`, `warn`, `fail` ou `info`) ;
- les métriques de comparaison ;
- la courbe simulée et la courbe de référence ;
- les éléments de traçabilité associés, par exemple la formule, la source, la date et le niveau de confiance.
- un filtre par statut pour cibler rapidement les proxys en échec ou à surveiller ;
- un export CSV de la synthèse et des courbes.
- une comparaison multi-scénarios pour un proxy donné, lancée à la demande pour éviter de bloquer le changement de scénario, avec superposition des courbes simulées et export CSV dédié.

Cette vue est utile pour relier la lecture qualitative des trajectoires à une lecture plus formalisée de la cohérence temporelle du scénario.

### Repérage spatial

La carte n'a pas vocation à remplacer un SIG complet. Elle sert à situer :

- le domicile ;
- la destination interne éventuelle ;
- la position associée à l'heure choisie ;
- les changements de lieu dans la journée.

La représentation reste volontairement simple pour faciliter une lecture rapide.

## 5. Méthode de vérification conseillée

Une lecture utile consiste à :

1. choisir un profil ;
2. vérifier si sa répartition horaire est cohérente avec le scénario ;
3. examiner plusieurs personnes de ce profil ;
4. relever les cas qui paraissent peu plausibles ;
5. revenir ensuite au code ou à la configuration pour corriger la logique.

Anomalies typiques à rechercher :

- amplitude journalière trop faible pour les actifs ;
- trop de scolaires internes au regard des capacités déclarées ;
- profils différents mais journées presque identiques ;
- destinations internes attribuées à des usages peu crédibles ;
- enfant trop éloigné de l'école sans mode d'accès plausible ;
- adulte référent qui n'effectue jamais l'escale école alors que l'enfant est marqué `escort`.

## 6. Accessibilité scolaire et accompagnement

Le modèle distingue plusieurs statuts pour les scolaires :

- `walk` : école assignée à distance compatible avec la marche ;
- `escort` : un adulte référent effectue une escale liée à l'école ;
- `outside_commune` : affectation scolaire hors commune ;
- `unverified_far` : cas à surveiller, si l'école paraît trop éloignée ;
- `inactive` : cas sans école active dans le scénario, par exemple pendant les vacances.

Les paramètres associés sont contrôlés dans `config.yaml` :

- `temporal_model.household_dynamics.school_walk_max_distance_m`
- `temporal_model.household_dynamics.school_pickup_overlap_hours`

## 7. Limites d'interprétation

Il faut garder trois points en tête :

- les personnes affichées sont synthétiques, pas réelles ;
- la trajectoire lue est un résultat de modèle, pas un relevé de terrain ;
- l'interface aide à tester la cohérence d'un scénario, pas à prouver qu'une personne réelle se trouvait à tel endroit.

Formulation possible dans le mémoire :

> L'interface individuelle sert d'outil de contrôle qualitatif pour repérer des incohérences entre profils, horaires, destinations et logiques familiales.

## 8. Lien avec les autres sorties

Ces interfaces complètent les sorties de `data/04_visualization/validation/`.

Lecture recommandée :

- `validation_dashboard.png` pour les agrégats globaux ;
- `external_proxy_validation.csv` pour la confrontation à des ordres de grandeur publics ;
- `profile_activity_explorer.html` pour l'inspection des profils et des trajectoires individuelles.
