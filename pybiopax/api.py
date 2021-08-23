__all__ = ['model_from_owl_str', 'model_from_owl_file', 'model_to_owl_str',
           'model_to_owl_file', 'model_from_owl_url', 'model_from_pc_query',
           'model_from_reactome', 'model_from_ecocyc', 'model_from_metacyc',
           'model_from_biocyc', 'model_from_humancyc', 'model_from_netpath',
           ]

import requests
from lxml import etree
from .biopax.model import BioPaxModel
from .xml_util import xml_to_str, xml_to_file
from .pc_client import graph_query


def model_from_owl_str(owl_str):
    """Return a BioPAX Model from an OWL string.

    Parameters
    ----------
    owl_str : str
        A OWL string of BioPAX content.

    Returns
    -------
    pybiopax.biopax.BioPaxModel
        A BioPAX Model deserialized from the OWL string.
    """
    return BioPaxModel.from_xml(etree.fromstring(owl_str.encode('utf-8')))


def model_from_owl_file(fname, encoding=None):
    """Return a BioPAX Model from an OWL string.

    Parameters
    ----------
    fname : str
        A OWL file of BioPAX content.
    encoding : Optional[str]
        The encoding type to be passed to :func:`open`.

    Returns
    -------
    pybiopax.biopax.BioPaxModel
        A BioPAX Model deserialized from the OWL file.
    """
    with open(fname, 'r', encoding=encoding) as fh:
        owl_str = fh.read()
        return model_from_owl_str(owl_str)


def model_from_owl_url(url, **kwargs):
    """Return a BioPAX Model from an URL pointing to an OWL file.

    Parameters
    ----------
    url : str
        A OWL URL with BioPAX content.

    Returns
    -------
    pybiopax.biopax.BioPaxModel
        A BioPAX Model deserialized from the OWL file.
    """
    res = requests.get(url, **kwargs)
    res.raise_for_status()
    return model_from_owl_str(res.text)


def model_from_pc_query(kind, source, target=None, **query_params):
    """Return a BioPAX Model from a Pathway Commons query.

    For more information on these queries, see
    http://www.pathwaycommons.org/pc2/#graph

    Parameters
    ----------
    kind : str
        The kind of graph query to perform. Currently 3 options are
        implemented, 'neighborhood', 'pathsbetween' and 'pathsfromto'.
    source : list[str]
        A single gene name or a list of gene names which are the source set for
        the graph query.
    target : Optional[list[str]]
        A single gene name or a list of gene names which are the target set for
        the graph query. Only needed for 'pathsfromto' queries.
    limit : Optional[int]
        This limits the length of the longest path considered in
        the graph query. Default: 1
    organism : Optional[str]
        The organism used for the query. Default: '9606' corresponding
        to human.
    datasource : Optional[list[str]]
        A list of database sources that the query results should include.
        Example: ['pid', 'panther']. By default, all databases are considered.

    Returns
    -------
    pybiopax.biopax.BioPaxModel
        A BioPAX Model obtained from the results of the Pathway Commons query.
    """
    owl_str = graph_query(kind, source, target=target, **query_params)
    return model_from_owl_str(owl_str)



def model_from_netpath(identifier):
    """Return a BioPAX Model from a `NetPath <http://netpath.org>`_ entry.

    Parameters
    ----------
    identifier :
        The NetPath identifier for a pathway (e.g., ``22`` for the `leptin
        signaling pathway <http://netpath.org/pathways?path_id=NetPath_22>`_

    Returns
    -------
    :
        A BioPAX Model obtained from the NetPath resource.

    """
    url = f"http://netpath.org/data/biopax/NetPath_{identifier}.owl"
    return model_from_owl_url(url)


def model_from_reactome(identifier: str) -> BioPaxModel:
    """Return a BioPAX Model from a Reactome entry (pathway, event, etc.).

    Parameters
    ----------
    identifier :
        The Reactome identifier for a pathway (e.g., https://reactome.org/content/detail/R-HSA-177929)
        or reaction (e.g., https://reactome.org/content/detail/R-HSA-177946)

    Returns
    -------
    :
        A BioPAX Model obtained from the Reactome resource.
    """
    if identifier.startswith("R-"):
        # If you give something like R-XXX-YYYYY, just get the YYYYY part back for download.
        identifier = identifier.split("-")[-1]
    url = f"https://reactome.org/ReactomeRESTfulAPI/RESTfulWS/biopaxExporter/Level3/{identifier}"
    return model_from_owl_url(url)


