import matplotlib.pyplot as plt
import numpy as np
import seaborn

def colorFromMap(value, startv=0, stopv=1, cmap='viridis'):
    if cmap != 'seaborn-colorblind':
        cmap = plt.get_cmap(cmap)
        N = np.size(cmap.colors, 0)
        idx = int(np.floor((value - startv) / (stopv - startv) * N))
        idx = np.min([idx, N-1])
        return cmap.colors[idx]
    else:
        cmapArray = seaborn.color_palette('colorblind')
        N = len(cmapArray)
        idx = int(np.floor((value - startv) / (stopv - startv) * N))
        idx = np.min([idx, N-1])
        return cmapArray[idx]
