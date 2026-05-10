# Backlog Technique - Revue Code MOGEC

Date de revue: 2026-05-08  
Portee: robustesse, utilisabilite globale, reutilisation, securite, formalite des resultats, tests, CI/CD, reproductibilite, configurabilite.

## Legende priorite
- P0: critique (fiabilite/resultat/science/securite)
- P1: important (industrialisation et maintien)
- P2: amelioration utile (ergonomie et dette)

## Backlog priorise

| ID           | Nom                                           | Priorite | Emplacement(s)                                                                            | Description                                                                                                                                                                       |
|--------------|-----------------------------------------------|----------|-------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| MOGEC-BL-001 | Pipeline CI de reference                      | P0       | `.github/workflows/ci.yml` (a creer), `requirements.txt`, `tests/`                        | Ajouter une CI automatique (lint, tests rapides, tests integration marques) sur push/PR pour eviter regressions silencieuses.                                                     |
| MOGEC-BL-002 | Verrouillage des dependances                  | P0       | `requirements.txt`, `pyproject.toml`/`requirements-lock.txt` (a creer)                    | Pinner les versions runtime + dev, separer dependances de test, et produire un lock file reproductible.                                                                           |
| MOGEC-BL-003 | Validation existence fichiers de config       | P0       | `src/io/config_validation.py`, `src/pipeline.py`                                          | La validation verifie les types mais pas l'existence des chemins d'entree/sortie; ajouter une verification explicite et des messages d'erreur actionnables.                       |
| MOGEC-BL-004 | Mode strict sans fallback reseau OSM          | P0       | `src/io/loaders.py`                                                                       | Eviter le fallback implicite vers OSM quand la frontiere locale est absente; en mode recherche/reproductible, echouer explicitement sauf option `allow_network_fallback=true`.    |
| MOGEC-BL-005 | Detection de boucle `extends` YAML            | P0       | `src/pipeline.py`                                                                         | `load_config` est recursif sans protection contre cycles d'heritage; ajouter detection de cycles et erreur claire.                                                                |
| MOGEC-BL-006 | Verification integrite des jeux telecharges   | P0       | `scripts/download_open_data.sh`, `docs/`                                                  | Ajouter checksum/empreinte (SHA256) des ressources open-data et controler l'integrite avant unzip/usage.                                                                          |
| MOGEC-BL-007 | Export atomique des artefacts                 | P1       | `src/io/exporters.py`, `src/io/external_data_preparation.py`                              | Ecrire d'abord dans des fichiers temporaires puis renommer atomiquement pour eviter fichiers partiels en cas d'erreur/interruption.                                               |
| MOGEC-BL-008 | Metadonnees de traçabilite des sorties        | P1       | `src/io/exporters.py`, `src/pipeline.py`, `data/03_processed/`                            | Exporter un manifeste (`json`) associe au GPKG: scenario, seed, hash config, versions libs, date UTC, hash des entrees.                                                           |
| MOGEC-BL-009 | Decoupage tests unitaires/integration         | P1       | `tests/conftest.py`, `tests/`, `pytest.ini` (a creer)                                     | Introduire des marqueurs (`unit`, `integration`, `slow`), fixtures synthetiques pour unitaires, et execution selective rapide en CI.                                              |
| MOGEC-BL-010 | Mesure de couverture                          | P1       | `tests/`, configuration pytest (a creer)                                                  | Ajouter `pytest-cov` avec seuil minimal (ex. 80% sur modules critiques) et rapport HTML/XML en CI.                                                                                |
| MOGEC-BL-011 | Hygiene repository (fichiers parasites)       | P1       | `.gitignore`                                                                              | Ignorer `__pycache__/`, `.pytest_cache/`, `.idea/`, fichiers locaux, pour stabiliser les diffs et eviter bruit de versionnement.                                                  |
| MOGEC-BL-012 | Validation schema plus formelle               | P1       | `src/io/config_validation.py`                                                             | Migrer vers schema typé (Pydantic/JSON Schema) pour messages standardises, contraintes composees et evolution plus sure des configs.                                              |
| MOGEC-BL-013 | Catalogue de scenarios decouvrable            | P1       | `config/`, `docs/config_reference.md`, script CLI (a creer)                               | Ajouter commande `list-scenarios` + metadata (description, objectifs, prerequis) pour usage non-informaticien sans lecture manuelle des YAML.                                     |
| MOGEC-BL-014 | Paquet CLI unique pour non-dev                | P0       | `main.py`, `scripts/`, `src/cli/` (a creer)                                               | Unifier les scripts en sous-commandes (`run`, `prepare`, `validate`, `explore`, `proxy-validate`) avec aide integree, presets scenario, et codes de sortie fiables.               |
| MOGEC-BL-015 | Validation robuste des colonnes source        | P1       | `src/io/external_data_preparation.py`                                                     | Verifier explicitement les colonnes attendues des CSV/GPKG source et lever une erreur intelligible si schema amont change.                                                        |
| MOGEC-BL-016 | Suppression des chemins/fichiers hardcodes    | P1       | `src/io/external_data_preparation.py`                                                     | Remplacer la reference fixe `DS_TOUR_CAP_2026_data.csv` par une resolution configurable/auto-detectee de fichier Insee.                                                           |
| MOGEC-BL-017 | Durcissement preparation plages               | P1       | `src/io/external_data_preparation.py`                                                     | Eviter les hypotheses implicites sur colonnes `id`, `nom`, `commune`; ajouter mapping de colonnes configurable + checks prealables.                                               |
| MOGEC-BL-018 | Journalisation structuree                     | P2       | `main.py`, `scripts/*.py`, `src/**`                                                       | Standardiser logs JSON/horodates/niveaux, limiter `print`, ajouter correlation id de run pour debugging et audit.                                                                 |
| MOGEC-BL-019 | Journal d'execution scientifique              | P2       | `src/pipeline.py`, `src/io/exporters.py`                                                  | Emettre un rapport machine lisible (etape, duree, nb objets, filtres appliques) pour formaliser les resultats et faciliter revue scientifique.                                    |
| MOGEC-BL-020 | Baseline performance et guardrail             | P2       | `tests/test_profiling.py`, CI                                                             | Definir budgets temps/memoire par etape, suivre les regressions de performance dans CI.                                                                                           |
| MOGEC-BL-021 | Politique de securite serveur local           | P2       | `scripts/run_realtime_profile_explorer.py`, `src/visualization/realtime_explorer.py`      | Documenter et restreindre explicitement l'exposition reseau (`127.0.0.1` par defaut), avertissement clair si bind externe.                                                        |
| MOGEC-BL-022 | Stabilite des chemins relatifs YAML           | P2       | `src/pipeline.py`                                                                         | La normalisation de chemins ignore les chemins relatifs sans slash; etendre la detection pour eviter ambiguite de resolution.                                                     |
| MOGEC-BL-023 | Contract tests des sorties GPKG               | P2       | `tests/test_full_pipeline.py`, `src/io/exporters.py`                                      | Ajouter tests de contrat (colonnes obligatoires, types, bornes, non-null critiques) sur les sorties finales pour GAMA.                                                            |
| MOGEC-BL-024 | Mode simulation "dry-run" config              | P2       | `main.py`, `src/pipeline.py`, `src/io/config_validation.py`                               | Ajouter une commande de validation complete sans execution lourde (charge config + verif chemins + schema + prerequis).                                                           |
| MOGEC-BL-025 | Guide d'onboarding operateur non-tech         | P2       | `README.md`, `docs/fonctionnement_modele.md`                                              | Produire une procedure operationnelle pas-a-pas (preparation, lancement, interpretation, erreurs frequentes) orientee utilisateur non dev.                                        |
| MOGEC-BL-026 | Interdire menages dans batiments de culte     | P0       | `src/pipeline.py`, `src/core/agendas.py`, `src/core/cultes.py`, `tests/`                  | Ajouter une regle explicite "no household in `is_culte`" (sauf exception configurable type presbytere) et un test de non-regression.                                              |
| MOGEC-BL-027 | Reordonner pipeline pour contraintes d'usage  | P1       | `src/pipeline.py`                                                                         | Appliquer l'identification des usages speciaux (ecole/culte) avant generation des foyers, pour que les contraintes metier agissent au bon moment.                                 |
| MOGEC-BL-028 | Selection robuste accompagnateur scolaire     | P0       | `src/core/agendas.py`, `src/core/temporal.py`, `tests/test_temporal.py`                   | Remplacer le choix "premier adulte" par un score de faisabilite horaire/proximite; fallback explicite si aucun accompagnateur valide.                                             |
| MOGEC-BL-029 | Corriger pickup/dropoff incoherents           | P0       | `src/core/temporal.py`, `tests/test_temporal.py`                                          | Eviter les pickups qui contredisent l'horaire de travail. Ajouter contraintes de continuite temporelle et de disponibilite au pickup.                                             |
| MOGEC-BL-030 | Corriger scolaires `outside_commune`          | P0       | `src/core/temporal.py`, `tests/test_temporal.py`                                          | Un scolaire marque `outside_commune` ne doit pas rester `domicile` toute la journee; il doit etre `exterieur` pendant la plage scolaire.                                          |
| MOGEC-BL-031 | Distinguer transport vs presence destination  | P1       | `src/core/temporal.py`, `src/visualization/realtime_explorer.py`                          | Introduire un etat/evenement "transport" pour separer l'acte d'accompagnement de la presence stationnaire dans le batiment ecole.                                                 |
| MOGEC-BL-032 | Tests d'invariants comportementaux metier     | P1       | `tests/test_temporal.py`, `tests/test_agendas.py`                                         | Ajouter invariants: pas de menages en culte, pas de pickup impossible, coherence etats domicile/interne/exterieur, transitions horaires plausibles.                               |
| MOGEC-BL-033 | Journal d'audit anomalies agent-level         | P2       | `src/core/temporal.py`, `src/io/exporters.py`                                             | Exporter un CSV d'audit des anomalies (pickup incoherent, scolaire hors commune a domicile, destination introuvable) pour revue scientifique.                                     |
| MOGEC-BL-034 | Conservation population residentielle culte   | P0       | `src/core/downscaling.py`, `src/core/agendas.py`, `tests/`                                | Garantir la conservation des masses (`pop_t0`) malgre l'exclusion des menages en culte (au moins a l'echelle globale, idealement par carreau) et ajouter tests de non-regression. |
| MOGEC-BL-035 | Score accompagnateur configurable             | P1       | `src/core/temporal.py`, `config/base.yaml`, `docs/config_reference.md`, `tests/`          | Externaliser les poids du score de selection accompagnateur (role/disponibilite/proximite) dans la config pour calibration et audit.                                              |
| MOGEC-BL-036 | Test integration outside_commune scenario     | P0       | `tests/test_temporal.py`, `tests/test_full_pipeline.py`, `tests/test_proxy_validation.py` | Ajouter un test d'integration sur scenario reel garantissant que les scolaires `outside_commune` ne restent pas a `domicile` sur la plage scolaire.                               |
| MOGEC-BL-037 | Coherence doc ordre pipeline                  | P2       | `src/pipeline.py`, `README.md`, `docs/fonctionnement_modele.md`                           | Aligner la documentation des etapes pipeline avec l'ordre reel d'execution (culte integre en amont).                                                                              |
| MOGEC-BL-038 | Campagne robustesse multi-seed                | P1       | `tests/`, `tests/test_proxy_validation.py`, `tests/test_reproducibility.py`, CI           | Executer une campagne sur ~100 seeds aleatoires et comparer les distributions/resultats proxies + tests de base; ajouter proxies/tests manquants pour couvrir la variabilite.     |
| MOGEC-BL-039 | Parametre population non residentielle a T0   | P0       | `config/base.yaml`, `src/core/non_residential.py`, `src/pipeline.py`, `tests/`            | Ajouter un parametre global de scenario pour activer/desactiver/moduler l'injection de population non residentielle a `T0`, puis adapter le moteur et les tests associes.         |
| MOGEC-BL-040 | Marqueurs tests unit/integration/slow (suite) | P1       | `tests/`, `pytest.ini`, CI                                                                | Completer le marquage de la suite (unit/integration/slow) pour accelerer le feedback local et fiabiliser les jobs CI differencies.                                                |
| MOGEC-BL-041 | Verbosite CLI progressive                     | P1       | `src/cli/app.py`, `README.md`, `tests/test_cli.py`                                         | Ajouter `-v`/`-vv` sur la CLI unifiee pour tracer explicitement les etapes executees, avec niveaux INFO/DEBUG et tests associes.                                                   |
| MOGEC-BL-042 | Acceleration suite tests sans reduction       | P1       | `tests/`, `tests/test_reproducibility.py`, `tests/test_destinations.py`, `tests/test_temporal.py` | Reduire le temps total d'execution sans diminuer le nombre de tests, via optimisation des jeux de test lourds et ajout de tests de couverture complementaires.                      |

