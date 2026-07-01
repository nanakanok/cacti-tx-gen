from cacti_tx_gen.extract.base import BaseExtractor
from cacti_tx_gen.extract.jpix import JPIXExtractor
from cacti_tx_gen.extract.bbix import BBIXExtractor
from cacti_tx_gen.extract.jpnap import JPNAPExtractor

EXTRACTORS = {
    "jpix": JPIXExtractor,
    "bbix": BBIXExtractor,
    "jpnap": JPNAPExtractor,
}

__all__ = ["BaseExtractor", "JPIXExtractor", "BBIXExtractor", "JPNAPExtractor", "EXTRACTORS"]
