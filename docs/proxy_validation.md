# Validation temporelle par proxys

Cette validation sert a confronter des courbes horaires simulees a des
references externes documentees, sans pretendre reconstruire une verite
terrain exacte.

## Principe

Comparer uniquement la population totale communale sur 24h est peu informatif :
les deplacements internes changent peu ce total. La validation par proxy doit
donc porter sur des courbes plus discriminantes, par exemple :

- part des residents au domicile ;
- part des navetteurs hors commune ;
- part des scolaires en presence interne ;
- part de population presente dans les batiments `Enseignement` ;
- part de population presente dans certains usages BD TOPO.

Le moteur ajoute des metriques de comparaison simples :

- correlation entre la courbe simulee et la courbe de reference ;
- RMSE sur la courbe comparee ;
- decalage entre heure de pic simulee et heure de pic de reference.

## Configuration

Les proxys se declarent dans `config.yaml`, bloc `proxy_validation.temporal_proxies`.

Exemple minimal :

```yaml
proxy_validation:
  temporal_proxies:
    - proxy_id: "navetteurs_exterieur"
      label: "Navetteurs hors commune"
      metric: "role_state_share"
      role: "actif_navetteur"
      state: "exterieur"
      comparison_normalization: "none"
      reference_curve: [0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0]
      applicability:
        day_types: ["weekday"]
        school_holidays: [false]
      thresholds:
        correlation_pass_min: 0.80
        correlation_warn_min: 0.60
        rmse_pass_max: 0.08
        rmse_warn_max: 0.15
        peak_gap_pass_max_hours: 1
        peak_gap_warn_max_hours: 2
      evidence:
        formula: "Part_navetteurs_exterieur(t)"
        source_name: "Source publique a renseigner"
        source_url: "https://example.org/source"
        source_file: ""
        extraction_date: "2026-03-24"
        confidence: "medium"
```

## Types de proxies supportes

- `member_state_share`
- `member_state_count`
- `role_state_share`
- `role_state_count`
- `building_usage_share`
- `building_usage_count`

Etats supportes :

- `domicile`
- `interne`
- `exterieur`

## Execution

Script dedie :

```bash
./.venv/bin/python main.py proxy-validate --config config.yaml
```

Avec plusieurs scenarios explicites :

```bash
./.venv/bin/python main.py proxy-validate \
  --configs config.yaml config_summer_day.yaml
```

Sorties par defaut :

- `data/04_visualization/proxy_validation/proxy_validation_summary.csv`
- `data/04_visualization/proxy_validation/proxy_validation_curves.csv`

## Premier lot configure

Le depot contient maintenant un premier lot de proxys directement declares dans
`config.yaml` :

- `navetteurs_hors_commune_weekday`
- `scolaires_presence_interne_weekday`
- `presence_enseignement_batiments_weekday`

Et un scenario dedie pour les faire parler :

- `config_weekday_school_day.yaml`

Ce scenario sert de base de comparaison "jour ouvre hors vacances". Le jeu
`proxy_validation.scenario_sets.default` compare par defaut ce scenario a
`config_summer_day.yaml`.

## Lecture scientifique

Cette validation est utile surtout pour comparer des **formes de courbe** et
des **pics horaires** entre scenarios. Elle ne remplace pas :

- les controles structurels du GeoPackage ;
- les ordres de grandeur INSEE ;
- la validation spatiale ;
- les observations de terrain ou l'expertise locale.
