import numpy as np

def getElSum(N, s):
    """
    Return list of all elements within ring s
    E.g.    s = 0 --> central element
            s = 1 --> sum3x3
            s = 2 --> sum5x5
    ===========================================================================
    Input       Meaning
    ---------------------------------------------------------------------------
    N           Number of rows/columns of the array, typically 5
    s           Outer ring number, typically between 0 and 2
    ===========================================================================
    Output      Meaning
    ---------------------------------------------------------------------------
    out         list of indices
    ===========================================================================
    """
    out = []
    for r in range(s+1):
        out = np.append(out, getElRingArray(N, r))
    return [int(x) for x in out]


def getElRingArray(N, r):
    """
    Return list of all elements of a square array that are in ring r around
    the center. E.g. for a 5x5 array, there are three rings, ring 0-2:
    2 2 2 2 2
    2 1 1 1 2
    2 1 0 1 2
    2 1 1 1 2
    2 2 2 2 2
    E.g. Ring 1 contains elements [6,7,8,11,13,16,17,18]
    ===========================================================================
    Input       Meaning
    ---------------------------------------------------------------------------
    N           Number of rows/columns of the array, typically 5
    r           Ring number, typically between 0 and 2
    ===========================================================================
    Output      Meaning
    ---------------------------------------------------------------------------
    out         list of indices
    ===========================================================================
    """
    dist = np.zeros((N,N))
    for i in range(N):
        for j in range(N):
            dist[i, j] = np.max([np.abs(i-np.floor(N/2)), np.abs(j-np.floor(N/2))])
    
    dist = np.reshape(dist, (N*N,1))
    
    return np.where(dist == r)[0]