## Ordre d'execution recommande
1. MOGEC-BL-001 a MOGEC-BL-006 (socle fiabilite/reproductibilite).  
2. MOGEC-BL-007 a MOGEC-BL-017 (industrialisation et robustesse data).  
3. MOGEC-BL-018 a MOGEC-BL-033 (ergonomie, observabilite, maintien long terme).

## Audit cible (2026-05-08)

- Culte/familles: risque architectural identifie car `is_culte` est integre apres la generation des foyers (`src/pipeline.py`), donc la contrainte metier n'est pas garantie en amont.
- Escort/accompagnateurs: cause principale probable = choix d'accompagnateur simpliste ("premier adulte") et regles de pickup sans contrainte de continuite horaire (`src/core/agendas.py`, `src/core/temporal.py`).
- Anomalie reproduite: sur scenario scolaire, 145 scolaires `outside_commune` restent a `domicile` toute la plage diurne (comportement incoherent a corriger).

## Suivi execution par lots

### LOT 1 (P0 metier prioritaire) - 2026-05-08

| ID           | Statut | Notes courtes                                                                                                                                 |
|--------------|--------|-----------------------------------------------------------------------------------------------------------------------------------------------|
| MOGEC-BL-026 | done   | Regle explicite `no household in is_culte`, avec exception configurable `culte_residential_exceptions_any_of` (ex: presbytere).               |
| MOGEC-BL-028 | done   | Selection accompagnateur remplacee par un score de faisabilite (disponibilite horaire + proximite destination/ecole) avec fallback explicite. |
| MOGEC-BL-029 | done   | Corrections pickup/dropoff: contraintes de disponibilite, suppression des pickups impossibles, et continuite horaire du parent.               |
| MOGEC-BL-030 | done   | Scolaires `outside_commune` forces a l'etat `EXTERIEUR` pendant la plage scolaire au lieu de rester `DOMICILE`.                               |
| MOGEC-BL-032 | done   | Ajout de tests d'invariants metier ciblant culte, escort scolaire, coherence pickup/dropoff et outside_commune.                               |

