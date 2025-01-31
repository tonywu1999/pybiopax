# -*- coding: utf-8 -*-

"""CREEDS Analysis."""

import pickle
import logging
from collections import defaultdict
from typing import Optional, Type

import bioregistry
import bioversions
import numpy as np
import pandas as pd
import protmapper.uniprot_client
import pyobo
import pystow
import seaborn
from indra.sources import creeds
from indra.statements import Agent, RegulateAmount, Statement, stmts_to_json_file
from scipy.stats import fisher_exact
from statsmodels.stats.multitest import multipletests
from tqdm import tqdm

import pybiopax
from pybiopax.biopax import Protein

logger = logging.getLogger(__name__)

REACTOME_MODULE = pystow.module("bio", "reactome", bioversions.get_version("reactome"))
CREEDS_MODULE = pystow.module("bio", "creeds")


def get_reactome_human_ids() -> set[str]:
    identifiers = pyobo.get_ids("reactome")
    species = pyobo.get_id_species_mapping("reactome")
    rv = {reactome_id for reactome_id in identifiers if species[reactome_id] == "9606"}
    return rv


def get_protein_hgnc(protein: Protein) -> Optional[str]:
    # only useful for reactome
    if protein.entity_reference is None:
        return None
    rv = {bioregistry.normalize_prefix(xref.db): xref.id for xref in protein.entity_reference.xref}
    hgnc_id = rv.get("hgnc")
    if hgnc_id is not None:
        return hgnc_id
    uniprot_id = rv.get("uniprot")
    if uniprot_id is not None:
        hgnc_id = protmapper.uniprot_client.get_hgnc_id(uniprot_id)
        if hgnc_id:
            return hgnc_id
    uniprot_isoform_id = rv.get("uniprot.isoform")
    if uniprot_isoform_id is not None:
        hgnc_id = protmapper.uniprot_client.get_hgnc_id(uniprot_isoform_id)
        if hgnc_id:
            return hgnc_id
    return None


def ensure_reactome(reactome_id: str, force: bool = False) -> BioPaxModel:
    path = REACTOME_MODULE.join(name=f"{reactome_id}.xml")
    if path.is_file() and not force:
        with path.open("rb") as file:
            return pickle.load(file)
    logger.info(f'Getting {reactome_id}')
    model = pybiopax.model_from_reactome(reactome_id)
    with path.open("wb") as file:
        pickle.dump(model, file)
    return model


def get_reactome_genes(reactome_id: str) -> set[str]:
    model = ensure_reactome(reactome_id)
    rv = set()
    for protein in model.get_objects_by_type(Protein):
        if (hgnc_id := get_protein_hgnc(protein)) is not None:
            rv.add(hgnc_id)
    return rv


def get_creeds_statements(entity_type: str) -> list[Statement]:
    path = CREEDS_MODULE.join(name=f"{entity_type}_stmts.pkl")
    if path.is_file():
        with path.open("rb") as file:
            return pickle.load(file)
    url = creeds.api.urls[entity_type]
    raw_path = CREEDS_MODULE.ensure(url=url)
    processor = creeds.process_from_file(raw_path, entity_type)
    stmts_to_json_file(processor.statements, path)
    with path.open("wb") as file:
        pickle.dump(processor.statements, file, protocol=pickle.HIGHEST_PROTOCOL)
    return processor.statements


def get_hgnc_id(agent: Agent) -> Optional[str]:
    hgnc_id = agent.db_refs.get("HGNC")
    if hgnc_id is not None:
        return hgnc_id
    up_id = agent.db_refs.get("UP")
    if up_id is None:
        return None
    return protmapper.uniprot_client.get_hgnc_id(up_id)


def get_regulates(
    stmts: list[Statement],
    stmt_cls: Type[RegulateAmount] = RegulateAmount,
) -> dict[str, set[str]]:
    rv = defaultdict(set)
    for stmt in stmts:
        if not isinstance(stmt, stmt_cls):
            continue
        subj_hgnc_id = get_hgnc_id(stmt.subj)
        obj_hgnc_id = get_hgnc_id(stmt.obj)
        if subj_hgnc_id is None or obj_hgnc_id is None:
            continue
        rv[subj_hgnc_id].add(obj_hgnc_id)
    return dict(rv)


