import multipletau
from spad_fcs.extractSpadData import extractSpadData
import matplotlib.pyplot as plt
import numpy as np
from spad_fcs.distance2detElements import distance2detElements
from spad_fcs.distance2detElements import SPADcoordFromDetNumb as coord
from spad_fcs.distance2detElements import SPADshiftvectorCrossCorr
from spad_tools.colorFromMap import colorFromMap
import fnmatch
from spad_tools.plotColors import plotColors
from spad_fcs.getFCSinfo import getFCSinfo, getFileInfo
from spad_fcs.meas_to_count import file_to_FCScount
from os import  getcwd
from pathlib import Path
from spad_tools.listFiles import listFiles
import ntpath
from spad_fcs.corr2csv import corr2csv
import scipy as spy
from spad_fcs.scipy import signal
from spad_fcs.binData import binDataChunks


class correlations:
    pass

def FCSsparseMatrices(fname, accuracy=16, split=10, timeTrace=False, returnObj=False, root=0):
    
    info = getFileInfo(fname[:-4] + "_info.txt")
    dwellTime = 1e-6 *info.timeResolution
    duration = info.duration
    
    N = np.int(np.floor(duration / split)) # number of chunks

    G = correlations()
    G.dwellTime = dwellTime
    chunkSize = int(np.floor( split/ dwellTime))
    Gcorrs = []
    
    for chunk in range(N):
        # --------------------- CALCULATE CORRELATIONS SINGLE CHUNK ---------------------
        print("+-----------------------")
        print("| Loading chunk " + str(chunk))
        print("+-----------------------")
        
        if root != 0:
            root.progress = chunk / N
        
        data = file_to_FCScount(fname, np.uint8, chunkSize, chunk*chunkSize)
        
        if timeTrace == True:
            binSize = int(chunkSize / 1000 * N) # time trace binned to 1000 data points
            bdata = binDataChunks(data, binSize)
            bdataL = len(bdata)
            if chunk == 0:
                timetraceAll = np.zeros((1000, 25), dtype=int)
            timetraceAll[chunk*bdataL:(chunk+1)*bdataL, :] = bdata 
        
        Gsplit,Gtimes = FCSsparse(data, dwellTime, accuracy)
        Gcorrs.append(Gsplit)
    G.lagtimes = Gtimes
    G.Gsplit   = Gcorrs
    
    if timeTrace:
        data = timetraceAll
    
    if returnObj:
        # convert 4D numpy array (chunk, y, corr1, corr2) to corr object
        Garr = np.asarray(G.Gsplit)
        Gshape = np.shape(Garr)
        Nchunk = Gshape[0]
        Ntau = Gshape[1]
        Nx = Gshape[2]
        Ny = Gshape[3]
        Gout = correlations()
        for c in range(Nchunk):
            for x in range(Nx):
                for y in range(Ny):
                    Gtemp = np.zeros((Ntau, 2))
                    Gtemp[:,0] = np.squeeze(G.lagtimes)
                    Gtemp[:,1] = Garr[c, :, x, y]
                    setattr(Gout, "det" + str(x) + "x" + str(y) + "_chunk" + str(c), Gtemp)
        Gout = FCSavChunks(Gout, list(range(Nchunk)))
        Gout.dwellTime = dwellTime
        G = Gout
    
    return G, data