### LOT 2 (CLI complete) - 2026-05-08

| ID           | Statut | Notes courtes                                                                                                                      |
|--------------|--------|------------------------------------------------------------------------------------------------------------------------------------|
| MOGEC-BL-014 | done   | CLI unique `main.py` avec sous-commandes `run`, `prepare`, `validate`, `explore`, `proxy-validate`; scripts en wrappers compat. |
| MOGEC-BL-024 | done   | Commande `validate` en dry-run: charge/valide config et verifie prerequis de chemins sans executer le pipeline lourd.            |
| DOC-CLI-LOT2 | done   | README + docs ciblees (`fonctionnement_modele`, `proxy_validation`, `exploration_profils`) alignees sur les nouveaux usages CLI. |

### LOT 2 bis (correctifs CLI + performance tests) - 2026-05-08

| ID           | Statut | Notes courtes                                                                                                                                   |
|--------------|--------|-------------------------------------------------------------------------------------------------------------------------------------------------|
| MOGEC-BL-014 | done   | Correctifs UX CLI: aide globale `-h`, gestion plus stricte des commandes inconnues, wrappers scripts testes.                                  |
| MOGEC-BL-024 | done   | Dry-run renforce: creation des dossiers de sortie manquants + validation des configs referencees dans `proxy_validation.scenario_sets`.       |
| MOGEC-BL-041 | done   | Ajout `-v`/`-vv` avec journalisation progressive des actions CLI (INFO/DEBUG) et tests dedies.                                                |
| MOGEC-BL-042 | done   | Optimisation suite tests sans reduction de volume: 85 tests executes, temps total ramene d'environ 10m23 a ~1m42 sur la meme machine/session. |

