import numpy as np


def calcDistFromCoord(data, coord=None):
    """
    Calculate the distance from a fixed point to every cell of an array
    ===========================================================================
    Input       Meaning
    ---------------------------------------------------------------------------
    data        2d np.array (only the dimensions of the array are needed, the
                             contents of the array can be whatever)
    coord       [idy, idx] indices of the data point from which to calculate
                            the distance, default is center
    ===========================================================================
    Output      Meaning
    ---------------------------------------------------------------------------
    dist        2d np.array with for each cell the distance from that cell to
                            the given coordinates
    ===========================================================================
    """

    dataShape = np.shape(data)
    
    Ny = dataShape[0]
    Nx = dataShape[1]

    if coord == None:
        # use center coordinate
        coord = [int(np.floor(Ny/2)), int(np.floor(Nx/2))]
    
    x = np.linspace(0, Nx-1, Nx)
    y = np.linspace(0, Ny-1, Ny)
    
    xv, yv = np.meshgrid(x, y)
    
    yv -= coord[0]
    xv -= coord[1]
    
    dist = np.sqrt(xv**2 + yv**2)

    return dist