def FCSsparse(data, dwellTime, m=50, normalize = True):
    # object from correlations class in which all correlation data is stored
    G = correlations()
    
    # dwell time
    G.dwellTime = dwellTime
    
    # Check parameters
    if m // 2 != m / 2:
        mold = m
        m = np.int_((m // 2 + 1) * 2)
    else:
        m = np.int_(m)

    N = N0 = data.shape[0]
    Nchan = data.shape[1]
    k = np.int_(np.floor(np.log2(N / m)))
    lenG = m + k * m // 2 + 1
    Gtimes = np.zeros((lenG, 1), dtype = "float32")
    G = np.zeros((lenG, Nchan, Nchan), dtype="float32")
    normstat = np.zeros(lenG, dtype="float32")
    normnump = np.zeros(lenG, dtype="float32")
    
    spdata = spy.sparse.csr_matrix(data.transpose())
    spdata = spdata.astype("float32")
    
    traceavg = spdata.mean(axis = 1)
    
    
    # Calculate autocorrelation function for first m+1 bins
    for n in range(0, m + 1):
        Gtimes[n] = dwellTime * n
        res = spdata[:,:N-n].dot(spdata[:,n:].transpose())
        G[n] = res.toarray()
        normstat[n] = N - n
        normnump[n] = N
    
    if N % 2 == 1:
        N -= 1
    # compress every second element
    spdata = (spdata[:,:N:2] + spdata[:,1:N:2]) / 2
    spdata = spdata.toarray() # spdata is now full
    
    spdata = spdata-traceavg
    
    N //= 2
    
    # Start iteration for each m/2 values
    for step in range(1, k + 1):
        # Get the next m/2 values via correlation of the trace
        for n in range(1, m // 2 + 1):
            npmd2 = n + m // 2
            idx = m + n + (step - 1) * m // 2
            if spdata[:,:N - npmd2].shape[1] == 0:
                # This is a shortcut that stops the iteration once the
                # length of the trace is too small to compute a corre-
                # lation. The actual length of the correlation function
                # does not only depend on k - We also must be able to
                # perform the sum with respect to k for all elements.
                # For small N, the sum over zero elements would be
                # computed here.
                #
                # One could make this for-loop go up to maxval, where
                #   maxval1 = int(m/2)
                #   maxval2 = int(N-m/2-1)
                #   maxval = min(maxval1, maxval2)
                # However, we then would also need to find out which
                # element in G is the last element...
                G = G[:idx - 1]
                normstat = normstat[:idx - 1]
                normnump = normnump[:idx - 1]
                # Note that this break only breaks out of the current
                # for loop. However, we are already in the last loop
                # of the step-for-loop. That is because we calculated
                # k in advance.
                break
            else:
                Gtimes[idx] = dwellTime * npmd2 * 2**step
                # This is the computationally intensive step
                G[idx] = spdata[:,:N-npmd2].dot(spdata[:,npmd2:].transpose())
                normstat[idx] = N - npmd2
                normnump[idx] = N
        # Check if len(trace) is even:
        if N % 2 == 1:
            N -= 1
        # compress every second element
        spdata = (spdata[:,:N:2] + spdata[:,1:N:2]) / 2  
        N //= 2
   
    if normalize:
        # G /= normstat.reshape(lenG,1,1)
        # G /= (traceavg*traceavg.transpose())
        # G -= 1
        G /= normstat.reshape(lenG,1,1)
        G /= (traceavg*traceavg.transpose())
        G[1:m+1] -= 1

    return G, Gtimes
    


def correlate_parallel(a, m=16, deltat=1, normalize=False, copy=True, dtype=None,
                  compress="average", ret_sum=False):
   
    if not isinstance(normalize, bool):
        raise ValueError("`normalize` must be boolean!")
    if not isinstance(copy, bool):
        raise ValueError("`copy` must be boolean!")
    if not isinstance(ret_sum, bool):
        raise ValueError("`ret_sum` must be boolean!")
    if normalize and ret_sum:
        raise ValueError("'normalize' and 'ret_sum' must not both be True!")
    compress_values = ["average", "first", "second"]
    if compress not in compress_values:
        raise ValueError("Invalid value for `compress`! Possible values "
                         "are '{}'.".format(','.join(compress_values)))

    if dtype is None:
        dtype = np.dtype(a[0].__class__)
    else:
        dtype = np.dtype(dtype)

    ZERO_CUTOFF = 1e-15

    # If copy is false and dtype is the same as the input array,
    # then this line does not have an effect:
    trace = np.array(a, dtype=dtype, copy=copy)
    trace = trace.transpose()

    # Check parameters
    if m // 2 != m / 2:
        mold = m
        m = np.int_((m // 2 + 1) * 2)
    else:
        m = np.int_(m)

    N = N0 = trace.shape[0]

    # Find out the length of the correlation function.
    # The integer k defines how many times we can average over
    # two neighboring array elements in order to obtain an array of
    # length just larger than m.
    k = np.int_(np.floor(np.log2(N / m)))

    # In the base2 multiple-tau scheme, the length of the correlation
    # array is (only taking into account values that are computed from
    # traces that are just larger than m):
    lenG = m + k * (m // 2) + 1

    G = np.zeros((lenG, 2), dtype=dtype)

    normstat = np.zeros(lenG, dtype=dtype)
    normnump = np.zeros(lenG, dtype=dtype)

    traceavg = np.average(trace, axis = 1)

    # We use the fluctuation of the signal around the mean
    if normalize:
        trace -= traceavg.reshape(len(traceavg),1)

    # Otherwise the following for-loop will fail:
    if N < 2 * m:
        raise ValueError("`len(a)` must be >= `2m`!")

    # Calculate autocorrelation function for first m+1 bins
    # Discrete convolution of m elements
    for n in range(0, m + 1):
        G[n, 0] = deltat * n
        # This is the computationally intensive step
        G[n, 1] = np.sum(trace[:N - n] * trace[n:])
        normstat[n] = N - n
        normnump[n] = N
    # Now that we calculated the first m elements of G, let us
    # go on with the next m/2 elements.
    # Check if len(trace) is even:
    if N % 2 == 1:
        N -= 1
    # compress every second element
    if compress == compress_values[0]:
        trace = (trace[:N:2] + trace[1:N:2]) / 2
    elif compress == compress_values[1]:
        trace = trace[:N:2]
    elif compress == compress_values[2]:
        trace = trace[1:N:2]
    N //= 2
    # Start iteration for each m/2 values
    for step in range(1, k + 1):
        # Get the next m/2 values via correlation of the trace
        for n in range(1, m // 2 + 1):
            npmd2 = n + m // 2
            idx = m + n + (step - 1) * m // 2
            if len(trace[:N - npmd2]) == 0:
                # This is a shortcut that stops the iteration once the
                # length of the trace is too small to compute a corre-
                # lation. The actual length of the correlation function
                # does not only depend on k - We also must be able to
                # perform the sum with respect to k for all elements.
                # For small N, the sum over zero elements would be
                # computed here.
                #
                # One could make this for-loop go up to maxval, where
                #   maxval1 = int(m/2)
                #   maxval2 = int(N-m/2-1)
                #   maxval = min(maxval1, maxval2)
                # However, we then would also need to find out which
                # element in G is the last element...
                G = G[:idx - 1]
                normstat = normstat[:idx - 1]
                normnump = normnump[:idx - 1]
                # Note that this break only breaks out of the current
                # for loop. However, we are already in the last loop
                # of the step-for-loop. That is because we calculated
                # k in advance.
                break
            else:
                G[idx, 0] = deltat * npmd2 * 2**step
                # This is the computationally intensive step
                G[idx, 1] = np.sum(trace[:N - npmd2] *
                                   trace[npmd2:])
                normstat[idx] = N - npmd2
                normnump[idx] = N
        # Check if len(trace) is even:
        if N % 2 == 1:
            N -= 1
        # compress every second element
        if compress == compress_values[0]:
            trace = (trace[:N:2] + trace[1:N:2]) / 2
        elif compress == compress_values[1]:
            trace = trace[:N:2]
        elif compress == compress_values[2]:
            trace = trace[1:N:2]

        N //= 2

    if normalize:
        G[:, 1] /= traceavg**2 * normstat
    elif not ret_sum:
        G[:, 1] *= N0 / normnump

    if ret_sum:
        return G, normstat
    else:
        return G
    
def FCS2Corr(data, dwellTime, listOfG=['central', 'sum3', 'sum5', 'chessboard', 'ullr'], accuracy=50):
    """
    Convert SPAD-FCS data to correlation curves
    ==========  ===============================================================
    Input       Meaning
    ----------  ---------------------------------------------------------------
    data        Data variable, i.e. output from binFile2Data
    dwellTime   Bin time [in ??s]
    listofG     List of correlations to be calculated
    accuracy    Accuracy of the autocorrelation function, typically 50
    ==========  ===============================================================
    Output      Meaning
    ----------  ---------------------------------------------------------------
    G           Object with all autocorrelations
                E.g. G.central contains the array with the central detector
                element autocorrelation
    ==========  ===============================================================
    """

    # object from correlations class in which all correlation data is stored
    G = correlations()
    
    # dwell time
    G.dwellTime = dwellTime

    if len(np.shape(data)) == 1:
        # vector is given instead of matrix, single detector only
        print('Calculating autocorrelation ')
        setattr(G, 'det0', multipletau.correlate(data, data, m=accuracy, deltat=dwellTime*1e-6, normalize=True))

    for i in listOfG:
        if isinstance(i, int):
            # autocorrelation of a detector element i
            print('Calculating autocorrelation of detector element ' + str(i))
            dataSingle = extractSpadData(data, i)
            setattr(G, 'det' + str(i), multipletau.correlate(dataSingle, dataSingle, m=accuracy, deltat=dwellTime*1e-6, normalize=True))

        elif i == "central":
            # autocorrelation central detector element
            print('Calculating autocorrelation central detector element')
            dataCentral = extractSpadData(data, "central")
            G.central = multipletau.correlate(dataCentral, dataCentral, m=accuracy, deltat=dwellTime*1e-6, normalize=True)

        elif i[0] == 'x':
            # cross correlation two detector elements: e.g. 'x0112' for det1 x det12
            det0 = int(i[1:3])
            det1 = int(i[3:5])
            dataSingle0 = extractSpadData(data, det0)
            dataSingle1 = extractSpadData(data, det1)
            print('Calculating cross-correlation detector elements ' + str(det0) + 'x' + str(det1))
            Gtemp = multipletau.correlate(dataSingle0, dataSingle1, m=accuracy, deltat=dwellTime*1e-6, normalize=True)
            setattr(G, i, Gtemp)

        elif i == "sum3":
            # autocorrelation sum3x3
            print('Calculating autocorrelation sum3x3')
            dataSum3 = extractSpadData(data, "sum3")
            G.sum3 = multipletau.correlate(dataSum3, dataSum3, m=accuracy, deltat=dwellTime*1e-6, normalize=True)

        elif i == "sum5":
            # autocorrelation sum3x3
            print('Calculating autocorrelation sum5x5')
            dataSum5 = extractSpadData(data, "sum5")
            G.sum5 = multipletau.correlate(dataSum5, dataSum5, m=accuracy, deltat=dwellTime*1e-6, normalize=True)
        
        elif i == "allbuthot":
            # autocorrelation sum5x5 except for the hot pixels
            print('Calculating autocorrelation allbuthot')
            dataAllbuthot = extractSpadData(data, "allbuthot")
            G.allbuthot = multipletau.correlate(dataAllbuthot, dataAllbuthot, m=accuracy, deltat=dwellTime*1e-6, normalize=True)

        elif i == "chessboard":
            # crosscorrelation chessboard
            print('Calculating crosscorrelation chessboard')
            dataChess0 = extractSpadData(data, "chess0")
            dataChess1 = extractSpadData(data, "chess1")
            G.chessboard = multipletau.correlate(dataChess0, dataChess1, m=accuracy, deltat=dwellTime*1e-6, normalize=True)
            
        elif i == "chess3":
            # crosscorrelation small 3x3 chessboard
            print('Calculating crosscorrelation small chessboard')
            dataChess0 = extractSpadData(data, "chess3a")
            dataChess1 = extractSpadData(data, "chess3b")
            G.chess3 = multipletau.correlate(dataChess0, dataChess1, m=accuracy, deltat=dwellTime*1e-6, normalize=True)

        elif i == "ullr":
            # crosscorrelation upper left and lower right
            print('Calculating crosscorrelation upper left and lower right')
            dataUL = extractSpadData(data, "upperleft")
            dataLR = extractSpadData(data, "lowerright")
            G.ullr = multipletau.correlate(dataUL, dataLR, m=accuracy, deltat=dwellTime*1e-6, normalize=True)
        
        elif i == "twofocus":
            # crosscorrelations sum5left and sum5right, sum5top, and sum5bottom
            dataL = extractSpadData(data, "sum5left")
            dataR = extractSpadData(data, "sum5right")
            dataT = extractSpadData(data, "sum5top")
            dataB = extractSpadData(data, "sum5bottom")
            
            print('Calculating crosscorrelation two-focus left and right')
            G.twofocusLR = multipletau.correlate(dataL, dataR, m=accuracy, deltat=dwellTime*1e-6, normalize=True)
            G.twofocusRL = multipletau.correlate(dataR, dataL, m=accuracy, deltat=dwellTime*1e-6, normalize=True)
            
            print('Calculating crosscorrelation two-focus left and top')
            G.twofocusTL = multipletau.correlate(dataT, dataL, m=accuracy, deltat=dwellTime*1e-6, normalize=True)
            G.twofocusLT = multipletau.correlate(dataL, dataT, m=accuracy, deltat=dwellTime*1e-6, normalize=True)
            
            print('Calculating crosscorrelation two-focus left and bottom')
            G.twofocusLB = multipletau.correlate(dataL, dataB, m=accuracy, deltat=dwellTime*1e-6, normalize=True)
            G.twofocusBL = multipletau.correlate(dataB, dataL, m=accuracy, deltat=dwellTime*1e-6, normalize=True)
            
            print('Calculating crosscorrelation two-focus right and top')
            G.twofocusRT = multipletau.correlate(dataR, dataT, m=accuracy, deltat=dwellTime*1e-6, normalize=True)
            G.twofocusTR = multipletau.correlate(dataT, dataR, m=accuracy, deltat=dwellTime*1e-6, normalize=True)
            
            print('Calculating crosscorrelation two-focus right and bottom')
            G.twofocusRB = multipletau.correlate(dataR, dataB, m=accuracy, deltat=dwellTime*1e-6, normalize=True)
            G.twofocusBR = multipletau.correlate(dataB, dataR, m=accuracy, deltat=dwellTime*1e-6, normalize=True)
            
            print('Calculating crosscorrelation two-focus top and bottom')
            G.twofocusTB = multipletau.correlate(dataT, dataB, m=accuracy, deltat=dwellTime*1e-6, normalize=True)
            G.twofocusBT = multipletau.correlate(dataB, dataT, m=accuracy, deltat=dwellTime*1e-6, normalize=True)
            
            
        elif i == "crossCenter":
            # crosscorrelation center element with L, R, T, B
            dataCenter = extractSpadData(data, 12)
            for j in range(25):
                print('Calculating crosscorrelation central element with ' + str(j))
                data2 = extractSpadData(data, j)
                Gtemp = multipletau.correlate(dataCenter, data2, m=accuracy, deltat=dwellTime*1e-6, normalize=True)
                setattr(G, 'det12x' + str(j), Gtemp)
        
        elif i == "2MPD":
            # crosscorrelation two elements
            # check first non empty channel
            j = -1
            ch1Found = False
            ch2Found = False
            while not ch1Found:
                j += 1
                data1 = extractSpadData(data, j)
                if np.sum(data1) > 10:
                    ch1Found = True
                    ch1 = j
            while not ch2Found:
                j += 1
                data2 = extractSpadData(data, j)
                if np.sum(data2) > 10:
                    ch2Found = True
                    ch2 = j
            if ch1Found and ch2Found:
                print('Cross correlation elements ' + str(ch1) + ' and ' + str(ch2))
                Gtemp = multipletau.correlate(data1, data2, m=accuracy, deltat=dwellTime*1e-6, normalize=True)
                G.cross12 = Gtemp
                print('Cross correlation elements ' + str(ch2) + ' and ' + str(ch1))
                Gtemp = multipletau.correlate(data2, data1, m=accuracy, deltat=dwellTime*1e-6, normalize=True)
                G.cross21 = Gtemp
                print('Autocorrelation element ' + str(ch1))
                Gtemp = multipletau.correlate(data1, data1, m=accuracy, deltat=dwellTime*1e-6, normalize=True)
                G.auto1 = Gtemp
                print('Autocorrelation element ' + str(ch2))
                Gtemp = multipletau.correlate(data2, data2, m=accuracy, deltat=dwellTime*1e-6, normalize=True)
                G.auto2 = Gtemp
                
        elif i == "crossAll":
            # crosscorrelation every element with every other element
            for j in range(25):
                data1 = extractSpadData(data, j)
                for k in range(25):
                    data2 = extractSpadData(data, k)
                    print('Calculating crosscorrelation det' + str(j) + ' and det' + str(k))
                    Gtemp = multipletau.correlate(data1, data2, m=accuracy, deltat=dwellTime*1e-6, normalize=True)
                    setattr(G, 'det' + str(j) + 'x' + str(k), Gtemp)
        
        elif i == "autoSpatial":
            # number of time points
            Nt = np.size(data, 0)
            # detector size (5 for SPAD)
            N = int(np.round(np.sqrt(np.size(data, 1)-1)))
            # G size
            M = 2 * N - 1
            deltats = range(0, 1, 1) # in units of dwell times
            G.autoSpatial = np.zeros((M, M, len(deltats)))
            # normalization
            print("Calculating average image")
            avIm = np.mean(data, 0)
            # avInt = np.mean(avIm[0:N*N]) - can't be used since every pixel
            # has a different PSF amplitude!!
            # for j in range(np.size(data, 0)):
                # data[j, :] = data[j, :] - avIm
            avIm = np.resize(avIm[0:N*N], (N, N))
            # calculate autocorrelation
            k = 0
            for deltat in deltats:
                print("Calculating spatial autocorr delta t = " + str(deltat * dwellTime) + " ??s")
                for j in range(Nt-deltat):
                    im1 = np.resize(data[j, 0:N*N], (N, N))
                    im1 = np.ndarray.astype(im1, 'int64')
                    im2 = np.resize(data[j + deltat, 0:N*N], (N, N))
                    im2 = np.ndarray.astype(im2, 'int64')
                    # G.autoSpatial[:,:,k] = G.autoSpatial[:,:,k] + ssig.correlate2d(im1, im2)
                    # calculate correlation between im1 and im2
                    for shifty in np.arange(-4, 5):
                        for shiftx in np.arange(-4, 5):
                            # go through all detector elements
                            n = 0  # number of overlapping detector elements
                            Gtemp = 0
                            for detx in np.arange(np.max((0, shiftx)), np.min((5, 5+shiftx))):
                                for dety in np.arange(np.max((0, shifty)), np.min((5, 5+shifty))):
                                    GtempUnNorm = im1[dety, detx] * im2[dety-shifty, detx-shiftx]
                                    GtempNorm = GtempUnNorm - avIm[dety, detx] * avIm[dety-shifty, detx-shiftx]
                                    GtempNorm /= avIm[dety, detx] * avIm[dety-shifty, detx-shiftx]
                                    Gtemp += GtempNorm
                                    n += 1
                            Gtemp /= n
                            G.autoSpatial[shifty+4,shiftx+4,k] += Gtemp
                G.autoSpatial[:,:,k] /= (Nt-deltat)
                k = k + 1

        elif i == "av":
            # average of all 25 individual autocorrelation curves
            for j in range(25):
                # autocorrelation of a detector element j
                print('Calculating autocorrelation of detector element ' + str(j))
                dataSingle = extractSpadData(data, j)
                Gtemp = multipletau.correlate(dataSingle, dataSingle, m=accuracy, deltat=dwellTime*1e-6, normalize=True)
                setattr(G, 'det' + str(j), Gtemp)
            Gav = Gtemp[:, 1]
            for j in range(24):
                Gav = np.add(Gav, getattr(G, 'det' + str(j))[:, 1])
            Gav = Gav / 25
            G.av = np.zeros([np.size(Gav, 0), 2])
            G.av[:, 0] = Gtemp[:, 0]
            G.av[:, 1] = Gav

    return G


def FCS2CorrSplit(data, dwellTime, listOfG=['central', 'sum3', 'sum5', 'chessboard', 'ullr'], accuracy=50, split=10):
    """
    Chunk SPAD-FCS trace into different parts and calculate correlation curves
    ==========  ===============================================================
    Input       Meaning
    ----------  ---------------------------------------------------------------
    data        Data variable, i.e. output from binFile2Data
    dwellTime   Bin time [in ??s]
    listofG     List of correlations to be calculated
    accuracy    Accuracy of the autocorrelation function, typically 50
    split       Number of traces to split the data into
                E.g. split=10 will divide a 60 second stream in 10 six second
                traces and calculate G for each individual trace
    ==========  ===============================================================
    Output      Meaning
    ----------  ---------------------------------------------------------------
    G           Object with all autocorrelations
                E.g. G.central contains the array with the central detector
                element autocorrelation
    ==========  ===============================================================
    """
    if split == 1:
        G = FCS2Corr(data, dwellTime, listOfG, accuracy)
    else:
        G = correlations()
        G.dwellTime = dwellTime
        N = int(np.size(data, 0))
        chunkSize = int(np.floor(N / split))
        for j in listOfG:
            # --------------------- CALCULATE CORRELATION ---------------------
            print('Calculating correlation ' + str(j))
            i = 0
            for chunk in range(split):
                print('     Chunk ' + str(chunk+1) + ' --> ', end = '')
                # ------------------ CHUNK ------------------
                if data.ndim == 2:
                    dataSplit = data[i:i+chunkSize, :]
                else:
                    dataSplit = data[i:i+chunkSize]
                newList = [j]
                Gsplit = FCS2Corr(dataSplit, dwellTime, newList, accuracy)
                GsplitList = list(Gsplit.__dict__.keys())
                for k in GsplitList:
                    if k.find('dwellTime') == -1:
                        setattr(G, k + '_chunk' + str(chunk), getattr(Gsplit, k))
                i += chunkSize
            # ---------- CALCULATE AVERAGE CORRELATION OF ALL CHUNKS ----------
            if j == '2MPD':
                avListBase = ['cross12', 'cross21', 'auto1', 'auto2']
                for avBase in avListBase:
                    avList = list(G.__dict__.keys())
                    avList = [i for i in avList if i.startswith(avBase + '_chunk')]
                    print('Calculating average correlation ' + avBase)
                    Gav = sum(getattr(G, i) for i in avList) / len(avList)
                    setattr(G, avBase + '_average', Gav)
                print('Calculating average cross correlation')
                G.cross_average = (G.cross12_average + G.cross21_average) / 2
            else:
                # Get list of "root" names, i.e. without "_chunk"
                Gfields = list(G.__dict__.keys())
                t = [Gfields[i].split("_chunk")[0] for i in range(len(Gfields))]
                t = list(dict.fromkeys(t))
                t.remove("dwellTime")
                # average over chunks
                for field in t:
                    print('Calculating average correlation ' + str(field))
                    avList = [i for i in Gfields if i.startswith(field + '_chunk')]
                    Gav = sum(getattr(G, i) for i in avList) / len(avList)
                    setattr(G, str(field) + '_average', Gav)
    return G


def FCSLoadAndCorrSplit(fname, listOfG=['central', 'sum3', 'sum5', 'chessboard', 'ullr'], accuracy=16, split=10, timeTrace=False, metadata=None, root=0):
    """
    Load SPAD-FCS data in chunks (of 10 s) and calculate G and Gav
    ==========  ===============================================================
    Input       Meaning
    ----------  ---------------------------------------------------------------
    fname       File name with the .bin data
    listofG     List of correlations to be calculated
    accuracy    Accuracy of the autocorrelation function, typically 16
    split       Number of seconds of each chunk to split the data into
                E.g. split=10 will divide a 60 second stream in 6 ten-second
                traces and calculate G for each individual trace
    timeTrace   see output
    metadata    if None: metadata is extracted from .txt info file
                if metadata Object: meta is given as input parameter
    root        only used for the FaCtS GUI to pass progress
    ==========  ===============================================================
    Output      Meaning
    ----------  ---------------------------------------------------------------
    G           Object with all autocorrelations
                E.g. G.central contains the array with the central detector
                element autocorrelation
    data        if timetrace == False: last chunk of raw data
                if timetrace == True: full time trace binned: [Nx25] array
    ==========  ===============================================================
    """
    
    if metadata is None:
        metadata = getFileInfo(fname[:-4] + "_info.txt")
    dwellTime = 1e-6 * metadata.timeResolution # s
    print(dwellTime)
    duration = metadata.duration
    
    N = np.int(np.floor(duration / split)) # number of chunks

    G = correlations()
    G.dwellTime = dwellTime
    chunkSize = int(np.floor(split / dwellTime))
    for chunk in range(N):
        # --------------------- CALCULATE CORRELATIONS SINGLE CHUNK ---------------------
        if root != 0:
            root.progress = chunk / N
        string2print = "| Loading chunk " + str(chunk+1) + "/" + str(N) + " |"
        stringL = len(string2print) - 2
        print("+" + "-"*stringL + "+")
        print(string2print)
        print("+" + "-"*stringL + "+")
        data = file_to_FCScount(fname, np.uint8, chunkSize, chunk*chunkSize)
        if timeTrace == True:
            binSize = int(chunkSize / 1000 * N) # time trace binned to 1000 data points
            bdata = binDataChunks(data, binSize)
            bdataL = len(bdata)
            print("chunksize = " + str(chunkSize) + " - " + str(binSize))
            print("N = " + str(N))
            if chunk == 0:
                timetraceAll = np.zeros((1000, 25), dtype=int)
            timetraceAll[chunk*bdataL:(chunk+1)*bdataL, :] = bdata 
            
        for j in listOfG:
            print('     --> ' + str(j) + ": ", end = '')
            # ------------------ CHUNK ------------------
            newList = [j]
            Gsplit = FCS2Corr(data, 1e6*dwellTime, newList, accuracy)
            GsplitList = list(Gsplit.__dict__.keys())
            for k in GsplitList:
                if k.find('dwellTime') == -1:
                    setattr(G, k + '_chunk' + str(chunk), getattr(Gsplit, k))
    # ---------- CALCULATE AVERAGE CORRELATION OF ALL CHUNKS ----------
    print("Calculating average correlations")
    # Get list of "root" names, i.e. without "_chunk"
    Gfields = list(G.__dict__.keys())
    t = [Gfields[i].split("_chunk")[0] for i in range(len(Gfields))]
    t = list(dict.fromkeys(t))
    t.remove("dwellTime")
    # average over chunks
    for field in t:
        avList = [i for i in Gfields if i.startswith(field + '_chunk')]
        # check if all elements have same dimension
        Ntau = [len(getattr(G, i)) for i in avList]
        avList2 = [avList[i] for i in range(len(avList)) if Ntau[i] == Ntau[0]]
        Gav = sum(getattr(G, i) for i in avList2) / len(avList2)
        setattr(G, str(field) + '_average', Gav)   
    # average over same shifts in case of 'crossAll'
    if 'crossAll' in listOfG:
        print("Calculating spatially averaged correlations.")
        spatialCorr = np.zeros([9, 9, len(G.det0x0_average)])
        for shifty in np.arange(-4, 5):
            for shiftx in np.arange(-4, 5):
                avList = SPADshiftvectorCrossCorr([shifty, shiftx])
                avList = [s + '_average' for s in avList]
                Gav = sum(getattr(G, i) for i in avList) / len(avList)
                spatialCorr[shifty+4, shiftx+4, :] = Gav[:,1]
        G.spatialCorr = spatialCorr

    if timeTrace == True:
        data = timetraceAll

    return G, data


def FCSSpatialCorrAv(G, N=5):
    spatialCorr = np.zeros([2*N-1, 2*N-1, len(G.det0x0_average)])
    for shifty in np.arange(-(N-1), N):
        for shiftx in np.arange(-(N-1), N):
            avList = SPADshiftvectorCrossCorr([shifty, shiftx], N)
            avList = [s + '_average' for s in avList]
            Gav = sum(getattr(G, i) for i in avList) / len(avList)
            spatialCorr[shifty+N-1, shiftx+N-1, :] = Gav[:,1]
    G.spatialCorr = spatialCorr
    return G


def FCSavChunks(G, listOfChunks):
    """
    Average for each correlation mode the chunks given in listOfChunks.
    Used to calculate the average correlation for the good chunks only.
    ===========================================================================
    Input       Meaning
    ----------  ---------------------------------------------------------------
    G           Correlations object that contains all correlations
    listOfChunks List with chunk numbers used for the calculation of the average
                e.g. [1, 3, 4, 7]
   ============================================================================
    Output      Meaning
    ----------  ---------------------------------------------------------------
    G           Same object as input but with the additional fields
                G.det10_F0_averageX
                G.sum3_F0_averageX
                G.sum5_F0_averageX
                G.det10_F1_averageX
                ...
                where the averages are calculated over the listed chunks only
    ===========================================================================
    """
    
    listOfCorr = list(G.__dict__.keys())
    listOfCorr2 = []
    
    for corr in listOfCorr:
        if 'average' not in corr and 'chunk' in corr:
            pos = corr.find('chunk')
            listOfCorr2.append(corr[0:pos])
    
    # remove duplicates
    listOfCorr2 = list(dict.fromkeys(listOfCorr2))
    
    for corr in listOfCorr2:
        Gtemp = getattr(G, corr + 'chunk0') * 0
        for chunk in listOfChunks:
            print('chunk:   ' + str(chunk))
            Gtemp += getattr(G, corr + 'chunk' + str(chunk))
        Gtemp /= len(listOfChunks)
        setattr(G, corr + 'averageX', Gtemp)
    
    return G


def FCSCrossCenterAv(G, returnField='_averageX', returnObj = True):
    """
    Average pair-correlations between central pixel and other pixels that are
    located at the same distance from the center
    ===========================================================================
    Input       Meaning
    ----------  ---------------------------------------------------------------
    G           Correlations object that (at least) contains all
                cross-correlations between central pixel and all other pixels:
                G.det12x12_average, G.det12x13_average, etc.
   ============================================================================
    Output      Meaning
    ----------  ---------------------------------------------------------------
    G           Same object as input but with the additional field
                G.crossCenterAv, which contains array of 6 columns, containing
                averaged cross-correlations between central pixel and pixels
                located at a distance of
                    | 0 | 1 | sqrt(2) | 2 | sqrt(5) | sqrt(8) |
    ===========================================================================
    """
    
    try:
        tau = G.det12x12_average[:,0]
    except:
        tau = G.det12x12_chunk0[:,0]
    G.crossCenterAv = np.zeros((len(tau), 6))
    
    # average autocorrelation center element
    try:
        G.crossCenterAv[:,0] = getattr(G, 'det12x12' + returnField)[:,1]
    except:
        G.crossCenterAv[:,0] = getattr(G, 'det12x12' + '_average')[:,1]
    
    # average pair-correlations 4 elements located at distance 1 from center
    try:
        G.crossCenterAv[:,1] = np.mean(np.transpose(np.array([getattr(G, 'det12x' + str(det) + returnField)[:,1] for det in [7, 11, 13, 17]])), 1)
    except:
        G.crossCenterAv[:,1] = np.mean(np.transpose(np.array([getattr(G, 'det12x' + str(det) + '_average')[:,1] for det in [7, 11, 13, 17]])), 1)
    
    # average pair-correlations 4 elements located at distance sqrt(2) from center
    try:
        G.crossCenterAv[:,2] = np.mean(np.transpose(np.array([getattr(G, 'det12x' + str(det) + returnField)[:,1] for det in [6, 8, 16, 18]])), 1)
    except:
        G.crossCenterAv[:,2] = np.mean(np.transpose(np.array([getattr(G, 'det12x' + str(det) + '_average')[:,1] for det in [6, 8, 16, 18]])), 1)
    
    # average pair-correlation 4 elements located at distance 2 from center
    try:
        G.crossCenterAv[:,3] = np.mean(np.transpose(np.array([getattr(G, 'det12x' + str(det) + returnField)[:,1] for det in [2, 10, 14, 22]])), 1)
    except:
        G.crossCenterAv[:,3] = np.mean(np.transpose(np.array([getattr(G, 'det12x' + str(det) + '_average')[:,1] for det in [2, 10, 14, 22]])), 1)
    
    # average pair-correlation 8 elements located at distance sqrt(5) from center
    try:
        G.crossCenterAv[:,4] = np.mean(np.transpose(np.array([getattr(G, 'det12x' + str(det) + returnField)[:,1] for det in [1, 3, 5, 9, 15, 19, 21, 23]])), 1)
    except:
        G.crossCenterAv[:,4] = np.mean(np.transpose(np.array([getattr(G, 'det12x' + str(det) + '_average')[:,1] for det in [1, 3, 5, 9, 15, 19, 21, 23]])), 1)
    
    # average pair-correlation 4 elements located at distance sqrt(8) from center
    try:
        G.crossCenterAv[:,5] = np.mean(np.transpose(np.array([getattr(G, 'det12x' + str(det) + returnField)[:,1] for det in [0, 4, 20, 24]])), 1)
    except:
        G.crossCenterAv[:,5] = np.mean(np.transpose(np.array([getattr(G, 'det12x' + str(det) + '_average')[:,1] for det in [0, 4, 20, 24]])), 1)
    
    if returnObj:
        return G
    else:
        return G.crossCenterAv


def FCSBinToCSVAll(folderName=[], Glist=['central', 'sum3', 'sum5', 'chessboard', 'ullr'], split=10):
    # PARSE INPUT
    if folderName == []:
        folderName = getcwd()
    folderName = folderName.replace("\\", "/")
    folderName = Path(folderName)
    
    # CHECK BIN FILES
    allFiles = listFiles(folderName, 'bin')
    
    # GO THROUGH EACH FILE
    for file in allFiles:
        fileName = ntpath.basename(file)
        print("File found: " + fileName)
        [G, data] = FCSLoadAndCorrSplit(file, Glist, 50, split)
        corr2csv(G, file[0:-4], [0, 0], 0)


def plotFCScorrelations(G, plotList='all', limits=[0, -1], vector=[], pColors='auto', yscale='lin'):
    """
    Plot all correlation curves
    ==========  ===============================================================
    Input       Meaning
    ----------  ---------------------------------------------------------------
    G           Object with all autocorrelations
                Possible attributes:
                    det*,
                    central, sum3, sum5, allbuthot, chessboard, ullr, av
                    autoSpatial,
                    det12x*
                    dwellTime (is not plotted)
    ==========  ===============================================================
    Output      Meaning
    ----------  ---------------------------------------------------------------
    figure
    ==========  ===============================================================
    """

    spatialCorrList = ['autoSpatial']

    start = limits[0]
    stop = limits[1]

    # plotList contains all attributes of G that have to be plotted
    if plotList == 'all':
        plotList = list(G.__dict__.keys())
        
    # remove dwellTime from plotList
    if 'dwellTime' in plotList:
        plotList.remove('dwellTime')

    if 'av' in plotList:
        # remove all single detector element correlations
        plotListRemove = fnmatch.filter(plotList, 'det?')
        for elem in plotListRemove:
            plotList.remove(elem)
        plotListRemove = fnmatch.filter(plotList, 'det??')
        for elem in plotListRemove:
            plotList.remove(elem)
    
    if np.size(fnmatch.filter(plotList, 'det12x??')) > 10:
        # replace all individual cross-correlations by single crossCenter element
        plotListRemove = fnmatch.filter(plotList, 'det12x?')
        for elem in plotListRemove:
            plotList.remove(elem)
        plotListRemove = fnmatch.filter(plotList, 'det12x??')
        for elem in plotListRemove:
            plotList.remove(elem)
        plotList.append('crossCenter')
    
    if fnmatch.filter(plotList, '*_'):
        plotListStart = plotList[0]
        # plot chunks of data and average
        plotList = list(G.__dict__.keys())
        plotList.remove('dwellTime')
        plotList = [i for i in plotList if i.startswith(plotListStart)]
        

    # -------------------- Check for temporal correlations --------------------
    plotTempCorr = False
    for i in range(np.size(plotList)):
        if plotList[i] not in spatialCorrList:
            plotTempCorr = True
            break

    if plotTempCorr:
        leg = []  # figure legend
        h = plt.figure()
        plt.rcParams.update({'font.size': 15})
        maxy = 0
        miny = 0
        minx = 25e-9
        maxx = 10
        pColIndex = 0
        for i in plotList:

            #if i not in list(G.__dict__.keys()):
              #  break

            if i in ["central", "central_average", "sum3", "sum3_average", "sum5", "sum5_average", "allbuthot", "allbuthot_average", "chessboard", "chessboard_average", "chess3", "chess3_average", "ullr", "ullr_average", "av", "cross12_average", "cross21_average", "cross_average", "auto1_average", "auto2_average"]:
                # plot autocorrelation
                Gtemp = getattr(G, i)
                plt.plot(Gtemp[start:stop, 0], Gtemp[start:stop, 1], color=plotColors(i), linewidth=1.3)
                maxy = np.max([maxy, np.max(Gtemp[start+1:stop, 1])])
                miny = np.min([miny, np.min(Gtemp[start+1:stop, 1])])
                minx = Gtemp[start, 0]
                maxx = Gtemp[stop, 0]
                leg.append(i)

            elif i == 'crossCenter':
                for j in range(25):
                    Gsingle = getattr(G, 'det12x' + str(j))
                    # plotColor = colorFromMap(distance2detElements(12, j), 0, np.sqrt(8))
                    plt.plot(Gsingle[start:stop, 0], Gsingle[start:stop, 1], color=plotColors(i))
                    maxy = np.max([maxy, np.max(Gsingle[start+1:stop, 1])])
                    miny = np.min([miny, np.min(Gtemp[start+1:stop, 1])])
                    leg.append(i + str(j))
            
            elif i == 'crossCenterAv':
                tau = G.det12x12_average[:,0]
                for j in range(6):
                    plt.plot(tau[start:stop], G.crossCenterAv[start:stop, j], color=plotColors(j))
                miny = np.min(G.crossCenterAv[start+10:stop,:])
                maxy = np.max(G.crossCenterAv[start+1:stop,:])
                leg = ['$\Delta r = 0$', '$\Delta r = 1$', '$\Delta r = \sqrt{2}$', '$\Delta r = 2$', '$\Delta r = \sqrt{5}$', '$\Delta r = 2\sqrt{2}$']

            elif i != 'autoSpatial' and i != 'stics' and i != 'crossAll' and i != 'crossVector':
                # plot autocorr single detector element
                if pColors == 'auto':
                    plt.plot(getattr(G, i)[start:stop, 0], getattr(G, i)[start:stop, 1])
                else:
                    plt.plot(getattr(G, i)[start:stop, 0], getattr(G, i)[start:stop, 1], color=plotColors(pColors[pColIndex]))
                    pColIndex += 1
                maxy = np.max([maxy, np.max(getattr(G, i)[start+1:stop, 1])])
                miny = np.min([miny, np.min(getattr(G, i)[start+1:stop, 1])])
                minx = getattr(G, i)[start, 0]
                maxx = getattr(G, i)[stop, 0]
                if '_average' in i:
                    iLeg = i[0:-8]
                else:
                    iLeg = i
                leg.append(iLeg)

        # figure lay-out
        plt.xscale('log')
        plt.xlabel('Temporal shift [s]')
        plt.ylabel('G')
        if yscale == 'log':
            plt.yscale('log')
        else:
            plt.yscale('linear')
        axes = plt.gca()
        axes.set_xlim([minx, maxx])
        axes.set_ylim([miny, maxy])
        if np.size(leg) > 0 and np.size(leg) < 10 and 'crossCenter' not in plotList:
            axes.legend(leg)
        plt.tight_layout()
        
        if 'crossCenter' in plotList:
            plotCrossCenterScheme()
            
    # -------------------- Check for spatial correlations --------------------
    if 'autoSpatial' in plotList:
        Gtemp = G.autoSpatial
        Gmax = np.max(Gtemp)
        xmax = (np.size(Gtemp, 0)) / 2
        extent = [-xmax, xmax, -xmax, xmax]
        for j in range(np.size(Gtemp, 2)):
            h = plt.figure()
            plt.imshow(Gtemp[:, :, j], extent=extent, vmin=0, vmax=Gmax)
            plt.title('delta_t = ' + str(G.dwellTime * j) + ' ??s')
    
    if 'crossAll' in plotList:
        Gtemp = G.spatialCorr
        tau = G.det0x0_average[:,0]
        for vector in [[4, 4], [3, 4], [3, 3], [2, 4], [2, 3], [2, 2]]:
            plt.plot(tau, Gtemp[vector[0], vector[1], :])
        plt.legend(['[0, 0]', '[1, 0]', '[1, 1]', '[0, 2]', '[2, 1]', '[2, 2]'])
        plt.xscale('log')
        plt.xlabel('Temporal shift [s]')
        plt.ylabel('G')
        axes.set_ylim([miny, np.max(Gtemp[:,:,2:])])
#        Gtemp = G.spatialCorr
#        Gmax = np.sort(Gtemp.flatten())[-2] # second highest number
#        extent = [-4, 5, -4, 5]
#        for j in range(np.size(Gtemp, 2)):
#            h = plt.figure()
#            plt.imshow(Gtemp[:, :, j], extent=extent, vmin=0)
#            plt.title('delta_t = ' + str(G.dwellTime * j) + ' ??s')
    
    if 'crossVector' in plotList:
        Gtemp = G.spatialCorr
        tau = G.det0x0_chunk0[:,0]
        for i in range(len(vector)):
            vectorI = vector[i]
            plt.plot(tau, Gtemp[4+vectorI[0], 4+vectorI[1], :], label='[' + str(vectorI[0]) + ', ' + str(vectorI[1]) + ']')
        plt.xscale('log')
        plt.xlabel('Temporal shift [s]')
        plt.ylabel('G')
        plt.legend()
        axes.set_ylim([miny, np.max(Gtemp[:,:,2:])])
    
    if 'stics' in plotList:
        Gtemp = getattr(G, 'det12x12')
        Gplot = np.zeros([9, 9])
        N = 10
        indArray = np.concatenate(([0], np.round(np.logspace(0, np.log10(len(Gtemp) - 1), N)).astype('int')))
        for i in range(N):
            # go through all lag times
            ind = np.round(indArray[i])
            print(ind)
            for yshift in np.arange(-4, 5):
                for xshift in np.arange(-4, 5):
                    # go through each shift vector
                    detDiff = -yshift * 5 - xshift
                    Gv = 0
                    nG = 0
                    for det1 in range(25):
                        [y, x] = coord(det1)
                        if x-xshift < 0 or x-xshift>4 or y-yshift < 0 or y-yshift > 4:
                            # don't do anything
                            pass
                        else:
                            det2 = det1 + detDiff
                            print('det1 = ' + str(det1) + ' and det2 = ' + str(det2))
                            if det2 >= 0 and det2 <= 24:
                                Gv += getattr(G, 'det' + str(det1) + 'x' + str(det2))[int(ind), 1]
                                nG += 1
                    Gplot[yshift+4, xshift+4] = Gv / nG
            if i == 0:
                plotMax = np.max(Gplot)
            xmax = 9 / 2
            extent = [-xmax, xmax, -xmax, xmax]
            h = plt.figure()
            plt.imshow(Gplot, extent=extent, vmin=0, vmax=plotMax)
            plt.title('delta_t = ' + str(int(G.dwellTime * ind)) + ' ??s')
            
    return h


def plotGsurf(G):
    N = np.size(G, 0)
    N = (N - 1) / 2
    fig = plt.figure()
    ax = fig.add_subplot(111, projection='3d')
    x = y = np.arange(-N, N + 1)
    X, Y = np.meshgrid(x, y)
    ax.plot_surface(X, Y, G)
    return fig


def plotCrossCenterScheme():
    detEl = range(25)
    distances = np.zeros(25)
    for i in detEl:
        distances[i] = distance2detElements(12, i)
    distances = np.resize(distances, (5, 5))
    plt.figure()
    plt.imshow(distances, 'viridis')
    plt.title('Color scheme cross-correlations')