### LOT 3 (socle fiabilite/reproductibilite) - 2026-05-08

| ID           | Statut | Notes courtes                                                                                                                                            |
|--------------|--------|----------------------------------------------------------------------------------------------------------------------------------------------------------|
| MOGEC-BL-003 | done   | Validation explicite des chemins config (entrees/sorties) au chargement, avec erreurs actionnables et respect du mode fallback frontiere.              |
| MOGEC-BL-004 | done   | Fallback OSM des frontieres desactive par defaut; activation uniquement via `study_area.allow_network_fallback: true`; tests de non-regression ajoutes. |
| MOGEC-BL-005 | done   | Detection de boucle `extends` dans `load_config` avec message clair incluant la chaine de fichiers impliquee.                                          |
| MOGEC-BL-006 | done   | Verification SHA256 des open-data telecharges avant usage/unzip via manifeste versionne + tests hors reseau du script.                                |

### LOT 4 (industrialisation de base) - 2026-05-08

| ID           | Statut | Notes courtes                                                                                                                                                 |
|--------------|--------|---------------------------------------------------------------------------------------------------------------------------------------------------------------|
| MOGEC-BL-001 | done   | Workflow CI GitHub Actions ajoute (`unit-fast`, `integration`, `coverage`) avec syntax-check, execution par marqueurs et artefact `coverage.xml`.         |
| MOGEC-BL-002 | done   | Dependances epinglees (`requirements.txt`, `requirements-dev.txt`) + snapshot reproductible `requirements-lock.txt`.                                       |
| MOGEC-BL-009 | done   | Decoupage tests via marqueurs `unit/integration/slow` (`pytest.ini` + attribution auto dans `tests/conftest.py`).                                          |
| MOGEC-BL-010 | done   | Couverture `pytest-cov` configuree (job CI dedie, `.coveragerc`, rapport XML exporte, seuil initial `fail_under=70`).                                     |
| MOGEC-BL-011 | done   | Hygiene `.gitignore` completee (`__pycache__`, `.pytest_cache`, `.idea`, fichiers coverage et artefacts locaux).                                          |

