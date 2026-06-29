import numpy as np
from dataclasses import dataclass


@dataclass
class SequenceEmbedding:
    sequence_id: str
    tokens: list[int]
    kmers: list[str]
    vocabulary_size: int


def tokenize_sequence(sequence: str, k: int = 6) -> tuple[list[str], dict[str, int]]:
    """
    Splits a DNA sequence into overlapping k-mers and maps them to integer tokens.
    k=6 is the standard used by DNABERT and Nucleotide Transformer.
    """
    kmers = [sequence[i:i + k] for i in range(len(sequence) - k + 1)]
    unique_kmers = sorted(set(kmers))
    vocabulary = {kmer: idx for idx, kmer in enumerate(unique_kmers)}
    return kmers, vocabulary


def embed_sequence(sequence_id: str, sequence: str, k: int = 6) -> SequenceEmbedding:
    kmers, vocabulary = tokenize_sequence(sequence, k)
    tokens = [vocabulary[kmer] for kmer in kmers]
    return SequenceEmbedding(
        sequence_id=sequence_id,
        tokens=tokens,
        kmers=kmers,
        vocabulary_size=len(vocabulary)
    )


def compute_mutation_distance(wild_type: str, mutant: str, k: int = 6) -> float:
    """
    Computes the cosine distance between the token frequency vectors
    of two sequences to quantify how far a mutation is from the reference.
    A value closer to 1.0 indicates a highly divergent (likely pathogenic) mutation.
    """
    _, vocab_wt = tokenize_sequence(wild_type, k)
    _, vocab_mut = tokenize_sequence(mutant, k)

    all_kmers = list(set(vocab_wt) | set(vocab_mut))

    vec_wt = np.array([vocab_wt.get(kmer, 0) for kmer in all_kmers], dtype=float)
    vec_mut = np.array([vocab_mut.get(kmer, 0) for kmer in all_kmers], dtype=float)

    dot = np.dot(vec_wt, vec_mut)
    norm = np.linalg.norm(vec_wt) * np.linalg.norm(vec_mut)

    cosine_similarity = dot / norm if norm > 0 else 0.0
    return float(round(1.0 - cosine_similarity, 6))
