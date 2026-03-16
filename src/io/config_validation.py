"""
Validation légère de la configuration scientifique.

Le but n'est pas de faire un schéma YAML complet, mais de refuser les scénarios
activant des briques sensibles sans métadonnées minimales de preuve.
"""


def _evidence_is_complete(evidence: dict) -> bool:
    """
    Vérifie qu'un bloc `evidence` contient la trace minimale d'un paramètre.

    L'objectif n'est pas de valider toute la littérature mobilisée, mais
    d'imposer qu'un paramètre activé dans un scénario puisse être relié à :
    - une formule explicitée ;
    - une source identifiable ;
    - une date d'extraction ou de vérification ;
    - un niveau de confiance déclaré.
    """
    required = ['formula', 'source_name', 'extraction_date', 'confidence']
    has_required_fields = all(str(evidence.get(field, '')).strip() for field in required)
    has_traceable_source = any(str(evidence.get(field, '')).strip() for field in ['source_url', 'source_file'])
    return has_required_fields and has_traceable_source


def validate_config_for_evidence(config: dict) -> None:
    non_residential_cfg = config.get('non_residential_model', {})

    for section_name in ['accommodation', 'activities', 'beaches']:
        section = non_residential_cfg.get(section_name, {})
        if not section.get('enabled', False):
            continue

        evidence = section.get('evidence', {})
        if not _evidence_is_complete(evidence):
            raise ValueError(
                f"La section non résidentielle '{section_name}' est activée sans bloc 'evidence' complet dans config.yaml."
            )
