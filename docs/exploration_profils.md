# Explorer les profils et les activites individuelles

Ce document explique comment lire l'explorateur HTML des profils MOGEC et ce qu'il permet de verifier.

## 1. Objectif

L'explorateur sert a repondre a trois questions simples :

- quels profils existent dans le scenario ;
- comment chaque profil se repartit entre domicile, destinations internes et exterieur de la commune selon l'heure ;
- a quoi ressemble la trajectoire horaire d'un individu donne.

Il ne s'agit pas d'une verite terrain individuelle. L'outil montre une trajectoire simulee, generee a partir des regles du scenario et des donnees ouvertes utilisees pour calibrer le modele.

## 2. Deux modes d'exploration

### Mode 1. HTML autonome

Depuis la racine du projet :

```bash
./.venv/bin/python scripts/generate_profile_activity_explorer.py --config config.yaml
```

Sortie par defaut :

`data/04_visualization/profile_activity_explorer.html`

Le fichier est autonome et peut etre ouvert localement dans un navigateur.

### Mode 2. Serveur web local

Depuis la racine du projet :

```bash
./.venv/bin/python scripts/run_realtime_profile_explorer.py --config config.yaml
```

URL par defaut :

`http://127.0.0.1:8765`

Ce mode est a privilegier si tu veux :

- changer l'heure en continu ;
- basculer entre fond plan et fond satellite ;
- suivre un foyer entier ;
- selectionner une personne sans regenerator un fichier HTML ;
- modifier quelques parametres de scenario directement dans l'interface ;
- recharger le scenario depuis l'interface.

Le fond satellite repose sur des tuiles web. Il faut donc une connexion internet cote navigateur pour cet habillage de carte.
Si ces tuiles ne sont pas disponibles, la preview garde quand meme un fond de carte autonome et les trajectoires restent visibles.

Les modifications appliquees depuis l'interface web sont calculees en memoire pour la session en cours. Elles ne reecrivent pas `config.yaml`.
Le bloc `Patch YAML session` permet aussi d'injecter directement un petit morceau de configuration sans sortir de la preview.

## 3. Ce que contient l'explorateur

L'interface web locale est organisee autour de quatre zones :

- un resume des effectifs par profil ;
- un filtre de profil ;
- un selecteur de foyer et d'individu ;
- une vue horaire combinant synthese de profil, suivi individuel et lecture familiale.

Profils actuellement visibles :

- `scolaire`
- `senior`
- `actif_local`
- `actif_navetteur`
- `inactif`

## 4. Lire les indicateurs

### Cartes de profil

Les cartes du haut donnent l'effectif total de chaque profil dans le scenario.
Elles servent a verifier rapidement qu'un profil ne disparait pas par erreur ou qu'il n'est pas sur-represente.

### Resume horaire du profil

Pour le profil selectionne, l'explorateur affiche heure par heure le nombre d'individus :

- au `domicile` ;
- sur une destination `interne` a la commune ;
- a `l'exterieur` de la commune.

Cette vue est utile pour verifier la logique temporelle :

- les `actif_navetteur` doivent quitter la commune en journee ;
- les `actif_local` doivent davantage occuper des destinations internes ;
- les `scolaire` ne doivent pas depasser artificiellement la capacite scolaire interne ;
- les `inactif` doivent conserver une presence plus forte au domicile.

### Tableau individuel

Le panneau individuel montre, pour un agent selectionne :

- son domicile ;
- sa destination principale assignee ;
- son etat a chaque heure ;
- le libelle de destination a l'heure choisie.

Cette lecture sert a reperer les cas illogiques, par exemple :

- un navetteur qui ne quitte jamais son domicile ;
- un scolaire affecte a l'exterieur alors qu'une capacite interne existe encore ;
- un profil local qui passe toute la journee hors commune ;
- des changements de destination impossibles a justifier.

### Lecture familiale

Sur le serveur web local, le panneau foyer permet de verifier :

- la taille du foyer ;
- la presence d'enfant(s) ;
- le nombre d'enfants accompagnes ;
- l'activite courante de chaque membre a l'heure choisie.

Cette vue sert a reperer des incoherences de coordination familiale.

### Suivi spatial simplifie

Le schema spatial ne remplace pas une carte SIG complete. Il sert a montrer :

- le domicile ;
- la destination interne eventuelle ;
- la position associee a l'heure selectionnee.

Il est volontairement simple, pour permettre une lecture rapide des trajectoires individuelles.

## 5. Usage recommande pour la verification

L'explorateur est surtout utile comme outil de controle qualitatif.

Workflow conseille :

1. filtrer un profil ;
2. verifier si la synthese horaire raconte quelque chose de plausible ;
3. echantillonner plusieurs individus de ce profil ;
4. noter les cas visiblement aberrants ;
5. revenir ensuite au code ou a la configuration pour corriger la logique.

Exemples d'anomalies a chercher :

- amplitude journaliere trop faible pour les actifs ;
- trop de scolaires internes par rapport aux capacites declarees ;
- profils differents mais trajectoires presque identiques ;
- destinations internes attribuees a des usages peu credibles.
- enfant trop loin de l'ecole sans mode d'acces plausible ;
- parent qui n'effectue jamais l'escale ecole alors que l'enfant est marque `escort`.

## 6. Accessibilite scolaire et accompagnement

Le modele distingue maintenant plusieurs statuts pour les scolaires :

- `walk` : l'ecole assignee est a une distance compatible avec un trajet a pied ;
- `escort` : un parent ou adulte referent fait une escale a l'ecole avant son activite principale ou sur le retour ;
- `outside_commune` : l'affectation scolaire sort de la commune ;
- `unverified_far` : un cas a surveiller, si un enfant est trop loin sans mecanisme d'accompagnement exploitable ;
- `inactive` : cas de scenario sans ecole active, par exemple vacances scolaires.

Le seuil de marche et la tolerance de reprise parentale sont controles dans `config.yaml` :

- `temporal_model.household_dynamics.school_walk_max_distance_m`
- `temporal_model.household_dynamics.school_pickup_overlap_hours`

## 7. Limites d'interpretation

Il faut rester strict sur ce point :

- l'explorateur suit des individus synthetiques, pas des personnes reelles ;
- la trajectoire affichee est un resultat de modele, pas un releve terrain ;
- l'outil aide a tester la coherence du scenario, pas a prouver qu'un individu reel est a tel endroit.

Formulation robuste dans le memoire :

> L'explorateur individuel est utilise comme instrument de controle qualitatif des comportements simules et de detection d'incoherences logiques entre profils, horaires et destinations.

## 8. Articulation avec la validation scientifique

L'explorateur complete les sorties du dossier `data/04_visualization/validation/`.

Utilisation recommandee :

- `validation_dashboard.png` pour les agregats globaux ;
- `external_proxy_validation.csv` pour la confrontation a des ordres de grandeur publics ;
- `profile_activity_explorer.html` pour l'inspection dynamique des profils et des trajectoires individuelles.
