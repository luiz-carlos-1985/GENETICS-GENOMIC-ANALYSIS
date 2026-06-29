from dataclasses import dataclass
from Bio import SeqIO
import io


@dataclass
class ParsedSequence:
    sequence_id: str
    sequence: str
    length: int
    gc_content: float


@dataclass
class ParsedVariant:
    chromosome: str
    position: int
    ref_allele: str
    alt_allele: str
    gene_symbol: str


def parse_fasta(file_content: bytes) -> list[ParsedSequence]:
    sequences = []
    handle = io.StringIO(file_content.decode("utf-8"))
    for record in SeqIO.parse(handle, "fasta"):
        seq = str(record.seq).upper()
        gc = (seq.count("G") + seq.count("C")) / len(seq) * 100 if len(seq) > 0 else 0
        sequences.append(ParsedSequence(
            sequence_id=record.id,
            sequence=seq,
            length=len(seq),
            gc_content=round(gc, 2)
        ))
    return sequences


def parse_vcf(file_content: bytes) -> list[ParsedVariant]:
    variants = []
    lines = file_content.decode("utf-8").splitlines()
    for line in lines:
        if line.startswith("#"):
            continue
        parts = line.strip().split("\t")
        if len(parts) < 5:
            continue
        variants.append(ParsedVariant(
            chromosome=parts[0],
            position=int(parts[1]),
            ref_allele=parts[3],
            alt_allele=parts[4],
            gene_symbol=_extract_gene_from_info(parts[7] if len(parts) > 7 else "")
        ))
    return variants


def _extract_gene_from_info(info_field: str) -> str:
    for token in info_field.split(";"):
        if token.startswith("GENEINFO="):
            return token.split("=")[1].split(":")[0]
    return "UNKNOWN"