def model_from_humancyc(identifier: str) -> BioPaxModel:
    """Return a BioPAX Model from a HumanCyc entry.

    Parameters
    ----------
    identifier :
        The HumanCyc identifier for a pathway (e.g., ``PWY66-398`` for `TCA cycle
        <https://humancyc.org/HUMAN/NEW-IMAGE?type=PATHWAY&object=PWY66-398>`_)

    Returns
    -------
    :
        A BioPAX Model obtained from the HumanCyc pathway.
    """
    return _model_from_xcyc("https://humancyc.org/HUMAN/pathway-biopax", identifier)


def model_from_biocyc(identifier: str) -> BioPaxModel:
    """Return a BioPAX Model from a `BioCyc <https://biocyc.org>`_ entry.

    BioCyc contains pathways for model eukaryotes and microbes.

    Parameters
    ----------
    identifier :
        The BioCyc identifier for a pathway (e.g., P105-PWY for `TCA cycle IV (2-oxoglutarate decarboxylase)
        <https://biocyc.org/META/NEW-IMAGE?type=PATHWAY&object=P105-PWY>`_)

    Returns
    -------
    :
        A BioPAX Model obtained from the BioCyc pathway.
    """
    return _model_from_xcyc("https://biocyc.org/META/pathway-biopax", identifier)


def model_from_metacyc(identifier: str) -> BioPaxModel:
    """Return a BioPAX Model from a` MetaCyc <https://metacyc.org/>`_ entry.

    MetaCyc contains pathways for all organisms

    Parameters
    ----------
    identifier :
        The MetaCyc identifier for a pathway (e.g., TCA for
        https://metacyc.org/META/NEW-IMAGE?type=PATHWAY&object=TCA)

    Returns
    -------
    :
        A BioPAX Model obtained from the MetaCyc pathway.
    """
    return _model_from_xcyc("https://ecocyc.org/ECOLI/pathway-biopax", identifier)


def model_from_ecocyc(identifier: str) -> BioPaxModel:
    """Return a BioPAX Model from a `EcoCyc <https://ecocyc.org/>`_ entry.

    EcoCyc contains pathways for Escherichia coli K-12 MG1655.

    Parameters
    ----------
    identifier :
        The EcoCyc identifier for a pathway (e.g., TCA for
        https://ecocyc.org/ECOLI/NEW-IMAGE?type=PATHWAY&object=TCA)

    Returns
    -------
    :
        A BioPAX Model obtained from the EcoCyc pathway.
    """
    return _model_from_xcyc("https://metacyc.org/META/pathway-biopax", identifier)


def _model_from_xcyc(url: str, identifier: str) -> BioPaxModel:
    """Return a BioPAX Model from a XXXCyc entry.

    Parameters
    ----------
    url :
        The base url for the XXXCyc BioPax download endpoint. All of them have the form
        ``https://....../META/pathway-biopax``.
    identifier :
        The site-specific identifier for a pathway

    Returns
    -------
    :
        A BioPAX Model obtained from the pathway.
    """
    params = {
        "type": "3",
        "object": identifier
    }
    # Not sure if the SSL issue is temporary. Remove verify=False later
    return model_from_owl_url(url, params=params, verify=False)


def model_to_owl_str(model):
    """Return an OWL string serialized from a BioPaxModel object.

    Parameters
    ----------
    model : pybiopax.biopax.BioPaxModel
        The BioPaxModel to serialize into an OWL string.

    Returns
    -------
    str
        The OWL string for the model.
    """
    return xml_to_str(model.to_xml())


def model_to_owl_file(model, fname):
    """Write an OWL string serialized from a BioPaxModel object into a file.

    Parameters
    ----------
    model : pybiopax.biopax.BioPaxModel
        The BioPaxModel to serialize into an OWL file.
    fname : str
        The path to the target OWL file.
    """
    xml_to_file(model.to_xml(), fname)
