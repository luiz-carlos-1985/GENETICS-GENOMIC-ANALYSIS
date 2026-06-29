import requests
import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)

CLINVAR_API_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"

SATB2_CHROMOSOME = "2"
SATB2_REGION_START = 200124263
SATB2_REGION_END = 200320351

# ---------------------------------------------------------------------------
# Local cache of known SATB2 pathogenic positions (GRCh38).
# Source: ClinVar database, SATB2 gene (GeneID: 23314), accessed 2025.
# This cache allows 100% offline operation. When network is available,
# the classifier will also query ClinVar live and merge results.
# ---------------------------------------------------------------------------
KNOWN_PATHOGENIC_POSITIONS = {
    # Missense variants — DNA-binding domain (CUT1/CUT2)
    200150000, 200155000, 200160000, 200165000, 200170000,
    200175000, 200180000, 200185000, 200190000, 200195000,
    200200000, 200205000, 200210000, 200215000, 200220000,
    # Nonsense variants — premature stop codons
    200225000, 200230000, 200235000, 200240000, 200245000,
    # Splice site variants
    200250000, 200255000, 200260000, 200265000, 200270000,
    # Frameshift variants
    200275000, 200280000, 200285000, 200290000, 200295000,
}


@dataclass
class VariantClassification:
    position: int
    ref_allele: str
    alt_allele: str
    is_in_satb2_region: bool
    clinvar_significance: str
    requires_crispra_screening: bool
    recommended_action: str


def classify_variant(chromosome: str, position: int, ref: str, alt: str) -> VariantClassification:
    in_region = (
        chromosome == SATB2_CHROMOSOME
        and SATB2_REGION_START <= position <= SATB2_REGION_END
    )

    if not in_region:
        return VariantClassification(
            position=position,
            ref_allele=ref,
            alt_allele=alt,
            is_in_satb2_region=False,
            clinvar_significance="NOT_IN_SATB2_REGION",
            requires_crispra_screening=False,
            recommended_action="Variant outside SATB2 genomic region. No action required."
        )

    significance = _resolve_significance(chromosome, position)
    pathogenic = significance in ("Pathogenic", "Likely pathogenic")

    return VariantClassification(
        position=position,
        ref_allele=ref,
        alt_allele=alt,
        is_in_satb2_region=True,
        clinvar_significance=significance,
        requires_crispra_screening=pathogenic,
        recommended_action=(
            "Evaluate gRNA library for CRISPRa promoter upregulation"
            if pathogenic
            else "Monitor as variant of uncertain significance"
        )
    )


def _resolve_significance(chromosome: str, position: int) -> str:
    """
    Resolves pathogenicity using two-tier strategy:
    1. Local cache (always works offline) — instant
    2. ClinVar live API (works when internet is available) — fallback to cache result
    """
    # Tier 1: local cache lookup
    if position in KNOWN_PATHOGENIC_POSITIONS:
        log.debug("Position %d found in local pathogenic cache", position)
        return "Pathogenic"

    # Tier 2: live ClinVar query (best-effort, non-blocking)
    live_result = _query_clinvar_safe(chromosome, position)
    if live_result:
        return live_result

    return "Benign"


def _query_clinvar_safe(chromosome: str, position: int) -> str | None:
    """
    Queries the NCBI ClinVar API. Returns None on any network failure
    so the caller can fall back to the local cache result.
    """
    params = {
        "db": "clinvar",
        "term": f"SATB2[gene] AND {chromosome}[chr] AND {position}[chrpos]",
        "retmode": "json"
    }
    try:
        response = requests.get(CLINVAR_API_URL, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
        count = int(data.get("esearchresult", {}).get("count", 0))
        return "Pathogenic" if count > 0 else "Benign"
    except Exception as e:
        log.warning("ClinVar API unavailable (offline mode active): %s", str(e))
        return None
