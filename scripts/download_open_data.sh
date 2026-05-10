#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${MOGEC_ROOT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
CHECKSUM_FILE="${MOGEC_CHECKSUM_FILE:-$ROOT_DIR/docs/open_data_checksums.sha256}"
SKIP_DOWNLOADS="${MOGEC_SKIP_DOWNLOADS:-0}"
SKIP_UNZIP="${MOGEC_SKIP_UNZIP:-0}"

mkdir -p \
  "$ROOT_DIR/data/01_raw/tourisme_pdl" \
  "$ROOT_DIR/data/01_raw/plages" \
  "$ROOT_DIR/data/01_raw/economie" \
  "$ROOT_DIR/data/01_raw/insee_tourisme"

if [[ ! -f "$CHECKSUM_FILE" ]]; then
  echo "Checksum manifest not found: $CHECKSUM_FILE" >&2
  exit 1
fi

verify_checksum() {
  local output="$1"
  local rel_path="${output#"$ROOT_DIR"/}"
  local expected
  expected="$(awk -v path="$rel_path" '$2 == path {print $1}' "$CHECKSUM_FILE")"
  if [[ -z "$expected" ]]; then
    echo "Missing checksum entry for $rel_path in $CHECKSUM_FILE" >&2
    exit 1
  fi
  local actual
  actual="$(sha256sum "$output" | awk '{print $1}')"
  if [[ "$actual" != "$expected" ]]; then
    echo "Checksum mismatch for $rel_path" >&2
    echo "Expected: $expected" >&2
    echo "Actual:   $actual" >&2
    exit 1
  fi
}

download() {
  local url="$1"
  local output="$2"
  if [[ "$SKIP_DOWNLOADS" == "1" ]]; then
    echo "Skipping download for $(basename "$output")"
  else
    echo "Downloading $(basename "$output")"
    curl -L --fail --retry 3 --retry-delay 2 -o "$output" "$url"
  fi
  if [[ ! -f "$output" ]]; then
    echo "Required file not found after download phase: $output" >&2
    exit 1
  fi
  verify_checksum "$output"
}

download_optional() {
  local url="$1"
  local output="$2"
  if [[ "$SKIP_DOWNLOADS" == "1" ]]; then
    echo "Skipping optional download for $(basename "$output")"
  else
    echo "Downloading optional $(basename "$output")"
    if ! curl -L --fail --retry 3 --retry-delay 2 -o "$output" "$url"; then
      echo "Warning: optional download failed for $(basename "$output")" >&2
      rm -f "$output"
      return 0
    fi
  fi
  if [[ -f "$output" ]]; then
    verify_checksum "$output"
  fi
}

# Flux touristiques institutionnels Pays de la Loire / DATAtourisme
download "https://data.paysdelaloire.fr/api/explore/v2.1/catalog/datasets/234400034_070-008_offre-touristique-restaurants-rpdl/exports/csv?use_labels=true" \
  "$ROOT_DIR/data/01_raw/tourisme_pdl/restaurants_pdl.csv"
download "https://data.paysdelaloire.fr/api/explore/v2.1/catalog/datasets/234400034_070-006_offre-touristique-hotels-rpdl/exports/csv?use_labels=true" \
  "$ROOT_DIR/data/01_raw/tourisme_pdl/hotels_pdl.csv"
download "https://data.paysdelaloire.fr/api/explore/v2.1/catalog/datasets/234400034_070-005_offre-touristique-hotelleries-de-plein-air-rpdl/exports/csv?use_labels=true" \
  "$ROOT_DIR/data/01_raw/tourisme_pdl/campings_pdl.csv"
download "https://data.paysdelaloire.fr/api/explore/v2.1/catalog/datasets/234400034_070-007_offre-touristique-residences-de-tourisme-rpdl/exports/csv?use_labels=true" \
  "$ROOT_DIR/data/01_raw/tourisme_pdl/residences_tourisme_pdl.csv"
download "https://data.paysdelaloire.fr/api/explore/v2.1/catalog/datasets/234400034_070-003_offre-touristique-hebergements-collectifs-rpdl/exports/csv?use_labels=true" \
  "$ROOT_DIR/data/01_raw/tourisme_pdl/hebergements_collectifs_pdl.csv"
download "https://data.paysdelaloire.fr/api/explore/v2.1/catalog/datasets/234400034_070-004_offre-touristique-hebergements-locatifs-rpdl/exports/csv?use_labels=true" \
  "$ROOT_DIR/data/01_raw/tourisme_pdl/hebergements_locatifs_pdl.csv"

# Référentiels littoraux et tourisme Insee
download "https://www.data.gouv.fr/api/1/datasets/r/57b07c5e-5261-4051-8321-84ff8c62cedd" \
  "$ROOT_DIR/data/01_raw/plages/plages_sable_loire_atlantique.zip"
download "https://www.data.gouv.fr/api/1/datasets/r/84f64cd2-74e1-48ec-bc40-a3ea0346a8a6" \
  "$ROOT_DIR/data/01_raw/insee_tourisme/capacites_hebergements_touristiques.zip"
download_optional "https://www.insee.fr/fr/statistiques/fichier/8742829/pa_ina_155.xlsx" \
  "$ROOT_DIR/data/01_raw/insee_tourisme/frequentation_hebergements_collectifs_pays_loire_2024.xlsx"

# La BPE et SIRENE restent à télécharger dans un second temps :
# - BPE : le lien de ressource courant doit être ré-identifié sur data.gouv.
# - SIRENE : le dump national est très volumineux et mérite une stratégie filtrée.

if [[ "$SKIP_UNZIP" != "1" ]]; then
  rm -rf "$ROOT_DIR/data/01_raw/plages/plages_sable_loire_atlantique"
  mkdir -p "$ROOT_DIR/data/01_raw/plages/plages_sable_loire_atlantique"
  unzip -o "$ROOT_DIR/data/01_raw/plages/plages_sable_loire_atlantique.zip" -d "$ROOT_DIR/data/01_raw/plages/plages_sable_loire_atlantique" >/dev/null

  rm -rf "$ROOT_DIR/data/01_raw/insee_tourisme/capacites_hebergements_touristiques"
  mkdir -p "$ROOT_DIR/data/01_raw/insee_tourisme/capacites_hebergements_touristiques"
  unzip -o "$ROOT_DIR/data/01_raw/insee_tourisme/capacites_hebergements_touristiques.zip" -d "$ROOT_DIR/data/01_raw/insee_tourisme/capacites_hebergements_touristiques" >/dev/null
fi

echo "Downloads completed with checksum verification."