def get_disease_groups(
    stmts: list[Statement],
    stmt_cls: Type[RegulateAmount] = RegulateAmount,
) -> dict[str, set[str]]:
    rv = defaultdict(set)
    for stmt in stmts:
        if not isinstance(stmt, stmt_cls):
            continue
        subj_doid = stmt.subj.db_refs.get("DOID")
        obj_hgnc_id = get_hgnc_id(stmt.obj)
        if subj_doid is None or obj_hgnc_id is None:
            continue
        rv[subj_doid].add(obj_hgnc_id)
    return dict(rv)


def get_chemical_groups(
    stmts: list[Statement],
    stmt_cls: Type[RegulateAmount] = RegulateAmount,
) -> dict[str, set[str]]:
    rv = defaultdict(set)
    for stmt in stmts:
        if not isinstance(stmt, stmt_cls):
            continue
        subj_pubchem = stmt.subj.db_refs.get("PUBCHEM")
        obj_hgnc_id = get_hgnc_id(stmt.obj)
        if subj_pubchem is None or obj_hgnc_id is None:
            continue
        rv[subj_pubchem].add(obj_hgnc_id)
    return dict(rv)


def _prepare_hypergeometric_test(
    query_gene_set: set[str],
    pathway_gene_set: set[str],
    gene_universe: int,
) -> np.ndarray:
    """Prepare the matrix for hypergeometric test calculations.

    :param query_gene_set: gene set to test against pathway
    :param pathway_gene_set: pathway gene set
    :param gene_universe: number of HGNC symbols
    :return: 2x2 matrix
    """
    return np.array(
        [
            [
                len(query_gene_set.intersection(pathway_gene_set)),
                len(query_gene_set.difference(pathway_gene_set)),
            ],
            [
                len(pathway_gene_set.difference(query_gene_set)),
                gene_universe - len(pathway_gene_set.union(query_gene_set)),
            ],
        ]
    )


def _main():
    reactome_ids = get_reactome_human_ids()
    reactome_it = [
        (reactome_id, get_reactome_genes(reactome_id))
        for reactome_id in tqdm(reactome_ids, desc="Downloading Reactome pathways")
    ]

    universe_size = len(pyobo.get_ids("hgnc"))
    groups = [
        ("hgnc", "gene", get_regulates),
        ("pubchem.compound", "chemical", get_chemical_groups),
        ("doid", "disease", get_disease_groups),
    ]

    for prefix, entity_type, f in groups:
        tqdm.write(f"generating CREEDS types {entity_type}")
        stmts = get_creeds_statements(entity_type)
        perts = f(stmts)
        dfs = []
        for pert_id, pert_genes in tqdm(perts.items()):
            rows = []
            for reactome_id, reactome_genes in tqdm(reactome_it, leave=False):
                table = _prepare_hypergeometric_test(pert_genes, reactome_genes, universe_size)
                _, p_value = fisher_exact(table, alternative="greater")
                rows.append((f"{prefix}:{pert_id}", f"reactome:{reactome_id}", p_value))
            df = pd.DataFrame(rows, columns=["perturbation", "pathway", "p"])
            correction_test = multipletests(df["p"], method="fdr_bh")
            df["q"] = correction_test[1]
            df["mlq"] = -np.log10(df["q"])  # minus log q
            df.sort_values("q", inplace=True)
            dfs.append(df)

        path = CREEDS_MODULE.join(name=f"{entity_type}.tsv")
        df = pd.concat(dfs)
        df.to_csv(path, sep="\t", index=False)
        print("output to", path)

        # TODO: cut off genes that don't have anything good going on
        square_df = df.pivot(columns="pathway", index="perturbation")["mlq"]
        img_path = CREEDS_MODULE.join(name=f"{entity_type}.png")
        g = seaborn.clustermap(square_df)
        g.savefig(img_path)


if __name__ == "__main__":
    _main()
