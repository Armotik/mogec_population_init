# Validation scientifique et veracite des resultats

Ce document sert a distinguer trois choses qu'il ne faut pas melanger dans le memoire :

1. la coherence technique du pipeline ;
2. la coherence scientifique interne du scenario ;
3. la veracite externe du resultat simule.

Le projet MOGEC peut demontrer assez fortement les points 1 et 2.
Le point 3 ne peut pas etre "prouve" uniquement par le modele lui-meme. Il faut une confrontation a des references externes.

## 1. Ce que le projet peut verifier directement

### Structure de l'export

Questions a poser :
- le GeoPackage final est-il complet ?
- les identifiants sont-ils stables et sans doublon ?
- les colonnes horaires `pop_h0` a `pop_h23` sont-elles toutes presentes ?
- des valeurs negatives existent-elles ?

Dans le projet :
- `src/visualization/validation.py::structural_quality_report`
- `scientific_methodology_checklist`

Interpretation :
- si ces tests echouent, il ne faut pas discuter de resultat scientifique avant correction ;
- ce sont des preconditions de validite.

### Coherence demographique

Questions a poser :
- la somme des roles reconstruits retombe-t-elle sur `pop_t0` ?
- les roles realises restent-ils proches des cibles du `config.yaml` ?

Dans le projet :
- `role_targets_vs_realized`
- `scientific_methodology_checklist`

Interpretation :
- un ecart faible renforce la defendabilite du scenario ;
- un ecart fort indique soit un parametre mal calibre, soit une logique de generation qui derive par rapport aux cibles.

### Coherence temporelle

Questions a poser :
- le cycle journalier varie-t-il vraiment ?
- l'heure de pic et l'heure de creux sont-elles plausibles pour le scenario choisi ?
- l'amplitude journaliere est-elle compatible avec le recit du territoire ?

Dans le projet :
- `hourly_population_profile`
- `plot_scientific_validation_dashboard`
- `src/visualization/temporal_visu.py`

Interpretation :
- une serie totalement plate est suspecte ;
- une dynamique tres forte doit etre justifiee par les hypotheses (navetteurs, tourisme, saison, alerte).

### Tracabilite des hypotheses sensibles

Questions a poser :
- les briques non residentielles actives sont-elles rattachees a une source identifiable ?
- la formule est-elle explicite ?
- la date d'extraction ou de verification est-elle indiquee ?
- le niveau de confiance est-il declare ?

Dans le projet :
- `src/io/config_validation.py`
- `evidence_traceability_report`

Interpretation :
- sans bloc `evidence`, une hypothese peut etre utile operatoirement mais reste fragile scientifiquement ;
- un bloc `evidence` complet ne prouve pas que l'hypothese est vraie, mais il rend la methode auditabile.

## 2. Ce que la coherence interne ne prouve pas

Une exportation propre, des roles bien calibres et des courbes lisibles ne suffisent pas a dire :

- que les personnes sont dans les "bons" batiments reellement ;
- que les heures exactes de depart/retour sont vraies sur le terrain ;
- que les populations non residentielles sont observees au bon niveau ;
- que le comportement simule reproduit fidelement une journee reelle.

Autrement dit :

- la coherence interne repond a "le modele fait-il ce qu'il pretend faire ?";
- la veracite externe repond a "le modele ressemble-t-il suffisamment au monde reel?".

## 3. Comment commencer une verification externe serieuse

La bonne approche est une validation multi-niveaux.

### Niveau A. Ordres de grandeur institutionnels

Comparer le modele a des chiffres de reference independants :

- population communale INSEE ;
- structure par age ;
- part d'actifs travaillant dans la commune ;
- capacites scolaires ;
- capacites touristiques ;
- capacites d'hebergement declarees.

But :
- verifier que le scenario reste dans une enveloppe plausible.

### Niveau B. Validation par composante

Verifier chaque bloc separatement :

