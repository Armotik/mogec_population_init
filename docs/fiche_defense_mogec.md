# Fiche de defense MOGEC

Cette fiche sert a presenter le projet sans survendre le modele et sans devoir
reciter le code ligne par ligne.

## 1. Ce que je peux dire en une phrase

"J'ai construit et organise un pipeline Python qui transforme des donnees
ouvertes heterogenes en un etat initial spatio-temporel exploitable dans GAMA,
avec des scenarios parametrables, des controles de coherence et une premiere
validation par proxys."

## 2. Ce que le projet fait vraiment

Le pipeline execute les etapes suivantes :

1. charger la zone d'etude et les batiments ;
2. filtrer les batiments non plausibles ;
3. attribuer un `building_id` stable ;
4. rattacher les batiments au carroyage Filosofi ;
5. ventiler la population residente vers les batiments ;
6. ajouter des composantes non residentielles si elles sont activees ;
7. generer des foyers, des roles et des destinations ;
8. produire une matrice horaire `pop_h0` a `pop_h23` ;
9. exporter le resultat final en GeoPackage pour GAMA.

Le point d'entree reel est `main.py`, qui delegue tout a
`src/pipeline.py::run_pipeline_to_export`.

## 3. Ce que j'ai apporte au projet

La formulation la plus defendable est :

"Mon apport principal n'est pas seulement une carte finale. J'ai mis en place
un moteur de generation par scenarios, en reliant plusieurs sources de donnees,
en structurant les etapes du pipeline, en ajoutant des exports exploitables
dans GAMA et en encadrant le tout par des tests et des outils de validation."

Si on me demande "qu'est-ce que tu as vraiment fait ?", je peux repondre :

- j'ai assemble les sources de donnees autour du bati comme referentiel central ;
- j'ai structure un pipeline reproductible plutot qu'un traitement manuel ;
- j'ai rendu les hypotheses scenario-dependantes via YAML ;
- j'ai ajoute des sorties de validation et de visualisation ;
- j'ai formalise une posture scientifique prudente sur les resultats.

## 4. Ce que je peux prouver, et comment

Il faut separer trois niveaux.

### A. Coherence technique

Je peux prouver que l'export final est bien forme.

Sur l'export actuel (`data/03_processed/population_batz_t0.gpkg`) :

- `4 779` entites exportees ;
- `24` colonnes horaires presentes ;
- `0` `building_id` dupliques ;
- `0` geometries nulles ;
- `0` valeurs horaires negatives.

Source :

- `data/04_visualization/validation/structural_quality.csv`

### B. Coherence interne du scenario

Je peux prouver que le scenario principal est coherent avec ses propres
parametres.

Sur le scenario courant :

- `pop_t0 = 3 726` ;
- heure de reference = `h2` ;
- population a l'heure de reference = `3 726` ;
- ecart `pop_t0` vs heure de reference = `0` ;
- population minimale sur 24h = `2 615` ;
- population maximale sur 24h = `3 726`.

Les roles cibles sont exactement respectes :

- scolaires : `361` ;
- seniors : `1 580` ;
- actifs locaux : `578` ;
- actifs navetteurs : `919` ;
- inactifs : `288`.

Sources :

- `data/04_visualization/validation/export_metrics.csv`
- `data/04_visualization/validation/role_targets_vs_realized.csv`
- `data/04_visualization/validation/scientific_methodology_checklist.csv`

### C. Plausibilite externe partielle

Je ne peux pas "prouver la verite terrain", mais je peux montrer que le modele
a ete confronte a des references externes.

Pour le scenario `jour_ouvre_hors_vacances`, les proxys temporels donnent :

- navetteurs hors commune : correlation `0.9721`, RMSE `0.112`, pic a `9h` ;
- presence scolaire interne : correlation `0.9498`, RMSE `0.1271`, pic a `9h` ;
- charge des batiments d'enseignement : correlation `0.9498`, RMSE `0.1271`,
  pic a `9h`.

Source :

- `data/04_visualization/proxy_validation/proxy_validation_summary.csv`

Formulation correcte :

"Ces proxys ne prouvent pas que le modele reproduit exactement le terrain. Ils
montrent seulement que certaines formes de courbe sont compatibles avec des
references publiques documentees."

## 5. Ce que je ne dois pas dire

Je ne dois pas dire :

- "le modele montre la population reelle heure par heure" ;
- "chaque personne est dans le bon batiment" ;
- "les horaires sont vrais sur le terrain" ;
- "les validations internes prouvent la realite empirique".

Je dois dire a la place :

"Le modele produit une reconstruction plausible, parametree, tracable et
reproductible, utile pour la simulation, mais pas une observation directe du
reel."

## 6. Reponse simple si on me demande pourquoi j'ai utilise l'IA

Reponse defendable :

"L'IA m'a aide a accelerer l'implementation et la structuration technique, mais
la valeur du travail ne repose pas sur le fait d'avoir genere du code. Elle
repose sur la definition du probleme, le choix des donnees, le parametriage des
scenarios, l'interpretation scientifique des sorties et la capacite a verifier
ce que le pipeline produit reellement."

Version plus directe :

"Je ne presente pas chaque ligne comme une creation originale. En revanche, je
dois etre capable d'expliquer l'architecture, les hypotheses, les limites et
les validations du modele. C'est cela que je defend."

## 7. Questions probables et reponses courtes

### "Comment sais-tu que ton resultat est credible ?"

"Je ne le presente pas comme vrai par definition. Je le defend sur trois plans :
qualite structurelle de l'export, coherence interne du scenario et confrontation
partielle a des references externes par proxys."

### "Comment sais-tu que ce n'est pas arbitraire ?"

"Les hypotheses sensibles sont mises dans la configuration YAML, documentees par
des blocs `evidence`, puis relues dans des tableaux de validation. Cela rend la
methode auditable."

### "Qu'est-ce que tu ferais pour aller plus loin ?"

"Je renforcerais la validation externe avec des comptages locaux, des retours
d'acteurs du territoire et une comparaison plus fine a des observations de
terrain."

## 8. Commandes a connaitre pour la soutenance

Regenerer l'export :

```bash
./.venv/bin/python main.py --config config.yaml
```

Regenerer le dossier de validation :

```bash
./.venv/bin/python scripts/generate_scientific_validation.py --config config.yaml
```

Regenerer la validation par proxys :

```bash
./.venv/bin/python scripts/run_proxy_validation.py --config config_weekday_school_day.yaml
```

## 9. Ligne de defense finale

Si je dois conclure en 20 secondes :

"Le projet ne fournit pas une verite terrain observee. Il fournit un pipeline
reproductible qui reconstruit une population spatio-temporelle plausible a
l'echelle du bati, scenario-dependante, exportable vers GAMA et deja encadree
par des controles internes et une premiere confrontation externe."
