import numpy as np
from numpy import genfromtxt
from spad_tools.checkfname import checkfname

def csv2array(file, dlmt='\t'):
    file = checkfname(file, 'csv')
    data = genfromtxt(file, delimiter=dlmt)
    return data


def array2csv(data, fname='test.csv', dlmt='\t', dtype=float):
    data = np.asarray(data, dtype)
    fname = checkfname(fname, 'csv')
    if dtype == int:
        np.savetxt(fname, data, delimiter=dlmt, fmt='%i')
    else:
        np.savetxt(fname, data, delimiter=dlmt)