- residentiel : total population, nombre de batiments habites, densites aberrantes ;
- scolaire : nombre d'eleves affectes, adequation aux lieux `Enseignement` ;
- actifs locaux : volume affecte a des destinations internes plausibles ;
- navetteurs : baisse diurne compatible avec la structure d'emploi ;
- hebergement : ordre de grandeur compatible avec les capacites touristiques ;
- plages : population ajoutee compatible avec la saison et la meteo du scenario.

But :
- eviter qu'un bon resultat global masque une composante aberrante.

### Niveau C. Validation spatiale

Verifier la plausibilite spatiale :

- les poles d'arrivee sont-ils des batiments credibles ?
- des zones importantes du territoire restent-elles vides de facon suspecte ?
- les plus fortes densites apparaissent-elles la ou cela a du sens ?

But :
- detecter les erreurs invisibles dans les seuls tableaux agreges.

### Niveau D. Validation temporelle

Verifier la plausibilite des horaires :

- le pic nocturne est-il logique ?
- le creux diurne correspond-il bien a une sortie des navetteurs ou des scolaires ?
- les reprises de fin de journee sont-elles trop abruptes ?

But :
- confronter le recit temporel du modele a la realite du territoire.

### Niveau E. Validation de terrain ou experte

Si possible, confronter le modele a :

- comptages ponctuels ;
- observations communales ;
- expertise locale ;
- retours d'acteurs du territoire ;
- documentation d'evenements reels.

But :
- sortir du modele auto-referentiel.

## 4. Sorties ajoutees dans le depot

Le script suivant genere un dossier de validation complet :

```bash
./.venv/bin/python scripts/generate_scientific_validation.py --config config.yaml
```

Sorties produites par defaut dans `data/04_visualization/validation/` :

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

Ce dernier fichier sert a confronter le modele a des proxys publics deja disponibles dans le projet :

- emplois locaux de la commune ;
- capacites scolaires locales ;
- capacite touristique retenue.

Attention :

- sur un scenario marque `is_school_holiday: true`, le proxy scolaire devient surtout indicatif ;
- dans ce cas, le statut peut etre `info` plutot que `pass`, pour signaler qu'il ne faut pas sur-interpreter une absence de frequentation scolaire interne.

Un second outil complete cette lecture :

```bash
./.venv/bin/python scripts/generate_profile_activity_explorer.py --config config.yaml
```

Il produit `data/04_visualization/profile_activity_explorer.html`, utile pour controler qualitativement les profils, leurs activites et quelques trajectoires individuelles sans passer par un notebook.

Un troisieme script cible la confrontation multi-scenarios a des courbes
horaires de reference documentees :

```bash
./.venv/bin/python scripts/run_proxy_validation.py --config config.yaml
```

Il produit par defaut :

- `data/04_visualization/proxy_validation/proxy_validation_summary.csv`
- `data/04_visualization/proxy_validation/proxy_validation_curves.csv`

Voir aussi `docs/proxy_validation.md` pour le schema YAML et la logique de
comparaison par correlation, RMSE et decalage d'heure de pic.

Pour une lecture plus dynamique, un serveur web local est aussi disponible :

```bash
./.venv/bin/python scripts/run_realtime_profile_explorer.py --config config.yaml
```

Il permet de suivre un foyer, une personne et les statuts `walk` / `escort` des scolaires sur une carte interactive, y compris en fond satellite.

## 5. Ligne de defense pour le memoire

Formulation robuste :

> Le modele ne pretend pas observer directement la verite terrain. Il produit une reconstruction spatio-temporelle coherente, parametree et tracable, dont la validite est evaluee a la fois par des controles internes, par la traçabilite des hypotheses et par une confrontation progressive a des references externes.

Formulation a eviter :

> Le modele montre la population reelle de Batz-sur-Mer heure par heure.

La seconde phrase est trop forte scientifiquement.
