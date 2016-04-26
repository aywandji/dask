from __future__ import print_function, division, absolute_import

from io import BytesIO
from warnings import warn

import pandas as pd

from ..delayed import delayed
from .io import from_delayed

from ..bytes import read_bytes
from ..bytes.compression import seekable_files, files as cfiles
from ..utils import ensure_bytes


delayed = delayed(pure=True)


def bytes_read_csv(b, header, kwargs, dtypes=None):
    """ Convert a block of bytes to a Pandas DataFrame

    Parameters
    ----------
    b: bytestring
        The content to be parsed with pandas.read_csv
    header: bytestring
        An optional header to prepend to b
    kwargs: dict
        A dictionary of keyword arguments to be passed to pandas.read_csv
    dtypes: dict
        DTypes to assign to columns

    See Also:
        dask.dataframe.csv.read_csv_from_bytes
    """
    bio = BytesIO()
    if header:
        bio.write(header)
    bio.write(b)
    bio.seek(0)
    df = pd.read_csv(bio, **kwargs)
    if dtypes is not None:
        d = dict((c, df[c].astype(dt)) for c, dt in dtypes.items()
                                        if df[c].dtype != dt)
        df = df.assign(**d)
    return df


def read_csv_from_bytes(block_lists, header, head, kwargs, collection=True,
        enforce_dtypes=True):
    """ Convert blocks of bytes to a dask.dataframe or other high-level object

    This accepts a list of lists of values of bytes where each list corresponds
    to one file, and the value of bytes concatenate to comprise the entire
    file, in order.

    Parameters
    ----------
    block_lists: list of lists of delayed values of bytes
        The lists of bytestrings where each list corresponds to one logical file
    header: bytestring
        The header, found at the front of the first file, to be prepended to
        all blocks
    head: pd.DataFrame
        An example Pandas DataFrame to be used for metadata.
        Can be ``None`` if ``collection==False``
    kwargs: dict
        Keyword arguments to pass down to ``pd.read_csv``
    collection: boolean, optional (defaults to True)

    Returns
    -------
    A dask.dataframe or list of delayed values
    """
    if enforce_dtypes:
        dt = head.dtypes.to_dict()
    else:
        dt = None
    dfs1 = [[delayed(bytes_read_csv)(blocks[0], '', kwargs, dt)] +
            [delayed(bytes_read_csv)(b, header, kwargs, dt) for b in blocks[1:]]
            for blocks in block_lists]
    dfs2 = sum(dfs1, [])

    if collection:
        return from_delayed(dfs2, head)
    else:
        return dfs2


def read_csv(filename, blocksize=2**25, chunkbytes=None,
        collection=True, lineterminator='\n', compression=None,
        enforce_dtypes=True, sample=10000, **kwargs):
    if chunkbytes is not None:
        warn("Deprecation warning: chunksize csv keyword renamed to blocksize")
        blocksize=chunkbytes
    if 'index' in kwargs or 'index_col' in kwargs:
        raise ValueError("Keyword 'index' not supported "
                         "dd.read_csv(...).set_index('my-index') instead")

    if blocksize and compression not in seekable_files:
        print("Warning %s compression does not support breaking apart files\n"
              "Please ensure that each individiaul file can fit in memory and\n"
              "use the keyword ``blocksize=None to remove this message``\n"
              "Setting ``blocksize=None``" % compression)
        blocksize = None
    if compression not in seekable_files and compression not in cfiles:
        raise NotImplementedError("Compression format %s not installed" %
                                  compression)

    b_lineterminator = lineterminator.encode()
    sample, values = read_bytes(filename, delimiter=b_lineterminator,
                                          blocksize=blocksize,
                                          sample=sample, compression=compression)
    if not isinstance(values[0], (tuple, list)):
        values = [values]
    header = sample.split(b_lineterminator)[0] + b_lineterminator
    head = pd.read_csv(BytesIO(sample), **kwargs)

    df = read_csv_from_bytes(values, header, head, kwargs,
            collection=collection, enforce_dtypes=enforce_dtypes)

    return df
