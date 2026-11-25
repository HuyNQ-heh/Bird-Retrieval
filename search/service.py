"""Search operations shared by the command line and the web demo."""

from pathlib import Path

from search.query_image import prepare_query
from search.retrieval import GalleryIndex


def build_index(records, exclude=()):
    ids = [i for i in records if i not in exclude]
    return GalleryIndex.fit(ids, [records[i][2] for i in ids])


def search_query(source, records, index):
    """Search from a path or an open binary image stream."""
    query = prepare_query(source)
    hits = index.rank(query.vectors)
    for hit in hits:
        path, species, _ = records[hit["image_id"]]
        hit.update(image_path=path, filename=Path(path).name, species=species)
    return query, hits