### LOTS complementaires proposes (a planifier)

#### LOT 5 (robustesse metier post-LOT1)

| ID           | Statut | Notes courtes                                                                      |
|--------------|--------|------------------------------------------------------------------------------------|
| MOGEC-BL-034 | done   | Conservation de masse `pop_t0` apres exclusion culte via redistribution controlee + tests downscaling/agendas. |
| MOGEC-BL-036 | done   | Tests d'integration scenario reel `weekday_school_day` ajoutes (temporal/full_pipeline/proxy_validation).       |
| MOGEC-BL-037 | done   | Documentation alignee sur l'ordre reel du pipeline (culte identifie en amont).                                    |

#### LOT 6 (stabilite statistique & calibration)

| ID           | Statut | Notes courtes                                                                         |
|--------------|--------|---------------------------------------------------------------------------------------|
| MOGEC-BL-035 | done   | Score accompagnateur externalise dans `temporal_model.household_dynamics.escort_scoring` + validation schema et tests de calibration. |
| MOGEC-BL-038 | done   | Campagne multi-seed (100 seeds) automatisee en test de robustesse avec comparaison proxy + invariants horaires et ajout proxy scolaire exterieur. |

#### LOT 7 (non residentiel T0)

| ID           | Statut | Notes courtes                                                                         |
|--------------|--------|---------------------------------------------------------------------------------------|
| MOGEC-BL-039 | todo   | Nouveau parametre de controle pop non residentielle a `T0` + adaptation moteur/tests. |
