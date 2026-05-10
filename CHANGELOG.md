# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned
- BL-039: ajouter un paramètre moteur pour contrôler l'injection de population non résidentielle à `T0`.

## [2.0.1] - 2026-05-08

### Added
- CLI unifiée `main.py` avec sous-commandes `run`, `prepare`, `validate`, `explore`, `proxy-validate`.
- Mode dry-run complet pour validation de configuration et prérequis de chemins.
- Verbosité CLI progressive `-v`/`-vv`.
- Validation stricte de config: détection de cycles `extends`, contrôle d'existence des chemins, erreurs actionnables.
- Paramètre `study_area.allow_network_fallback` pour activer explicitement le fallback OSM.
- Vérification SHA256 des open-data téléchargées via manifeste versionné.
- Workflow CI GitHub Actions (`unit-fast`, `integration`, `coverage`) avec artefact `coverage.xml`.
- Marqueurs de tests `unit`, `integration`, `slow` et découpage d'exécution correspondant.
- Configuration de couverture (`pytest-cov`, `.coveragerc`) et seuil initial.
- `requirements-dev.txt` et `requirements-lock.txt` pour améliorer la reproductibilité.
- Paramétrage explicite du score de sélection d'accompagnateur scolaire via `temporal_model.household_dynamics.escort_scoring`.
- Test de campagne multi-seed (100 seeds) avec comparaison proxy et invariants horaires.
- Proxy de robustesse `scolaires_exterieur_weekday` ajouté à la validation temporelle.
- Tests de non-régression supplémentaires sur:
  - contraintes culte/ménages,
  - sélection accompagnateur scolaire,
  - cohérence pickup/dropoff,
  - scolaire `outside_commune`,
  - checksums des téléchargements,
  - classification automatique des tests.

### Changed
- Réordonnancement du pipeline: identification des écoles/culte en amont de la ventilation résidentielle.
- Durcissement du chargement des frontières: plus de fallback OSM implicite.
- Documentation CLI et configuration alignée avec les comportements réels.
- Hygiène repository renforcée (`.gitignore` élargi pour caches/IDE/coverage).
- Référence de configuration mise à jour pour documenter la calibration `escort_scoring`.

### Fixed
- Interdiction des ménages dans les bâtiments de culte (hors exceptions configurables).
- Correction des choix d'accompagnateur scolaire avec score de faisabilité.
- Correction des pickups/dropoffs incohérents avec continuité temporelle.
- Correction des scolaires `outside_commune` pour éviter l'état `domicile` sur la plage scolaire.
- Conservation de la masse `pop_t0` quand un carreau perd son résidentiel à cause d'une exclusion culte (redistribution sur le parc résidentiel éligible).
- Sélection d'accompagnateur rendue calibrable sans modification de code (poids rôle/proximité/pickup/alignement horaire).
