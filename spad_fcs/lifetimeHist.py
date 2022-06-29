import numpy as np


def lifetimeHist(data, MM=260, laserF=80e6):
    """
    Make lifetime histograms of all channels
    ===========================================================================
    Input       Meaning
    ----------  ---------------------------------------------------------------
    data        data object with macro and microtimes
    MM          number of microtime bins
    laserF      laser frequency (Hz)
    ===========================================================================
    Output      Meaning
    ----------  ---------------------------------------------------------------
    data        same data object as input, but with histograms aligned in time
    ===========================================================================
    """
    
    # get list of detector fields
    listOfFields = list(data.__dict__.keys())
    listOfFields = [i for i in listOfFields if i.startswith('det')]
    Ndet = len(listOfFields)
    
    for det in range(Ndet):
        
        # macrotimes
        macroTime = getattr(data, "det" + str(det))[:,0] # ps
        
        # calculate proper microtimes
        microTime = getattr(data, "det" + str(det))[:,1]
        microTime = np.mod(microTime, 1 / data.microtime / laserF)
        microTime = -microTime + np.max(microTime)
        
        # make histogram of microtimes
        [Ihist, lifetimeBins] = np.histogram(microTime, MM)
        lifetimeBins = lifetimeBins[0:-1]
        
        # store histogram
        setattr(data, "hist" + str(det), np.transpose(np.stack((lifetimeBins, Ihist))))
        setattr(data, "det" + str(det), np.transpose([macroTime, microTime]))
        
    return data
